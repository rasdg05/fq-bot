# Cerebro FQ — Arquitectura funcional unificada

> Estado: **diseño aprobado-con-cambios**. Fusión de 6 diseños dimensionales, cada uno
> pasado por dos lentes adversariales (overfit/humo, fragilidad/capital). Este documento
> ya **incorpora los `mustFix`** y manda al cementerio lo que los escépticos marcaron como
> overfit disfrazado, humo o frágil. Lo que sobrevive es lo real-construible-hoy.
>
> Disciplina no negociable: **measure-first**. Cada etapa entrega algo, se mide, y es
> reversible. Nada toca el bot vivo salvo en modo lectura. Distinguimos siempre
> **REAL-construible-ya** de **ASPIRACIONAL (bloqueado por falta de datos)**.

---

## 0. Tesis

El cerebro FQ no es una red que memoriza el pasado. Es una **máquina de research-y-ejecución
que se propone hipótesis a sí misma y solo se cree las que pasan el gate** (DSR>0.95 + CPCV +
PBO + walk-forward + forward real). Todo lo que no pasa, al cementerio — con su acta, sin
borrarlo. Eso es "aprender sin overfit": no convicción, sino **supervivencia estadística
honesta**.

Y entiende de trading porque su vocabulario son los edges que YA pagaron en este stack —
order-flow firmado (CVD, cableado) y persistencia/memoria larga del flujo (F2, luz verde en
BTC) — no una métrica física inventada para sonar listo. Cuando le toque reemplazarnos, no se
caga encima porque **nunca mueve capital solo**: propone, mide forward fuera de muestra, y
espera el sign-off humano hasta que el track real diga que merece confianza. El robot que sabe
lo que NO sabe.

La trampa que este diseño evita (y que los seis diseños originales pisaban): invocar el gate
como talismán sobre muestras minúsculas. **El gate solo protege si la contabilidad es honesta**
— `n_trials` que acumula TODAS las auto-propuestas, sample mínimo duro por segmento, corrección
de multiple-testing entre segmentos, y cuarentena forward antes de influir en nada. Sin eso,
"solo me creo lo que pasa el gate" es mentira. Con eso, es el moat.

---

## 1. Realidad del stack (verificado en código, no prometido)

Antes de diseñar, lo que HAY hoy en disco — porque media arquitectura original descansaba sobre
datos que no existen:

| Pieza | Estado real | Implicación |
|---|---|---|
| `fq_ledger.db` (SQLite, SOLO-SOL, 4-TP) | **No está en este disco**; vive en `/data` de Railway | La ingesta lo lee remoto; aquí no hay forward acumulado |
| `motor_paper_{SYM}.jsonl` (1-TP, SHA-chain) | **El único en disco es un fixture de test** (`/tmp/.../motor_paper_TEST.jsonl`) | El "forward sobre los últimos N trades" **no existe aún**: es aspiracional hasta que el bot acumule meses |
| `cosecha_cubes/tp_cube_SOL_USDT.parquet` | **976 eventos únicos** en TODA la historia | 976 / 72 segmentos ≈ 13 eventos/segmento. Rolling-20 por segmento = meses |
| `cosecha_cubes/tp_cube_BTC_USDT.parquet` | **1301 eventos únicos** | Igual: ~18/segmento. Cube de ETH **no existe todavía** |
| `tools/validation_gate.py` | Real y testeado (DSR/PSR/CPCV/PBO, stdlib+numpy) | El gate es bueno; el problema es **cómo se alimenta** |
| `tools/validate_persistence_flow.py` | Real, pero `n_trials` es **CLI default 16/20 puesto a mano** (líneas 192, 230, 155) | **El agujero central**: el conteo de selección no acumula el universo de auto-propuestas |
| `execution.py::DurableHashLedger` | `append` hace `open(a)+write` **sin fsync ni rename atómico**; `load` **lanza** ante línea parcial | Un torn-write en un restart de Railway **brickea** el ledger de ese símbolo |
| `ops/backup_ledger.py` | Respalda **SOLO** el SQLite SOL, cada 6h | Los `motor_paper_{BTC,ETH}.jsonl` —único registro de 2/3 del producto— tienen **CERO backup** |
| `PaperBroker._pid` | Se reinicia a `0` en cada restart; `load()` no lo restaura | **PID-reuse**: trades post-restart sobrescriben a los pre-restart en stats keyed por pid |
| `tools/fetch_cvd.py` y otros fetchers | Ya usan `os.replace(tmp, path)` atómico | El patrón crash-safe **ya existe en el repo**: copiar de ahí |
| `ops/heartbeat.py` | Watchdog por mtime, reusable | Sirve para vigilar que el cerebro/monitor no se cuelgue |
| CCX33 Hetzner (8 vCPU/32GB) | Online, dedicado | Host del cerebro. **SPOF**: si muere, se cae todo el research a la vez |

**Conclusión operativa**: hoy se puede construir el **esqueleto read-only** (ingesta + lago +
ledger de decisiones + hash-chain + registro de experimentos). Toda la capa de
"edge-health/auto-evolución por segmento" está **bloqueada por falta de datos** hasta acumular
forward real. Eso no es una opinión: es contar filas.

---

## 2. Principios de diseño (los `mustFix` convertidos en ley)

Estas reglas son **vinculantes** y atraviesan ambos tracks. Si una etapa las viola, no se
mergea.

1. **SAMPLE-MÍNIMO DURO ANTES DE CUALQUIER DSR.** Prohibido calcular DSR/CPCV/PBO en ventanas
   chicas. `n_min` por segmento ≥ **100** cierres reales (≥150 preferido) antes de que el número
   signifique algo. A n=20: falso-positivo 6.2% sobre puro ruido (peor que el 5% que dice
   controlar), power 35%, folds CPCV de 3-7 trades, PBO=`nan` con 1 sola serie. **El "measure-first
   check a 20 closes" es estadística de adorno.** Se reemplaza por un monitor honesto (ver §5.B.4).

2. **`n_trials` HONESTO Y ACUMULATIVO.** El contador de selección NO lo pone el operador a mano.
   Un contador **persistente y monótono** por familia (`feature_family` / `segment_key`) cuenta
   TODAS las hipótesis evaluadas, y `deflated_sharpe_ratio` se deflacta SIEMPRE por ese total.
   Demostrado: con `n_trials=200` reales, 200 features de RUIDO → **0 validadas** (dsr≈0.72); con
   el `n_trials=20` del CLI → **7 falsas validadas**. Se loguea el conteo en `hypothesis_log`.

3. **CORRECCIÓN DE MULTIPLE-TESTING ENTRE SEGMENTOS.** 72 segmentos × 24h = 1728 tests/día. Se
   aplica **FDR (Benjamini-Hochberg)** o umbral familywise sobre el conjunto de segmentos por
   corrida. Jamás un threshold per-segment independiente (`dsr<0.90`) — eso genera ~854 alertas
   falsas/día y entrena al operador a ignorar alarmas (alarm fatigue) justo cuando una
   degradación real importa.

4. **CUARENTENA FORWARD OBLIGATORIA.** "validated" **NO** significa "candidato a producción".
   Toda hipótesis validada entra a **cuarentena forward pre-registrada** (out-of-sample real, sin
   tocar parámetros) por un mínimo de trades reales por segmento ANTES de poder influir en
   sizing/vetos/escaladas. El camino `validated → candidato-pool → autoevolución` **se elimina**
   como ruta automática.

5. **HUMANO-EN-EL-LOOP VINCULANTE + FRENO FÍSICO.** Ningún cambio toca parámetros del bot vivo
   sin sign-off humano por Telegram. La transición a autonomía es **propose-only**. El kill-switch
   del cerebro es **independiente del CCX33**: si el host muere, un pool huérfano no puede modificar
   el bot. Cualquier cambio auto-aplicado es canary (shadow/paper primero) y reversible por commit.

6. **CRASH-SAFE ANTES DE INGERIR.** No se ingiere nada hasta que el ledger sea crash-safe
   (`append` con fsync + `os.replace`; `load` tolera la última línea parcial) y los durables de
   BTC/ETH tengan backup. **Garbage-in al gate = capital hacia ruido.** Esto es bloqueante.

7. **NAMING HONESTO.** "Blockchain Lite" → **"hash-chain append-only (log tamper-evident)"**. No
   es prueba anti-manipulación (lo firma el mismo proceso); para garantía real se ancla el
   head-hash fuera del host (commit a git, o el backup de Telegram que ya existe). El dueño odia el
   vendehumos; el propio módulo no lo vende.

8. **EL CEMENTERIO ES SAGRADO.** Las hipótesis rechazadas se guardan completas (no se borran). El
   cerebro aprende qué NO funciona. Cada 3 meses se auditan para no reinventar la rueda.

---

## 3. Arquitectura en dos tracks paralelos

RasDG pidió **dos vías paralelas**. La división es por riesgo y por dependencia de datos, no por
capricho:

- **Track A — Memoria y observabilidad del proceso (read-mostly).** El esqueleto que YA se puede
  construir: ingesta crash-safe, lago analítico, ledger de decisiones, hash-chain, registro de
  experimentos, API y dashboard read-only. **Bajo riesgo, valor inmediato, no toca el bot vivo.**
  Es el "diario del cerebro" + el cimiento de datos. **No depende de acumular forward**: trabaja
  con lo que el bot ya escribe.

- **Track B — Bucle de aprendizaje disciplinado (research engine).** El motor que se auto-propone
  hipótesis, las valida con el gate honesto, y monitorea la salud de los edges cableados. **Su
  capa de propuesta/validación sobre el cube histórico es real-hoy**; su capa de
  **edge-health/cuarentena/autoevolución está GATED por datos forward que aún no existen**.

**Dependencia entre tracks:** Track B **se alimenta del lago y del registro de Track A**. Por eso
Track A va primero en el camino crítico, pero ambos avanzan en paralelo una vez el cimiento (A0)
está. La regla dura: **ninguna etapa de Track B que requiera forward real arranca hasta que Track
A demuestre N cierres reales acumulados por segmento** (ese N es el gate de etapa, §5.B).

```
                        ┌─────────────────────────────────────────────┐
   Bot vivo (Railway)   │  TRACK A — Memoria / observabilidad (R-only) │
   durables /data  ───► │  A0 ingesta → A1 lago → A2 decisiones+hash   │
   (RO, nunca escribe)  │       → A3 registro exp → A4 API+dash        │
                        └───────────────┬─────────────────────────────┘
                                        │ (lago + registro = fuente de verdad)
                                        ▼
                        ┌─────────────────────────────────────────────┐
                        │  TRACK B — Research engine (measure-first)   │
                        │  B0 propuesta → B1 validación honesta        │
                        │   → B2 graduación dormida → [GATE DATOS] →   │
                        │   B3 monitor honesto → B4 cuarentena forward │
                        │   → B5 autoevolución propose-only (aspirac.) │
                        └─────────────────────────────────────────────┘
```

---

## 4. Mapa de ejecución y flujo de datos

| Componente | Corre en | Acceso |
|---|---|---|
| Bot vivo (`fq_bot_v3_2.py`, broadcast VIP + motor paper) | **Railway** | Escribe sus durables en `/data`. **El cerebro NUNCA le escribe.** |
| Durables (`fq_ledger.db`, `motor_paper_*.jsonl`, `cvd.parquet`, `cosecha_cubes/*`) | **Railway `/data`** | Fuente read-only para la ingesta |
| Ingesta crash-safe + lago DuckDB/parquet | **CCX33** `/opt/fq-cerebro/lake/` | Lee remoto (SSH/SCP o pull), escribe local |
| Ledger de decisiones + hash-chain + registro experimentos | **CCX33** `/opt/fq-cerebro/research/` (JSONL) | Append-only, head-hash anclado a git/Telegram |
| Generador de hipótesis + validador (gate honesto) | **CCX33** (jobs compute-heavy, paraleliza por símbolo) | Lee lago, escribe `hypothesis_log` / `validation_results` |
| Monitor de salud de edges (honesto) | **CCX33** (job programado) | Lee lago; alerta a Telegram |
| Cosecha de cubes pesada (p.ej. ETH), validación batch | **GitHub Actions** (ya existe: `eth_cosecha.yml`, `physics_validation.yml`, `cvd_signed_flow_validation.yml`) o CCX33 | Reproducible, versionada |
| API read-only (FastAPI) + dashboard | **CCX33** `127.0.0.1` (no expuesto) / dashboard estático | Solo inspección, no edita |
| Comandos e alertas | **Telegram** (bot existente) | `/memoria`, `/edges`, `/hipotesis`, `/auditorias`; sign-off de cambios |
| Heartbeat/watchdog del cerebro | **Railway/Telegram** vigilan al **CCX33** (reusa `ops/heartbeat.py`) | Si el cerebro/monitor muere, avisa — no quedarse ciego |

**Flujo de datos (una sola dirección):**
`bot vivo → durables /data → [ingesta crash-safe, RO] → lago CCX33 → research/validación → propuestas → Telegram (humano) → (eventual) PR a git → bot lo lee en restart`.
Nunca al revés. El bot vivo no sabe que el cerebro existe.

---

## 5. Etapas

Cada etapa: **entregable** + **check measure-first** (cómo sabemos que sirve) + **reversibilidad**.
Ordenadas para entregar valor temprano.

### TRACK A — Memoria y observabilidad (REAL-construible-ya)

#### A0 — Crash-safety + backup (BLOQUEANTE, va primero)
*No se ingiere un solo byte hasta cerrar esto. Es el `mustFix` de fragilidad.*

- **Entregable:**
  1. `DurableHashLedger.append` reescrito: `write` línea + `fh.flush()` + `os.fsync()`, y mejor aún
     escritura a temp + `os.replace` (patrón que `tools/fetch_cvd.py:185` ya usa).
  2. `DurableHashLedger.load` **tolera la última línea parcial**: la descarta + avisa
     ("ledger sospechoso, última línea truncada"), en vez de lanzar `ValueError`. La ingesta
     envuelve `load()` en try/except y degrada a "ledger sospechoso", nunca crashea.
  3. Fix **PID-reuse**: restaurar `_pid` del último OPEN al cargar, o re-keyear `ledger_report` por
     `(pid, run_epoch/seq global)`. Sin esto los stats que el cerebro "aprende" están corruptos tras
     cada restart.
  4. Extender `ops/backup_ledger.py` (o job en CCX33) para respaldar `motor_paper_{SYM}.jsonl` +
     `cvd.parquet` con la misma cadencia que el SQLite (Telegram/S3 + checksum + retención).
- **Check measure-first:** simular un kill a mitad de línea (truncar el JSONL a mano) → `load()`
  debe **descartar y seguir**, no crashear. Tras un restart simulado, verificar que pids NO colisionan
  y que `ledger_report` no sobrescribe trades pre-restart. Confirmar que existe copia de los 3
  `motor_paper_*.jsonl` fuera de Railway, restaurable.
- **Reversible:** son cambios localizados con tests (`tests/test_durable_ledger.py` ya existe);
  revert por commit.

#### A1 — Ingesta read-only + lago analítico
- **Entregable:** proceso programado en CCX33 (cron 5-10 min) que copia y normaliza los durables a
  un lago DuckDB/parquet multi-símbolo. Tablas: `signals_vip` (ts_emitted, symbol, direction,
  entry, sl, tp1-tp4, session, tier, killzone, regime, cvd_confirmed, p_master_raw/final),
  `outcomes` (ts_closed, symbol, outcome, exit, pnl_r, fill_type, maker_pending_bars,
  slippage_*_bps), `flow` (ts, symbol, cvd, cvd_slope, imbalance, n_bars, venues), `backtest_cubes`
  (desagregación de los cubes). Incremental (solo deltas, hash-chain integrity check). Maneja
  desconexión con reintentos exponenciales. **Cero escritura hacia Railway.**
- **Check measure-first:** ejecutar una vez manual. Validar: (1) `row_count(signals_vip)` ==
  señales del ledger original; (2) `outcome_id` linkan a `signal_id`; (3) símbolos presentes
  (SOL/BTC/ETH si existen); (4) últimas 10 filas nuevas (no dupes); (5) hash de últimas 100 filas
  == durable. Si verde, agendar.
- **Reversible:** el lago es una copia derivada; borrarlo no afecta nada. Apagar el cron.

#### A2 — Ledger de decisiones + hash-chain append-only (tamper-evident)
- **Entregable:** tabla `decision_ledger` (ts, actor, descripción, `config_snapshot` = env vars +
  git commit hash, motivación, `linked_outcome_ids`, wr_pre/wr_post) — el diario operativo de
  RasDG. Tabla `audits` (ts, n_closed_since_last, win_rate, opus_suggestions, rasdg_notes,
  accepted_suggestions). **Integridad:** hash-chain append-only (NO "blockchain") con head-hash
  anclado periódicamente fuera del host (commit a git o el backup Telegram existente) — para que sea
  prueba real, no teatro.
- **Check measure-first:** registrar 3-5 decisiones reales (cambio de veto, escalada de equity),
  recomputar la cadena, romper una entrada a mano → la cadena debe detectarlo. Verificar que el
  head-hash quedó anclado fuera del CCX33.
- **Reversible:** append-only; no se "deshace" pero las decisiones son inertes (texto). Reversa de
  cualquier cambio operativo va como nueva entrada.

#### A3 — Registro permanente de experimentos (anti-p-hacking)
- **Entregable:** `cerebro_experimentos.jsonl` (append-only): `{id, ts, symbol, feature_name, rule,
  param_range, n_configs, n_trials_acumulado, dsr, cpcv_pass, pbo, walk_forward_score, expected_r,
  status: pending|passed|failed|redundant, notes}`. **Es la defensa contra "intentar de nuevo
  porque se me olvidó".** Quién probó qué, cuándo, y qué pasó. Tabla `rejected_hypotheses` para no
  re-proponer lo mismo.
- **Check measure-first:** registrar el experimento F2-persist BTC ya conocido; verificar que es
  reproducible desde el lago y que el registry no duplica. Intentar re-proponer una hipótesis ya
  rechazada → el sistema la marca redundante.
- **Reversible:** append-only; es metadata, no afecta al bot.

#### A4 — API read-only + dashboard
- **Entregable:** FastAPI ligero en CCX33 (`127.0.0.1`, no expuesto): `/memory/edge-status`,
  `/hypothesis-log?status=`, `/decisions?range=`, `/research`, `/audit-trail`, `/stats`. JSON puro,
  sin cómputo pesado. Comandos Telegram: `/memoria`, `/edges`, `/hipotesis-pendientes`,
  `/auditorias`. Dashboard read-only (Jinja o React simple): mapa de salud de edges (cuando haya
  datos), hipótesis propuestas vs validadas, timeline de decisiones, audit trail. **Solo inspección.**
- **Check measure-first:** llamar cada endpoint, latencia <200ms; `/memoria` devuelve un resumen
  legible; dashboard carga <2s. Nada editable.
- **Reversible:** servicio aparte; apagarlo no afecta lago ni bot.

---

### TRACK B — Bucle de aprendizaje disciplinado

> **Realidad partida en dos:** B0-B2 (propuesta → validación honesta → graduación DORMIDA) son
> **real-construible-ya** sobre el cube histórico. B3-B5 (monitor de degradación, cuarentena
> forward, autoevolución) están **GATED**: no arrancan hasta acumular forward real. Marcado abajo.

#### B0 — Generador de hipótesis causales (REAL-hoy)
- **Entregable:** `tools/cerebro_hypothesis_gen.py`. Propone variaciones **temáticas de la familia
  validada** (residual de impacto F1, persistencia F2, correlación de régimen KL, order-flow ×
  spread) — **NO data-mining a ciegas**. Cada propuesta declara: símbolo, feature_type, rule,
  rango de parámetros, `n_configs`, y `feature_family` (para el contador acumulativo). **White-list
  de features causales**: si alguien propone `future_price` o un "spread de nanotecnología", se
  rechaza automático (veto por causalidad). Escribe a `cerebro_experimentos.jsonl` con
  `status=pending`.
- **Check measure-first:** correr sobre BTC/F2 con umbrales reales (0.0/0.05/0.10/0.20) → exactamente
  16 configs, JSON parseable por el validador, registry sin duplicar.
- **Reversible:** solo escribe propuestas inertes; nada se aplica.

#### B1 — Validador measure-first con gate honesto (REAL-hoy, con los `mustFix`)
- **Entregable:** `tools/cerebro_validation_harness.py`. Toma una hipótesis, corre contra el cube
  (`cosecha_cubes/*.parquet`) con el gate completo de `validation_gate.py`. **Las tres correcciones
  duras integradas:**
  - **`n_trials` acumulativo automático**: lee el contador persistente de `feature_family` del
    registry y lo pasa a `deflated_sharpe_ratio` — NO un default 16/20. (Arregla el agujero de
    `validate_persistence_flow.py`.)
  - **FDR entre segmentos**: cuando evalúa múltiples segmentos en una corrida, aplica
    Benjamini-Hochberg, no un threshold per-segment.
  - **Sample mínimo duro**: si un segmento tiene < `n_min`, status `pending_data`, NO se valida.
    CPCV/PBO solo con muestra suficiente (PBO necesita N≥2 configs y T≥n_splits; con n=20 da `nan`).
  - **Ortogonalidad obligatoria** vs edges cableados: una feature nueva debe **apilar DENTRO** del
    CVD-confirmado (uplift within-edge > +0.02R), no solo tener convicción standalone.
  - Salida: `{passed, dsr, cpcv_paths, pbo, expected_r, n_trials_actual, within_edge_uplift,
    survivorship}` → append a `cerebro_experimentos.jsonl`.
- **Check measure-first:** validar F2-persist BTC con el `n_trials` REAL acumulado (no 16). Test de
  control negativo: inyectar 200 features de **puro ruido** → con `n_trials=200` deben pasar **≈0**
  (si pasa más de un puñado, el contador está mal cableado). Verificar que CPCV con muestra chica se
  abstiene en vez de devolver basura.
- **Reversible:** escribe resultados al registry; no cablea nada.

#### B2 — Graduación a capa 3 DORMIDA (REAL-hoy)
- **Entregable:** `tools/cerebro_graduate.py`. Si una hipótesis pasa el gate honesto, se gradúa a
  `signal_scorer.py.feature_register` como `{feature_name, enabled: False, params: config
  sobreviviente (CONGELADO), dsr, n_trials, since, reason_dormant: "pending_forward_quarantine"}`.
  El bot **lee la feature pero no la dispara**. Se documenta en CHANGELOG con el id del experimento.
  Script de reversa `--disable <feature>` → la quita limpio, log a `cerebro_revert.jsonl`.
  **Parámetros CONGELADOS**: cambiar un parámetro exige re-validar (no "ajustar porque 0.07 hubiera
  sido mejor").
- **Check measure-first:** graduar F2-persist como dormida → `signal_scorer.py` carga sin error,
  `--disable` la quita limpio, `feature_register` versionable en git. El bot vivo se comporta
  byte-idéntico (feature OFF).
- **Reversible:** por diseño — dormida y `--disable` en un comando.

---

> 🔒 **GATE DE DATOS — frontera REAL / GATED.** Las etapas B3-B5 **NO arrancan** hasta que el lago
> (Track A) demuestre **≥100-150 cierres reales acumulados por segmento que se quiera monitorear**.
> Hoy ese número es ~13-18 (cube histórico) y **0 forward en disco** (solo el fixture TEST). Este N
> es el gate de etapa, medible en el lago. Hasta entonces, B3-B5 viven en §6 (cementerio/aspiracional).

#### B3 — Monitor de salud de edges HONESTO (GATED)
*Reemplaza el "Radar de Degradación DSR rolling-20 por segmento" original, que era una fábrica de
~854 falsas alertas/día. Eso va al cementerio.*

- **Entregable:** job que vigila los edges **cableados** (CVD, F2) — **no 72 micro-segmentos**.
  Detección de cambio honesta: **CUSUM/SPRT sobre expectancy** o **intervalos de Wilson**, con
  umbral **calibrado por simulación bajo H0 del propio edge** (no un DSR que finge significancia a
  n=20). Señales operativas adicionales: drawdown rolling, racha de SL consecutivos.
  **Multiple-testing descontado** (Bonferroni/BH por nº de edges vigilados). Las alertas son
  **borrador para auditoría humana**, no señal de acción automática. Escribe `rolling_edge_health.jsonl`.
- **Check measure-first:** correr sobre el mes anterior de forward real (cuando exista); verificar
  que la tasa de falsas alarmas bajo H0 simulado coincide con el umbral configurado (p.ej. <1/semana),
  no 854/día. Si un edge real se degrada, el CUSUM lo marca con retraso acotado y conocido.
- **Reversible:** solo lee y alerta; no apaga nada solo.

#### B4 — Cuarentena forward (GATED, el freno del `mustFix`)
- **Entregable:** toda hipótesis "validated" entra a **cuarentena forward pre-registrada**:
  out-of-sample real, parámetros congelados, sin tocar el bot. Acumula trades reales por segmento
  hasta un mínimo pre-declarado. Solo si **sobrevive la cuarentena con DSR forward-real ≥ umbral
  sobre n suficiente** puede pasar a la siguiente fase. **El camino `validated → candidato-pool`
  automático NO existe** — está físicamente bloqueado por esta etapa.
- **Check measure-first:** una hipótesis validada en cube que **falla** en cuarentena forward debe
  quedar archivada con su acta (no resucitar). Verificar que ninguna hipótesis puede saltarse la
  cuarentena (no hay ruta de código que lo permita).
- **Reversible:** la cuarentena es observación pura; archivar es el default.

#### B5 — Autoevolución propose-only (ASPIRACIONAL, con freno físico)
- **Entregable (futuro):** cuando una hipótesis sobrevive cube + cuarentena forward, el sistema
  **propone** un cambio de config (p.ej. `FQ_CVD_IMB_MIN=0.55`) y lo manda a RasDG por Telegram con
  botón ✓/✗. Si ✓ → **PR en GitHub** (comentado con hipótesis + validation_results + forward), que
  el bot pickea en el siguiente restart. **Canary primero** (shadow/paper), reversible por commit,
  límite 1 PR/día. **Kill-switch del cerebro independiente del CCX33**: si el host muere, un pool
  huérfano no puede modificar el bot.
- **Check measure-first:** simular el flujo completo con 1 hipótesis: el PR se crea, el comentario
  incluye evidencia, el bot lo parsea en restart. **NO a producción** sin OK de RasDG + ≥3 ciclos de
  forward previos.
- **Reversible:** todo cambio es un commit; revert es un commit.

---

## 6. Cementerio y aspiracional (honestidad measure-first)

Lo que los lentes adversariales mataron, explícito, para no auto-engañarnos:

### Al cementerio (overfit/humo/frágil — NO se construye así)
- **"Radar de Degradación: DSR rolling sobre 20 closes por segmento, horario, 72 segmentos."**
  Muerto. A n=20: FP 6.2%, power 35%, ~854 falsas alertas/día sin corrección, CPCV de 3-7 trades,
  PBO=`nan`. Era ritual de rigor: invocar el gate como talismán donde es matemáticamente inservible.
  **Reemplazado por B3 (CUSUM/SPRT calibrado, edges cableados, no micro-segmentos).**
- **`n_trials` fijo 16/20 puesto a mano.** Muerto. Puerta trasera al overfit (7/200 features de ruido
  pasaban). Reemplazado por contador acumulativo automático (B1).
- **`validated → candidato-pool → autoevolución` automático.** Muerto. Reemplazado por cuarentena
  forward vinculante (B4) + propose-only (B5).
- **"Blockchain Lite".** Muerto como nombre. Es hash-chain append-only tamper-evident; la garantía
  real viene de anclar el head-hash fuera del host (A2).
- **Etiquetas "memoria que aprende / corazón del remember-and-measure / autoevolución del cerebro"**
  como si hubiera cognición. Rebajadas a lo que técnicamente son: ETL read-only + stats + cola de
  propuestas con sign-off. El producto es bueno; el naming no infla.

### Aspiracional (necesita más — datos o madurez), claramente marcado
- **Edge-health, validador forward, cuarentena (B3-B4):** bloqueados por falta de forward real en
  disco. Arrancan al cruzar el GATE DE DATOS.
- **Autoevolución propose-only (B5):** tras B4 + ≥3 ciclos forward.
- **Proposición de features por ML** (clustering de patrones, árboles para feature-importance): solo
  cuando el bucle measure-first esté maduro y el gate honesto demostrado.
- **Integración LLM (Claude) en la PROPUESTA** para sugerir hipótesis: aspiracional, siempre bajo el
  mismo gate (el LLM propone, el gate decide).
- **Cross-asset (Random Matrix Theory, correlaciones de régimen ETH vs BTC):** solo con cubes
  validados en más nombres.
- **Auto-disable de edge degradado sin humano / rebalanceo automático de equity:** explícitamente
  fuera por ahora — viola el freno físico hasta tener años de track.

### REAL-construible-ya (lo que entra al sprint)
- Track A completo (A0-A4): crash-safety+backup, ingesta RO, lago, decisiones+hash-chain, registro,
  API+dashboard.
- Track B hasta B2: generador de hipótesis, validador con gate honesto, graduación dormida.

---

## 7. Roadmap de autonomía por niveles de confianza

La autonomía **se gana con evidencia**, no se concede por diseño. El bot "no se caga encima" porque
cada nivel exige más track real que el anterior:

- **Nivel 0 — Observa (HOY).** Lee, mide, registra. Cero acción sobre el bot. Entrega: memoria viva +
  edges visibles. (Track A + B0-B2.)
- **Nivel 1 — Propone a humano.** Detecta degradación honesta (B3) y propone hipótesis validadas;
  RasDG decide todo por Telegram. Gate de ascenso: lago con forward real ≥ n_min por segmento.
- **Nivel 2 — Cuarentena forward.** Las propuestas viven en out-of-sample real pre-registrado (B4)
  antes de poder influir. Gate de ascenso: hipótesis que sobreviven cuarentena con DSR forward ≥
  umbral.
- **Nivel 3 — Canary con sign-off.** Cambios aplicados en shadow/paper, 1 PR/día, reversible, humano
  aprueba cada uno (B5). Gate de ascenso: ≥3 ciclos forward sin sorpresas + kill-switch externo
  probado.
- **Nivel 4 — Autonomía acotada (lejano).** Solo dentro de límites duros pre-aprobados
  (sizing máximo, vetos), con el `RiskGovernor` existente (max 0.25%/trade, -4%/día, kill-switch) y
  freno físico. **Nunca** sin años de track y nunca tocando capital por una alerta de degradación sin
  confirmación.

---

## 8. Riesgos vivos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Ingesta stale silenciosa (CVD no actualiza) | Hash-chain check por ingesta; alerta si el timestamp no avanza en 15 min |
| Overfit silencioso del generador | `n_trials` acumulativo + FDR + cuarentena forward; control negativo de ruido en B1 |
| CCX33 SPOF (cae todo el research) | Backups del lago+research fuera del host (A0); heartbeat vigilado desde Railway/Telegram |
| Torn-write brickea el ledger | A0 crash-safe (fsync+replace) + load tolerante; bloqueante antes de ingerir |
| Pérdida del track de BTC/ETH | A0 backup de los `motor_paper_*.jsonl` (hoy CERO) |
| PID-reuse corrompe stats | A0 restaura `_pid` / re-key por run global |
| Alarm fatigue del monitor | B3 con umbral calibrado por simulación (<1/semana), no per-segment |
| Autoevolución runaway | Propose-only, 1 PR/día, sign-off humano, kill-switch externo |
| Bloat del lago | Partición por mes; vaciar data >1 año manteniendo agregados |
| Falso negativo del gate (edge bueno rechazado por volatilidad) | Re-evaluación periódica; el cementerio se audita cada 3 meses |

---

## 9. El ángulo premio — por qué esto es disruptivo y creíble

Lo disruptivo **no es el hype** — es la **disciplina como producto**. Casi todo el mundo "quant
retail" hace lo contrario: ajusta hasta que el backtest brilla y se enamora del número. Este cerebro
hace lo raro y honesto:

1. **Se propone hipótesis a sí mismo y casi siempre se dice que no.** El valor está en el cementerio
   tanto como en lo validado. Una máquina que documenta qué NO funciona — con `n_trials` honesto, FDR
   y forward real — es **anti-overfit por construcción**, no por promesa. Eso es defendible ante
   cualquier jurado técnico o inversor serio: se puede auditar la cadena de decisiones.

2. **Entiende de trading sin physics-envy.** Su vocabulario son edges falsables y ya pagados (CVD,
   F2-persistencia de Bouchaud-Farmer-Lillo) — no una métrica inventada para sonar inteligente. Mide
   memoria larga del flujo firmado porque eso es real y samplable, y lo cruza contra lo que ya gana
   dinero.

3. **No se caga encima en el handoff.** El freno físico (cuarentena forward + sign-off + kill-switch
   externo) significa que cuando le toque operar más solo, **lo hace solo sobre lo que sobrevivió
   meses de out-of-sample real**, dentro de límites duros. Un robot que sabe lo que no sabe vale más
   que uno que finge certeza.

La historia que se cuenta (al premio, al inversor, a uno mismo) es verdadera: *"construimos una
máquina que aprende de su propio proceso, reconoce cuándo un edge se muere, y es honesta hasta el
punto de archivar sus propias ideas fallidas — y por eso, cuando dice que algo funciona, le creés."*
Eso es el moat. El hype se evapora; la disciplina compone.

---

## 10. Los 3 primeros pasos accionables

1. **Cerrar A0 (crash-safety + backup) — esta semana, bloqueante.** Reescribir
   `DurableHashLedger.append` con fsync+`os.replace` (copiar el patrón de `tools/fetch_cvd.py:185`),
   hacer `load` tolerante a la última línea parcial, arreglar el PID-reuse, y extender
   `ops/backup_ledger.py` para respaldar los `motor_paper_{SYM}.jsonl` + `cvd.parquet`. Sin esto, todo
   lo demás ingiere basura. Tests en `tests/test_durable_ledger.py`.

2. **Levantar A1 (ingesta RO + lago) en el CCX33.** Cron que copia los durables de Railway a un lago
   DuckDB/parquet normalizado, con el check de integridad. Primer entregable visible: el cerebro
   "ve" lo que el bot hace, sin tocarlo. **Empieza a acumular el forward real que destraba Track B.**

3. **Arreglar el `n_trials` del validador (B1, parcial) sobre el cube actual.** Implementar el
   contador acumulativo por `feature_family` y conectarlo a `deflated_sharpe_ratio` reemplazando los
   defaults 16/20 de `validate_persistence_flow.py`. Correr el **control negativo de ruido** (200
   features random → ≈0 pasan) para demostrar, con número, que el gate ya no es decorativo. Ese test
   es la prueba de que el moat es real.

> Mientras tanto, el contador de cierres reales por segmento en el lago es el **gate de datos** que va
> destrabando B3-B5. No se fuerza: se mide y se espera. Measure-first hasta el final.