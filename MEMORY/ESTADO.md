# Estado del proyecto — fq-bot (foto HOY)

> La página que más caduca. Qué está vivo, qué duerme, qué mide, qué espera veredicto, qué
> es plan en papel. Si la fecha de abajo es vieja, confírmala contra `git log` y `research/*.md`
> antes de confiar. Fecha de corte: **2026-08-05**, rama `claude/claude-brief-vip-v2-q1obx4`.
>
> **Las secciones "Por símbolo" y "Las 3 capas" de abajo son de junio y en BRUTO.** El
> bloque de agosto que sigue les pasa por encima: léelo primero, o vas a citar números
> que el neto ya desmintió.

---

## ⚠️ Encima de todo lo de abajo (agosto 2026)

Los números por capa y por símbolo de esta página son **BRUTOS**. E8 midió el neto sobre las
mismas 13.429 señales y el resultado cambia la lectura de todo lo que sigue:

- **bruto +0.2305R → NETO −0.0258R**, IC95% [−0.059, +0.013]. Coste **−0.256R/trade**.
- **Ningún subconjunto** (13 símbolos × 8 años × 2 lados × 5 quintiles de stop) clarea
  DSR > 0.95. El mejor es 2020 con 0.359.
- E7 midió que la **entrada sí separa**: asimetría de recorrido **+1.011R**, IC95%
  [+0.825, +1.199], en ambos lados y los ocho años. El problema no es la señal.
- **Con entrada maker el signo se voltea** (+0.060R, IC95% [+0.024, +0.096]) — pero eso
  asume fill del 100%, y este repo ya midió que los maker rápidos pierden el 80% del R.
  **La pregunta abierta que decide el proyecto es la calidad del fill, y es medible.**

- **El fill maker está medido y NO salva**: 88,4% de fills, pero selección adversa
  **−1,039R** (llenadas +0,114R vs escapadas +1,153R). Neto maker real
  **−0,0350R**. → `CEMENTERIO.md`.
- **La geometría ancha: señal confirmada, producto inviable. CERRADA.**
  Seis controles la respaldan (óptimo interior, control de inversión, CPCV 13-15/15,
  PBO 0,198, holdout por símbolo 8/8, fill resuelto a favor con entrada taker).
  La matan dos: **DSR 0,432** aun con la celda pre-fijada, y sobre todo el
  **riesgo de cartera** — hold de 2 días deja **13,7 posiciones simultáneas**;
  a risk 1% sin límite **arruina la cuenta**, y la mejor por Calmar paga **71% de
  drawdown tirando el 66% de las señales**. Las pérdidas llegan juntas (−26R en
  24 cierres el mismo día). → `CEMENTERIO.md`.
  **La palanca de la geometría está medida y agotada.**

- **EL VIP, MEDIDO (2026-08-05).** Universo exacto del producto (`FQ_VIP_PAIRS =
  BTC,ETH,SOL`), n=3.774 señales canónicas 2019-2026, neto de costes:
  - **La selección de símbolos se sostiene**: VIP **+0.010R** en tp4/h288 (IC95%
    [−0.060, +0.080]) vs **−0.040R del resto del pool** (n=9.655). Elegir SOL/BTC/ETH
    en junio fue correcto, y ahora con 7 años detrás.
  - **La geometría viva NO**: en **tp1/h288 — la celda que el motor realmente opera —
    −0.069R neto, IC95% [−0.112, −0.028]**. Entero bajo cero: signo determinado, no
    "no concluye". Por símbolo (tp4): ETH +0.059 · BTC +0.003 · **SOL −0.054**.
  - El problema del VIP **no es el símbolo ni la señal: son las barreras y el capital
    simultáneo**. → `CEMENTERIO.md`.

- **V1 ENTREGADO (2026-08-05) — la nota es ya un arreglo, y el eje TP está cerrado.**
  `tools/vip_report.py` contesta "¿funciona el VIP?" con **un comando** y reproduce los
  números de arriba al cuarto decimal. `tests/test_vip_report.py` los fija.
  - **Barrido del eje TP a horizonte fijo (h288), universo VIP, n=3.774**, con
    `portfolio_risk` aplicado **ANTES** de nombrar candidata a ninguna celda:
    tp1 **−0.069** · tp2 **−0.053** · tp3 **−0.018** · tp4 **+0.010**.
    **Ninguna es candidata**: ninguna tiene el IC95% entero sobre cero.
  - **El diagnóstico NO es el de la geometría ancha, y confundirlos cuesta trabajo.**
    Aquí el hold medio es ~0.1 días y la concurrencia ~1.3; las tres celdas negativas
    tienen el **DD dentro de la cota (26–27% < 35%)** y aun así hunden la cuenta.
    **No sobra riesgo: falta edge.** Un mecanismo de concurrencia no arreglaría ninguna.
  - **Abierto y dicho en voz alta: máximo en la esquina.** El neto sube monótonamente
    hasta tp4, que es el **último peldaño que el cube trae etiquetado**. La tabla no dice
    que tp4 sea el óptimo — dice que el gradiente apunta **fuera del rango medido**.
    Saberlo exige **re-etiquetar** con objetivos más lejanos (`geometry_sweep`, que
    necesita velas locales; **hoy no hay `data/binance` en el repo**), no extrapolar.
    Aviso pegado: alejar el objetivo alarga la vida del trade → devuelve la concurrencia
    que ya mató la geometría ancha. El informe lo imprime solo.
  - **Desglose por año de la celda viva (tp1/h288): 7 de 8 años con n≥30 salen
    NEGATIVOS.** No es un régimen malo tapando uno bueno: es consistente.
  - **Invariantes nuevas:** una celda no se nombra candidata sin sostener una cartera
    (`screen_cell` + `require_screened`), el gate corre **sin cap** de concurrencia
    (capear hace pasar cualquier cosa tirando señales), y el universo medido es el que
    el bot difunde (`FQ_VIP_PAIRS`).

- **V2 ENTREGADO (2026-08-05) — la cola medida, y el maker cerrado por ejecución.**
  El fill deja de ser binario: `bt_engine.maker_fill_probability` devuelve
  **P(fill) condicionada al flujo FIRMADO** que imprimió en el nivel (a una BID la
  consume el taker SELL, no el volumen total), con la cola declarada en `queue_frac` =
  múltiplos del volumen mediano de barra del símbolo.
  - **`queue_frac = 0` ES `maker_entry_fill_mask`**: la regla que el repo usó hasta hoy
    es la **esquina más optimista** del modelo nuevo — la de estar siempre el primero de
    la cola. Un test lo comprueba en cada corrida; el informe la imprime como primera fila.
  - **Pool completo, n=12.941, tp4/h288, neto maker:** cola 0.00 **−0.0350**
    [−0.076, **+0.004**] · **0.05 −0.0635 [−0.104, −0.025]** · 0.25 −0.1549 · 1.00 −0.3294
    · 2.00 −0.4453. **Con 0.05 barras de cola el IC ya está entero bajo cero**: el último
    número maker que rozaba el cero por arriba deja de rozarlo. No hacía falta
    microestructura fina — bastaba con no ser el primero.
  - **El mecanismo está medido, no argumentado:** **corr(P(fill), R neto) = −0.2267**,
    monótona en cinco tramos (p<0.25 → **+0.8548R** n=1.468; **p=1 → −0.3784R** n=7.757).
    Es la selección adversa de agosto (−1.039R) explicada: la cola **no filtra al azar**,
    te deja justo las señales en las que el precio te atravesó.
  - **VIP (BTC/ETH/SOL), n=3.565:** cola 0.00 +0.0282 [−0.047, +0.106] → 0.25 **−0.0845**
    [−0.161, −0.007] → 2.00 −0.3884. Ni la esquina optimista clarea cero.
  - **Qué muere:** arreglar el maker **por ejecución**. No hay dónde ponerse en la cola.
  - **Invariante nueva:** cada fila de `simulate` sale marcada `taker`/`modelado`/
    `asumido_100` y `maker_expectancy` levanta `MakerFillAssumedError` ante el último.
    El techo se imprime **solo** por la puerta que lo etiqueta TECHO.
  - **Honestidad del alcance:** `queue_frac` es un supuesto declarado, no una medición
    (no hay libro L2 aquí). Por eso se publica la **curva** y el resultado que se cita es
    el **umbral** (0.05), no un punto.
  - Reproducir: `python tools/fill_quality.py --klines data/binance` (las velas se bajan
    con `tools/fetch_binance_vision_klines.py`; `data/` está en `.gitignore`).

- **V3 ENTREGADO (2026-08-05) — la capacidad, con la liquidez MEDIDA. Cinco dígitos.**
  `python tools/capacity_analysis.py --vip`. El tool existía desde N8.4 y contestaba con
  **parámetros de catálogo**: su default `avg_bar_notional=3e6` estaba **8x por debajo del
  BTC real** (2.563e7 USD/barra 5m, medido) y el `stop_frac=0.012` era el doble del real.
  - **Liquidez medida de las velas locales** (mediana, no media — cola derecha gordísima):
    BTC **2.563e7** USD/barra · σ 20.3bps · stop 0.45% || ETH **1.428e7** · 26.5bps · 0.50%
    || SOL **4.278e6** · 34.9bps · 0.63%. El coeficiente de impacto **se deriva de esa σ**
    (ley raíz `Y·σ·√q`); lo único declarado que queda es **Y** (~0.5–1.5 en la literatura),
    y por eso se publica la **curva** sobre Y, no un punto. Mismo trato que `queue_frac`.
  - **Bug que nadie podía ver: `fill_bars` elegía la respuesta.** σ iba por barra y la
    liquidez por ventana → la capacidad escalaba con √fill_bars (C0 de **$12k a $1.1M**
    de fill_bars 1 a 96). Con σ escalada a la misma ventana la ley raíz es **invariante**
    y hay test. El default de 24 multiplicaba la capacidad por 24.
  - **La curva (tp4/h288, VIP, risk 1%, Y=1):** bruto BTC C½ $308k / C0 $1.2M · ETH
    $162k/$650k · SOL $15k/$60k. **Neto: solo ETH tiene algo — C½ $5k, C0 $22k.**
    BTC (+0.0027R) y SOL (−0.0539R) no tienen capacidad que medir.
  - **A tamaños reales (Y=1), la única celda positiva del producto entero es ETH a $10k
    (+0.019R).** A $100k: BTC −0.081 · ETH −0.068 · SOL −0.267. A $1M, SOL paga el 37%
    de una barra de 5m.
  - **La frontera, que es lo accionable:** capital al que el impacto (escala) iguala al
    coste fijo por trade (no escala): **BTC $1.2M · ETH $434k · SOL $106k**. Por debajo
    manda el coste fijo — **encoger la cuenta no arregla nada**. El rango de la
    conversación ($10k–$500k) **cruza esa frontera en SOL**.
  - **Por qué sale tan baja, y no es lo que parece:** no falta libro (BTC mueve 2.6e7 por
    barra). Es que el **stop apretado** (0.45–0.63%) divide el impacto en R. Y el repo ya
    midió (2026-06-30) que **el stop apretado ES el edge** (Q1 +0.316R vs Q4 +0.147R):
    **lo que hace rentable a la señal es lo que la hace frágil al tamaño.** Un compromiso
    con números por los dos lados, no dos problemas.
  - **Por año (E9):** el notional de SOL creció ~100x dentro del cube; su C0 bruto va de
    $8k (2023) a $867k (2026). La capacidad sube con el mercado; el edge neto no.
  - **Veredicto de negocio: SERVICIO DE SEÑALES, no vehículo de capital.** Es el escenario
    "\$5k" del brief, no el "\$500k". Con el matiz obligado: la capacidad del neto es ~cero
    porque **no hay edge neto que escalar**, no por falta de libro.
  - **Invariante nueva:** `require_measured` levanta `CapacityAssumedError` ante liquidez
    supuesta **y** ante serie bruta sin `allow_ceiling=True`. Sin velas locales el informe
    **se para** y dice cómo bajarlas, en vez de contestar con el default de catálogo.

- **CONTEXTO DE NEGOCIO (2026-08-05) — presión de inversor, y por qué NO se pivota.**
  Un inversor del proyecto lleva meses viendo gasto sin producto rentable y mandó un vídeo
  de TikTok proponiendo copy-trading de Trump/políticos (Autopilot + Hyperliquid) con
  dashboard para inversores privados. **Se midió antes de construir: queda 1 de 100**
  (→ `CEMENTERIO.md`, "Copy-trading por leaderboard"). No se pivota, y la razón no es
  terquedad: el pivote **sube** la quema (dominio nuevo, instrumento desde cero, frente
  legal) justo cuando la queja es la quema. Tres cosas para hablar con él, todas medidas:
  **(a)** la geometría viva del VIP pierde (−0.069R, IC entero bajo cero, n=3.774) y se
  dice primero; **(b)** la señal SÍ separa (E7 +1.011R, IC [+0.825, +1.199], 8 años);
  **(c)** lo que queda por medir (V1/V2/V3) es **local y gratis** — el cube ya está
  cosechado. **NO uses el `n=12` con él**: está bajo `MIN_N=30` y no concluye.
  **V3 (capacidad) es la respuesta a su ansiedad** — convierte "confía en mí" en una cifra:
  si la capacidad es \$5k esto es un servicio de suscripción y se deja de hablar de fondos;
  si es \$500k, hay otra conversación. Ojo legal: custodiar capital de terceros (el "Trust")
  es gestión de fondos; Autopilot, con mucho más músculo, eligió **no** tocarlo.

Detalle: `internal/DIAGNOSTICO_E7_E8_2026-08.md` · `MEMORY/CEMENTERIO.md` ·
`internal/EXPERIMENT_COPYTRADE_ONCHAIN.md` (el espejo sin capital, si alguna vez se retoma).
**Encargo: `internal/BRIEF_VIP_2026-08.md` — V1, V2 y V3 ENTREGADOS. El encargo está cerrado.**
- ~~**V2 · posición en cola**~~ **ENTREGADO** (ver bloque arriba): P(fill) por flujo
  firmado, la binaria como esquina `queue_frac=0`, y `MakerFillAssumedError` impidiendo
  que una cifra maker salga con fill al 100%.
- ~~**V3 · capacidad**~~ **ENTREGADO** (ver bloque arriba): liquidez medida de las velas,
  `fill_bars` ya no elige la respuesta, y la cifra de negocio es **de cinco dígitos**.

Las tres brechas del brief están medidas y **ninguna abrió una puerta**: la geometría
(V1) no tiene celda operable, la ejecución (V2) no tiene dónde ponerse en la cola, y el
tamaño (V3) se acaba antes de que el edge empiece. **Lo que falta no es otra medición del
mismo cube: es una señal con más edge bruto, o un coste de ejecución estructuralmente
menor.** Cualquier encargo nuevo que no ataque una de esas dos cosas está decorando.

Reproducir: `python tools/vip_report.py` · `python tools/cube_report.py cosecha_cubes/` ·
`python tools/fill_quality.py` · `python tools/geometry_sweep.py` ·
`python tools/capacity_analysis.py --vip`
(los cuatro últimos necesitan las velas en `data/binance`, que **no están en el repo**:
`python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end 2026-06-30
--out-dir data/binance`, ~40 s por símbolo, gratis, sin API key.)

### Instrumento cableado en agosto (todo dormido por defecto)

| Qué | Flag | Invariante que lo hace cumplir |
|---|---|---|
| Vector completo en el OPEN | `FQ_FEATURE_SNAPSHOT` | `SCHEMA` append-only; `read()` distingue "no existía" de "fue nula" |
| Fires vetados repreciables | (siempre) | cada camino de supresión sella geometría + `stage` |
| Desglose obligatorio del E[R] | (siempre) | `format_expectancy` levanta sin `by_period` + guarda AST |
| `/salud` | (admin) | el veredicto es el PEOR chequeo, nunca el promedio |
| Procedencia | (siempre) | el audit corta `tracker.outcomes` y lo que cuelga deja de publicarse |
| Batches API | `FQ_LLM_BATCH` | superficie declarada o no se difiere (falla cerrado) |
| Riesgo de cartera | (siempre) | `portfolio_risk`: el R por trade no describe la cuenta |

---

## Las 3 capas de edge — dónde está cada una

| Capa | Edge | Números (validados, no prometidos) | Estado |
|---|---|---|---|
| **1 — Direccional** | motor maker + veto | ~~+0.10R OOS, DSR ✓ (BTC 1.00 / SOL 0.97)~~ **BRUTO. El neto del mismo universo en la geometría viva (tp1) es −0.069R, IC95% [−0.112, −0.028], n=3.774** | **VIVO en clientes, sin edge neto demostrado** |
| **2 — Carry** | short-perp funding, delta-neutral | +12.5% APY net, Sharpe 13.6 bruto, positivo 6 años incl. bear | **Midiendo forward** (`carry_paper`, 0% real) |
| **3 — Order-flow** | CVD firmado (imb≥0.50) | +0.27R (SOL) / +0.34R (BTC), 5 años tick data | **Cableado, midiendo forward** |

Graduación de la capa 3: **≥30 fires confirmados forward + uplift ≥ +0.1R + DSR ✓** → recién ahí
sube conviction client-facing. Hoy mide, no decide.

---

## Por símbolo

- **SOL/USDT** — pilar. Ledger SQLite rico (4 TP, contexto, conceptos). Motor paper a 5m. CVD validado.
  F2-persist **no aplica** (SOL no apila — firma retail/momentum).
- **BTC/USDT** — broadcasting a clientes (commit `8a5c11d`). Motor paper a 5m. CVD validado (DSR ✓).
  **F2-persist con luz verde** (cableado dormido, `FQ_PERSIST_BOOST=BTC`). En el ledger rico **solo
  vía motor_paper** (1 TP), no en el SQLite de 4 TP — gap conocido (ver cerebro).
- **ETH/USDT** — cableado (motor paper, broadcast gated, vetos, regime tag) **pero no certificado**.
  Pendiente: cosechar su cube + correr DSR completo + CVD signed-flow. Si pasa → `FQ_ETH_VIP_BROADCAST=1`.
- **BCH/USDT** — **DEMOTADO a paper (VIP off, RasDG 2026-06-30: `FQ_BCH_VIP_BROADCAST=0`).** F2✓ + POC✓
  (cube), **top de por vida** (+0.207R) pero **sin forward + sin KL**; empeoraba el DD de la ventana de 2m
  (ruido — esos 2 meses fueron −0.128R, atípicos para BCH). Sigue en `motor_paper`; **reversible** (re-evaluar
  forward). Decisión de calidad de VIP, no de edge.
- **BNB/USDT** — **VIP APAGADO (decisión RasDG 2026-06-30):** peor de por vida (+0.061R, apenas positivo) +
  **sin validar** (fuera de POC y F2 — token de exchange). Sigue en `motor_paper` (mide forward), sin exponer
  clientes. Acción: `FQ_BNB_VIP_BROADCAST=0` en Railway (kill-switch sin redeploy).
- **LINK/USDT** — **NO en VIP. VALIDACIÓN COMPLETA (2026-06-30): falla 3/4 gates.** CVD **NO PASA**
  (uplift −0.161R, los confirmados rinden PEOR, DSR 0.380); F2 **NO PASA** (DSR 0.921 + redundante within-CVD
  −0.045R); POC **NO PASA** (near>far invertido); KL pasa **DÉBIL** (DSR 0.969, sep 0.075R). Base +0.181R = solo
  el motor; **ninguna familia validada (CVD/F2/POC) funciona en LINK.** La racha de 2m (+0.831R) fue **100%
  ruido** — el ejemplo perfecto de "la ventana miente". → **NO a VIP.** Opcional: medir forward en paper
  (`FQ_MOTOR_PAPER_LINK=1` + `FQ_LINK_VIP_BROADCAST=0`). Instinto de RasDG: confirmado por el gate.
- **VIP AHORA = SOL / BTC / ETH** (núcleo más validado, todos CVD✓). BCH+BNB bajados a paper (2026-06-30);
  LINK nunca entró. Cualquier re-alta se decide por **forward**, no por ventana.
- **Filtro de calidad KL (`FQ_KL_FILTER`) — RECOMENDADO PRENDER (medido 2026-06-30).** Por defecto está OFF
  → el VIP difunde TODAS las señales del motor. Sobre la ventana 2m (SOL/BTC/ETH, 3.6%/trade, sim paper),
  difundir **solo el subconjunto KL-bajo** (lo que pasa `_kl_pass`, ~56% de las señales) dio **+139% con
  drawdown −12%**, vs **todas: +177% pero −36%** → mismo orden de return, **1/3 del drawdown**. El filtro
  esquiva el mal régimen (trending/irreversible) y suaviza el viaje. → **encender `FQ_KL_FILTER=SOL,BTC,ETH`**
  (medir forward antes de fijarlo). Mejor riesgo-ajustado y retención. (irrev proxy de klines Binance.)

---

## Qué está vivo / dormido / midiendo / pendiente

**VIVO (en clientes / capital):**
- Motor direccional capa 1 (+0.10R **bruto**, DSR ✓; **neto tp1 −0.069R** — ver bloque de agosto).
  Vetos de régimen/sesión (default ON, validados 5 años).
- Gate de validación (`tools/validation_gate.py`). Colectores forward (read-only, no-críticos).
- Ejecución taker + maker en motor paper (mide R neto: fees + slippage).

**CABLEADO DORMIDO (OFF, byte-idéntico cuando off):**
- **Cockpit "show" (`FQ_COCKPIT`, 2026-07-03, encargo marketing de RasDG):** terminal institucional en
  vivo del motor. Arquitectura de COLECTOR NO-CRÍTICO: el motor solo deja caer un JSON atómico throttled
  (`cockpit.py`, no-op si off, todo try/except) y el server (`tools/cockpit_server.py`, stdlib) es hijo
  `critical=False` del launcher — si la interfaz muere, el bot NI SE ENTERA (regla de RasDG). Prender:
  `FQ_COCKPIT=1` + exponer puerto en Railway (Networking → Generate Domain). Modo `?demo=1` con badge.
  **REDISEÑO 2026-07-03 (RasDG: "me da asco… parece infantil… cajero de Citigroup + terminal de Matrix,
  gestor de fondo big-capital"):** `cockpit.html` reescrito como **"FQ CAPITAL · Fibonacci Quantum
  Framework — Terminal"** (sin la palabra "cockpit"): statusbar con reloj UTC vivo, hairline gradiente
  Solana (#9945FF→#14F195), constante φ 1.6180339887, cinta ticker, tarjetas de instrumento con badges
  PRODUCCIÓN/LABORATORIO, sparkline oro (#c9a227), tracks KL + funding con veredictos direccionales
  ("frío→viento de cola del LONG"/"caliente→combustible del SHORT"), "REGISTRO DE DECISIONES DEL MOTOR",
  y **lluvia Matrix animada de fondo** (canvas: ~9% columnas DORADAS a velocidad φ 0.618× deletreando
  Fibonacci, glifos φΦΣλΞ◎₿+katakana, `prefers-reduced-motion` respetado). Data-contract INTACTO (cero
  backend). Paleta validada por dataviz (contraste, no banda-L: serie única). El merge auto-despliega.
- **Lluvia digital FQ en Python (piezas de SHOW standalone, 2026-07-03, encargo RasDG "como Matrix, en
  movimiento, con φ/Solana/oro"):** `tools/matrix_rain.py` (curses, **stdlib puro** — 0 deps, corre en
  cualquier terminal) y `tools/matrix_rain_gl.py` (**Pygame/SDL2**, alto rendimiento, adaptado del repo
  StanislavPetrovV con glifos pre-renderizados+cacheados = "instancing"). Ambos: oro φ deletrea
  Fibonacci, degradado Solana, mensajes de la casa que se materializan (FQ CAPITAL, DSR>0.95, MEDIDA O
  MUERTE), marca de agua institucional. `--self-test` (física φ verificada), `--seconds`/`--record`/
  `--screenshot` para clips/stills de marketing. **pygame JAMÁS en `requirements.txt`** (el bot no
  depende de vanidad; el test hace `importorskip`). Para grabar: `matrix_rain_gl.py --record f_%04d.png`.
- CVD a conviction/size (`FQ_CVD_VIP_CONVICTION`, `FQ_CVD_BOOST_TIER`).
- **Funding-boost DIRECCIONAL a conviction (`FQ_FUNDING_BOOST`, 2026-07-03):** +1 tier con badge
  "FUNDING FAVORABLE", apilable con CVD/POC. **LONG & pctl≤0.5** (+0.173R vs +0.121, DSR 1.000/CPCV
  80%/PBO 0.04) y **SHORT & pctl≥0.7** (+0.224R vs +0.156, DSR 1.000/CPCV 100%/PBO 0.00 — el mejor
  gate del programa). Zona neutra sin boost. Decisión RasDG: despierto; `by_funding` sigue de juez.
- F2-persistencia (`FQ_PERSIST_BOOST=BTC`) — luz verde tras re-confirm n_trials=44 (commit `c355d25`).
- **Regime tags KL + POC-distance + FUNDING** (`FQ_REGIME_TAGS`, 2026-06-29/07-03): sella `kl_low`/`kl_irrev`
  (KL fiel, ventana 64) + `poc_dist` (developing) + **`funding_pctl`** (percentil ~90d del funding del
  propio símbolo, OKX público cacheado — el funding-gate que PASÓ el gate in-cube: LONG & pctl≤0.5 →
  +0.173R vs +0.121, DSR 1.000/CPCV 80%/PBO 0.04) en `MOTOR_OPEN_META`; el reporte agrega
  `by_kl`/`by_poc`/**`by_funding`** (umbral fijo 0.5). Mide forward KL, POC-distance y funding-gate. El
  POC-distance ESTRICTO del día previo se mide offline con `gate_poc_distance.py` sobre el ledger.

**MIDIENDO FORWARD (0% capital):**
- Motor paper SOL + BTC (+ ETH). CVD filter/tag (`FQ_CVD_FILTER`, pendiente encender en Railway).
- Carry market-neutral (`carry_paper`, basket CLEAN).

**ESPERANDO VEREDICTO (validador armado, sin run reportado):**
- OI, global_ls, toptrader_ls, taker_ls. Workflows listos para dispatch (ver `CEMENTERIO.md`).

**PLAN EN PAPEL:**
- Cerebro (analítica dedicada multi-símbolo). Etapa 0 lista para arrancar al OK de RasDG.
- OFI verdadero (Tardis L2): solo si el CVD validado lo justifica forward.
- A vivo (FASE 2): `FQ_EXEC_MODE=live` en sub-cuenta chica cuando el fill-rate maker selle.

---

## TradFi híbrido + features nuevos (2026-06-29)

**Híbrido data/venue (DECISIONES §11):** validar TradFi sobre la historia profunda de Dukascopy
(gratis, años) y ejecutar en el perp de MEXC. El motor **DIGIERE** la OHLCV sin order-flow (verify:
45 eventos en XAU). **Cosecha 5y × 5 símbolos CERRÓ** (run 28413719153, 2026-06-30, ~6h en Hetzner;
XAU/NQ/ES/WTI/plata). Transfieren KL/ICT/precio; CVD/F2 **no** (son del venue). **Veredicto POC-distance
TradFi: NO PASA** (n=1992, `far>near` consistente en 5/5 y DSR ✓, pero **PBO 0.76**; en cripto SÍ pasa,
PBO 0.17). **KL-standalone TradFi TAMPOCO transfiere** (2026-06-30: inconsistente, solo NQ pasa y en el
lado OPUESTO a cripto; 4/5 no separan). → **NINGÚN edge de régimen (POC ni KL) transfiere a TradFi: el
bot es cripto-específico.** Útiles al paper (cross-asset), **NO tier** en TradFi. Ver `CEMENTERIO.md`.

**Volume Profile (POC/VA) — `volume_profile.py` (PR #121):** la pata de "volumen" de la confluencia
triple, construida (puro, 7 tests, crypto+TradFi). Medida sobre crypto (`measure_vp_tier.py`, #123):
zona premium/discount **REFUTADA** (inconsistente), rev-aligned **ESPEJISMO** (n=39). **POC-distance
PASA el gate** (#125: DSR + ortogonal a KL + CPCV/PBO) y queda **cableado dormido para forward**
(`FQ_REGIME_TAGS`, junto a KL). Ver `CEMENTERIO.md`.

**TJR/ICT:** el bot YA implementa el framework ICT (sweeps/OB/FVG/PD/killzones/`session_bias`). Es
capa de **convicción+gating**, no el edge validado (ese es CVD/F2/KL). `session_bias.py` ES la tesis
"Asia rango → London fake → NY continuación". MSS/CHoCH se detectan pero **NO gatean** (a propósito).

---

## El roadmap (de `research/plan_evolucion_2026.md`)
- **FASE 1 — MAX EDGE (~30-45 días, sin capital extra):** encender + medir el CVD filter; sellar el
  fill-rate maker (a 30-50 fills); poner a punto ETH (cube + validación).
- **FASE 2 — A VIVO:** ejecución real en sub-cuenta chica (OKX, sizing ≤25x); carry a vivo.
- **FASE 3 — ESCALA:** multi-símbolo (XRP/LTC/DOGE/ADA — el carry ya probó perps sanos); OFI si se
  justifica; distribución.

---

## Auditoría del registro forward (el detonante del cerebro, 2026-06-27)
El registro es **asimétrico**: SOL se graba completo (ledger SQLite rico, 4 TP, contexto); **BTC y ETH
se broadcastean a clientes pero su único registro es el motor paper de 1 TP** — el ledger rico es
SOL-only (sin columna de símbolo). Una señal BTC/ETH puede salir a VIP y no quedar en ningún registro
con outcome. El plan **cerebro** (`research/cerebro_arquitectura.md`, commit `f0cce80`) lo cierra:
- **Etapa 0** (siguiente): `ALTER TABLE signals ADD COLUMN symbol` (no-destructiva, filas viejas = SOL)
  + helper `_record_vip_signal` en los 3 sitios de broadcast (graba 4 TP + símbolo). Additivo, con tests.
- **Etapas 1-3:** lago DuckDB read-only → jobs background (mapa convicción, prometido vs realizado,
  edge-health DSR-rolling, integridad) → dashboard web + Telegram enriquecido.

---

## Trabajo reciente (últimos commits, contexto)
- **TradFi híbrido + Volume Profile (2026-06-29):** cosecha unsharded XAU+NQ + alias de índices
  (PR #122); `measure_vp_tier` (PR #123); módulo Volume Profile (PR #121); fetcher Dukascopy
  (#117/#118/#120); probes Dukascopy/MEXC (#114/#115/#116).
- `f0cce80` blueprint del cerebro (analítica por etapas).
- `7197ede` F2-persist re-confirm n_trials=44 + cableado dormido (PR #85); `c355d25` registra la luz verde.
- `4176dd6` F1 impacto + F2 persistencia, validadores measure-first (PR #84).
- `6fc2f09` global_ls deep-dive 6 años + ortogonalidad (PR #82); `943aaaf` validador generalizado de
  metrics (PR #81); `0995f57` ortogonalidad OI×CVD (PR #80); `2bde2d2` pipeline OI con DSR (PR #79).
- `8c9187e` CVD sube +1 tier (PR #77); `0e89321` badge VIP (PR #75); `fbce1e9` cablea CVD filter (PR #73).

---

## Cosas a no olvidar (trampas de contexto)
- **F2 es BTC-only.** No intentes prenderlo en SOL: no apila (está medido, ver `CEMENTERIO.md`).
- **F1 NO se cabló** aunque su DSR standalone es altísimo — es redundante con el CVD (within-CVD negativo).
- **El +1.47R del CVD estricto (n=17) es un espejismo** que el gate descartó. El R real es +0.27/+0.34.
- **El carry NO es arbitraje sin riesgo** — es prima de régimen; el bruto resta ~2-4pp al neto; en 2026
  la prima se comprime a ~0.
- **BTC/ETH aún no están en el ledger rico de 4 TP** — solo en motor_paper. No asumas que el SQLite
  tiene los 3 símbolos hasta que Etapa 0 del cerebro esté hecha.
- **El +2.4R/54%WR del "rev-aligned" de Volume Profile en ETH es ESPEJISMO (n=39).** El motor es de
  momentum: el bucket contrarian es chico. La zona premium/discount NO da edge consistente cross-símbolo;
  lo único que aguanta es **POC-distance** (lejos>cerca), y aun ése está PENDIENTE del gate.
- **CVD/F2 NO transfieren a TradFi** (order-flow del venue; Dukascopy da solo OHLCV). En oro/NASDAQ
  solo cuentan KL + precio + ICT. No asumas el "motor premium" completo fuera de cripto.
- **"0 disparos" puede ser DEPLOY, no el motor — revisa Railway ANTES de asumir "selectivo".** El
  2026-06-30 el bot no disparó en todo el día y yo lo expliqué como comportamiento selectivo normal;
  la captura de Railway mostró la verdad: un **deploy fallido** (`Heartbeat timeout / Infra Error`).
  Raíz: los `.pdf/.html/.png` de `MEMORY/`+`presentaciones/` NO estaban en la blacklist de
  `watchPatterns` (solo `*.md`), así que **cada commit de docs re-desplegaba el worker** → reseteaba
  contadores ("Total: 0") y lo exponía a blips transitorios. Fix: blacklist `MEMORY/`,
  `presentaciones/`, `*.pdf/*.html/*.png` (**PR #138**, `funding_paper.py` sigue runtime al final).
  **Lección:** ante 0 cadencia, primero confirma uptime/deploy en Railway; sólo después sospecha del edge.
- **"0 disparos" también puede ser RÉGIMEN, no falla — y ahora hay HERRAMIENTA para probarlo (2026-07-03).**
  RasDG reportó 5 días sin señales; el replay del motor sobre datos reales (`run_research_real` en venv
  py3.12 — pandas-ta exige ≥3.12, por eso el sandbox 3.11 no podía) probó que del 29-jun al 1-jul el motor
  legítimamente NO encontró setups en los 5 símbolos vivos (0 fires salvo 2 BCH-paper el 30-jun), y los
  últimos fires salieron con irrev ALTO (0.37-0.69 = trending). **El motor caza colapso/reversión: en
  tendencia limpia se calla** — limitación de estilo anotada (la cadencia muere en trend puro; el
  funding-boost mejora convicción de longs, no cadencia). Receta del replay: klines Vision recientes →
  datasets canónicos 5m/15m/1h + funding → `run_research_real --date-start/--date-end` → comparar vs lo
  recibido. Sin señales VIP ni descartes FREE cuando el motor no dispara = comportamiento correcto.
- **No apagues un símbolo por UN stop-out — el "stop dentro del ruido" es de COLA y UNIVERSAL.** El
  2026-06-30 una señal de BCH tocó SL al instante (stop 0.249% < vela 5m mediana 0.265%). Medido cross-símbolo
  (`tools/sl_noise_screen.py`): el stop MEDIANO está bien en TODOS (ratio stop/vela 1.7–2.8; BCH 2.04, a media
  tabla), pero el **p10 (~0.24–0.31%) roza el ruido en todos** → en baja vol cualquier símbolo emite un stop de
  cola dentro del ruido (esa señal cayó bajo el p10 de BCH). BCH **tiene edge** (positivo en todas las celdas);
  no se apaga. **MEDIDO (mismo día, pooled n=13429): el stop apretado ES el edge, NO el bug.** Por cuartil de
  stop%: Q1-apretado WR 23% pero **expR +0.316R** vs Q4-ancho WR 28% y **expR +0.147R** (monótono). El stop
  comprimido baja el WR (más ruido) pero su R-múltiplo lo paga con creces. → **un piso/ensanche de stop BAJARÍA
  la expectativa — NO hacerlo.** (Mi intuición de "floor the stop" la refutó el dato.) La palanca para la
  *experiencia* (no la expectativa) es **gestionar a TP1** (WR ~29%→~50%), no tocar el stop. Caveat: es
  correlacional (el stop% es endógeno al setup); el causal per-trade confirmaría, pero la dirección es clara.

---

_Fuente de verdad: `git log`, `research/plan_evolucion_2026.md`, `research/cerebro_arquitectura.md`,
`research/fisica_moderna_2026_resultados.md`, `research/carry_regime.md`, `motor_paper.py`,
`fq_bot_v3_2.py`, `railway.toml`. Actualizado 2026-06-30._
