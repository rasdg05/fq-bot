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

## v3 — SACÁNDOLE FILO (RasDG: "es el motor base, agrega todo lo demás y pule el edge")

Aplicado el arsenal validado en cripto al motor base, pre-registrado (3 exits × 2 entradas):

| entrada | exit | Sharpe-anual (maker) | maxDD | WR |
|---|---|---|---|---|
| open | 3R fija (=base) | 1.35 | 19.3R | 38% |
| open | parcial+BE | 1.18 | 22.9R | 54% |
| open | trailing | 0.89 | 21.5R | 38% |
| breakout | 3R fija | 1.55 | 30.1R | 41% |
| **breakout | parcial+BE** | **1.66** | **17.7R** | **57%** |
| breakout | trailing | 0.98 | 20.8R | 40% |

**Ganador: opening-range breakout + parcial+BE.** Sharpe 1.35→1.66 (maker), drawdown BAJA
(19.3→17.7R), WR 38→57%. Gate taker: DSR 0.994, CPCV 100%, Sharpe 1.42. Hallazgos medidos:
- **El breakout** (esperar que rompa el rango de apertura) filtra los días que se desinflan
  — menos trades (1807 vs 2343), mejores.
- **El parcial+BE** (la "gestión del fantasma" de cripto) sube WR y BAJA drawdown.
- **El trailing HIERE** (0.9) — se sacude en momentum intradía. Bueno saberlo, medido.
- **Las capas INTERACTÚAN**: parcial+BE solo, sobre la entrada cruda, EMPEORA (1.18); sobre el
  breakout, es lo mejor (1.66). Juntas valen más que la suma.

## HOLDOUT OOS — el juez más honesto sin feed en vivo

Config elegida en 2017-2023, aplicada INTACTA a 2024-2026 (taker, el costo duro):

| | Sharpe-anual | avgR | n |
|---|---|---|---|
| TRAIN 2017-2023 | 1.57 | +0.111 | 1291 |
| **TEST 2024-2026 (OOS)** | **1.04** | +0.071 | 516 |

**El edge SOBREVIVE fuera de muestra pero DEGRADA ~36%** (ratio OOS/IS 0.64, justo sobre el
umbral). Por año OOS: 2024 +0.198 (fuerte), 2025 −0.028 (plano — bandera amarilla), 2026 +0.012.

**La verdad honesta para decidir: no es el 1.66 del titular — es ~1.0 Sharpe OOS.** Real,
tradeable, degrada como se espera de una selección de config, con 2025 flojo a vigilar. Sigue
siendo el edge más fuerte del proyecto fuera de cripto, y sobrevive el costo taker. Pero el juez
DEFINITIVO es el forward en vivo — el holdout confirma que NO es puro overfit, no que sea bala de
plata.

## Forward paper — qué falta (honesto)
El bot en vivo corre sobre OKX (cripto). NQ es futuro CME → necesita un **feed en vivo de NQ**
(Databento live streaming, o broker paper tipo Tradovate/IBKR). Eso es ingeniería con dependencia
de data en vivo, no un flip de esta noche. Hecho ya: la validación OOS más fuerte posible sin feed
(holdout 2024-2026). Próximo: montar el feed + runtime paper (la infra motor_paper/gold_paper es
reusable) para que el fantasma del NASDAQ respire OOS en tiempo real.

## Reproducibilidad
`/tmp/cme/nq_momentum.py` (base), `/tmp/cme/nq_sharpen.py` (v3 filo + holdout). Data
`data/cme/NQ-USDT_5m.parquet` (NQ.v.0). Resultados `/tmp/cme/nq_sharpen_best.parquet`.
Gate: DSR (n_trials 6-100) + CPCV 15 + PBO + holdout temporal, taker+maker.
