# FQ — Plan de ingeniería: siguiente nivel (jun-2026)

> Estado: **plan aprobable por etapas, sin código aún**. Complementa (no
> duplica) a `ARCHITECTURE.md` (extracción del monolito, etapas 3–6) y a
> `RETRIEVAL_PLAN.md` (roadmap de research F0–F4). Este documento cubre lo
> TRANSVERSAL: reproducibilidad, guardas, calidad de código, config,
> industrialización del research y operación.
>
> Contexto duro: la rama de trabajo está **deployada en producción** (Railway,
> servicio `worker`; cada push redeploya) y hay una **poda en curso** (run #31)
> que puede matar módulos. Por eso el plan es incremental, reversible y
> explícitamente **poda-aware**: no se invierte esfuerzo en código que puede
> morir la semana que viene.

## 0. Principios (no negociables)

1. **Prod vivo**: nada se mergea sin suite verde; cambios de runtime por env,
   reversibles, con confirmación del usuario.
2. **Toda lección aprendida se convierte en un test** (ver N2). El bug de
   reloj (§6.7 del RETRIEVAL_PLAN) ocurrió DOS veces (`volume_quality`,
   `killzones_pd`); la tercera la tiene que atrapar CI, no un humano.
3. **Calidad antes que features**: con baseline OOS negativo, el sistema no
   necesita más señales ni más capas — necesita menos mentiras en la medición
   y menos peso muerto.
4. **El gate ORO y sus puertas de leakage no se degradan jamás** por
   conveniencia de ingeniería.

## 1. CUARENTENA — qué NO refactorizar todavía

Candidatos a morir o cambiar de forma según resultados pendientes. Hasta el
veredicto, se tocan solo para fixes; cero inversión estética:

| Módulo / área | Por qué está en cuarentena | Veredicto llega de |
|---|---|---|
| ~~`signal_scorer.py`, `regime_detector.py`, `session_bias.py`~~ **RESUELTO (#31)** | session_bias VIVE y sostiene el edge (sin él +0.018→−0.003); scorer/regime son additivos inertes para el disparo PERO acoplados al gate ORO (7/13 features del vector) → **NO se apagan**. Ver §6.6 del RETRIEVAL_PLAN. Salen de cuarentena: ninguno se toca por env. | ✅ run #31 |
| bloque vector quantum (`qt_*` en `bt_retrieval`/`bt_features`) | NO SUMA en Eje A dos corridas seguidas (#30: −0.288R); `qt_sync_score` es dimensión 100% NaN (muerta) | decisión tras 1 corrida más o retiro directo |
| `emergent_time.py` Phase E (`FQ_EMERGENT_TIME_ENABLED`) | OFF por default, sin validación shadow registrada | shadow/paper si alguien lo pide |
| `tools/research_demo.py`, `tools/repro_fvg_selection.py`, `tools/build_deck.py`, `internal/_staging` | posible peso muerto de tooling | auditoría N5 |

Nota: `quantum_timelines.py` (QTE del bot vivo) NO es el bloque `qt_*` del
vector de retrieval; no está en cuarentena por esos números.

## N1. Reproducibilidad y cadena de suministro (primera, barata, urgente)

El hallazgo: `requirements.txt` tiene cotas abiertas (`pandas>=2.3.2`,
`numpy>=2,<3`…). Hoy eso resuelve **pandas 3.x**: cada redeploy de Railway
puede saltar versiones mayores SIN cambio de código. Para un bot de dinero es
una bomba de relojería silenciosa.

- [x] **Lockfile**: `requirements.lock` (57 paquetes, set completo pinneado ==),
      generado con `uv pip compile requirements.txt --python-version 3.12`
      (= la versión de CI/prod). Captura el set vivo hoy (pandas==3.0.3,
      numpy==2.2.6, ccxt==4.5.58, anthropic==0.109.1…). `requirements.txt` queda
      como declaración de intención. Regenerar = PR consciente con suite verde.
- [ ] **Pin de runtime** (FASE 2, supervisada): fijar Python 3.12 en Nixpacks
      (`runtime.txt`/`NIXPACKS_PYTHON_VERSION`) para que prod=CI=research.
      Pendiente: cambia el build de prod → aplicar con el usuario mirando el
      dashboard, junto al switch de Railway al lock.
- [x] **Docs no redeployan**: `railway.toml` → `watchPatterns` (excluye
      `**/*.md`, `internal/`, `.github/`, `tests/`, `tools/`). Ya en producción.
- [x] CI: job **`lockcheck`** (`ci.yml`) — instala desde `requirements.lock` en
      3.12, corre `pip check` (conflictos) + la suite. Si el lock se rompe o se
      desfasa, CI rojo ANTES de tocar prod.

**Criterio de salida**: dos deploys consecutivos sin cambio de código instalan
bit-a-bit las mismas versiones. **Estado: lock CONSTRUIDO y validado en CI
(cero riesgo de prod). FASE 2 (supervisada con dashboard):** apuntar Railway/
Nixpacks a `requirements.lock` + pin de runtime 3.12 → ahí se cumple el criterio.
El lock listo + `lockcheck` verde es el prerequisito que vuelve esa fase segura.

## N2. Guardas que codifican lecciones (tests de invariantes)

- [x] **Guarda de reloj de pared** (`tests/test_no_wallclock.py`): parsea (AST)
      los módulos del path del motor y FALLA si aparece un
      `datetime.now()/utcnow()/date.today()/Timestamp.now()` por encima del
      BASELINE auditado. Es la versión permanente de "§6.7: todo reloj nuevo en
      el motor es sospechoso". 13-jun-2026: añadido `segment_veto.py` (baseline
      0) — el veto de sesión juzga el ts de la VELA, jamás el reloj de pared.
- [ ] **Guarda de esquema del vector**: si `meta.json` declara N features, el
      vectorizer debe rechazar (no rellenar en silencio) una query con otro
      esquema. Ya hay telemetría de dims muertas; falta el contrato duro.
- [ ] **Guarda de superficie de cliente** ya existe (`test_client_surfaces`);
      mantener el patrón.
- [ ] Las puertas de leakage del research ya son guardas (placebo/oracle/
      embargo); documentarlas como tales y NO permitir bypass por flag.

**Criterio de salida**: reintroducir a propósito el bug de reloj en
`killzones_pd` rompe CI.

## N3. Higiene de código (gradual, sin big-bang)

- [ ] **ruff** (lint + format) con config en `pyproject.toml`:
      primero `ruff check` informativo en CI (no bloquea), luego bloqueante
      módulo a módulo empezando por `bt_*` y `tools/` (los más jóvenes y
      limpios). El monolito entra ÚLTIMO (post-extracciones ARCHITECTURE.md).
- [ ] **Logs de research sin spam**: el warning del vectorizer (`features con
      NaN>=50%`) se repite por fit → decenas de líneas idénticas por run
      (ensucia los artefactos que luego se leen a mano). Dedupe: una vez por
      fit/firma. Cambio pequeño en `bt_retrieval.py` con test.
- [ ] **Type hints**: mypy/pyright en modo gradual SOLO para `bt_*` y
      `tools/` (donde más duelen los NaN/None silenciosos). No al monolito.
- [ ] `pyproject.toml` único para metadata + tool config (pytest ya corre con
      defaults; centralizar `testpaths`, markers, ruff, etc.).

**Criterio de salida**: `ruff check bt_*.py tools/` verde y bloqueante en CI.

## N4. Config: una sola fuente de verdad para los `FQ_*`

Hoy: ~30 envs `FQ_*` leídos con `os.environ.get` disperso; `.env.example` es
la documentación. Funciona, pero cada env nuevo es un punto de divergencia
silenciosa (typo en el nombre = default sin aviso).

- [ ] `fq_settings.py`: registro central tipado (nombre, tipo, default,
      descripción, ¿afecta dinero?), leído UNA vez al boot; el resto del
      código importa de ahí. Migración mecánica módulo a módulo.
- [ ] Al boot, log de la config efectiva (sin secretos) + warning por env
      `FQ_*` desconocida (caza typos).
- [ ] Generar `.env.example` DESDE el registro (deja de mantenerse a mano).

**Criterio de salida**: `FQ_SEGMENT_VETO_KILLZONES=londn_open_kz` (typo) se ve
en el log de boot como env desconocida, no como default silencioso.

## N5. Research industrial (la fábrica de evidencia)

- [ ] **Provenance en artefactos**: `REPORTE.md` y `meta.json` deben llevar
      `git sha` + `run id` + inputs efectivos. Hoy el REPORTE trae fecha e
      inputs; el sha/run id se reconstruye a mano (lo hicimos para #26 vs
      #30 — no debería ser arqueología).
- [ ] **Catálogo de runs**: tabla única (en RETRIEVAL_PLAN §6.x o `RUNS.md`)
      con id, sha, inputs, veredictos clave (#26 ficción NY / #28 ficción
      madrugada / #30 baseline honesto / #31 poda…). Los artefactos de
      GitHub expiran (~90 días): los runs-hito se archivan al Volume o Drive.
- [x] **`tools/regrade_events.py`** (F2.6 §6.8 paso 1): carga el cubo de un run
      y re-mide OOS con un filtro/veto SIN replay; mismo motor de costes
      (`bt_engine`/`bt_metrics`) + matriz maker×veto. 13-jun-2026: su predicado
      `_veto_mask` se EXTRAJO a `segment_veto.py` (módulo puro), ahora COMPARTIDO
      por el regrade offline, el replay integrado (`run_research_real`) y el loop
      vivo (`fq_bot_v3_2`) → cero divergencia. (Falta el comparador de runs.)
- [ ] **Comparador de runs**: `tools/compare_runs.py run30/ run31/` → tabla
      lado a lado (funnel, OOS, leakage, segmentos top). Hoy se hace a ojo
      entre logs de 500 líneas.

**Criterio de salida**: responder "¿el veto london_open mejora el OOS del
#30?" toma minutos y cero replays.

## N6. Estructura del código (POST-poda; dueño: ARCHITECTURE.md)

La hoja de ruta de extracción del monolito ya existe (ARCHITECTURE.md etapas
3–6: `fq_broadcast`, `fq_commands/`, `fq_signal_loop`, paquete `fq/`). Este
plan solo añade el ORDEN respecto a la poda:

1. Veredicto del run #31 → aplicar MATAR (env primero; borrado de código un
   ciclo después, cuando el forward confirme).
2. Recién entonces retomar extracciones de ARCHITECTURE.md (no extraer interfaces
   para módulos muertos).
3. El paquete `fq/` (etapa 6) es lo ÚLTIMO, con shims de import para no
   romper `launcher.py`/Procfile en Railway.

## N7. Observabilidad y operación (ya casi está; rematar)

- Ya hay: heartbeat + watchdog, backup del ledger (+S3 opcional), digest ORO
  (`FQ_GOLD_DIGEST_EVERY=288`), logs JSON opcionales, HashLedger.
- [ ] **Self-check del artefacto al boot**: si `FQ_GOLD_LIVE=1` y el artefacto
      del Volume no carga / esquema incompatible / leakage≠ok en su meta →
      mensaje al admin con el motivo exacto (hoy: revisar logs).
- [ ] Alerta si el ledger paper ORO no recibe eventos en N días (detecta gate
      muerto en silencio).

## N8. Programa de cosecha de evidencia (la fábrica de números honestos)

Objetivo: convertir el research en una BATERÍA de evidencia reproducible que
(a) enriquezca el sistema y (b) sostenga, con números medidos, la tesis de
inversión. Siete corridas; cada una deja un artefacto versionado (sha + inputs)
y una lámina para el deck. Orden pensado para que 1–6 alimenten el 7 (el forward).

1. [ ] **Cosecha multi-símbolo** (ETH/USDT, BNB, majors perp). Reutiliza
   `tools/build_dataset.py --symbol X` + `tools/cosecha_shard.py --symbol X`
   (symbol-agnóstico; sólo cambia la ruta del artefacto). Entrega un **portafolio
   de edges candidatos** por símbolo/TF → diversificación medible, no narrada.
   [coste: runner self-hosted, ~horas/símbolo].
2. [x] **Walk-forward / OOS purgado**. Folds en `cosecha_shard` (`--n-splits 7
   --embargo 8`) + `tools/walkforward_report.py`: expectancy y dispersión FOLD A
   FOLD + lámina → evidencia de que el edge es estable y NO un overfit.
3. [x] **Monte Carlo de la curva** (`tools/montecarlo_curve.py`). Bootstrap de
   la serie de R por-trade → distribución de **drawdown máximo**, **risk-of-ruin**
   y **bandas de equity** (p5–p95). La lámina de riesgo que todo LP exige.
4. [x] **Análisis de capacidad** (`tools/capacity_analysis.py`). Modela el
   decaimiento del edge vs. tamaño de orden (impacto raíz-cuadrada sobre la
   participación de volumen) → **cuánto capital absorbe** el edge antes de
   comérselo (C½ y C0). Define el techo de despliegue y el tamaño honesto de la
   ronda. Paramétrico: `avg_bar_notional`/`impact_coef` se CALIBRAN con volumen y
   fills reales (el forward maker los dará).
5. [x] **Segmentación por régimen**. `tools/regime_report.py` segmenta el cubo
   por régimen/volatilidad/sesión (numérica → bins; categórica → grupos) y mide
   expectancy OOS por segmento + lámina → dónde VIVE el alpha y dónde abstenerse.
6. [x] **Atribución de features** (la joya analítica). `tools/attribution_report.py`
   cablea `bt_ablation.run_ablation` (que estaba sin usar) en un reporte +
   **lámina** ranqueada: qué componentes del motor (P_master, regime, session_bias,
   volume_quality…) generan realmente la expectancy, SOLO en OOS walk-forward con
   costes reales, con veredicto VIVE/MATAR. Vuelve el motor transparente y
   defendible, no mágico. Requiere columnas-gate por módulo en el cubo (si no, se
   re-cosecha guardándolas, o ablación por replay con toggles de env).
7. [→] **Forward vivo** (en curso). El motor paper SOL+BTC ya corre a 0% real;
   es la **prioridad #1 de datos**. 1–6 lo contextualizan (régimen, capacidad,
   riesgo); el forward lo confirma. El `fill-rate maker` es el sello final.

**Criterio de salida**: cada paso deja artefacto reproducible + lámina; el deck
se arma SÓLO con lo medido (no se extrapola el forward antes de tiempo).

## Secuencia recomendada

| Cuándo | Qué |
|---|---|
| Ya (no depende de la poda) | N1 lockfile + pin runtime + watchPatterns; N2 guarda de reloj; N3 dedupe de logs; N5 provenance + `regrade_events` |
| Tras veredicto #31 | aplicar poda por env; N5 catálogo actualizado; F2.6 (RETRIEVAL_PLAN §6.8) |
| Tras forward de la poda/F2.6 | borrado de código muerto; retomar ARCHITECTURE.md etapas 3–5; N4 settings |
| Config estable | cosecha F3 (months 36 / step 1); etapa 6 (paquete `fq/`) |

## Qué NO vamos a hacer (anti-objetivos)

- Reescritura big-bang, microservicios, async total, cambiar de exchange-lib
  o de framework de bot: riesgo sin retorno para un sistema de una persona
  con dinero en juego.
- "Subir cobertura" como métrica: los tests nuevos nacen de invariantes y
  lecciones (N2), no de porcentajes.
- Tocar el gate ORO, sus umbrales o sus puertas de leakage por motivos de
  ingeniería.
