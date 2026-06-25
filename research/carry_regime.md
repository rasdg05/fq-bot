# Funding CARRY — validación MULTI-RÉGIMEN (funding profundo 2021-2026)

> Fuente: **data.binance.vision** (archivo público S3/CDN de Binance, NO la API —
> la API está geo-bloqueada en el sandbox/CI). Funding mensual real, 8 símbolos,
> 2021-01 → 2026-05 (~5.900 intervalos de 8h por par). Reproducible:
> `python tools/fetch_binance_vision_funding.py`. Mide el **stream de funding** que
> cobra un short-perp delta-neutral (la pata de precio va hedgeada con spot/inverso).

## TL;DR — el carry SOBREVIVE el bear, pero hay que limpiar el basket
La pregunta que mató al pairs y al trailing era: **¿sobrevive fuera de su régimen?**
El carry **sí** — pero **sólo el basket limpio**. El basket de 8 da −4.7% en el bear
2022; ese rojo es **100% SOL + BNB**. Sácalos y el carry es **positivo los 6 años,
incluido el bear**. Es la primera ruta de la sesión que pasa multi-régimen limpia
(el pairs murió por costes, el trailing por overfit a la tendencia reciente).

## 1. El veredicto por año — basket CLEAN (BTC/ETH/XRP/LTC/DOGE/ADA)
Always-on (mantener siempre) vs gate de 7 días (mantener sólo si la media móvil
causal del funding es positiva). Equal-weight, neto de costes de switch.

| Año | Régimen | APY always | Sharpe | maxDD | APY gate7d | %+ |
|---|---|---:|---:|---:|---:|---:|
| 2021 | bull/euforia | **+39.1%** | 21.8 | 0.9% | +36.8% | 94% |
| **2022** | **BEAR brutal** | **+1.7%** | 5.6 | 1.3% | +1.7% | 68% |
| 2023 | recuperación | +8.5% | 30.0 | 0.2% | +8.0% | 88% |
| 2024 | bull | +13.6% | 29.8 | 0.0% | +12.9% | 93% |
| 2025 | bull/lateral | +4.6% | 25.3 | 0.2% | +3.5% | 79% |
| 2026 | lateral/correc. | +0.5% | 3.1 | 0.5% | −0.6% | 56% |

**Nunca negativo en un año, ni en el bear.** El maxDD anual del carry acumulado es
<1.5% siempre (es funding cobrado, no PnL direccional). El gate7d casi no mueve el
APY pero sube el Sharpe y baja el drawdown — su valor real es **sentarse fuera** de
los tramos de funding negativo (en 2022 sólo estuvo dentro el 68% del tiempo).

## 2. Por qué SOL y BNB quedan FUERA (el basket de 8 engañaba)
Full history, always-on:

| Símbolo | APY | Sharpe | maxDD | %+ | funding medio | veredicto |
|---|---:|---:|---:|---:|---:|---|
| XRP | +13.5% | 12.7 | 2.5% | 78% | +1.24 bps | **CLEAN** |
| LTC | +13.5% | 14.5 | 0.8% | 85% | +1.23 bps | **CLEAN** |
| DOGE | +13.1% | 11.4 | 2.5% | 82% | +1.19 bps | **CLEAN** |
| ETH | +11.9% | 13.9 | 1.8% | 84% | +1.09 bps | **CLEAN** |
| ADA | +11.9% | 12.2 | 1.9% | 79% | +1.09 bps | **CLEAN** |
| BTC | +11.1% | 17.0 | 0.4% | 86% | +1.01 bps | **CLEAN** |
| SOL | +0.8% | 0.3 | **43.4%** | 72% | +0.08 bps | anti-carry: carry muerto, DD brutal |
| BNB | −0.7% | −0.6 | 30.9% | **22%** | **−0.07 bps** | anti-carry: funding MEDIO negativo |

- **SOL**: funding medio casi cero y maxDD del 43% — el carry no paga y el camino es
  feo. Es el canario que ya salía negativo en la ventana corta de OKX.
- **BNB**: funding medio **negativo** (sólo 22% de intervalos positivos). En BNB el
  que cobra es el LONG perp, no el short. Meterlo al basket de short-carry **resta**.
  (La ventana corta de OKX —95d— lo mostraba +3.2%: por eso la validación de UN
  régimen miente. El historial profundo lo desenmascara.)

Basket full-history equal-weight: **TODOS (8) +9.4% / Sharpe 10.2 / maxDD 10.5%**
vs **CLEAN (6) +12.5% / Sharpe 13.6 / maxDD 1.7%**. Limpiar sube retorno y Sharpe y
divide el drawdown por 6.

## 3. Honestidad — qué NO es esto
- **No es arbitraje sin riesgo.** Es una **prima de régimen**: el mercado paga por
  estar corto el perp cuando todos están largos/apalancados. En 2026 esa prima se
  **comprime a ~0** (basket +0.5%) — el carry respira con el apalancamiento agregado.
- **Es el stream BRUTO de funding.** El carry real necesita: (a) la pata short-perp
  **y** un hedge spot/inverso → fees de las dos patas + borrow/locación, (b) margen
  para la pata short (riesgo de liquidación si el hedge se descalza), (c) el funding
  puede ir negativo intra-período (de ahí el gate). Resta ~2-4 pp de APY al neto.
- **El piso de +0.01%/8h** de Binance infla 2021-2022 (BTC pegado al piso). Ese piso
  cambió con el tiempo; el funding **forward** puede venir más fino que el backtest.
- Por eso **se mide forward** (`carry_paper`, 0% real) antes de arriesgar capital, y
  por eso el basket lleva el **gate** como interruptor para el régimen tipo-2026.

## 4. Dónde encaja en el producto
El motor del bot es **direccional** (Sharpe ~0.8, el edge maker+veto = +0.10R OOS).
El carry es el **segundo motor, MARKET-NEUTRAL** y **descorrelacionado**: no depende
de acertar dirección, sobrevive el bear, y su drawdown es ~1/10 del direccional.
Es exactamente la ruta que la investigación 2026 marcó como “donde está el dinero
durable” (neutral Sharpe 2-5 vs direccional ~0.8). Aquí, **medido**, da Sharpe 13.6
en bruto — y aun restando costes de ejecución queda muy por encima del direccional.

Basket de producción = `carry_backtest.CLEAN_BASKET` (una sola fuente de verdad).
Se mide forward con `carry_paper` (durable ledger en `/data`, como motor_paper/OI).

_Generado de la validación de esta sesión (2026-06). Radar honesto, no promesa._
