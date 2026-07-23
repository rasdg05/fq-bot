# Plan: construir un track record FORWARD de verdad (`FQ_FORWARD_MEASURE`)

**Fecha:** 2026-07-23 · **Origen:** auditoría del backup (fq_ledger.db + motor_paper_*.jsonl).

## Qué encontró la auditoría (los 3 huecos)
1. **Cobertura de un solo símbolo.** El ledger vivo (`fq_ledger.db.signals`) tiene 24
   señales, **100% SOL** (mean +2.56R, pero n=24 y súper seleccionado). BTC/ETH y el
   resto no tienen historia viva. El "+0.34R BTC" del proof strip es de **cubo**, no vivo.
2. **Cadencia letal.** Los `motor_paper_*.jsonl` (forward por símbolo) suman **4 trades
   cerrados** (BTC 2, ETH 1, SOL 1), **todos stops**, en ~1 mes. n así no concluye nada.
3. **El motor mide solo lo que EJECUTA.** Para saber si KL ayuda a ETH o el flujo lo
   daña, hay que medir la **población base** y filtrar en análisis — no al revés.
   Además el tag `kl_low` **no se está grabando** (falta `FQ_REGIME_TAGS=1`), así que
   hoy no se puede segmentar base vs base+KL ni siquiera con los datos que hay.

La cadena hash de los ledgers está **íntegra** (verificado): el problema NO es la
fontanería del cierre — es cadencia + cobertura + tags.

## Las dos mitades

### Mitad de análisis — HECHA
`tools/forward_measure.py` (+ `tests/test_forward_measure.py`): lee todos los
`motor_paper_<SYM>.jsonl`, reconstruye trades por pid, verifica la cadena hash y saca
por símbolo la R en buckets **base / +flujo (CVD✓) / +KL (irrev-bajo)**, con n y
win-rate, y un veredicto honesto de suficiencia (n≥30). Solo LEE; cero riesgo.

### Mitad de medición — POR CABLEAR (`FQ_FORWARD_MEASURE=1`)
Un solo switch en `launcher.py` que, para el **set de candidatos** (SOL, BTC, ETH, BCH,
BNB, LINK — los que el estudio KL marcó ✅/PASA), arma hijos **no-críticos** de motor
paper con:

| env por hijo | valor | por qué |
|---|---|---|
| `FQ_MOTOR_PAPER_<SYM>` | `1` | prende el runtime paper del símbolo |
| `FQ_REGIME_TAGS` | `1` | **graba `kl_low` por disparo** → habilita el bucket +KL |
| `FQ_CVD_FILTER` | `1` (medición) | taggea `cvd_confirmed` por disparo → bucket +flujo |
| `FQ_<SYM>_VIP_BROADCAST` | `0` | **jamás difunde a clientes** (regla de hierro) |

Clave measure-first: el motor paper **abre en cada disparo base y TAGGEA** los filtros
(no gatea con ellos). Así el ledger acumula la población completa y `forward_measure.py`
compara base vs base+KL vs base+flujo con n creciendo — **la data decide**, no un prior.

**Sin filtros ajenos:** BCH corre **sin KL** (su edge vive en irrev-ALTO); ETH con KL
y **sin** el confirmador de flujo (el flujo le resta, −0.167). El tag de ambos igual se
graba para poder medir las dos caras.

### Estado del wiring (actualizado 2026-07-23)
- **Switch `FQ_FORWARD_MEASURE` — HECHO** (`launcher.py::_apply_forward_measure`). Con
  `=1` prende BCH/BNB/LINK en paper (broadcast OFF) + `FQ_REGIME_TAGS=1`, vía setdefault
  (tus overrides de Railway ganan). **NO toca `FQ_KL_FILTER`** — measure-first taggea,
  no gatea (el edge de BCH vive en irrev-ALTO; gatearlo lo dañaría).
- **Scans BNB/LINK — YA existían** (no hubo que escribirlos): flags dedicados
  `FQ_MOTOR_PAPER_BNB/LINK` + la flota free (`_xsym_motor_paper_scan`, broadcast off,
  ledger propio por símbolo). El switch solo los enciende.
- **`audits` revivida — HECHO**: se arregló un DEADLOCK en `save_audit` (tomaba `_lock`
  y `compute_entropy_metrics` lo re-tomaba) y se desacopló el write de Claude — la fila
  cuantitativa se escribe siempre cada N cierres.
- **Honestidad del proof strip — HECHO**: los números salen de investigación validada
  con DSR y etiquetados por tier (SOL/BTC order-flow, ETH régimen KL). El forward vivo,
  cuando `forward_measure.py` tenga n suficiente, los reemplaza etiquetados como "vivo".

**Para encenderlo:** en Railway pon `FQ_FORWARD_MEASURE=1` (y ya). Empieza a acumular
BCH/BNB/LINK forward sin exponer clientes; léelo con `python tools/forward_measure.py`.

## Salida esperada (cuando corra unas semanas)
`forward_measure.py` imprime, por símbolo, la R base vs +KL vs +flujo con n real. Ese es
el número que —solo entonces— puede subir al proof strip, ganado y etiquetado como vivo.
