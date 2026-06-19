# Backtest multi-simbolo — Motor de Imanes [v3 (macro + entrar en valor)]

OKX 5m, ~12000 velas/par, paso 1, min_rr=2.00, trades NO solapados, etiquetado pesimista (empate TP/SL -> SL), costes via bt_engine.

**Robustez:** IS = expectancy 1a mitad (in-sample), OOS = 2a mitad (out-of-sample). OK = positivo en AMBAS (el edge persiste, no es una racha de un solo regimen). Muestra corta (~6 semanas): tomar como senal, no como verdad final.

| Par | dias | trades | WR | exp (R) | IS | OOS | robusto | total (R) | maxDD |
|---|---:|---:|---:|---:|---:|---:|:--:|---:|---:|
| BTC-USDT-SWAP | 42 | 130 | 23% | +0.327 | +0.158 | +0.381 | OK | +42.5 | 41% |
| SOL-USDT-SWAP | 42 | 119 | 24% | +0.310 | -0.250 | +1.246 | — | +36.9 | 39% |
| ETH-USDT-SWAP | 42 | 86 | 17% | +0.201 | -0.172 | +0.412 | — | +17.3 | 38% |
| ADA-USDT-SWAP | 42 | 127 | 22% | +0.131 | -0.312 | +0.474 | — | +16.7 | 40% |
| XRP-USDT-SWAP | 42 | 119 | 22% | +0.103 | -0.170 | +0.655 | — | +12.3 | 41% |
| BNB-USDT-SWAP | 42 | 142 | 20% | +0.022 | -0.185 | +0.476 | — | +3.1 | 59% |
| DOGE-USDT-SWAP | 42 | 152 | 19% | -0.007 | +0.044 | +0.286 | OK | -1.1 | 45% |
| LTC-USDT-SWAP | 42 | 158 | 16% | -0.101 | -0.434 | +0.309 | — | -16.0 | 67% |

**Resumen:** 6/8 pares positivos; 2/8 ROBUSTOS (IS y OOS +). Mejores: BTC, DOGE.

