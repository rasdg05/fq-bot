# Research sprint — ¿hay edge en la "física del mercado"? (jun 2026)

Hunt honesto de edge tradeable a partir de la cosmovisión física (oscilador alrededor
del valor, reversión/momentum por régimen). Datos: OKX 5m, 8 símbolos
(BTC/ETH/SOL/BNB/XRP/DOGE/ADA/LTC), ~7 meses. Split temporal IS(70%)/OOS(30%) por
símbolo; el **OOS es el juez**. Scripts en `tools/` (espectro, cascada, matriz,
mr_edge, mom_edge, regime_edge, confluence_edge, edge_htf).

## La pregunta
La descripción física es real, pero **¿es tradeable?** ¿Se puede sacar plata, o es
lindo en el gráfico y nada más?

## Lo que se confirmó (la física descriptiva ES real)
- **Espectro de saltos** (`spectro_legs`): los tamaños de pierna son un **continuo**
  (unimodal), NO cuantos discretos. Escala característica ~2.78 ATR. → no hay órbitas
  de Bohr; hay una *escala*, no *cuantos*.
- **Cascada** (`cascade_laser`): el alcance más allá del sweep es ~exponencial,
  reach medio **2.54 ATR**, tasa de descuento ρ≈0.39/ATR. Funding como proxy de
  inversión de población: **null** (sin OI y casi plano → sub-potenciado).
- **Matriz de transiciones** (`transition_matrix`, Heisenberg): estructura conditional
  real (entropía 0.556 vs null 0.824) pero confundida por alternancia + clipping. Señal
  limpia: **repulsión del valor + amplitud característica ~2.5 ATR**. BTC ≈ SOL
  (decoherencia entre activos NO confirmada).
- **Convergencia:** los tres dan **~2.5 ATR** = un **oscilador continuo** alrededor del
  valor, no un átomo discreto. El lado onda/continuo ajusta; el discreto no.

## Lo que se midió como edge (la respuesta honesta: ~no hay)
Expectancy OOS por trade (R, neto de costos), pooled 8 símbolos:

| Regla | Costos | OOS exp (R) | PF | Veredicto |
|---|---|---|---|---|
| Reversión naive (fade z>θ) | taker 6bps | **−0.316** | 0.69 | pierde en los 8 |
| Momentum naive (Donchian) | taker 6bps | **−0.406** | 0.37 | pierde peor |
| MR + régimen (ER<0.3) | taker 6bps | **−0.211** | 0.76 | mejora, sigue rojo |
| MR + régimen | **maker 0bps** | **+0.010** | 1.01 | breakeven |
| Confluencia≥3 | maker 1bps | **+0.019** | 1.03 | positivo pero **ruido** |

- Confluencia≥3 vs <3 (OOS, maker): **+0.019R (PF 1.03)** vs **−0.056R (PF 0.92)** →
  el edge **se concentra en la confluencia alta** (valida `confluencia≥3`
  direccionalmente). PERO: conf=4 no confirma, e **IS de conf≥3 ≈ −0.05R** →
  **inconsistente IS↔OOS, NO desplegable.**
- **TF más alto (1h/4h):** no rescata; muestras chicas, nada estable.

## La parte ÚTIL: la descomposición de levers
Cada lever vale algo medible — y stackean **hacia cero, no arriba**:
- **Ejecución (taker→maker): ~+0.30R.** El lever más grande. Valida tu "límite en el
  imán" (maker): es la diferencia entre perder y no perder.
- **Régimen (right tool, right regime): ~+0.10–0.30R.** La hipótesis MR-en-rango /
  momentum-en-tendencia se valida direccionalmente.
- **Selección (confluencia): el multiplicador que falta.** Disparar sobre TODA señal
  promedia a cero; el subset de alta confluencia es donde vive lo poco que hay.

## Veredicto
**No hay edge robusto, estable IS↔OOS, en ninguna regla físico-derivada simple** — ni a
5m/1h/4h, ni con maker, ni con régimen, ni con confluencia. El mercado a estas escalas es
~eficiente respecto a costos+ruido para factores simples. La física dio un **modelo
descriptivo real** y **cuantificó dónde está el apalancamiento** (ejecución > selección >
régimen), pero un edge desplegable exige **más** que estos proxies crudos.

## Qué NO hacer / Qué SÍ
- **NO** seguir inventando reglas mono-factor a 5m (p-hacking; ya sabemos que no cruzan).
- **SÍ** medir el edge del **motor real** vía su propio harness (`bt_features` replaya el
  `fusion_engine` real sobre histórico) — la pregunta correcta es si el stack completo
  (confluencia + estructura + P_master + scorer) bate el breakeven que tocan los factores
  sueltos. Ahí, si existe, está el edge.
- **SÍ** asegurar **ejecución maker** en vivo (el lever más certero, +0.30R).
- **SÍ** conseguir **OI** (no solo funding) para testear el láser/cascada en serio.

> Moraleja de marca/contenido: *"Sometí mi teoría hermosa a 7 meses de datos y 8 activos.
> El mercado dijo: la estructura es real, pero el edge fácil no existe — y acá está
> exactamente cuánto vale cada pieza."* Eso es honestidad que construye más que cualquier
> feed de ganadores.

---

## ACTUALIZACIÓN — el MOTOR REAL sí tiene edge (la respuesta a la pregunta)

Medimos el `fusion_engine` real vía sus `cosecha_cubes` (señales evaluadas con outcome):
**27.504 señales fired, 2019→2026 (7 años, SOL+BTC), ~10.8/día.** (`tools/measure_engine_edge.py`)

| | exp/trade | PF | wr |
|---|---|---|---|
| bruto | +0.191R | 1.31 | 38% |
| **neto MAKER (~4bps)** | **+0.105R** | 1.16 | 38% |
| neto TAKER (~10bps) | −0.025R | 0.97 | 38% |

- **Estable IS↔OOS:** IS +0.107R / OOS +0.098R (los factores naive cambiaban de signo;
  este NO). Positivo OOS en SOL (+0.14) y BTC (+0.07).
- **El maker es TODO el edge:** +0.10R maker vs −0.03R taker. Confirma en el motor real
  el lever #1 del sprint y tu "límite en el imán": sin maker, no hay negocio.

**El edge está concentrado — ahí está la palanca:**
- **Selectividad (gate P2, excluir killzones perdedoras): +0.098 → +0.142R OOS.**
  conf 3-4 + kz-gate → +0.161R. La selección SÍ suma (a diferencia de los factores sueltos).
- **Mapa de killzones (OOS, neto maker):** ganadoras → ny_pm **+0.40**, asia_kz +0.37,
  silver_bullet_lo +0.32, sb_ny_am +0.27. Perdedoras → asia_open **−0.68**, ny_close −0.29,
  sb_ny_pm/fuera −0.11. El edge vive en sesiones específicas.
- **Asimetría direccional: short +0.16R vs long +0.02R.** Casi todo el edge es del lado
  corto en esta muestra (2019-26) → entender/explotar la asimetría.
- **p_master y confluencia NO rankean limpio** (p_master en U, conf no monótona) →
  headroom: recalibrar la confianza / mejor capa de selección puede subir la expectancy.

**El asterisco honesto (riesgo vivo):** el +0.10R asume que tu límite **llena** al nivel.
En maker real hay *adverse selection*: llenás en los perdedores y te quedás afuera de
ganadores que se van sin vos → el edge vivo es **menor** que el backtest. Validar fill-rate
en paper es obligatorio. (Y el Sharpe anual ~3.5 es naive: trades correlacionados → el real
es bastante menor.)

**Bottom line:** los factores sueltos tocan cero; **el stack completo del motor, disparando
maker y selectivo, SÍ cruza a positivo y estable (+0.10→0.16R OOS).** El edge existe — chico,
maker-dependiente, concentrado en sesiones/cortos — el tipo de edge real que produce un stack
de confluencia. *La arquitectura funciona.*

---

## ACTUALIZACIÓN 2 — validación robusta (corrige la #1; "de dónde sale el edge")

**Corrección honesta:** el cube tiene **12 variantes de TP por señal** → la medición #1 contó
cada señal ~12×. Reales: **2.277 señales distintas** (no 27.504). El expectancy no cambia
(+0.109R neto maker) pero la significancia baja: **Sharpe anual ~1.3** (no 3.5), OOS t≈1.9.
(`tools/engine_edge_robust.py`)

**¿De dónde sale el edge? — descomposición (1 fila/señal):**

| | exp | PF | bootstrap IC95% |
|---|---|---|---|
| GROSS (sin costo) | **+0.195R** | 1.36 | [+0.098, +0.282], P≤0=**0.000** |
| neto MAKER (límite) | +0.109R | 1.18 | [+0.012, +0.196], P≤0=0.013 |
| neto TAKER (mercado) | −0.021R | 0.97 | — |

→ **El edge NO sale del límite: sale de la SELECCIÓN** (gross +0.195R, fuertemente
significativo). El "límite en el imán" hace dos cosas: (1) entra AL precio del imán = buena
ubicación predictiva (ya está en el gross) y (2) entra MAKER = ahorra costo. **La selección
es la fuente; el maker PRESERVA** (mantiene 56% del gross; el taker lo funde a −0.02R).

**Robustez (lo más honesto posible):**
- **Bootstrap por bloques** (robusto a correlación): neto maker IC95% **[+0.012, +0.196]** —
  sobre 0 pero piso FINO. Gross IC [+0.098,+0.282] = sólido.
- **Walk-forward 6 folds: 4/6 positivos**, pero **2 años seguidos flojos (2023-2025)** →
  edge **NO estacionario**, drawdowns de régimen multi-anuales.
- **Por símbolo: BTC lo carga** (+0.153R, IC [+0.042,+0.260]); **SOL inconcluso** (+0.050R,
  IC cruza 0).
- **Fee:** positivo hasta ~8bps, muere en taker. Breakeven ~8.5bps.

**Veredicto robusto:** edge real (la selección predice, gross sólido) pero **modesto,
BTC-dependiente, no estacionario y maker-dependiente**. Como el piso del IC es +0.01R, **la
prueba de fill maker (adverse selection) es ahora CRÍTICA**: si los fills reales se comen
0.05R, el neto desaparece. Test obligatorio antes de creerse cualquier número.

**(c) OI:** OKX rubik solo da OI a 5m de ~días / 1D de ~6 meses → sin profundidad para el
láser intradía. Requiere fuente paga (Coinglass) o colección forward.

---

## ACTUALIZACIÓN 3 — test make-or-break: fill maker / adverse selection

Simulé fills de límite pasiva contra el OHLC 5m (overlap reciente: **194 señales**,
2025-11..2026-06). `tools/maker_fill_test.py`.

- **Fill rate alto: 89-97%** (la mayoría llena; la límite descansa ~0.15 ATR en pullback).
- **Pero adverse selection SEVERA:** las que NO llenan son los **grandes ganadores**
  (+0.88 a +1.98R) — arrancan sin volver a tu límite. Las que SÍ llenan: **+0.08R**.
- **Edge realista (filled-only): ~+0.08R** vs +0.126R asumido (all-fill) = **haircut ~35%.**
- Por símbolo (W=12): SOL filled +0.104R, BTC +0.060R (ambos sobreviven, finos).

**Mecanismo:** la entrada en pullback cambia ahorro-de-fee por **runners perdidos**. Tunable
(límite más cerca = más runners, peor precio) pero NO se toca ahora (overfit sobre la misma
muestra). **Caveat:** 194 señales/6 meses → la dirección (adverse selection real) es robusta;
la magnitud (~0.05R) es incierta.

### Bottom line consolidado (toda la investigación del motor)

| capa | número |
|---|---|
| Alfa de selección (gross) | +0.195R (sólido, P≤0=0.000) |
| neto maker (all-fill) | +0.109R |
| **neto maker REALISTA (post-fill)** | **~+0.08R** |
| ejecución taker | −0.02R (muere) |

Edge **real pero frágil**: alfa genuino en la selección, neto desplegable ~+0.08R — fino,
maker-dependiente, adverse-selection-haircut, BTC-dependiente y no estacionario (2 años flojos
de 7). **Creíble, no money-printer.** La fuente del edge es la SELECCIÓN; el maker lo preserva;
el fill se lleva ~35%.

---

## ACTUALIZACIÓN 4 — arranque de la validación forward (maker, sellada)

El harness ya existe: `motor_paper.py` (RETRIEVAL_PLAN §6.10.1) — paper del MOTOR BASE,
**ejecución maker real** (penetración→fill, TTL→fallback taker), costo neto maker, **ledger
sellado SHA-256** (`DurableHashLedger`, verify()=True), wired en el loop vivo (no-op si
`FQ_MOTOR_PAPER!=1`). 20 tests verdes; smoke: maker neto > taker, cadena sellada.

**Seguridad:** `FQ_EXEC_MODE` lo lee SOLO `motor_paper` (cost taker/maker). **NO gatea live**
(eso es `exchange_adapter.mode==LIVE`, que jamás llama `create_order` en paper). Corregido el
comentario engañoso de `.env.example`. `FQ_EXEC_MODE=maker` = **0% real**.

**Arranque (env vars en Railway — no se puede desde el sandbox efímero):**

    FQ_MOTOR_PAPER=1          # track SOL (motor base, 15m)
    FQ_EXEC_MODE=maker        # ejecución + costo maker (el techo a validar)
    FQ_MOTOR_PAPER_BTC=1      # (recomendado) BTC en paralelo — carga el edge full-history
    FQ_MOTOR_PAPER_TP=tp4     # config del techo (matchea el +0.10R medido)
    FQ_MOTOR_PAPER_VETO_KILLZONES=   # sin veto de sesión = motor base puro

Ledgers durables en el Volume: `/data/motor_paper_SOL_USDT.jsonl` y `_BTC_USDT.jsonl`.

**Monitoreo:** `python tools/motor_paper_stats.py` → fill-rate real, neto maker, adverse
selection. **Éxito = neto maker forward ≈ +0.08R con fill ~90%** (confirma el backtest). Si
deriva a ~0 o el fill empeora → el backtest era optimista. Sellado = incorruptible.
