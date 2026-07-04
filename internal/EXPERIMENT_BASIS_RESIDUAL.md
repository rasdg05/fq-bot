# Experimento measure-first: basis-residual como gemelo del funding (XAU/NQ)

> ¿Transfiere el edge de funding a oro y NASDAQ? No literal (CME = dated, sin funding).
> El análogo es el **residual de la basis**. Este es el protocolo para medirlo por el
> MISMO gate (DSR>0.95 + CPCV + PBO) antes de que toque un dólar. Feature ya codificada y
> testeada en `tools/basis_residual.py`; falta el harness de datos (Databento).

## 1. Hipótesis

La funding de un perp ≈ la basis anualizada del dated equivalente. El edge de funding
(percentil direccional 90d) debería tener gemelo en la basis:

- **residual = basis_obs − carry_teórico** = `ln(F/S)/τ − (r − q)`.
- residual ALTO (futuro rico vs carry) → longs pagando premium → crowded longs → **SHORT**.
- residual BAJO/negativo (futuro barato) → shorts crowded → **LONG**.
- Umbrales de partida = los del funding: `pctl ≤ 0.5 → LONG`, `pctl ≥ 0.7 → SHORT`.

**Caveat honesto (por qué el prior es MEDIO-BAJO):** la basis de oro/NQ está arbitrada
tensa contra `r − q` → casi determinística, dominada por tasas, NO por crowding. El
raw-basis casi seguro NO informa. Toda la apuesta está en que el **residual** (lo que
sobra tras quitar el carry) cargue posicionamiento. Y el signo podría **invertirse** — el
gate lo decide, no la narrativa. Más probable que aterrice como feature de régimen/contexto
que como edge direccional standalone.

## 2. Qué computar por barra (CAUSAL, sin fuga)

Por cada evento/entrada del cubo TradFi (mismo sampling que la cosecha 5y×5símbolos):
1. `residual = basis_residual(front, spot, r, q, τ)` — `tools/basis_residual.py`.
2. `signal = rolling_signal(residuals, i, n_hist=300)` — percentil del residual[i] contra
   SOLO la ventana previa (idéntico a `funding_pctl_live`). +1 long / −1 short / 0 neutro.
3. Guardar junto a `pnl_r`, `ts`, e `irrev` (KL) para la ortogonalidad.

`τ` = años a vencimiento del front (recalcular por barra; en rolls, saltar el día de roll o
usar continuo ajustado por back-adjust). `q` = dividend yield (NQ) o convenience/lease yield
(oro). Aproximación válida measure-first: `q≈0` para NQ intradía y refinar si el residual
sobrevive; para oro, lease rate ≈ 0 casi siempre.

## 3. Datos (qué jalar)

| Serie | Fuente | Nota |
|-------|--------|------|
| Front-month F (MNQ, MGC) | **Databento GLBX.MDP3** (OHLCV-1m o trades) | $0.50/GB, $125 crédito |
| Spot/near S | Databento (cash index / near contract) o **Dukascopy gratis** (XAU spot, NDX) | para la basis |
| Curva (2 meses) | Databento — front + next para el calendar spread | alternativa a spot |
| r (tasa libre de riesgo) | SOFR / T-bill (FRED, gratis) | anualizada |
| q (yield) | dividend yield NDX (gratis) / lease oro (≈0) | refinamiento |

Barato: la basis se puede armar con **Dukascopy gratis** (XAU spot + índice) contra el
front de Databento. El order-flow necesita el libro (Databento); la basis NO — sólo precios.

## 4. Cómo se gatea (mirror de `gate_poc_distance.py`)

`tools/gate_basis_residual.py` (siguiente paso) debe clonar la estructura del gate POC:
- **Barrido direccional**: en vez de tiers de magnitud, barrer `(long_pctl, short_pctl)` y
  mapear `signal` → tomar/saltar la entrada (o invertir). Sharpe de cada config.
- **DSR** `deflated_from_trials(R[signal], all_sh)` — deflactado por n_configs barridas.
- **Ortogonalidad vs KL**: ¿suma DENTRO de irrev-bajo o es redundante con el filtro ya
  validado? `uplift (KL-bajo & signal) − (KL-bajo) > 0.02`.
- **CPCV**: mejor config IS → uplift OOS en el test purgado (`cpcv_paths(n_groups=6,…)`).
- **PBO**: matriz (tiempo × config) → `pbo(M) < 0.5`.
- **Pooled cross-símbolo** (MNQ+MGC; y contra ES para el lead-lag) + consistencia por símbolo.

**Barras de PASA:** `DSR ✓ (>0.95) · ortho-KL ✓ (>0.02) · OOS ✓ (mediana>0, %paths≥60%) · PBO ✓ (<0.5)`.
Si pasa → dormido → forward en micros → producto. Si NO → queda medido y muerto (como POC 0.76).

## 5. Estado

- ✅ Feature pura + tests: `tools/basis_residual.py`, `tests/test_basis_residual.py` (7 verdes).
  Semántica de percentil y umbrales IDÉNTICOS al funding del bot.
- ⏳ Harness de datos: cargar F/S/r/q del cubo TradFi + Databento → correr `gate()`.
- ⏳ Decisión: gate. Nada opera antes.

*Riesgo de quant-envy a vigilar: si el residual sólo “funciona” en un régimen de tasas
concreto (2y de historia con una curva), es overfitting a la macro, no edge — por eso el
PBO y el CPCV multi-régimen son innegociables aquí.*
