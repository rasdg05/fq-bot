# MEMORIA DE PROCESO — fq-bot (la puerta)

> **Lee esto ANTES de tocar nada.** 60 segundos. El problema (tweet de @vibeeeng):
> los agentes se descarrilan por **falta de CONTEXTO**, no de inteligencia. Olvidan
> por qué se decidió algo, qué está prohibido, qué se validó o se mató. Esta carpeta
> es la bitácora durable que cierra ese hueco. Honesta, concreta, aterrizada en el
> repo real. Si vas a editar código, abrir un PR o proponer una idea: pasa por aquí.

## Qué es fq-bot (en 3 líneas)
Bot de señales cripto de **order-flow** (RasDG + Claude), vivo en producción (Railway)
con suscriptores reales. Símbolos: SOL (pilar), BTC, ETH. Disciplina central:
**measure-first** — nada se cree ni se despliega sin pasar el gate de validación; lo
que no pasa va al cementerio, honesto.

## Dónde estamos HOY (act. 2026-08-17) — 30 segundos

- **No hay edge demostrado.** Ninguna configuración medida tiene el IC95% de la expectancy
  por encima de cero. Motor paper con fees: E[R] −0.510 (n=90). Cube bruto: +0.224R. La
  diferencia **es el coste de ejecución**. Los números vigentes están en `CLAUDE.md`.
- **La línea de Polymarket está CERRADA** (ago-2026, 4 pasos medidos, 0 capital). El venue
  es bueno y no tenemos qué venderle. **No re-proponerla** — ni entera ni por partes.
  Ver `CEMENTERIO.md` §Polymarket (incluye el triaje de los 10 repos que la originaron).
- **El trabajo que toca es `internal/BRIEF_INSTRUMENTO_2026-08.md`**, E7 y E8 primero: son
  diagnósticos que pueden invalidar el resto y leen datos que ya existen.
- **Rama con el contexto más fresco:** `claude/polymarket-trading-tools-grx05x`.
  ⚠️ **`main` NO la tiene mergeada**: arrancar desde `main` re-propondría lo ya muerto.

---

## Ruteo por ROL (el ecosistema, una sola verdad)
La memoria es el **cerebro compartido** de todo el equipo. Cada función entra por su vista, pero
todas leen el MISMO registro — Marketing no puede afirmar lo que Ingeniería no validó, y viceversa.
- **Marketing / contenido / ventas** → `ROLES/MARKETING.md` (qué SÍ afirmar, qué NO, el track record).
- **Ingeniería / backend** → `ROLES/INGENIERIA.md` (invariantes, decisiones, build rules, arquitectura).

## Cómo usar esta carpeta
1. Empieza aquí (`00-INDICE.md`).
2. ¿Vas a tocar el motor / la config / una invariante? → `CONSTITUCION.md`.
3. ¿Por qué existe X, por qué se eligió Y? → `DECISIONES.md`.
4. ¿Esta idea ya se probó? (antes de "reinventar" algo) → `CEMENTERIO.md`.
5. ¿Qué está vivo / dormido / midiendo / pendiente HOY? → `ESTADO.md`.

## Los 5 archivos (resumen de 5 líneas cada uno)

### `00-INDICE.md` (esta página)
La puerta. Qué es el proyecto, cómo se navega la memoria, las 3 reglas de oro y un
resumen de cada archivo. Se lee en 60s y orienta a cualquiera desde cero. Si solo
puedes leer una página antes de actuar, que sea esta — y luego la que aplique a tu
tarea. Actualizado 2026-06-27.

### `DECISIONES.md` — Decisiones clave y por qué
Las 10 decisiones de arquitectura/producto con su razonamiento y la evidencia real
(archivos, commits, PRs). Measure-first, CVD, física F1/F2, carry market-neutral,
ETH, colectores desacoplados, ejecución taker+maker, cerebro, producto de 3 capas.
Cada decisión cita el archivo o commit que la sostiene. Si quieres entender "por qué
está así", está aquí. Termina con las disciplinas inegociables.

### `CEMENTERIO.md` — Validado vs muerto (registro de evidencia)
Lo que PASÓ el gate (CVD DSR 0.988, F2-persist DSR 0.985/0.997) y lo que MURIÓ
(quantum finance, LPPL, Khrennikov, rough-vol, early-warning — refutados 3-0 o
infalsables). Más los candidatos esperando veredicto (OI, global_ls, toptrader/taker).
Existe para que NADIE re-pruebe lo ya muerto ni re-crea un espejismo de muestra chica.
Regla: medida o muerte.

### `CONSTITUCION.md` — Invariantes no-negociables
Las reglas que NO se rompen por conveniencia de ingeniería: el gate (DSR>0.95) no se
degrada jamás; las puertas de leakage no se bypassean; features experimentales corren
**dormidas** (env-gated, default OFF); el ledger es append-only con hash-chain SHA-256;
los colectores nunca bloquean una señal. Stack, flags y mapa de infra. Léelo antes de
cambiar runtime, gate o cualquier `FQ_*`.

### `ESTADO.md` — Foto del proyecto HOY
Qué está vivo en clientes, qué está cableado-pero-dormido (OFF), qué mide forward, qué
espera veredicto, qué es plan en papel. Las 3 capas de edge y su etapa. La auditoría
del registro (SOL rico vs BTC/ETH solo motor_paper) y el plan cerebro. Es la página que
más caduca: si la fecha es vieja, confírmala contra `git log` y `research/*.md`.
Fecha: 2026-06-27.

### Obras del proyecto (sub-carpetas)
Además de los 5 archivos núcleo, la memoria guarda las **obras** (PDF + texto):
- `ingenieria/` — la ecuación del motor (P_master, de la vela al disparo).
- `marketing/` — guías de marca y de cómo se construye una ventaja.
- `investigacion/` — **review científico (preview)** + **preprint EN (SSRN-ready)** +
  **presentación del perfil académico** (físico→quant, CDMX → Cornell/Oxford) +
  **`rutas-nuevas-2026.md`** (ideación estructura/motor/premios/investigación/vanguardia,
  cada idea con su experimento measure-first, **respetando el cementerio**) +
  **Ruta A Numerai Crypto** (`tools/numerai_crypto_pipeline.py`, end-to-end). **Aquí va TODA
  obra nueva del proyecto** (reviews, papers, decks, rutas) — directiva RasDG, 2026-06-29.

---

## Las 3 reglas de oro (si solo recuerdas tres cosas)

1. **MEASURE-FIRST O MUERTE.** Nada entra a vivo (clientes / capital) sin pasar el gate
   `tools/validation_gate.py`: **DSR > 0.95** (Deflated Sharpe, corrige multiple-testing)
   + ortogonalidad + CPCV/PBO. Si "tiene lógica" pero falla el gate → cementerio. No se
   re-prueba lo que ya murió ahí.

2. **DORMIDO POR DEFECTO + DESACOPLADO.** Toda feature experimental nace OFF tras un flag
   `FQ_*` (señal byte-idéntica cuando off). Los colectores (CVD, OI, carry) son read-only
   y no-críticos: si uno cae, el motor de señales sigue. El path crítico jamás depende de
   un colector ni de un experimento.

3. **EL LEDGER ES LA VERDAD, Y ES INMUTABLE.** `/data/*.jsonl` (motor_paper, hash-chain
   SHA-256 append-only) y `/data/fq_ledger.db` (VIP) son la fuente de verdad del track
   record (fill-rate, R neto, regímenes). No se editan. Cada decisión de graduar un edge
   se lee del ledger forward, no del backtest.

---

## Fuentes de verdad (para auditar esta memoria)
`git log` · `research/*.md` · `tools/validation_gate.py` · `motor_paper.py` ·
`fq_bot_v3_2.py` · `launcher.py` · `execution.py` · `ENGINEERING_PLAN.md` · `tests/`.

_Mantenimiento: cuando una decisión cambie de estado (un edge se gradúa, un candidato
muere, una etapa se ejecuta), actualiza el archivo que aplique y la fecha. La memoria
solo sirve si es honesta y está al día._
