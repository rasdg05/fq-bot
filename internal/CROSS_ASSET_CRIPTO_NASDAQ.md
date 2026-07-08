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

## 🔥 La otra mitad (NASDAQ → cripto) — LA QUE MUEVE LA AGUJA (toca el producto vivo)

Priorizado por impacto: esto filtra las señales de reversión cripto que YA van a VIP. Para cada
señal VIP (KL-bajo, majors, 2021-2026, n=1681 con NQ disponible), se mide el move de NASDAQ (NQ,
casi 24h) en las 6h PREVIAS (causal) y se ve si la dirección de la señal cripto se alinea:

| señal cripto VIP filtrada por NASDAQ | n | avgR | Sharpe/trade |
|---|---|---|---|
| todas (baseline) | 1681 | +0.305 | 0.136 |
| **ALINEADA con NASDAQ** | 874 | **+0.431** | **0.182** |
| CONTRA NASDAQ | 807 | +0.169 | 0.081 |

Por lado (limpio en ambos):
- LONG cripto + NASDAQ↑: +0.380 · LONG + NASDAQ↓: +0.229
- SHORT cripto + NASDAQ↓: **+0.485** · SHORT + NASDAQ↑ (contra): +0.132

**El avgR MÁS QUE DUPLICA cuando la señal cripto se alinea con el estado de riesgo de NASDAQ**
(+0.431 vs +0.169). Bidireccional. Es el filtro de contexto cross-asset del dueño, aplicado al
motor cripto EN VIVO — no un motor nuevo, una capa de convicción sobre lo que ya paga.

### Por qué esta mueve más la aguja
- Toca el producto **desplegado** (señales VIP reales) → valor inmediato, sin feed de trading NQ.
- Solo necesita la **DIRECCIÓN** de NASDAQ (un proxy delayed/gratis basta — QQQ/NQ retardado),
  mucho más barato que un feed tick para ejecutar. Wireable de verdad.
- Aplicación: convicción/sizing — anti-alineadas siguen siendo +0.169 (no se descartan, se bajan);
  alineadas se refuerzan. `FQ_CROSS_ASSET` default OFF, medir forward.

### Caveats honestos
- Muestra 2021-2026 = **era de correlación cripto-equities** (post-2020). Si se descorrelacionan,
  el filtro se debilita — es régimen-dependiente de la correlación, a vigilar.
- 586 señales sin NQ (fines de semana, NQ cerrado) — esas no usan el filtro (default: neutral).
- Es capa de convicción, no señal nueva. El edge base (reversión) es el mismo.

## Veredicto de la ronda cross-asset
La intuición del dueño era correcta en su FORMA CORRECTA: no se porta la señal (opuesta entre
mercados), se porta el CONTEXTO de correlación. Y paga en AMBAS direcciones — confirma los longs de
NASDAQ (2.18 vs 1.04) Y las señales de reversión cripto (+0.431 vs +0.169). La segunda es la que
mueve la aguja porque toca el motor vivo. Candidato #1 a cablear (default OFF + forward).

## Reproducibilidad
NASDAQ←cripto: NASDAQ longs × BTC pre-open 6h. NASDAQ→cripto: señales VIP (ghost_tagged, KL≤0.40) ×
NQ move 6h previo. Data `data/cme/NQ-USDT_5m.parquet`, `data/kl_hist_BTCUSDT.parquet`,
`/tmp/ghost_tagged.parquet`. Alineados por timestamp, causal.
