# Dónde está (y dónde NO está) el edge en crypto 2026 — investigación externa

> Investigación deep-research de esta sesión (jun 2026): 5 ángulos, 22 fuentes
> primarias, 83 claims extraídos, **25 verificados adversarialmente (16 confirmados,
> 9 refutados a 2/3 votos)**. Foco: qué puede capturar de verdad un bot de señales
> chico (perps OKX/Binance, Python, capital modesto, sin colocation). Sólo se reporta
> lo que **sobrevivió** la verificación. Citas al final.

## TL;DR — la evidencia mató el build que íbamos a hacer
El plan era "rastrear smart money / copiar wallets ganadoras". **La mejor evidencia
causal dice que es la ruta más débil y más adversarial que existe.** Lo que SÍ
sobrevive es más aburrido y más útil: un **modelo de fragilidad/quiebra** cross-seccional
(barato, falsable, datos gratis) y unas **señales de flujo** débiles que **invierten** el
saber popular. Y el regalo real: la investigación nos entregó los **criterios** para
juzgar resultados — y esos criterios **validan exactamente lo que ya hacemos** (carry
multi-régimen, matar pairs/trailing, medir el fill-rate forward).

## 1. El build que querías (copiar smart money): NO, y por qué
- **La "imitation penalty" es demostrable.** En meme coins de Solana (pump.fun, ~1.000
  monedas post-$TRUMP), el mejor método de selección de wallets convirtió **+14% de
  retorno de la wallet en sólo +3% para el copista** tras fricciones; **3 de 4 modelos
  estadísticos dieron retorno NEGATIVO al copista** aun eligiendo wallets ganadoras. En
  una bonding curve se prueba como teorema: el copista **siempre sobrepaga**. El PnL de
  una wallet es un **techo** que el impacto de precio erosiona a casi nada. [1]
- **Es una superficie de ataque, no alpha gratis.** El copy-trading se modela como juego
  casi suma-cero: los KOLs/insiders cuyas wallets salen en trackers (GMGN, etc.)
  **front-runean al copista**, ocultan posición en varias wallets y fabrican volumen. Su
  ganancia *es* tu pérdida. [1]
- **El backtest canónico de Nansen es marketing-grade:** una sola cadena (Ethereum), un
  solo ciclo alcista (mar-2020→mar-2022), **in-sample**, con el mejor indicador elegido
  ex-post sobre el mismo dataset. (Ojo: la verificación **refutó** que las labels de
  Nansen sean un simple ranking por PnL, y refutó sus cifras exactas de Sharpe — no las
  repitamos.) [2]

**Veredicto:** un signal de "copiar whales" repetiría el error de pairs/trailing. No se
construye.

## 2. Lo que SÍ tiene información (pero débil, específico y al revés del lore)
- **Flujo a exchange = presión de VENTA, no compra.** Los **net-INflows de ETH a
  exchanges predicen retornos NEGATIVOS** de ETH intradía (1–6h, 2017–2023): mandar ETH
  al exchange = intención de vender. **Invierte** el "whale accumulation = bullish". Y
  **no generaliza**: en BTC el signal no funciona (incluso cambia de signo). [3]
- **Stablecoins = pólvora seca.** Net-inflows de **USDT** predicen *levemente* subidas de
  BTC/ETH, pero sólo a 1–2h y con efecto chico (~$100M USDT ≈ +0.11% ETH / +0.065% BTC la
  hora siguiente). [3]
- **MVRV, direcciones nuevas, direcciones activas** salen como los predictores on-chain
  más influyentes en un estudio de 12 modelos ML — pero es *importancia dentro del modelo*,
  **no alpha post-costo demostrado**. [4]

**Veredicto:** sirven como **features medidas forward** (no como deploy), y sólo en el
activo donde aplican (ETH ≠ BTC). Débiles. Techo, no promesa.

## 3. El hallazgo ESTRELLA (barato, falsable, datos gratis): fragilidad/quiebra
- **El sesgo de supervivencia es brutal y hay que corregirlo:** ~**28% de las monedas
  mueren en 1 año, ~80% en 5 años** (sin actividad 26 semanas = muerta). Un backtest
  equal-weight que sólo incluye sobrevivientes **sobreestima ~62% anualizado**. [5]
- **Modelo cross-seccional barato y testeable:** monedas **más grandes, más viejas, menos
  volátiles, más líquidas y con mejor retorno reciente** quiebran menos. Market cap, edad,
  volatilidad e iliquidez son predictores significativos (AUC in-sample ~0.83 monedas). [5]
- **Hay una prima de riesgo de quiebra real:** el quintil de mayor prob. de quiebra rinde
  **4.97% de alpha CAPM vs 0.05%** del más seguro — pero **limits-to-arbitrage** (concentrada
  en small-caps volátiles, cara de capturar). [5]

**Veredicto:** esto SÍ se construye y nos sirve **ya**: (a) **higiene de universo** — antes
de sumar un símbolo al motor o al basket, filtrar los candidatos a muerte; (b) **corrección
de survivorship** en nuestros backtests. Es defensivo y real, no alpha especulativo.

## 4. Los criterios para juzgar resultados (lo que pediste: "criterio sobre resultados")
La parte más valiosa. El estándar serio, según la evidencia:
1. **La predictibilidad in-sample es ruido out-of-sample.** Predictores conocidos de BTC
   (atención, volumen, métricas on-chain) **fallan OOS**; sólo la correlación con equities
   da un R² OOS modesto (~2.7%). **Ningún** estudio peer-reviewed bate al baseline naive
   across-regímenes a 1–6 meses. [6]
2. **Techo de acierto direccional ~57%.** La significancia estadística **rara vez** da
   profit: exigir test de **rentabilidad-en-exceso tras costos**, no sólo accuracy. [6]
3. **S2F y Metcalfe están desmentidos OOS** (espurios, tendencia común). No anclar tesis ahí. [6]
4. **Corregí survivorship o sobreestimás decenas de %.** [5]
5. **Tratá todo backtest de vendor / un-régimen / in-sample como marketing.** [2][6]
6. **El overfitting de backtest es el modo de fallo #1.** [6]

## 5. Qué significa para NOSOTROS (el reframe honesto)
- **Estos criterios validan nuestro método.** Todo lo que hicimos —validar el carry
  multi-régimen, **matar** trailing/pairs, medir el **fill-rate maker forward**, reportar R
  OOS— es *exactamente* lo que la evidencia dice que hacen los serios. No estábamos
  perdiendo el tiempo; estábamos aplicando el estándar correcto.
- **Nuestro carry es MÁS riguroso que lo publicado.** La única tesis de funding-arb que
  encontró la investigación (115.9%/6m) fue **refutada como marketing**. No sobrevivió
  ninguna cifra de APY/Sharpe sostenible publicada. Nuestro +12.5% medido año-por-año
  (que descontamos honestamente por costos) es **mejor evidencia que la que circula**.
- **Adverse selection es el muro — y ya lo sabíamos.** La investigación no halló evidencia
  de que "ganar el spread" sea capturable sin colocation; el asesino es la selección
  adversa. Es el **mismo** caveat de nuestro fill-rate maker. Coherente.
- **La palanca sigue siendo la misma:** ensanchar y probar el edge que YA tenemos. Y ahora
  el modelo de fragilidad **de-riesga** ese ensanche (filtrar símbolos frágiles antes de
  sumarlos).

## 6. El build re-scopeado (lo que la evidencia respalda)
1. **`coin_fragility`** (este commit): scorer de fragilidad cross-seccional con los signos
   documentados (mcap/edad/volatilidad/iliquidez/retorno). Datos gratis (CoinGecko).
   Uso: higiene de universo para el ensanche del motor + corrección de survivorship.
   Honesto: heurística de la literatura, **no** un modelo fiteado con dataset
   survivorship-corregido (eso exige data de monedas muertas — la lección misma).
2. **Capa de flujo (futuro, medida forward):** net-inflow ETH (presión de venta) y USDT
   dry-powder como features del motor en BTC/ETH, medidas como el motor_paper — NO deploy.

## Brechas que la investigación dejó abiertas (honestidad)
- **Yield market-neutral:** sin evidencia pública sólida que sobreviva (todo marketing).
  → nuestra propia medición forward del carry es la fuente de verdad, no la web.
- **Ejecución sin colocation:** sin evidencia de break-even publicada. → lo decide nuestro
  fill-rate forward.
- **Decay/crowding:** **todo** el framework cuantitativo de alpha-decay que se buscó fue
  **refutado** (no repetir esas cifras). No hay método validado de half-life/crowding;
  se estima empíricamente con nuestra propia medición forward.

---
**Fuentes (primarias, verificadas):**
[1] arXiv 2601.08641 — *Resisting Manipulative Bots in Meme Coin Copy Trading* (ACM Web Conf 2026).
[2] Nansen Research — *Trading Crypto with Nansen Smart Money* (vendor; estructura criticada, cifras refutadas).
[3] arXiv 2411.06327 — *Return and Volatility Forecasting Using On-Chain Flows* (2017–2023).
[4] Pacific-Basin Finance Journal v96 (2026), ScienceDirect S0927538X25003701 — 12-ML on-chain factors.
[5] Ma, Tu, Zhu — *In Search of Cryptocurrency Failure* (SSRN 4164139; supervivencia + modelo + prima).
[6] arXiv 2606.00071 — survey de predictibilidad crypto OOS (Baquero, 2026).

_Radar honesto, no promesa. Sólo claims que pasaron verificación adversarial 2/3._
