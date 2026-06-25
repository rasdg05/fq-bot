# Backtest de FUNDING CARRY — OKX perps (ruta con edge comprobado)

> ⚠️ VENTANA CORTA (95d OKX, UN régimen). Para el veredicto real ver
> **`research/carry_regime.md`** (funding profundo 2021-2026, multi-régimen). OJO:
> aquí BNB sale +3.2% pero en el historial profundo es **anti-carry** (−0.7%, funding
> medio negativo). Una sola ventana engaña — por eso el basket de producción es el
> CLEAN de 6 (sin SOL ni BNB), validado año por año.

Funding real OKX (8h), ~3000 puntos/par. 'always' = short-perp delta-neutral siempre; 'selective' = solo cuando el funding previo > 0.0000%. APY neto de costes (apertura/cambios 5bps). DD = del carry acumulado.

> Honesto: el carry es una PRIMA DE RIESGO, no arbitraje sin riesgo (funding puede ir negativo en bear; hay riesgo de contraparte/liquidacion de la pata short). Pero a diferencia del direccional, no te liquida la cuenta.

| Par | dias | APY always | Sharpe | DD carry | funding medio | %+ | APY selective |
|---|---:|---:|---:|---:|---:|---:|---:|
| DOGE-USDT-SWAP | 95 | +3.7% | 20.10 | 0.1% | +0.359 bps | 73% | -13.8% |
| LTC-USDT-SWAP | 95 | +3.4% | 20.08 | 0.0% | +0.332 bps | 71% | -17.1% |
| BNB-USDT-SWAP | 95 | +3.2% | 15.21 | 0.1% | +0.311 bps | 68% | -11.7% |
| XRP-USDT-SWAP | 95 | +2.3% | 10.75 | 0.1% | +0.225 bps | 63% | -18.9% |
| ADA-USDT-SWAP | 95 | +1.8% | 5.52 | 0.3% | +0.180 bps | 66% | -16.0% |
| ETH-USDT-SWAP | 95 | +1.7% | 10.40 | 0.2% | +0.176 bps | 63% | -13.8% |
| BTC-USDT-SWAP | 95 | +1.3% | 9.64 | 0.1% | +0.137 bps | 62% | -15.5% |
| SOL-USDT-SWAP | 95 | -1.2% | -3.55 | 0.3% | -0.088 bps | 49% | -20.6% |
