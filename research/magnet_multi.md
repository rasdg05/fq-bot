# Backtest multi-simbolo — Motor de Imanes (v1)

OKX 5m, ~12000 velas/par, paso 1, min_rr=1.50, trades NO solapados, etiquetado pesimista (empate TP/SL -> SL), costes via bt_engine.

> v1 honesto: el stop ('apenas pasado el iman opuesto cercano') es demasiado ajustado. Esta tabla es la LINEA BASE para iterar.

| Par | dias | trades | WR | exp (R) | total (R) | maxDD | mejor modo |
|---|---:|---:|---:|---:|---:|---:|---|
| BNB-USDT-SWAP | 42 | 431 | 32% | +0.230 | +99.2 | 82.2% | reversal (+1.22R n15) |
| DOGE-USDT-SWAP | 42 | 598 | 28% | +0.120 | +71.5 | 90.4% | reversal (+0.26R n23) |
| ADA-USDT-SWAP | 42 | 607 | 25% | +0.017 | +10.3 | 93.9% | continuation (+0.03R n585) |
| ETH-USDT-SWAP | 42 | 466 | 26% | -0.003 | -1.2 | 92.1% | reversal (+0.51R n18) |
| XRP-USDT-SWAP | 42 | 606 | 25% | -0.047 | -28.2 | 96.6% | reversal (+0.02R n20) |
| SOL-USDT-SWAP | 42 | 573 | 22% | -0.053 | -30.4 | 95.8% | continuation (-0.04R n551) |
| LTC-USDT-SWAP | 42 | 583 | 22% | -0.102 | -59.7 | 97.5% | reversal (+0.11R n23) |
| BTC-USDT-SWAP | 42 | 389 | 23% | -0.183 | -71.3 | 94.4% | reversal (+0.29R n14) |
