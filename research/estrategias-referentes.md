# Estrategias con edge comprobado — referentes para calibrar (research citado)

> Research multi-fuente (5 ángulos, verificación adversarial) para saber **cómo se ve
> el edge real, quién lo tiene y cuánto**, y dónde se para nuestra estrategia de imanes.
> Cada dato lleva fuente + confianza. Fecha: 2026-06.

---

## 0. Veredicto en una línea

El edge real es **chico, escaso y caro de defender**. Los que ganan lo hacen con
**win-rate ~50% + edge minúsculo a escala** (market making / stat-arb, con
infraestructura) o **trend-following con Sharpe 0.5–0.8 y sizing que sobrevive
drawdowns del 20-50%**. **Liquidation-hunting e ICT/SMC NO tienen edge probado** — son
narrativa. Nuestro 20% WR @ 2R con DD 90%+ es, matemáticamente, una estrategia perdedora
que necesita rediseño de **selectividad + sizing**, no más conceptos.

---

## 1. La escalera de Sharpe (cómo calibrar lo nuestro)

| Sharpe (neto, anualizado) | Lectura |
|---|---|
| < 1 | **Marginal — ignorar.** Los fondos quant descartan < 2 [QuantStart, alta] |
| 1–2 | **Bueno.** Target retail realista; fondo serio sostenido 1–1.5 es muy bueno |
| 2–3 | **Muy bueno** (barra institucional) |
| > 3 en estrategia diaria/retail | **Bandera roja de overfit** [QuantStart, alta] |
| Single–double digits | Territorio HFT genuino (estructural, por anualización √N) |

- Largo-only S&P ≈ Sharpe 0.4–0.5. "Si como retail lográs Sharpe > 2, te va muy bien"
  [QuantStart, alta]. — https://www.quantstart.com/articles/Sharpe-Ratio-for-Algorithmic-Trading-Performance-Measurement/

## 2. La matemática que nos condena (y la salida)

- **WR_breakeven = 1 / (1 + RR).** A 2:1 necesitás **>33.3%**; a 3:1 **25%**; a 5:1 **16.7%**
  [LuxAlgo/ComoFX, alta]. — https://www.luxalgo.com/blog/win-rate-and-riskreward-connection-explained/
- **20% WR @ 2R = −0.40R por trade** (0.20·(+2) − 0.80·(−1)). 30% @ 2R = −0.10R. **Ambos
  pierden.** [aritmética, alta] → nuestro motor está estructuralmente bajo agua.
- **La salida no es subir RR, es subir WR con selectividad** (menos trades, mejor sitio)
  o bajar a 1:1 con WR>50%. "Un 30% WR puede ganarle a un 70% según el RR" [LuxAlgo, alta].

## 3. Arquetipos con edge documentado (los referentes "buenos")

| Estrategia | Sharpe realista | Retorno | Drawdown / riesgo | WR | Fuente |
|---|---|---|---|---|---|
| **Trend-following / CTA** | ~0.5–0.8 LS | — | crashes −20 a −50%; momentum −79% (1932), −46% (2009) | **~30–40%** (paga la cola) | Daniel-Moskowitz *Momentum Crashes* [alta] |
| **Momentum cross-sectional** | 0.53 (acciones), 1.45 (multi-activo V&M) | ~8–10%/año long-only | sesgo negativo, cola izquierda gorda | baja | Asness-Moskowitz-Pedersen [alta] |
| **Mean-reversion corto plazo** | 1.1–1.5 **bruto** | ~2%/mes bruto | **costos se comen casi todo**; quant-quake Ago-2007 −18% a −31%/día | **~60–70%** pero sesgo negativo | Avellaneda-Lee; Khandani-Lo [alta] |
| **Stat-arb / pairs** | ~0.6–1.5 | ~11% exceso (GGR) | crowding desde ~2002 | — | Gatev-Goetzmann-Rouwenhorst [alta] |
| **Market making** | 3–6 (¡con infra!) | — | adverse selection = el asesino | ~50% alto | Avellaneda-Stoikov [alta] |

- **Decay post-publicación: −26% out-of-sample, −58% post-publicación** (McLean-Pontiff,
  97 factores) [alta]. → restar eso a cualquier backtest. — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623

## 4. Cripto perps — qué paga de verdad (y qué no)

- **Funding-rate / basis carry = el ÚNICO edge cripto con evidencia decente.**
  Delta-neutral (long spot / short perp). Vendor cita ~8–20% APY pero **se comprime al
  crowdearse** (CME basis 25%→<10%; un "carry Sharpe 6.45" se vuelve negativo cuando se
  llena). No es arbitraje sin riesgo — es una **prima de riesgo** con riesgo de
  contraparte/freeze. [media] — https://www.okx.com/en-us/learn/funding-rates-perpetual-futures-strategies
- **Market making en cripto SIN co-location/rebates = Sharpe NEGATIVO.** Backtest A-S
  sobre BTC: **Sharpe −0.24**; microestructura naïve neta **−11 a −52** (gross positivo,
  costos lo matan). El maker rebate (OKX top VIP −0.005%) es **precondición, no bonus**.
  [PLOS ONE 2022 / Frontiers 2026, alta] — https://pmc.ncbi.nlm.nih.gov/articles/PMC9767337/
- **Liquidation-hunting = NARRATIVA, no edge.** El único test riguroso: headline
  +2.33%/trade Sharpe 3.58 → **alpha +0.98% p=0.182 (no significativo); con control de
  volatilidad −0.74%**. Es **beta apalancada** (R²=0.54 con BTC), no alpha. Solo gana
  "cuando BTC se recupera". [verificado, alta] — https://medium.com/@tigroblanc/chasing-liquidation-cascade-alpha-in-crypto-how-to-get-299-return-with-sharpe-3-58-322ef625a8d1
  - Peor: data de liquidaciones de OKX/Binance está **throttled/incompleta** (~1/seg)
    [K33/NewsBTC, alta]; en el crash Oct-2025 los **market makers profesionales fueron
    arrasados por ADL** — el lado "fade the cascade" perdió [BitMEX Research, alta].
- **Arbitraje cross-exchange/triangular = competido a ~0.** 96–97% de oportunidades
  no rentables tras fees; hay que ejecutar en **<146 ms**; los spreads gordos (Kimchi
  ~40%) eran artefactos de control de capital, no repetibles [Muck et al. 2025; Makarov-
  Schoar, alta] — https://fis.uni-bamberg.de/bitstreams/8b9ae900-017a-4bed-94b9-609c16e89945/download

## 5. La competencia (los referentes "elite")

- **Medallion (RenTech): ~39% neto / ~66% bruto anual (1988–2018), Sharpe >2, 31 años
  sin pérdida** — ganando **~50.75% de las veces** (anécdota, media) con **150k–300k
  trades/día**, holding ~2 días. Capado a ~$10B (devuelve capital). [Cornell Capital, alta;
  WR anécdota media] — https://www.cornell-capital.com/blog/2020/02/medallion-fund-the-ultimate-counterexample.html
- **Virtu (HFT MM): 1 día perdedor en 1.238 días** (S-1 2014). Edge = fracción de centavo
  × volumen × rebates. [alta] — https://en.wikipedia.org/wiki/Virtu_Financial
- **Citadel Securities** ~35% del flujo retail US, $9.7B ingresos 2024; **Jane Street
  $20.5B ingresos 2024.** Todo **market making / arb**, no dirección. [alta]
- **Cripto MMs (Wintermute ~$5–15B/día, GSR, Cumberland, B2C2, Jump Crypto):** market
  making + OTC + arb; oligopolio (top-8 exchanges ~92% de la profundidad). Edge capturado
  por incumbentes con latencia + fee tier. [Kaiko, alta]

## 6. Order-flow / liquidez / ICT — el veredicto honesto

**Mecanismo real (úsalo):**
- **Stops se acumulan en números redondos y en máximos/mínimos previos** (take-profits
  *en* el número, stops *justo pasando*) — esto **es** el sustrato real de "liquidity
  grab" [Osler, FRBNY, alta]. — https://papers.ssrn.com/sol3/papers.cfm?abstract_id=888805
- **Cascadas de liquidación son reales** (amplificación por flujo forzado).
- **Order-flow imbalance** explica ~40–85% del retorno **contemporáneo**... pero su poder
  **predictivo** es R² ~3%, accuracy ~53%, Sharpe ~0.12 → **"los costos te comen vivo"**
  a latencia retail. Sirve para ejecución/timing, **no como generador de señal** [alta].

**Narrativa sin evidencia (no te apoyes acá):**
- **VWAP está probado como benchmark de EJECUCIÓN, no como señal predictiva** [Boyd, alta].
- **Soporte/resistencia: poder real pero DÉBIL y decae** (~5 días), y — clave — **"no hay
  poder en el acuerdo"**: niveles donde varios coinciden **NO** son más fuertes
  [Osler, alta]. → *Esto explica por qué nuestro v4 multi-TF no mejoró.*
- **ICT/SMC: cero evidencia out-of-sample de que supere al TA genérico**; es
  **infalsificable** (inputs discrecionales) y sus "ganadores" son la cola de
  supervivencia de un proceso de **edge cero** (Monte Carlo) [algostorm/Sentient, alta].

## 7. Por qué fallan las sistemáticas retail (la trampa que debemos evitar)

- **Overfitting de backtest = causa #1.** Con 5 años de data, **~45 configuraciones
  bastan para "garantizar" un Sharpe ~1 in-sample con expectativa OOS = 0**; "3 trials
  bastan para una estrategia probablemente falsa" [Bailey-López de Prado, alta]. — https://www.ams.org/notices/201405/rnoti-p458.pdf
- **65–82% de los factores publicados no pasan** corrección por multiple-testing; nuevo
  factor debería exigir **t>3.0**, no 2.0 [Harvey-Liu-Zhu, alta].
- **ETFs: ~5%/año en backtest → ~0% en vivo** [Bailey-LdP, alta].
- **Costos + slippage recortan >50%** y vuelven ganadores en perdedores.
- **Mínimo ~200–500 trades en MÚLTIPLES regímenes** para confianza; "500 trades en 6
  meses (un régimen) valen menos que 100 en 5 años (varios)" [alta].
- **Detector práctico de overfit:** si OOS Sharpe cae >40% o el DD ~se duplica vs IS →
  overfit. **Usar Deflated Sharpe (reportar N de trials).**

## 8. Dónde estamos nosotros (el espejo honesto)

| Métrica nuestra (6 meses, OKX 5m real) | Lectura vs referentes |
|---|---|
| Expectancy +0.02 a +0.07R/trade | marginal; consistente con "edge chico" |
| WR ~18–22% @ 2R | **bajo el breakeven (33%)** → estructuralmente perdedor |
| **DD 90–98%** | **inutilizable** (referentes sobreviven con 20–50% vía sizing) |
| IS vs OOS: 2/8 robustos (BTC, XRP) | mayormente régimen reciente |
| Señal de liquidaciones | = **beta, no alpha** (confirmado por la literatura) |
| Confluencia multi-TF (v4) | "no power in agreement" → por eso no ayudó |

**Conclusión:** nuestro backtest honesto **reproduce exactamente lo que la academia
predice** para una directional-momentum retail sin selectividad ni sizing: edge marginal,
DD catastrófico. No es fracaso — es **diagnóstico correcto**. El problema no es la tesis
de liquidez (el mecanismo es real); es que **(a) tradeamos demasiado, (b) el sizing
permite ruina, (c) la señal de liquidaciones es beta**.

## 9. Las 3 rutas reales para ganar (a decidir)

1. **Funding/basis carry (delta-neutral)** — el único edge cripto con evidencia. Menos
   sexy, real, sobrevivible; se comprime pero no te liquida. Construible sin latencia HFT.
2. **Directional honesto estilo trend-following** — aceptar techo Sharpe ~0.5–0.8 y WR
   ~35%, y poner TODO el esfuerzo en **sizing (risk-of-ruin)** + selectividad extrema
   (que el bot calle) + validación con Deflated Sharpe / walk-forward / 200+ trades.
3. **Market making** — requiere infra (latencia, rebates VIP) que probablemente no
   tenemos; los backtests académicos dan negativo sin eso. Improbable para nosotros.

> Lo que NO es ruta: seguir agregando conceptos ICT/liquidaciones esperando alpha
> direccional — la evidencia dice que ahí no hay edge, hay narrativa.

## Fuentes (principales)
- QuantStart — Sharpe benchmarks: https://www.quantstart.com/articles/Sharpe-Ratio-for-Algorithmic-Trading-Performance-Measurement/
- Bailey/López de Prado — Pseudo-Mathematics (overfit): https://www.ams.org/notices/201405/rnoti-p458.pdf
- Harvey-Liu-Zhu — …Cross-Section of Expected Returns (t>3): https://people.duke.edu/~charvey/Research/Published_Papers/P118_and_the_cross.PDF
- McLean-Pontiff — decay 26/58%: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2156623
- Daniel-Moskowitz — Momentum Crashes: https://www.stern.nyu.edu/sites/default/files/assets/documents/con_038332.pdf
- Asness-Moskowitz-Pedersen — Value & Momentum Everywhere: https://pages.stern.nyu.edu/~lpederse/papers/ValMomEverywhere.pdf
- Gatev-Goetzmann-Rouwenhorst — Pairs Trading: https://www.nber.org/papers/w7032
- Avellaneda-Lee — Stat-arb: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1153505
- Khandani-Lo — What Happened to the Quants (Aug 2007): https://web.mit.edu/Alo/www/Papers/august07.pdf
- PLOS ONE 2022 — RL + Avellaneda-Stoikov sobre BTC (Sharpe negativo): https://pmc.ncbi.nlm.nih.gov/articles/PMC9767337/
- Tigro Blanc — liquidation cascade alpha = beta (verificado): https://medium.com/@tigroblanc/chasing-liquidation-cascade-alpha-in-crypto-how-to-get-299-return-with-sharpe-3-58-322ef625a8d1
- BitMEX Research — State of Crypto Perps 2025 (MMs arrasados por ADL): https://www.bitmex.com/blog/state-of-crypto-perps-2025
- Muck-Schmidl-Wolf 2025 — Triangular arb no explotable: https://fis.uni-bamberg.de/bitstreams/8b9ae900-017a-4bed-94b9-609c16e89945/download
- Makarov-Schoar — Kimchi premium / arbitraje cripto: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3171204
- Osler — Support for Resistance (stop clustering, "no power in agreement"): https://papers.ssrn.com/sol3/papers.cfm?abstract_id=888805
- Cont-Kukanov-Stoikov — Order-flow imbalance: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1712822
- Cornell Capital — Medallion: https://www.cornell-capital.com/blog/2020/02/medallion-fund-the-ultimate-counterexample.html
- algostorm — ICT/SMC sin evidencia: https://algostorm.com/ict-smc-realistic-overview/
