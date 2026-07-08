# Cross-asset cripto ↔ NASDAQ — la correlación tech PAGA (intuición del dueño, medida)

> El dueño: "los setups se dan en ambos... por ser tech, NASDAQ encaja con cripto... ambos dan los
> mismos setups." Probé dos formas de su idea. Una falló, la otra —la de fondo— PAGA.

## Lo que NO funcionó: portar la señal por lado
La síntesis "reversión-short de cripto → shorts de NASDAQ" falla, porque **los shorts de NASDAQ
están muertos en toda forma:**

| setup × lado (NASDAQ) | Sharpe |
|---|---|
| Momentum LONG | +1.89 |
| Momentum SHORT | +0.12 |
| Reversión LONG | −0.16 |
| Reversión SHORT | **−0.68** |

NASDAQ es estructuralmente long-only (deriva al alza; fadear rallies pierde doble). No hay short
que pulir — ni con el playbook de cripto.

## Lo que SÍ funciona: la CORRELACIÓN tech como confirmación
La intuición de fondo del dueño es correcta — los dos mercados se hablan. Medido: **la dirección
de BTC en las 6h previas a la apertura de NASDAQ confirma los longs de NASDAQ.**

| NASDAQ longs, filtrado por BTC pre-open | n | Sharpe |
|---|---|---|
| todos | 591 | 1.69 |
| **BTC ↑ pre-open** | 355 | **2.18** |
| BTC ↓ pre-open | 236 | 1.04 |

Cuando cripto está bid (tech risk-on), el momentum-long de NASDAQ pega **2× más fuerte** (2.18 vs
1.04). Es un **filtro de contexto cross-asset**: no cambia la señal, la confirma con el estado del
mercado hermano. Sharpe 1.69 → 2.18 quedándose con el subset confirmado.

## El principio (refinado por esta ronda)
"Ambos dan los mismos setups" NO significa que la misma SEÑAL direccional pague en ambos (es
opuesta: cripto revierte, NASDAQ tiende). Significa que **comparten CONTEXTO de riesgo** (tech/
risk-on) — y ese contexto, medido en un mercado, confirma el edge propio del otro. La correlación
es la capa compartida; el edge sigue siendo específico de cada mercado.

## Caveats honestos
- Muestra 2021+ (kl_hist BTC empieza 2021) → ventana más corta, falta OOS más largo.
- Es un FILTRO (sube Sharpe dropeando ~40% de trades BTC↓, que igual daban +18R a Sharpe 1.04 —
  no son perdedores, son más débiles). Sube Sharpe, baja totR (+70→+52). Trade-off, no free lunch.
- corr continua ~0 (−0.012): es efecto de RÉGIMEN binario (BTC↑ vs ↓), no lineal.

## Próximo (la otra mitad de la idea del dueño, sin probar)
**NASDAQ → cripto**: ¿la sesión de NASDAQ confirma el crypto overnight? Simétrico a lo anterior;
podría afinar los longs del motor cripto EN VIVO (el bidireccional que mencionó el dueño). Vale el
test — es data en mano, feed cripto ya vivo.

## Reproducibilidad
Inline en la sesión (NASDAQ longs × BTC pre-open 6h). Data `data/cme/NQ-USDT_5m.parquet` +
`data/kl_hist_BTCUSDT.parquet`, alineados por timestamp UTC.
