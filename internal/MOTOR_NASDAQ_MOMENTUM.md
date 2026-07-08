# MOTOR NASDAQ (NQ) — momentum intradía: PASA EL GATE 🚀

> RasDG 2026-07-08, 2AM. Tras el motor de oro (pulso real pero marginal), llevamos el MISMO
> motor de continuación a NASDAQ, donde la research predijo TSM más fuerte (índices > oro > BTC).
> **Resultado: PASA el gate honesto, y lo aplasta — el primer motor de un mercado nuevo que
> cruza la barra en todo el proyecto.** Data NQ.v.0 comprada ($11.67, 3.2M barras 1m → 640k 5m).

## Señal (idéntica a la del oro, adaptada a sesión RTH de índices)
- Sesión RTH 09:30-16:00 ET. Opening move 09:30-10:30 ET define dirección; entrada 10:30 ET;
  salida 15:45 ET; barrera 3R / 1.5×ATR. Régimen KL-irreversibilidad (mismo detector).

## Validación measure-first (todo pre-registrado, causal, triple-barrier)

**Claim confirmado (más fuerte que oro):** regresión rest~first-move: **corr +0.053** (oro +0.040,
research: índices > oro). El movimiento de apertura predice el resto de la sesión, con más señal.

**Tradeable, y sobrevive el costo MÁS DURO (taker):**

| ejecución | avgR | SR/trade | Sharpe anual | totR 9yr |
|---|---|---|---|---|
| bruto | +0.137 | 0.090 | ~1.45 | +321 |
| **MAKER** (~$4 rt) | +0.130 | 0.085 | **~1.38** | +305 |
| **TAKER** (~$14 rt) | +0.113 | 0.074 | **~1.20** | +265 |

**Gate honesto — pasa robusto (taker, el más duro):**
- **DSR** deflactado: 0.998 (n_trials=6) … **0.980 (n_trials=100)** — aguanta deflación brutal.
- **PBO = 0.000** (cero overfitting).
- **CPCV**: 100% de 15 caminos positivos, peor camino +0.065.
- **Estabilidad**: 8/10 años positivos (oro 6/10), negativos chicos (2017 −0.20, 2020 −0.005),
  positivos consistentes (2021 +0.18, 2023 +0.27, 2024 +0.25).

vs oro (momentum): SR 0.013, anual ~0.2, DSR 0.00 → NQ es **~6× más fuerte per-trade** y estable.

## Por qué NQ pasa y el oro no (mecanismo, no suerte)
La research lo predijo y lo confirmamos: los índices son estructuralmente más tendenciales que el
oro (menos mean-reversion de commodity, más flujo direccional de riesgo). El MISMO motor de
continuación, misma disciplina, distinto mercado → el edge que en oro era marginal, en NASDAQ
cruza la barra. **Valida la tesis del método reciclable: no construimos un bot de oro, construimos
un MOTOR DE CONTINUACIÓN que se porta entre mercados.**

## Caveats honestos (medida o muerte, también en la victoria)
- Es un **gate in-sample** (DSR/CPCV/PBO sobre histórico). El juez final es el forward en paper,
  como todo — próximo paso obligatorio antes de un centavo real.
- El efecto opening→sesión es conocido (no novel) → menos riesgo de overfit, pero potencialmente
  más concurrido. La ventaja no es el descubrimiento, es la ejecución disciplinada + el reciclaje.
- Cadencia ~1 trade/día (2343 en 9 años) — manejable, maker-viable, liquidez sobra en NQ.

## Roadmap
1. **Forward paper NQ** (FQ_MOTOR_PAPER-style, 0% real) — validar OOS antes de cablear.
2. Refinar (con disciplina de trials): el gate KL-alto concentró menos que base aquí — investigar
   por qué (índices trending casi siempre); timing fino intradía; opening-range breakout.
3. **Reciclar a cripto**: motor de continuación (KL-alto) como complemento de las sequías VIP.
4. MNQ (micro) para footprint de capital chico en ejecución real.

## Reproducibilidad
`/tmp/cme/nq_momentum.py` · data `data/cme/NQ-USDT_5m.parquet` (NQ.v.0 full-density) ·
resultados `/tmp/cme/nq_momentum.parquet`. Gate: DSR (n_trials 6-100) + CPCV 15 + PBO, taker+maker.
