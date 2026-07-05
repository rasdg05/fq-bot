# Plan del Fantasma — decisiones + estado de implementación (2026-07-05)

> Las 6 decisiones del análisis de 7 años, su veredicto del gate, y CÓMO se implementan.
> Análisis completo: `GHOST_MAP_2026-07.md`. Visuales: `fantasma-2026-07.html`, `gate-2026-07.html`.
> **Todo cableado default OFF -> byte-idéntico hasta que se active. No despliega hasta merge.**

## Estado por decisión

| # | Decisión | Gate | Cómo se activa | Estado |
|---|---|---|---|---|
| 1 | **Costo ejecución** (maker-fills → 2× neto) | — | Proyecto: `FQ_EXEC_MODE=maker` + garantizar fills | ⏳ proyecto |
| 2 | **Símbolos igual-peso** (no concentrar) | GATE-D: ranking anti-persiste | Railway: toggles `FQ_MOTOR_PAPER_*` de los que pasan el gate | 🎛️ env var |
| 3 | **Dirección neutral** (no sesgo short) | GATE-A/H1: simétrica | Ya neutral en código (`sig["direction"]`) | ✅ ya está |
| 4 | **KL 0.34→0.40** (cadencia) | GATE-A: filtro sí, umbral overfit | Railway: `FQ_KL_THR=0.40` | 🎛️ env var |
| 5 | **Sizing por convicción en longs** | GATE-C: PASA (PBO 0.008, 15/15) | Código ✅ · `FQ_CONVICTION_LONGS=1` | ✅ cableado |
| 6 | **Sizing sobrevivible + halt DD** | Racha 48 losses, DD 168R | Código ✅ · `FQ_MOTOR_MAX_DD=0.25` | ✅ cableado |

## Env vars que activas en Railway (cero deploy, reversibles)
```
FQ_KL_THR=0.40                 # decisión 4: cadencia (mismo edge OOS, +16pp señales)
FQ_CONVICTION_LONGS=1          # decisión 5: barbell 4:2:1 en longs (GATE-C validado)
FQ_MOTOR_MAX_DD=0.25           # decisión 6: halt de supervivencia al -25% del pico
# decisión 2: activa los símbolos que pasan el gate base (igual-peso por construcción)
FQ_MOTOR_PAPER_BTC=1  FQ_MOTOR_PAPER_ETH=1  FQ_MOTOR_PAPER_BCH=1  ...
```
Tunables opcionales: `FQ_CONVICTION_HI/MID/LO` (default 1.0/0.5/0.25), `FQ_CONVICTION_MIN_HIST` (30).

## Lo cableado en código (rama, no despliega hasta merge)
- **`motor_paper.py`** · `conviction_weight()` + buffer rodante de p_master LONG + hook en
  `on_bar` (escala `requested_risk` por tercil, solo longs, sin look-ahead). Barbell HACIA
  ABAJO: solo reduce riesgo en longs de baja convicción, jamás sube sobre el cap. Tests: 12.
- **`execution.py`** · `GovernorConfig.max_drawdown_frac` + check en `decide()` (halt
  pico-a-valle usando el `peak_equity` que Account ya trackea). Reversible al recuperar. Tests: 6.

## Supervivencia (respuesta measure-first)
Secuencia real 7 años, neta: **racha perdedora más larga = 48 trades**, drawdown de camino = 168R.
El que te mantiene vivo, en orden: (1) **riesgo bajo** (0.25% sobrevive; ≥0.5% sin halt = ruina),
(2) **halt de DD** (convierte ruina en pérdida acotada a riesgo alto), (3) **parciales tp1-4**
(el bot real banca ganancias antes → DD mucho más suave que este tp4 all-or-nothing).

## Guardrail
Todo esto es cube BRUTO (etiquetas tp4, sin coste real). Antes de confiar 100%: **forward en vivo
con el ledger real, neto de costos**, es el juez final. Lo cableado está OFF por default justo para
medir A/B en vivo antes de graduar.
