# Cómo operar ORO correctamente — sesión, killzones, order-flow y gate (measure-first)

> Deep-research adversarial (48 agentes; búsqueda + fetch + extracción de claims sobre ~20
> fuentes primarias, calidad etiquetada). El paso de síntesis del harness murió por ciclo de
> sesión; esto es la síntesis hecha a mano sobre los claims verificados que quedaron en el
> journal. **Complementa** `RESEARCH_ORO_NASDAQ.md` (infra/feeds/qué-transfiere) llenando lo
> que aquella pasada dejó explícito como *"pendiente de medir: re-anclar killzones al reloj
> CME"*.
>
> Regla intacta: nada opera sin pasar **DSR>0.95 + CPCV + PBO**. Esto dice **qué vale la pena
> meter al cubo del oro y cómo muestrearlo causalmente**, no qué ya pasó el gate.

---

## TL;DR — por qué el motor cripto casi no dispara en oro, y el fix

El motor está afinado para un mercado 24/7 con killzones de sesión cripto. **El oro no es 24/7 y su
actividad está concentrada por sesión**, con el pico en la apertura de NY/COMEX. Las killzones cripto
caen justo donde el oro está muerto (sesión asiática/madrugada), por eso "casi no dispara".

**El fix no es tocar thresholds — es re-anclar el reloj.** Las killzones del oro son ventanas de
sesión US y de evento macro, medibles y causales por barra:

| Killzone oro (ET) | Qué es | Evidencia | Prioridad |
|---|---|---|---|
| **08:20 ET** apertura NY/COMEX | Pico único de volumen que *eclipsa* a Tokio; vol pico | Osaka/NY seasonality (primary) | **1** |
| **08:00–09:00 ET** ventana dato 08:30 | **17% de todos los jumps intradía** del oro | Sobti EFMA 2024, COMEX 2010-18 (primary) | **1** |
| **14:00–15:00 ET** decisión FOMC | **16% de los jumps**; FOMC = driver #1 (LASSO) | Sobti (primary) | **1** |
| **~03:00 ET** apertura Londres | 2º pico de volatilidad/ineficiencia del día | Osaka/NY seasonality (primary) | 2 |
| **10:00 ET** PM fix Londres (15:00 UK) | Subasta concentrada; spike vol/volumen + edge de retorno ~4min post-fix (fuga info) | Caminschi & Heaney 2014, futuros CME (primary) | 2 |
| **13:30 ET** settlement COMEX | Spike de volumen pero **price-impact CAE** (menor info) → *stand-aside*, no killzone | Ready & Ready (primary) | gate-out |

**Regla causal:** etiqueta las killzones por `ts_recv` (nanosegundos, lookahead-safe) sobre horario
CME Globex (Dom–Vie, corte diario ~17:00 ET). Durante el pre-open/pausa el libro puede estar
locked/crossed sin trades → **gatea fuera** esa ventana.

---

## (1) Estructura de sesión — el hecho que lo explica todo

- **El oro NO es 24/7.** GC/MGC dan acceso electrónico *"casi 24h"* en CME Globex con **corte/mantenimiento
  diario** (16:00–17:00 CT ≈ 17:00 ET). Diferencia estructural genuina vs cripto. *(CME, primary)*
- **La actividad está concentrada por sesión, no plana.** En oro *"el volumen construye hasta un pico en
  la apertura de NY en COMEX que eclipsa el volumen de TOCOM"*. La liquidez informada domina la **sesión
  de NY**; la asiática la dominan uninformed/liquidity traders. *(Osaka/NY seasonality 2018, primary)*
- **La volatilidad tiene forma, y pica en las aperturas:** *"picos en la apertura de Tokio, Londres y NY;
  Tokio y NY son los momentos más volátiles"*. L-shape en Tokio, U-shape en Londres, declive ~lineal en
  NY. → anclar killzones a **aperturas de sesión**, no a un reloj plano.
- **Eficiencia informacional (variance-ratio) en W:** el intervalo **menos eficiente / más predecible** es
  por lejos la apertura de Tokio (TI1), 2º pico en apertura de Londres (TI4). El variance-ratio es en sí
  una **feature de régimen samplable por barra** con estacionalidad causal de hora-del-día.
- **GC domina el descubrimiento de precio:** ~27M oz/día, ~30× el ETF SPDR (0.8M oz). → construir el motor
  sobre tick-data CME (no spot/ETF) es lo correcto. *(CME, primary)*

**Consecuencia de diseño:** la ventana operable del oro es la **sesión NY (apertura COMEX → ~mediodía)**,
más las aperturas de Londres y los picos de evento. Las killzones cripto (asiática/madrugada) muestrean
justo donde el oro está ilíquido → cero disparos.

## (2) Order-flow / CVD firmado — ¿transfiere? SÍ pero con matices duros

**La buena noticia (mejor data que cripto):** el lado agresor del oro es **nativo del exchange**, no
inferido. CME MDP 3.0 expone **Tag 5797-AggressorSide** (0=sin agresor, 1=Buy, 2=Sell); Databento lo
entrega en el esquema `trades` como `side` (Ask=sell aggr, Bid=buy aggr, None). *(CME + Databento,
primary)* → firmas el CVD del oro con el **agresor real**, no con tick-rule/Lee-Ready como en cripto.
Cobertura COMEX en GLBX.MDP3 desde jun-2010; **aggressor side sólo desde MDP3.0 (~mar-2017)**, MBO full
desde 2017-05-21 → eso **acota la profundidad honesta del backtest firmado** (pre-2017 = tick-rule ruidoso).

**Los matices que matan el atajo "el edge de cripto transfiere":**

1. **Contemporáneo y permanente, pero NO predictivo por sí solo.** En futuros de commodities *incluido oro*,
   el imbalance firmado tiene poder explicativo significativo y el impacto es **mayormente permanente a 1
   min** (no revierte = continuación), **PERO** *"el imbalance de cada minuto es mayormente una innovación
   impredecible"* → el flujo firmado **rezagado** tiene poco poder de forecast solo. *(Ready & Ready, primary,
   gold-specific)* **Este es el claim central.**
2. **Oro = el commodity menos sensible al flujo.** $1M mueve al oro ~**0.22 bps** (vs 1.43 del trigo) — el
   libro es profundo. → una feature de CVD cruda **debe normalizarse por profundidad/volumen/volatilidad**
   (impacto ∝ 1/profundidad; volumen+vol explican ~90% del impacto cross-sectional). *(Cont-Kukanov-Stoikov;
   Ready & Ready)*
3. **La persistencia del flujo es artefacto de order-splitting**, no predictibilidad genuina: un ballena
   troceando un metaorder autocorrelaciona los signos sin implicar edge de retorno. *(Tóth-Lillo-Farmer)* →
   "CVD continúa" puede ser espejismo → **exactamente por qué se necesita el gate honesto**.
4. **El flujo firmado predice MAGNITUD/toxicidad, no dirección.** VPIN se construye del imbalance *absoluto*
   y es explícitamente no-direccional. Mantener el signo para predecir continuación es una afirmación **más
   fuerte** que lo que la literatura soporta. *(Easley-LdP-O'Hara)* → usa CVD/VPIN más como **gate de régimen**
   (cuándo confiar / hacerse a un lado) que como señal direccional standalone — espeja tu régimen KL.
5. **Horizonte cortísimo.** El alpha del order-flow decae en *"~2 cambios de precio promedio"* → acota
   labeling/horizonte; no esperes continuación a barras largas. *(Kolm-Turiel-Westray)*
6. **Trade-only CVD deja poder en la mesa** vs OFI completo (eventos de libro): R² 65% (OFI) vs 32% (trade
   imbalance) — pero **contemporáneo, no predictivo**. *(Cont et al.)* → si quieres exprimir, computa OFI
   multinivel, no solo CVD de trades.
7. **Firmable sólo en Globex electrónico**, no pit (los fills de piso no se pueden alinear ni firmar).

**Matiz gold-específico a favor:** en jumps del oro, *el buy-side flow sube ANTES de jumps positivos y el
sell-side ANTES de negativos*, y actividad/costo/Amihud-illiquidity/vol están elevados **10–15 min ANTES**
del jump. *(Sobti, primary)* → flujo firmado + illiquidity como features **líderes por barra** sí tienen
soporte gold-específico, en ventana corta.

## (3) ICT/SMC en oro — generador de hipótesis, NO edge

**Lo escéptico (bien argumentado):**
- El relato *"liquidity sweep = un algo central imprime wicks para cazar stops"* **contradice la
  microestructura**: el MM gestiona inventario/adverse-selection, no caza liquidez. *(blog, pero sólido)*
- **FVG aislado ≈ profit factor 1.0** (breakeven); order block = supply/demand reempaquetado.
- ICT tal como se practica es **infalsificable** (la discreción rescata cualquier trade fallido) → sólo
  testeable una vez hecho **mecánico y causal por barra**.
- Monte Carlo: sistemas breakeven (25% WR, 1:3) producen outliers de **$1–3.7M sólo por varianza** → las
  "historias de éxito ICT" son consistentes con suerte + survivorship, no edge.

**Lo utilizable (mapea killzones del oro en ET, causal y contable):**
- Fases practitioner en ET: acumulación 19:00–02:00 (rango asiático), manipulación/Judas 02:00–03:30,
  distribución 03:30–10:00, **NY killzone 07:00–10:00** (1er pullback = entrada de continuación). Son
  ventanas **samplables por barra** para testear — no verdades. *(blogs, sin estadística)*
- Un intento cuantificado (2,600 trades, 10 activos *incl. oro*, 61% WR, PF 2.17, +2.27R) — pero
  autopublicado, **sin DSR/CPCV/PBO** → dato, no prueba.
- El paquete `joshyattridge/smart-money-concepts` (Python) convierte OB/FVG/BOS/CHoCH en **features
  deterministas por barra** → el antídoto a la subjetividad: codificar como reglas rígidas y A/B contra el
  gate, mismo estándar que cripto.

**Veredicto:** ICT te dice **dónde mirar** (qué ventanas/estructuras muestrear), no te da edge. Codifícalo
mecánico, mételo al gate, quédate con lo que pase. Igual que en cripto.

## (4) Drivers intradía — timing y ventanas de riesgo

- **Backbone macro (medible, institucional):** las **tasas reales 10y (TIPS)** + inflación esperada son los
  drivers dominantes del oro (relación inversa fuerte con la tasa real; +1pp inflación esperada 10y ≈ +37%
  precio real). *(Chicago Fed, 2021)* → **DXY, tasa real 10y, breakevens** como features exógenas
  condicionantes (deltas, no niveles).
- **Releases 08:30 ET dominan:** NFP/CPI/jobless/durables. Sorpresa "buena" de economía → **NEGATIVO para
  oro** (vía USD/tasas). *(Elder-Miao-Ramchander, primary)* **FOMC 14:00 ET** = la noticia individual más
  dominante para jumps del oro (LASSO). *(Sobti)*
- **Alrededor de noticias, el flujo se vuelve MENOS informativo:** sube el price-impact pero cae la
  informatividad del flujo, la vol estalla. *(SVAR ES futures)* → **suprime o re-pondera** la señal de
  order-flow en ventanas CPI/NFP/FOMC. Trátalas como **régimen de evento**, no como barras normales.
- **PM fix (10:00 ET):** evento documentado con **edge de retorno ~4 min post-fix** (fuga informativa) y
  spike de volumen/vol. *(Caminschi & Heaney, primary)* Killzone causal específica del oro que no existe en
  cripto.
- **Settlement 13:30 ET:** volumen sube pero **impacto cae** (menor contenido informativo) → stand-aside.

## (5) Features causales por barra + experimento measure-first

**Shortlist de features (todas samplables por barra, causales por `ts_recv`):**

| Feature | Fuente/racional | Tipo |
|---|---|---|
| One-hots de killzone (Londres 03:00, COMEX 08:20, dato 08:30, PM-fix 10:00, FOMC 14:00, settle 13:30) | secciones (1)(4) | régimen/timing |
| CVD firmado desde Tag 5797, **normalizado por profundidad/volumen/vol** | (2) | flujo (corto) |
| **OFI multinivel** (eventos de libro, no solo trades) | Cont et al. | flujo (más rico) |
| Amihud ILLIQ, half-spread, realized variance | Osaka/NY + Sobti | microestructura |
| Variance-ratio de eficiencia (W-shape hora-del-día) | Osaka/NY | régimen |
| VPIN-toxicidad (buckets de **volumen**, no reloj) | Easley-LdP | gate de régimen |
| ΔDXY, Δtasa real 10y / breakevens; dummies de evento programado | Chicago Fed + Elder | exógeno |

**Muestreo:** usa **barras de volumen/dólar**, no de reloj — la serie queda más normal y menos
heteroscedástica (el volumen es proxy de volatilidad/llegada de info). *(Easley-LdP)*

**El gate (mismo ethos que cripto — medida o muerte):**
1. Label triple-barrier; **PURGE + EMBARGO** de labels solapados (las features de order-flow crean leakage).
2. **CPCV** → *distribución* de Sharpe por paths (no un número). CPCV es superior a walk-forward para
   suprimir overfit (menor PBO, mejor DSR en benchmark controlado). *(Arian-Norouzi-Seco 2024)*
3. **DSR**: deflacta por **N configs probadas** (cada variante de killzone/threshold cuenta como trial) +
   skew/kurtosis + largo del track. *(Bailey-LdP 2014)*
4. **PBO** vía CSCV: rechaza si el mejor-in-sample cae bajo la mediana OOS. *(Bailey et al. 2017)*
5. Importancia de features vía **MDA bajo purged-CV** para podar ruido de sesión. *(AFML cap. 7-8)*

**La trampa a evitar (nombrada explícitamente):** re-afinar un motor cripto que "casi no dispara" en oro
**hasta que dispare** es el caso de libro de multiple-testing / false discovery. **Cuenta cada trial.**
*(López de Prado 2019)*

---

## Qué construir ya (desbloqueado por esta investigación)

1. **Re-anclar killzones del harvest de oro** al reloj CME: reemplazar las ventanas cripto por las de la
   tabla TL;DR (COMEX open 08:20, dato 08:30, PM-fix 10:00, FOMC 14:00; Londres 03:00 secundaria;
   gate-out settle 13:30 y pausa/uncross). Esto es lo que hará que el cubo del oro **dispare**.
2. **Firmar el CVD del oro con Tag 5797** (real), normalizado por vol/profundidad — no tick-rule.
3. **Correr el gate CVD del oro** con killzones re-ancladas: triple-barrier → CPCV → DSR → PBO. Si pasa,
   entra al cubo; si no, se queda en cosecha. Mismo veredicto binario que los 13 símbolos cripto.
4. **Tratar order-flow como régimen** (à la KL) más que como señal direccional standalone — es lo que la
   literatura soporta.

## Fuentes (calidad etiquetada en el journal)
Primary: CME Group (GC overview, MDP3.0 Trade Summary/Tag 5797), LBMA (fix), Osaka/NY intraday seasonality
(J. Commodity Markets 2018), Sobti (EFMA 2024, COMEX jumps 2010-18), Ready & Ready (order flow commodity
futures incl. gold), Caminschi & Heaney 2014 (PM fix, futuros CME), Elder-Miao-Ramchander 2012 (macro news
metals), Chicago Fed 2021 (drivers), Cont-Kukanov-Stoikov 2014 (OFI), Kolm-Turiel-Westray 2023 (deep OFI),
Tóth-Lillo-Farmer (order-flow persistence), Easley-López de Prado-O'Hara (VPIN), Bailey & López de Prado
(DSR/PBO), Arian-Norouzi-Seco 2024 (CPCV), Databento (GLBX.MDP3 trades schema, MDP2 sin trade-side).
Blog (marcado folklore): completetradersedge, Sentient Trading Society, FXNX, Quantum Algo.
