# Constitución del fq-bot — invariantes no-negociables

> Las reglas que **NO se rompen** por conveniencia de ingeniería. Léelas antes de tocar
> el motor, el gate, el runtime o cualquier `FQ_*`. fq-bot vive en producción (Railway)
> con capital real de suscriptores: cada push redeploya. El problema fundacional (tweet de
> @vibeeeng): los agentes se descarrilan por **falta de contexto**, no de inteligencia.
> Esta es la lista de lo prohibido y lo obligatorio.

---

## I. Invariante cero: measure-first + el gate

### A. El gate de validación (`tools/validation_gate.py`, ~221 líneas)
Todo lo que pasa a producción **pasa primero** por un gate de 3 métricas:
1. **DSR (Deflated Sharpe Ratio) > 0.95** — PSR que corrige multiple-testing. `n_trials` = cuántas
   configs se probaron (no 1); la vara sube con cada trial. No asume normalidad (usa skew + kurtosis).
2. **CPCV (Combinatorial Purged CV)** — valida todas las combinaciones como OOS, con embargo (purga
   el train dentro del borde del test → combate leakage temporal).
3. **PBO (Probability of Backtest Overfitting)** — ¿la mejor in-sample queda bajo la mediana OOS?
   PBO alto → selección sobre-ajustada, rechaza.

Pure stdlib + numpy, **sin scipy**. Referencia: commit `4176dd6` / `ba9f4d8`.

> **NO NEGOCIABLE:** nada entra a vivo sin DSR > 0.95 (+ ortogonalidad). Si algo "tiene lógica" pero
> falla el gate → cementerio (ver `CEMENTERIO.md`). **El gate ORO, sus umbrales y sus puertas de
> leakage NO se degradan jamás por conveniencia de ingeniería** (ENGINEERING_PLAN §0.4).

### B. Medición forward: motor paper
Cada edge validado en backtest debe **replicar forward** (orden real, 0% capital) medido en paralelo
al ledger VIP, **sin tocar el motor ni el trading real**. El motor paper:
- Abre/cierra en papel; resuelve PnL **NETO** (fees + slippage) vía PaperBroker.
- Shadow maker (limit con TTL) + fallback taker. Veto propio (`FQ_MOTOR_PAPER_VETO_*`) independiente
  del VIP. Juzga el veto con el **ts de la VELA**, nunca con `now()`.
- Escribe ledger JSONL append-only con hash-chain SHA-256.

Referencia: `motor_paper.py`. No se gradúa a real sin que el motor paper demuestre el uplift forward
(criterio: ≥30 fires, uplift ≥ +0.1R, DSR ✓).

---

## II. Invariantes de diseño (lo que jamás cambia)

1. **Dormido por defecto.** Toda feature experimental nace **OFF** tras un flag `FQ_*`. Cuando off, la
   señal y el ledger son **byte-idénticos** al histórico (sin claves nuevas). Se prende solo con flag
   explícito y criterio documentado.
2. **Desacoplamiento de colectores.** Los colectores (CVD, OI, carry) son **read-only y no-críticos**:
   escriben `/data/*.parquet`; el motor LEE, nunca escribe. Si un colector cae, el motor sigue. **La
   señal jamás depende de un colector.**
3. **Ledger inmutable.** El track record forward es el **producto** de la fase paper → append-only,
   hash-chain SHA-256, auditable. No se edita.
4. **El veto juzga el reloj de la vela, no el de pared.** `tests/test_no_wallclock.py` (AST) FALLA si
   aparece `datetime.now()/utcnow()/today()` sobre el baseline en el path del motor. El bug de reloj
   ocurrió dos veces (`volume_quality`, `killzones_pd`); la tercera la atrapa CI, no un humano.
5. **Toda lección aprendida se vuelve un test** (ENGINEERING_PLAN §0.2 / N2). Los tests nacen de
   invariantes y lecciones, no de porcentajes de cobertura.
6. **No hay veto sin dato.** Cada flag de veto/boost (`FQ_CVD_FILTER`, `FQ_PERSIST_BOOST`, …) tiene
   criterio de ON/OFF en `research/plan_evolucion_2026.md`.

---

## III. El ledger durable (hash-chain — proof of work)

`execution.py` define `HashLedger` / `DurableHashLedger`. Cada orden se sella **antes de conocer el
desenlace** (commit-then-reveal):
- Registro: `seq`, `prev` (hash anterior, "genesis" en el primero), `hash = sha256(prev + payload)`,
  `payload` (event OPEN/CLOSE, ts, symbol, entry, stop, tp, size, risk_frac…).
- `verify()` chequea la cadena al cargar. Ningún registro puede editarse sin romper el SHA-256 de
  todos los posteriores. Test: `tests/test_durable_ledger.py`.

> Garantía: el track record es **tamper-evident**. Es lo que re-ratea la valuación cuando se va a vivo.

---

## IV. Stack e infraestructura

### Ejecución (Railway, contenedor único — `launcher.py` envuelve 3 procesos)
- **VIP:** `entry_vip.py` → `fq_bot_v3_2.py` (loop principal, `fusion_engine.evaluate_signal`,
  `motor_paper.on_bar`, broadcast VIP, escritura `fq_ledger.db`).
- **Público:** `entry_public.py` → `public_outcome_announcer.py` (lee `fq_ledger.db` en RO, anuncia
  cierres/teasers).
- **Mantenimiento:** `ops.maintenance` (heartbeat, backup del ledger, detección de derive).
- Comunicación entre procesos: **solo vía el ledger SQLite** (el público es read-only).

### Datos (Railway Volume `/data`, persiste entre reinicios)
- `fq_ledger.db` (SQLite, VIP, **4 TP** — hoy **SOL-rico**; BTC/ETH aún solo en motor_paper).
- `fq_public.db` (SQLite, público, RO).
- `motor_paper_SOL_USDT.jsonl` / `_BTC_USDT.jsonl` / `_ETH_USDT.jsonl` (medición forward, 1 TP, hash-chain).
- `cvd.parquet` / `cvd/*.parquet` (order-flow), `cosecha_cubes/*.parquet` (backtest), carry ledger JSONL.

### Research (Hetzner CCX33, 8 vCPU)
GitHub self-hosted runner: descarga datasets (OKX/CCXT, append-only dedup), cosecha sharded, computa
features, etiqueta (bt_labeler), corre PBO + DSR. Workflows 1-tap en `.github/workflows/`.

### Exchanges y data
- Símbolos: **SOL/USDT** (pilar), **BTC/USDT**, **ETH/USDT** — swap/perpetuo (permite medir funding).
- **OKX** por defecto en runtime/research; **Binance Vision** (archivo público S3, no la API) para la
  data histórica gratis de validación (la API de Binance da 451 en runners). `tools/build_dataset.py`.

### Runtime / cadena de suministro
- Producción y CI/research apuntan a **Python 3.12**; `requirements.lock` pinea el set completo
  (`==`), `requirements.txt` queda como declaración de intención. `ci.yml` job `lockcheck`. (El README
  histórico dice 3.11; la fuente de verdad del pin es `requirements.lock` + ENGINEERING_PLAN §N1.)
- `railway.toml` → `watchPatterns` excluye `**/*.md`, `internal/`, `.github/`, `tests/`, `tools/`:
  **los docs no redeployan**. (Editar esta carpeta `MEMORY/` no toca prod.)

---

## V. Flags `FQ_*` (disciplina experimental — verificados en `fq_bot_v3_2.py`)

> Default OFF salvo donde se indica. Lista completa en `.env.example`. Estos son los que tocan la
> tesis de edge:

### Motor paper (medición forward)
- `FQ_MOTOR_PAPER` (SOL, default 0), `FQ_MOTOR_PAPER_BTC` (default 0), `FQ_MOTOR_PAPER_ETH` (default 0).
- `FQ_MOTOR_PAPER_TF` / `_BTC_TF` / `_ETH_TF` = `5m` (TF del research — **no tocar**).
- `FQ_MOTOR_PAPER_*_LEDGER_PATH` → los JSONL en `/data`. `FQ_MOTOR_PAPER_VETO_*` = veto propio.

### Capa 3: order-flow (CVD) y persistencia (F2)
- `FQ_CVD_FILTER` (colector/tag, default OFF; off → ledger byte-idéntico sin claves `cvd_*`).
- `FQ_CVD_VIP_CONVICTION` (badge "◆ ORDER-FLOW CONFIRMADO", marca el hecho, default OFF).
- `FQ_CVD_BOOST_TIER` (la confirmada sube +1 tier de convicción y size; **requiere** `FQ_CVD_FILTER`
  + re-confirm honesto, default OFF).
- `FQ_PERSIST_BOOST` (símbolos, p.ej. `BTC`; 2º medidor F2 ortogonal; **requiere** `FQ_CVD_FILTER`
  + el re-confirm n_trials=44 ANTES de prender; default vacío = sin boost).
- `FQ_CVD_IMB_MIN` = 0.50 (el umbral validado).

### Regímenes y vetos (default ON — validados en backtest 5 años)
`FQ_VOL_GATE_ENABLED`, `FQ_VOL_VETO_DEAD_HOURS`, `FQ_DEAD_2PM_MANIP` (protección manipulación
14:00-15:00 UTC), `FQ_ASIA_FAKEOUT_GUARD`, `FQ_REGIME_KL`/`_VOL_Z`/`_WR_DELTA`/`_MIN_N`. El veto de
sesión (`segment_veto.py`, puro) corta SOL **y** BTC **y** ETH (commit `be75534`).

### Ejecución y broadcast
`FQ_EXEC_MODE` (paper→live), `FQ_ETH_VIP_BROADCAST` (ETH a clientes — solo tras pasar DSR).

---

## VI. Cuarentena — qué NO refactorizar todavía (ENGINEERING_PLAN §1)
Candidatos a morir o cambiar según veredictos pendientes; se tocan solo para fixes, cero inversión
estética hasta el veredicto:
- Bloque vector `qt_*` en `bt_retrieval`/`bt_features` (no suma en OOS; `qt_sync_score` 100% NaN).
- `emergent_time.py` Phase E (`FQ_EMERGENT_TIME_ENABLED`, OFF, sin validación shadow).
- Tooling posible peso muerto: `research_demo.py`, `repro_fvg_selection.py`, `build_deck.py`,
  `internal/_staging`.

Nota: `quantum_timelines.py` (QTE del bot vivo) **NO** es el bloque `qt_*` del vector; no está en
cuarentena. `session_bias.py` / `signal_scorer.py` / `regime_detector.py` salieron de cuarentena
(run #31): sostienen el edge / están acoplados al gate ORO → **no se apagan por env**.

---

## VII. Anti-objetivos (lo que NO vamos a hacer)
- Reescritura big-bang, microservicios, async total, cambiar de exchange-lib o framework: riesgo sin
  retorno para un sistema de una persona con dinero en juego.
- "Subir cobertura" como métrica (los tests nacen de invariantes, no de porcentajes).
- Tocar el gate ORO, sus umbrales o sus puertas de leakage por motivos de ingeniería.

---

_Fuente de verdad: `tools/validation_gate.py`, `execution.py`, `motor_paper.py`, `fq_bot_v3_2.py`,
`launcher.py`, `ENGINEERING_PLAN.md`, `segment_veto.py`, `tests/`. Actualizado 2026-06-27._
