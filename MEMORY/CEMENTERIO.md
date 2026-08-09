# VALIDADO vs CEMENTERIO — registro de evidencia

> Existe para que **nadie re-pruebe lo ya muerto** ni vuelva a creer un espejismo de
> muestra chica. La vara es **DSR > 0.95** (significancia tras corregir multiple-testing)
> **+ ortogonalidad** (¿suma DENTRO del CVD ya confirmado, o es redundante?). Solo lo que
> pasa AMBAS se cabla. Lo que no, queda aquí, honesto. **Medida o muerte.**
>
> Lee esto ANTES de proponer "una idea nueva": probablemente ya pasó por el gate.

---

## VALIDADO (cableado o en marcha)

### CVD — confirmación de order-flow firmado — **DSR ✓ (BTC ~1.00 / SOL ~0.98)**
- **Idea:** el volumen comprado/vendido asimétrico (CVD) da el **signo** del flujo
  institucional. Confirma la dirección de la señal.
- **Validador:** `tools/validate_cvd_signed_flow.py` (causal, gratis vía Binance aggTrades).
- **Data:** BTC 2021-01-01 → 2026-06-27 (~2003 días).
- **Resultado:** dentro de CVD-confirmado, premium DSR ✓; uplift within-CVD claramente positivo
  (CVD✓ ≈ +0.56R vs CVD✗ ≈ −0.045R). R bruto: SOL +0.27R / BTC +0.34R a imb≥0.50.
- **Por qué sobrevive:** la ley de raíz cuadrada del impacto (δ≈0.5) está confirmada en cripto
  (Donier-Bonart 2015; Sato-Kanazawa, PRL 2025); el CVD da el SIGNO, el resto es samplable.
- **Status:** **CABLEADO** (capa 3 → motor 1, commit `fbce1e9`; badge VIP `0e89321`). Default OFF,
  midiendo forward (`FQ_CVD_FILTER`).
- **Trampa evitada:** el +1.47R estricto (n=17) lo **mató el gate** — muestra demasiado chica.

### F2 — persistencia del flujo (memoria larga, autocorrelación lag-1) — **DSR ✓ en BTC**
- **Idea:** order-splitting — las órdenes grandes se ejecutan en pedacitos → autocorrelación
  positiva del signo (continuación).
- **Validador:** `tools/validate_persistence_flow.py` (ac1 lag-1 sobre aggTrades).
- **Resultado (run 28287771057, `research/fisica_moderna_2026_resultados.md`):** standalone
  **DSR 0.997** (thr=0.0, n_trials=16); premium (CVD✓ & F2✓) **DSR 0.995**, n=299, exp +0.562R
  vs CVD✓ & F2✗ −0.045R. Robusto en 3 umbrales (0.0/0.05/0.10). **NO knife-edge.**
- **Ortogonalidad:** F2 apila DENTRO del CVD-confirmado (no redundante). **F2 rescata el CVD**:
  dentro de CVD✓, el no-persistente es break-even; el persistente paga.
- **Re-confirm honesto:** el barrido real probó ~44 configs, así que la vara de multiple-testing
  es n_trials=44, no 16 (workflow `physics_confirm.yml`). Re-confirmado → **luz verde** (commit
  `c355d25`).
- **Por qué sobrevive:** Bouchaud-Farmer-Lillo 2008 (arXiv:0809.0822) + reconfirmación 2026
  (arXiv:2606.16269). Falsable y samplable.
- **Status:** **CABLEADO DORMIDO** (default OFF, byte-idéntico). Commit `7197ede` (PR #85). Se
  prende con `FQ_PERSIST_BOOST=BTC`.
- **Barrido cross-asset — la tesis del "premio" REFUTADA (2026-06-28, `tools/cross_asset_sweep.py`,
  6 símbolos, ventana CVD 2024-26):** la hipótesis "la persistencia ESCALA con la institucional-idad /
  order-splitting" **NO se sostiene**. Uplift F2 (persist − base): **XRP +0.349 · BCH +0.280 ·
  BTC +0.257 · LTC +0.207** (apilan) · **SOL +0.000** (plano) · **ETH −0.167** (NEGATIVO). NO
  correlaciona con el ac1 del flujo (corr = −0.19) NI con el eje institucional→retail (XRP, retail,
  apila MÁS; ETH, institucional, es negativo; SOL retail tiene el ac1 más alto tras BTC). El
  order-splitting **no explica** el uplift. → F2 es un **confirmador por-símbolo, real pero
  idiosincrático** (paga en **4/6**), **NO una ley de escala**. La curva monótona institucional (el
  "premio") **no existe**. Cablear F2 donde paga (BTC/XRP/BCH/LTC), **NUNCA en ETH**; forward primero.

### KL — irreversibilidad temporal como CONDICIONADOR de régimen — **DSR ✓ cross-símbolo (cube)**
- **Idea:** la flecha del tiempo (termodinámica estocástica). KL(forward‖backward) de las
  distribuciones de grado del **grafo de visibilidad** = qué tan lejos del equilibrio está el
  mercado. **Sin parámetros libres** (no hay dónde hacer overfit).
- **Validador:** `tools/validate_regime_irreversibility.py` (klines, gratis).
- **Resultado (cube, historia completa):** el edge vive en irreversibilidad **BAJA**
  (reversible/mean-reverting), **NO** en trending. BTC low-irrev +0.348R **DSR 0.999**; SOL
  +0.225R **DSR 0.950**. **Monótono por cuartil en AMBOS**. **Cross-símbolo** (a diferencia de F2).
- **Ortogonal:** el `regime_state` del bot es todo "stable" → KL separa DENTRO de él (agrega).
- **Triple cruce CVD✓ & persist✓ & KL-bajo — PROBADO FUERA DE BTC, FALLA (2026-06-28):** con CVD
  de SOL y ETH ya bajado (ventana 2024-06→26, `tools/measure_tiers.py`), el out-of-sample del filtro:
  **BTC +0.782R (n=37) ✓** · **SOL −0.263R (n=43) ✗** · **ETH −0.139R (n=61) ✗**. Pool n=141 →
  **+0.065R bruto → −0.085R NETO**. El +0.874R/DSR 0.992 de BTC era **sobreajuste a BTC**: el edge
  **NO transfiere**. → **El "motor premium" global NO es producto: resta.** Solo BTC-only sobrevive
  (+0.63R neto) pero ~1 señal/3 sem y n=37 (< piso 100). Premium = **lead de investigación en BTC**, no tier.
- **Por qué sobrevive:** Kawai-Parrondo-Van den Broeck 2007 (KL = entropía producida); Lacasa
  et al. 2012 (estimador por grafo de visibilidad). Era el hilo de termo-estocástica del research.
- **TradFi — NO transfiere (5y × 5 símbolos, n=170–564, 2026-06-30, `validate_regime_irreversibility`):**
  el edge KL que en CRIPTO vive **consistente en irrev-BAJO** (reversible), en TradFi **NO separa de forma
  consistente**: XAU (sep 0.188R, irrev-ALTO, DSR 0.458 ✗) · **NQ (0.636R, irrev-ALTO, DSR 1.000 ✓)** · ES
  (0.193R, irrev-BAJO, 0.690 ✗) · WTI (0.174R, irrev-BAJO, 0.889 ✗) · XAG (0.046R, irrev-BAJO, 0.251 ✗).
  **Solo NQ es significativo, y en el lado OPUESTO a cripto** (trending, no choppy); **4/5 no separan ni
  concuerdan en el lado.** → **KL es edge cripto-nativo, NO ley de régimen cross-asset.** NQ-trending queda
  como **lead aislado de NASDAQ** (base +0.74R, a verificar forward), no edge gateado. Junto con POC-distance
  (tampoco pasa), confirma: **NINGÚN edge de régimen transfiere a TradFi — el bot es cripto-específico.**
- **Status:** **VALIDADO en cube (cripto), PENDIENTE forward. NO transfiere a TradFi.** No cableado. Falta ETH + forward + n_trials honesto.

### Volume Profile (POC/VA) — la pata de "volumen" de la confluencia triple — **PARCIAL**
- **Idea:** el setup de mayor probabilidad junta estructura + **VOLUMEN** + order-flow. El bot tenía
  estructura (pivotes/OB/PD/VWAP) y order-flow (CVD); faltaba el volumen-por-precio: **POC + Value
  Area del día PREVIO** (causal) como referencia de valor.
- **Módulo/medición:** `volume_profile.py` (PR #121, puro, 7 tests) + `tools/measure_vp_tier.py`
  (PR #123). Solo precio+volumen → sirve a crypto **y** TradFi.
- **Resultado crypto (BTC/ETH/SOL, tp4/h576, n≈1000 c/u, 2026-06-29):**
  - **Zona premium/discount → REFUTADA.** Inconsistente cross-símbolo (ETH ama premium +0.27, SOL
    discount +0.05, BTC plano). No transfiere — mismo patrón que la "ley de escala" de F2.
  - **Tesis reversión-a-value (rev-aligned) → ESPEJISMO.** ETH +2.4R / 54% WR pero **n=39**. El motor
    es de momentum (dispara rev-against ~95%); el bucket contrarian es muy chico. No sobrevive DSR
    (como el +1.47R del CVD estricto, n=17).
  - **POC-distance → PASA EL GATE (in-cube, 2026-06-29, `tools/gate_poc_distance.py`).** *lejos del
    POC > cerca* en LOS 3 símbolos. Pooled n=3136: tier "lejos" (q0.80, n=628) meanR +0.416 vs base
    +0.237 (**uplift +0.179**); DSR ✓ deflactado (n_trials=6). **ORTOGONAL a KL:** dentro de irrev-bajo,
    lejos suma **+0.290** (KL-bajo +0.332 → KL-bajo & lejos +0.622, n=329, DSR ✓). CPCV uplift OOS
    mediana +0.174 (**87% paths >0**); **PBO 0.26**. Es "no dispares en el chop de ayer", apila SOBRE KL.
    Caveat: **GROSS** (pre-coste); **SOL marginal** (+0.014, lo cargan BTC/ETH). El gate ✓ ≠ forward ✓.
  - **Cross-símbolo (2026-06-29):** extendido a **5 cripto (n=5162) → PASA MÁS FUERTE** (uplift +0.121,
    within-KL +0.272, CPCV OOS +0.111 / **93% paths>0**, **PBO 0.17**). **4/5 siguen** el patrón
    (BTC/ETH/SOL/BCH `far>near`); **BNB es la EXCEPCIÓN** (`far +0.077 < near +0.358`, AL REVÉS) — token
    de exchange, microestructura distinta (igual que lo excluimos del carry y F2 no le aplica). → el
    filtro "lejos" aplica a **BTC/ETH/SOL/BCH, NO a BNB** (símbolo-específico).
  - **TradFi — VEREDICTO con n grande (5y × 5 símbolos, n=1992, 2026-06-30, run 28413719153):**
    `far>near` **consistente en LOS 5/5** (XAU 306: +0.058 vs −0.058 · NQ 454: +0.973 vs +0.642 · ES 170:
    +0.355 vs −0.028 · WTI 564: +0.324 vs +0.043 · XAG 498: +0.245 vs −0.204). Pooled: base +0.192 → tier
    'lejos' +0.322 (uplift +0.131), **DSR 1.000 ✓**. PERO **NO PASA EL GATE**: within-KL uplift +0.057
    **DSR 0.922 ✗**; CPCV-OOS mediana **+0.046 / solo 67% paths>0**; **PBO 0.76 🚩**. → **La DIRECCIÓN
    transfiere (universal cross-asset, sirve al paper), pero NO es robusta para cablear en TradFi** — el
    umbral 'mejor' está sobreajustado (PBO alto). Contraste honesto: en CRIPTO el MISMO edge SÍ pasa
    (n=5162, PBO 0.17, 93% paths). → **TradFi POC-distance: lead de research, NO tier.** El gate dijo no.
    (Antes era RADAR a n=328; ahora con poder estadístico es VEREDICTO: no pasa.)
- **Status (POC-distance):** **VALIDADO en cube (5 cripto ✓, BNB excluido), CABLEADO DORMIDO forward**
  (`FQ_REGIME_TAGS`, #126 — sella `kl_low`/`poc_dist` en MOTOR_OPEN_META; `by_kl`/`by_poc` en el reporte).
  Próximo: medir forward + más data TradFi. Zona premium/discount y rev-aligned: muertos.

### Funding-gate para LONGS (percentil 90d) — **PASA EL GATE in-cube (2026-07-03)** ⭐
- **Idea (deep-research mejora-longs):** el funding alto = longs crowded (BIS WP1087: carry alto
  predice crashes; lo infla el retail trend-chaser). Gatear los LONGS por funding RELATIVO.
- **Validador:** `tools/validate_long_gates.py --exp funding` (funding mensual de data.binance.vision,
  causal por evento, 12,858/13,348 fires con dato).
- **Resultado:** LONG & funding-pctl90d≤0.5 → **+0.173R vs +0.121 base (n=1538) · DSR 1.000 ✓ ·
  CPCV-OOS +0.028 (80% paths>0) ✓ · PBO 0.04 ✓**. Gradiente limpio: longs mueren conforme el funding
  se calienta (+0.175→+0.095); **shorts al revés** (+0.105→+0.215, lead de boost no gateado).
- **OJO:** el gate por NIVEL crudo NO pasa (PBO 0.75) — solo el PERCENTIL relativo al propio símbolo.
  GROSS, in-cube. **Status: CABLEADO DORMIDO (2026-07-03)** — `funding_pctl`/`funding_rate` sellados en
  MOTOR_OPEN_META junto a `kl_low`/`poc_dist` (mismo flag `FQ_REGIME_TAGS`, ya ON en Railway), vía funding
  público de OKX cacheado 1h y defensivo (fallo -> sin tag, jamás rompe el fire). Juez forward =
  **`by_funding`** en `ledger_report` (umbral FIJO 0.5 = el validado, no mediana). Nota cross-venue:
  validado sobre historia Binance; en vivo cada venue se compara contra su PROPIA historia 90d (mismo
  constructo relativo). Mismo camino que el CVD: gate ✓ -> dormido -> forward -> producto.
- **BOOST DESPIERTO Y DIRECCIONAL (RasDG 2026-07-03):** `FQ_FUNDING_BOOST=1` prende el boost +1 tier
  con badge "FUNDING FAVORABLE" (apilable con CVD/POC, topado en 8x) en AMBOS lados, cada uno con su
  umbral VALIDADO: **LONG & pctl≤0.5** (+0.173R vs +0.121 · DSR 1.000/CPCV 80%/PBO 0.04) y **SHORT &
  pctl≥0.7** (+0.224R vs +0.156 · DSR 1.000/**CPCV 100% paths**/**PBO 0.00** — el mejor gate del
  programa; gateado el mismo día a pedido de RasDG, 3 configs short declaradas, n_trials=6; el
  sostenido≥15%APR crudo NO pasa — consistente: informan los percentiles, no los niveles). Zona neutra
  (0.5<pctl<0.7): sin boost. El juez `by_funding` sigue midiendo forward; kill-switch = misma env.
- **Muertos del mismo barrido (no re-probar):** *breadth/alt-season gate* para alt-longs (altseason
  ≥75%: uplift +0.002, PBO 1.00 — el decoupling macro NO baja a gate de 5m, horizon mismatch);
  *CVD-ortho sin-chase* (dirección pro-tesis +0.085 vs +0.003 pero n=34 — sin poder; colateral real:
  CVD-de-barra confirmado rinde PEOR que no confirmado = chase contamination); *NUPL<0.5 throttle*
  (gradiente monotónico precioso capitulación +0.317 → codicia +0.072, DSR ✓ CPCV ✓; PBO clásico no
  computable en régimen lento — se construyó el PROTOCOLO RÉGIMEN-LENTO (`slow_gate_report`: bootstrap
  de bloques + consistencia por mitades) y TAMPOCO pasa: P(uplift>0)=0.941<0.95, mitad 2019-22 ≈ +0.001
  → el gradiente es de la era 2023-26. NO cableable; NO es falta de cómputo (el test corre en ms), es
  falta de CICLOS — el unlock es forward/tiempo, no hardware).

### F1 — residual de impacto raíz-cuadrada — **REAL pero REDUNDANTE con CVD**
- **Idea:** ley δ≈0.5: impacto ∝ σ·√(Q/V). Si el precio se mueve MENOS de lo predicho →
  absorción (continuación). Reglas: coiled / extended / fragile.
- **Resultado:** standalone **fortísimo** (BTC coiled DSR 0.994/0.993/0.990/0.985 ✓). PERO
  within-CVD uplift **−0.186/−0.157/−0.022/+0.010** → **SUSTITUYE el CVD, no complementa**.
- **Veredicto:** real pero **redundante**. El CVD ya captura la dirección; F1 no añade información
  nueva. Pasa DSR, **no pasa ortogonalidad**.
- **Status:** **NO CABLEADO**. El CVD solo es más parsimonioso. (Si algún símbolo mostrara uplift
  within-CVD > 0.05, se reconsideraría — midiendo, no asumiendo.)

---

## CANDIDATOS — esperando veredicto (validador armado, sin run reportado)

> Estos tienen validador y workflow listos para dispatch. El veredicto está **pendiente de
> ejecución**, no de re-investigación. Si pasan (DSR + ortogonalidad) → capa 3. Si no → cementerio.

| Candidato | Idea | Regla | Validador / workflow | Próximo paso |
|---|---|---|---|---|
| **OI** (open interest) | posicionamiento nuevo entrando | directional | `validate_oi_flow.py`, `oi_validation.yml`; ortho OI×CVD añadido en `0995f57` | correr con `since=2021-01-01`, historia completa + ortho |
| **global_ls** | long/short de cuentas (retail) → fade a la multitud | **contrarian** | `validate_metric_flow.py`, `global_ls_deepdive.yml` (commit `6fc2f09`: 6 años + ortho) | re-test 6 años, ¿aguanta? ¿SOL o BTC-only? ¿suma within-CVD? |
| **toptrader_ls** | posiciones de top-traders (smart money) | directional | `validate_metric_flow.py`, `metrics_validation.yml` (`943aaaf`) | sweep de umbral SOL/BTC/ETH |
| **taker_ls** | taker buy/sell ratio (flujo agresivo) | directional | idem | idem |

Notas: `global_ls` pasó DSR en BTC pero **solo a 3 años** y solo standalone — por eso el deep-dive
a 6 años. Es símbolo-específico como F2 (firma institucional BTC vs retail SOL).

---

## CEMENTERIO (falsado, infalsable o sobreventa)

> Refutados en investigación adversarial (3-0 = 2 de 3 votos lo mataron) o por la literatura.
> **No se codifican.** Si alguien propone uno de estos, la respuesta es: ya murió, aquí está por qué.

### Quantum finance de Baaquie (QFT / path integrals para opciones) — 3-0
Funciona *solo en la medida en que suelta su contenido cuántico*. La parte útil son path
integrals de Feynman **como herramienta clásica de cómputo**. Arioli & Valente: Black-Scholes no
usa números imaginarios; "el éxito numérico de Baaquie viene de efectos no cuánticos". El
Monte-Carlo de timelines del bot (`quantum_timelines.py`) YA es el contenido path-integral
legítimo (clásico). Llamarlo "cuántico" no agrega nada. **Nunca cableado.**

### LPPL de Sornette (predicción log-periódica de cracks) — 3-0
Curve-fit de 7 parámetros con muchos mínimos locales; el mecanismo "fenómeno crítico" aplica a
~la mitad de las burbujas; los parámetros caen en el rango "teórico" (puesto post-hoc) en solo
7 de 11 cracks del Hang Seng; t_c es un proceso estocástico (O-U) → da un *rango* de fechas, no
predicción OOS nítida. **Diagnóstico, no predicción. No pasaría el DSR.** Nunca cableado.

### Quantum-like markets de Khrennikov (interferencia cuántica en el flujo) — 3-0
**Cero datos de mercado** (es un diseño de experimento que el propio autor admite irrealista).
Amañado: cualquier λ≠0 cuenta como "cuántico"; si λ>1 (imposible en interferencia real) el marco
salta a un "espacio de Hilbert hiperbólico" para absorberlo. **Infalsable por diseño.** Esta es
LA idea seductora ("interferencia cuántica en el flujo retail") que hay que NO perseguir.

### Critical-slowing-down / early-warning (AR(1) sube antes del crack) — muerto
Un estudio (5 mercados, 4 cracks) encontró **sin tendencia** pre-crack. Los cracks financieros
**no son transiciones críticas** en el sentido físico. Mata la versión ingenua. Nunca cableado.

### Rough volatility (Hurst H~0.1) — muerto (artefacto)
Cont-Das 2022 (arXiv:2203.13820): la "rugosidad" es un **artefacto de estimación**, no real. La
estimación sesga hacia H bajo; la volatilidad real probablemente está cerca de H~0.5. No pasaría
el DSR. Nunca cableado.

### El +0.224R bruto del cube como "el edge" — muerto por costes (2026-08-04, E8)
La cifra que sostenía la tesis de edge del backtest **no sobrevive al modelo de costes
del propio repo**. `bt_engine.CostModel` (taker ambos lados) sobre las 13.429 señales
canónicas, celda tp4/h288: bruto **+0.2305R → neto −0.0258R**, IC95% [−0.059, +0.013],
P(E[R]>0)=0.110. El coste son **−0.256R por trade**.

No es mala suerte de parámetros, es aritmética: el fee va sobre el *notional* y la R es
la *distancia al stop*, así que `coste_R ≈ (2·fee+2·slip)/(stop/precio)`. Con el stop
mediano de esta cosecha (**0.525% del precio**) eso da 0.23R antes de funding. Las **12
celdas tp × horizonte son negativas netas**.

Y no se salva por partes: se inspeccionaron 28 cortes (símbolo, año, lado, quintil de
distancia de stop) y **ninguno clarea DSR > 0.95** — el mejor es 2020 con DSR 0.359, o
sea el ganador de un concurso de 28 juzgado después de ver los resultados. Los dos que
más tientan ya estaban desmentidos: `GATE-D` (el liderazgo por símbolo no persiste,
rank-corr −0.19) y `H1` (el régimen del año se voltea).

Alcance: es **cota superior**, no simulación — la etiqueta asume fill perfecto en la
barrera. Lo realizable está por debajo; el −0.510R del motor paper es la misma cosecha
con fill real.

**Qué muere exactamente:** citar el +0.224R como evidencia de edge, y la esperanza de
que exista un subconjunto (símbolo / régimen / horizonte / TP) que lo salve tal cual.
**Qué NO muere:** la entrada. E7 midió que el recorrido es asimétrico a favor del lado
elegido (**+1.011R**, IC95% [+0.825, +1.199], en ambos lados y los ocho años). La señal
ve algo; lo que no hay es geometría que lo cobre por encima del peaje.

**Condición para revivir la línea:** una configuración cuyo **neto** —no bruto— pase el
gate (DSR>0.95 + IC95% > 0), lo que exige subir R por trade (stops/objetivos más anchos,
menos trades) o arreglar el fill. Ambas son E6-prohibidas hoy.

Cableado para que no vuelva: `tools/cube_report.cell_stats` levanta `GrossWithoutNetError`
si alguien resume una celda del cube sin `net_pnl_r` — ninguna sección del informe puede
imprimir el bruto solo. Tests: `tests/test_cube_costs.py`.
Detalle: `internal/DIAGNOSTICO_E7_E8_2026-08.md`.

### "Con entrada maker el edge se vuelve positivo" — muerto por el fill real (2026-08-04)
La última puerta abierta de E8. Aplicando `CostModel(maker_entry=True, maker_tp_exit=True)`
al cube, el signo se volteaba: **+0.0601R, IC95% [+0.0235, +0.0958]**, P(>0)=0.998 — la
primera configuración medida de este repo con el IC por encima de cero. Pero asumía
**fill del 100%** en el nivel.

Medido contra velas reales (`tools/fill_quality.py`, 12.941 señales, 13 símbolos, velas
5m de Binance Vision con gate de venue: corr MFE 0.995–1.000 vs el cube de OKX):

- fill rate **88.4%** — no falla por falta de fills.
- **llenadas +0.114R (WR 25.4%) vs escapadas +1.153R (WR 47.3%) → selección adversa −1.039R.**
  El 12% que se escapa son los ganadores: la límite no se llena justo cuando el precio
  se va a tu favor.
- **neto maker sobre lo que se llena: −0.0350R**, IC95% [−0.074, +0.004].

**Qué muere:** citar el +0.060R maker como evidencia de que el sistema es viable, y la
esperanza de que el problema fuera solo la pierna taker. Sigue siendo cota superior — el
fill se juzga con la vela y la cola de la orden no se conoce.

**AMPLIACIÓN V2 (2026-08-05) — la cola, medida: se cierra también el "roza el cero".**
Aquel −0.0350R tenía el IC95% [−0.074, **+0.004**]: el último número maker que aún tocaba
el cero por arriba. `bt_engine.maker_fill_probability` mete la cola en la ecuación
(p = flujo firmado que imprimió en el nivel / cola por delante, con `queue_frac` en
múltiplos del volumen mediano de barra del símbolo). Sobre las mismas n=12.941:

| cola por delante | fill | **neto maker** | IC95% |
|---|---|---|---|
| **0.00 = la binaria de siempre** | 88.4% | −0.0350 | [−0.076, **+0.004**] |
| **0.05** | 85.5% | **−0.0635** | **[−0.104, −0.025]** |
| 0.25 | 77.7% | −0.1549 | [−0.195, −0.116] |
| 1.00 | 61.9% | −0.3294 | [−0.370, −0.290] |

**Con 0.05 barras medianas de cola por delante — la suposición más pequeña que no sea
"soy el primero de la cola" — el IC95% ya está entero bajo cero.** Y el mecanismo está
medido, no argumentado: **corr(P(fill), R neto) = −0.2267**, monótona en cinco tramos
(p<0.25 → +0.8548R con n=1.468; p=1 → **−0.3784R** con n=7.757). La cola no te quita
señales al azar: te deja las que el precio atravesó.

**Qué muere además:** la esperanza de arreglar el maker **por ejecución** — ponerse mejor
en la cola, afinar el eps, esperar más. No hay dónde ponerse: la esquina de estar SIEMPRE
el primero ya no clarea cero, y todo lo demás está peor. En el universo VIP (n=3.565) pasa
lo mismo un peldaño arriba (cola 0.00 +0.0282 [−0.047, +0.106] → cola 0.25 −0.0845
[−0.161, −0.007]).

**Invariante que lo hace cumplir:** cada fila de `bt_engine.simulate` sale marcada
`taker`/`modelado`/`asumido_100`, y `maker_expectancy` levanta `MakerFillAssumedError`
ante `asumido_100`. El techo se puede imprimir; no se puede publicar sin la etiqueta.
Tests: `tests/test_bt_maker_fill.py`, `tests/test_fill_quality.py`.
Reproducir: `python tools/fill_quality.py --klines data/binance`.

**Qué NO muere:** la entrada (E7: asimetría +1.011R, IC95% por encima de cero, ambos lados,
ocho años). La señal ve algo. Lo que no hay es forma conocida de cobrarlo por encima del peaje.

**Condición para revivir:** una configuración cuyo neto **con fill medido** pase el gate
(DSR>0.95 + IC95%>0). Las dos palancas sin medir son R por trade más grande (re-etiquetar
con stops/objetivos anchos) y otro TF (cosecha nueva). Las dos son E6-adyacentes.

**Efecto lateral que hay que remedir, no apagar:** `FQ_MOTOR_MIN_FILL_BARS=2` (ON por
defecto) descarta los fills de 1 barra por un hallazgo de n=53. Sobre n=11.438 el orden se
invierte — 1 barra neto **+0.0010R** vs ≥2 barras **−0.2409R** — o sea que el gate tira el
único bucket no negativo y el 85% del flujo. La geometría no es la misma (cube tp4/h288 vs
motor tp1/TTL), así que no es refutación estricta: es orden de remedirlo.
Detalle: `internal/DIAGNOSTICO_E7_E8_2026-08.md`. Tests: `tests/test_fill_quality.py`.

### "Stops mas anchos diluyen el coste fijo" — senal confirmada, producto inviable (2026-08-04)
La ultima palanca que quedaba tras E7/E8 y la medicion del fill. Re-etiquetando las
13.429 senales con triple barrera sobre una rejilla de 84 geometrias (`tools/geometry_sweep.py`),
la hipotesis **se confirma como senal y se cae como producto**.

Lo que PASA (seis controles independientes):
- gradiente con **optimo interior** (kSL 5 -> 8 -> 12 empeora), no deriva a comprar-y-esperar.
- **control de inversion**: real +0.0608R vs invertida −0.1013R. Si fuera beta la invertida
  saldria mejor (el set es 57% short). No es beta.
- **CPCV OOS** temporal: +0.0797R, 13/15 caminos; le gana a la geometria actual **15/15**.
- **PBO 0.198** (referencia: umbral KL 0.897 = alerta; barbell 0.008 = limpio).
- **holdout por simbolo x8 particiones: 8/8 con TEST positivo**, media +0.0494R. (La primera
  particion alfabetica dio −0.0049 y casi lo mata: n=1 miente, tambien para matar.)
- **fill**: a stops 5x el coste taker son 0.047R, y la entrada taker siempre llena. Ir maker
  RESTA −0.0143R. El problema que mato la geometria vieja no aplica.

Lo que NO pasa, y por eso muere:
- **DSR = 0.432** incluso con la celda pre-fijada y `n_trials=1`. Perfil de loteria
  (skew +2.68, kurtosis 10.6): el Sharpe por trade es 0.0377 y la vara no se degrada.
- **RIESGO DE CARTERA — el decisivo.** Hold medio 2 dias -> **13.7 posiciones simultaneas**
  (p95 29, max 54). Con capital comprometido en la apertura: risk 1% sin limite **arruina la
  cuenta (DD 100%)**; risk 0.25% da x2.99 con **DD 69.3%**; la mejor por Calmar (risk 1%, cap 5
  abiertas) da x12.86 con **DD 71.1% tirando el 66% de las senales**. Peores dias: −26.0R en 24
  cierres el mismo dia. Las perdidas llegan juntas, medido.

**Que muere:** "ensanchar el stop rescata el neto" como via a producto. La geometria esta
**medida y agotada** — 84 celdas, seis controles, y la razon exacta por la que no basta.
**Que NO muere:** la senal. Sigue confirmada (E7 +1.011R de asimetria; aqui seis pruebas mas).
Lo que no existe es una forma conocida de cobrarla dentro de un perfil de riesgo operable.

**Condicion para revivir:** un mecanismo que baje la CONCURRENCIA sin tirar la cadencia
(no un cap ciego), o un perfil de riesgo que el producto pueda sostener con DD < 35%.
Detalle: `internal/DIAGNOSTICO_E7_E8_2026-08.md`. Herramientas: `tools/geometry_sweep.py`,
`tools/portfolio_risk.py`. Tests: `tests/test_geometry_sweep.py`, `tests/test_portfolio_risk.py`.

### "El VIP publica la mejor geometría" — tp1 medido en contra (2026-08-05)
Pregunta de RasDG: *"¿Y el VIP? ¿Funciona?"*. Se midió el universo exacto del producto
(`FQ_VIP_PAIRS = BTC,ETH,SOL`, n=3.774 señales canónicas 2019-2026) sobre el cube, neto
de costes. Dos cosas salieron, y las dos cuentan.

**Lo que SOBREVIVE — la selección de símbolos.** El universo VIP da **+0.010R neto** en
tp4/h288 (IC95% [−0.060, +0.080]) contra **−0.040R del resto del pool** (10 símbolos,
n=9.655). Elegir SOL/BTC/ETH en junio-2026 fue correcto y ahora tiene 7 años detrás en
vez de una ventana de 2 meses. Por símbolo: **ETH +0.059 · BTC +0.003 · SOL −0.054**
(el pilar del producto es el peor de los tres), ~16 señales/mes cada uno.

**Lo que MUERE — tp1 como geometría del producto.** En la celda que el motor vivo
realmente opera, **tp1/h288: −0.069R neto, IC95% [−0.112, −0.028]**, WR 51.0%. El
intervalo está **entero por debajo de cero**: no es "no concluye", es signo determinado
sobre n=3.774. En tp4 el IC cruza cero (+0.010 / +0.017); en tp1 no cruza.

**Qué muere:** la idea de que el VIP publica la geometría correcta y que lo que falta es
muestra. La muestra ya está: son las barreras. **Qué NO muere:** ni la señal (E7:
asimetría +1.011R) ni el universo (medido mejor que el resto del pool).

**No contradice el track record publicado** (`n=12 · WR 41.7% · E[R] +0.208`): n=12 está
bajo el `MIN_N=30` del propio repo y no concluye en ninguna dirección. n=3.774 sí.

> **CEMENTADO (V1, 2026-08-05).** Era una nota — script ad-hoc de sesión, sin tool ni
> test. Ya no: `tools/vip_report.py` contesta "¿funciona el VIP?" con un comando
> (`python tools/vip_report.py`) y reproduce estos números al cuarto decimal.
> `tests/test_vip_report.py` fija que el universo medido es el que el bot difunde
> (`FQ_VIP_PAIRS`) — medir un universo distinto del publicado son dos números
> correctos describiendo productos distintos, y nadie se enteraría.

### El eje TP como salida del VIP — barrido tp1→tp4 en contra (2026-08-05, V1)
La otra mitad de V1: si tp1 reparte mal, ¿alejar el objetivo lo arregla? Barrido del eje
TP a horizonte fijo (h288, el que opera), sobre el universo VIP, **con `portfolio_risk`
aplicado ANTES de nombrar candidata a ninguna celda** — no como post-mortem. n=3.774.

| celda | bruto | **neto** | IC95% | WR |
|---|---|---|---|---|
| tp1/h288 | +0.192 | **−0.069** | [−0.112, −0.028] | 51.0% |
| tp2/h288 | +0.208 | **−0.053** | [−0.106, −0.002] | 38.7% |
| tp3/h288 | +0.243 | **−0.018** | [−0.080, +0.044] | 33.3% |
| tp4/h288 | +0.271 | **+0.010** | [−0.060, +0.080] | 29.5% |

**Ninguna celda es candidata.** Ninguna tiene el IC95% entero sobre cero.

**Y el diagnóstico NO es el de agosto — esto importa.** La geometría ancha murió por
concurrencia (13.7 simultáneas, DD 71%). Aquí el hold medio son ~0.1 días y la
concurrencia ~1.3: el filtro de cartera **no es el que mata**. Las tres celdas negativas
tienen el DD *dentro* de la cota (26–27%) y aun así hunden la cuenta — no sobra riesgo,
falta edge. Confundir los dos casos mandaría el trabajo a inventar un mecanismo de
concurrencia que aquí no arreglaría nada. El informe los nombra por separado a propósito.

**Lo que queda abierto, dicho en voz alta:** el neto **sube monótonamente** hasta tp4, que
es el ÚLTIMO peldaño que el cube trae etiquetado — un **máximo en la esquina**, la misma
bandera roja que hizo extender la rejilla de `geometry_sweep` hasta kSL=12. La tabla NO
dice que tp4 sea el óptimo; dice que el gradiente apunta fuera del rango medido. Saberlo
exige **re-etiquetar** con objetivos más lejanos (`geometry_sweep`, que necesita velas
locales — hoy no hay `data/binance` en el repo), no extrapolar. Y con un aviso: alejar el
objetivo alarga la vida del trade, o sea que devuelve el problema de concurrencia que mató
la geometría ancha. El informe imprime este aviso solo, no depende de acordarse.

**Desglose por año de la celda que opera (tp1/h288): 7 de 8 años con n≥30 salen
NEGATIVOS.** No es un régimen malo tapando uno bueno: es consistente.

**Qué NO muere:** el universo. La selección VIP da +0.050R netos por señal sobre el resto
del pool (10 símbolos, n=9.655) en la misma celda de referencia. Son dos preguntas y solo
una salió mal.

Reproducir: `python tools/vip_report.py`. Tests: `tests/test_vip_report.py` (la invariante:
una celda no se nombra candidata sin sostener una cartera, y el gate corre **sin cap** de
concurrencia porque capear hace pasar cualquier cosa tirando señales).

### "El default de capacidad describe algún mercado" — 8x fuera, y la ventana elegía la cifra (2026-08-05, V3)
`tools/capacity_analysis.py` existía desde N8.4 y su propio docstring pedía "CALIBRARLOS
con volumen real". Nadie lo hizo en meses. Medido ahora contra las velas locales, el
default `avg_bar_notional=3e6` estaba **8x por debajo del BTC real** (2.563e7 USD por
barra de 5m) y el `stop_frac=0.012` era el doble del real (0.45–0.63%).

Y había algo peor que un default flojo: **`fill_bars` elegía la respuesta**. La ley raíz
es `impacto = Y·σ_ventana·√q`, pero el tool usaba σ **por barra** contra liquidez **por
ventana**, así que la capacidad escalaba con √fill_bars sin que nada lo delatara:

| fill_bars | C0 (σ sin escalar, lo que hacía) | C0 (σ escalada, correcto) |
|---|---|---|
| 1 | $12k | $12k |
| 6 | $70k | $12k |
| 24 (el default) | $282k | $12k |
| 96 | $1.126M | $12k |

`fill_bars` es **cómo troceas tu orden**, no una propiedad del mercado. El default de 24
estaba multiplicando la capacidad publicable por 24.

**Qué muere:** citar una capacidad de este repo anterior al 2026-08-05. No estaba
"aproximada": estaba compuesta de un volumen inventado, un stop inventado y una ventana
de ejecución que movía el resultado dos órdenes de magnitud.

**Invariante:** `require_measured` levanta `CapacityAssumedError` ante liquidez supuesta
y ante serie bruta sin `allow_ceiling=True`; sin velas locales el informe se para en seco
en vez de contestar con el catálogo. Tests: `tests/test_capacity_analysis.py`
(`test_capacity_is_invariant_to_fill_bars` fija la invariancia).

### La capacidad como defensa del producto — cinco dígitos, y por la razón equivocada (2026-08-05, V3)
La pregunta de V3 era de negocio: *¿a qué tamaño se muere esto?* Medido sobre el universo
VIP, celda tp4/h288, risk 1%/trade, con liquidez medida y Y=1:

| símbolo | bruto | C½ / C0 bruto | **neto** | **C½ / C0 neto** |
|---|---|---|---|---|
| BTC | +0.2912 | $308k / $1.2M | +0.0027 | <$1k / <$1k |
| ETH | +0.3220 | $162k / $650k | **+0.0586** | **$5k / $22k** |
| SOL | +0.1656 | $15k / $60k | −0.0539 | — |

**Todo el edge neto medido del producto cabe en ETH por debajo de ~$22k.** Es el escenario
"\$5k → servicio de señales" del brief, no el "\$500k → otra conversación".

**Pero la lectura honesta invierte la causa:** la capacidad del neto es ~cero **porque no
hay edge neto que escalar**, no por falta de libro. BTC mueve 2.6e7 USD por barra y a $1M
la orden es el 8.6% de una barra de 5m. La frontera donde el impacto iguala al coste fijo
por trade está en **$1.2M (BTC) / $434k (ETH) / $106k (SOL)**: por debajo manda el coste
fijo y **encoger la cuenta no arregla nada**.

**El hallazgo que conecta dos medidas viejas:** el impacto entra en R **dividido** por la
distancia al stop, así que el **stop apretado** del motor (0.45–0.63%) es lo que hace la
capacidad tan baja — y el 2026-06-30 se midió que **el stop apretado ES el edge**
(Q1 +0.316R vs Q4 +0.147R, pooled n=13.429). Lo que hace rentable a la señal es lo que la
hace frágil al tamaño. No son dos problemas: es un compromiso, y la salida natural
(ensanchar) ya está cerrada por cartera (2026-08-04).

**Qué NO muere:** el marco. La curva es útil y ahora está calibrada; lo que muere es la
esperanza de que "escalar" fuera una palanca. Reproducir: `python tools/capacity_analysis.py --vip`.

### "El sizing puede rescatar una celda sin edge" — f* = 0 en tres de cuatro (2026-08-05, V4)
La ergodicidad promete que dimensionar bien convierte una media en crecimiento. Medido sobre
el VIP (h288, neto, `growth.py`), con `f*` buscado sobre la distribucion REAL:

| celda | E[R] | g/trade | **f\*** | P(acabar arriba, 200 trades) |
|---|---|---|---|---|
| tp1 | −0.0692 | −0.000178 | **0.00%** | **21.2%** |
| tp2 | −0.0533 | −0.000142 | 0.00% | 31.4% |
| tp3 | −0.0179 | −0.000056 | 0.00% | 43.4% |
| tp4 | +0.0099 | +0.000010 | 0.20% | 51.0% |

**Tres de las cuatro celdas tienen f\* = 0**: ninguna fraccion positiva las hace crecer. No es
sizing mal puesto, es que no hay nada que dimensionar — la traduccion al idioma del crecimiento
de lo que V1 ya habia medido. **Qué muere:** la esperanza de que el tamaño de la apuesta sea una
palanca de rescate. Si μ ≤ 0, el sizing solo elige a qué velocidad se pierde.

**Qué NO muere, y es el hallazgo:** el punto ciego. `E[R]`, `IC95%` y `DSR` son **invariantes a
`f` por construccion** (`cube_report.apply_costs`: *"la R neta por trade sale invariante al
capital"*), asi que el sistema de medicion entero era incapaz de ver una sobre-apuesta. La cuenta
viva arriesga 0.25% contra un f\* de 0.20% — **1.2x, correcta por poco**, y hasta hoy nadie tenia
con que saberlo. Invariantes: `ArithmeticWithoutGrowthError` en `format_expectancy` y una sola
fuente para la fraccion (`GovernorConfig` ← `growth.configured_risk_frac`).

**Ojo con el texto de ergodicidad que origino esto:** el `1.5 × 0.6` supone apostar el **100%**
del capital. En multiplos de R a f=0.25% el arrastre es `f²σ²/2` ≈ 1e-5, invisible. **Medir en R
ya era la vacuna**; lo que faltaba era mirar `f`. Aplicar `μ − σ²/2` a nuestro +0.27R daria −2.12
y es un disparate — si alguien lo cita asi, esta mal.

### "Bajar a velas de 1m es lo que nos va a salvar" — medido, y son ~0.005R (2026-08-09)
Propuesta de RasDG: el order book cambia en segundos y leemos velas de 5m. La intuición es
correcta y el arreglo que sugiere va al revés. Dos medidas, las dos con número:

**(a) Operar señales de 1m — muerto por aritmética, sin correr nada.** El peaje es **fijo en
precio** y lo que capturas **escala con el timeframe**. Despejando de lo medido (`net=+0.0099R`
a stop 0.51%): capturas ~**12.5 bps** de movimiento por trade y pagas **12.0 bps**. A 1m, con
stop ~0.23% (σ/√5), capturarías ~5.6 bps y seguirías pagando 12 → **neto ≈ −0.28R**.

| stop | timeframe | coste en R (VIP0) |
|---|---|---|
| 0.51% | **5m, el de hoy** | **0.235R** |
| 0.23% | ~1m | 0.522R |
| 0.10% | scalp 1m | **1.200R** |

Por eso los que operan a esa velocidad tienen fees casi cero — y nosotros ya medimos que **no
bajamos de 4.32 bps** (pared, 2026-08-08). **Ir rápido amplifica justo la pared que nos mata.**
Corolario: la aritmética apunta al lado **contrario** (más ancho, no más rápido), y la regla de
salida es lo que hace la geometría ancha sostenible.

**(b) Velas de 1m para RESOLVER EL ORDEN INTRA-VELA — real, medido, y 10x demasiado pequeño.**
Ésta sí valía la pena: no toca el stop, solo la resolución. Mismas señales, misma geometría,
`max_bars` ×5 para cubrir el mismo tiempo de reloj. `python tools/geometry_sweep.py --intrabar
--vip`, n=3.565:

| celda | control 5m | control 1m | delta | vara |
|---|---|---|---|---|
| ancha (kSL=5, tpR=6) | +0.1087 | +0.1094 | **+0.0007** | 0.037 |
| **apretada (kSL=1, tpR=4)** | +0.0008 | +0.0054 | **+0.0045** | 0.070 |

**El signo es el esperado y la dirección es real** — la convención pesimista sí regalaba R. Pero
son **+0.0045R contra una brecha de +0.070R: el 6%.** Y algunas reglas salen PEOR a 1m
(techo T=288: −0.0414). **Qué muere:** el 1m como palanca de rescate. **Qué queda:** el sesgo
está medido en vez de supuesto, y las dos columnas siguen siendo COTA INFERIOR (dentro de una
vela de 1m tampoco se sabe el orden; la ambigüedad baja 5x, no desaparece).

**Error propio, corregido:** cité el **86% de ambigüedad** de `DIAGNOSTICO_E7_E8` para motivar
esto, y ese 86% se midió sobre la geometría **apretada** (tp4/h288, stop 0.51%), no sobre la
ancha — donde cruzar las dos barreras en la misma vela es raro. Citar el 86% fuera de su celda
prometía un arreglo que esa celda no necesitaba. El tool ahora lo imprime.

### Cuentas de fondeo (prop firms) al 1% por tiro — la vara más estricta, no la más blanda (2026-08-09)
Idea de RasDG: usar el sistema en cuentas fondeadas arriesgando <1% y cobrar payouts. Tres
números ya medidos la cierran, y ninguno es opinión:
- **El 1% es 5x sobre Kelly.** V4: `f* = 0.20%` en tp4 y **`f* = 0` en tp1, tp2 y tp3**. En la
  celda que opera hoy **ninguna fracción positiva hace crecer la cuenta**.
- **El max drawdown de una prop (6–10% total, 4–5% diario) es ~5x más estricto que la cota de
  35% del propio repo.** Nuestro DD medido a f=0.25% es **30.6%** (control) y **11.1%** con el
  trailing; a f=1% el control da **82.7%**. Breach casi seguro.
- **P(acabar arriba)=51% a 200 trades** con E[R]≈0: pasar la evaluación es un volado y **se paga
  por intento** → expectativa cero se convierte en negativa.
**Qué NO muere, y hay que comprobarlo:** el **tier de comisiones**. Cada bp vale +0.0436R; si una
firma diera 2 bps en vez de 4.32 serían **+0.10R**, más que toda la brecha. Se resuelve con un
correo preguntando el coste all-in por round-turn. Aviso: muchas prop de cripto son
CFD/sintéticas con spread MÁS ancho, así que puede salir al revés.
**Condición para revivir:** una celda con IC95% entero sobre cero **y** DD medido por debajo del
límite de la firma. Es el mismo gate de siempre.

### La regla de SALIDA dinámica — H1 ✓, H2 ✓, H3 ✗ (2026-08-08, pre-registrada)
Encargo `internal/BRIEF_SALIDA_2026-08.md`, ejecutado sobre la celda **pre-fijada** del
cementerio (kSL=5.0, tpR=6.0, h=1152), universo VIP, n=**3.565**, `n_trials=6` distintos
(la rejilla se declaró entera antes de correr). `python tools/geometry_sweep.py --exits --vip`.

**Lo que SÍ hace, y hace exactamente lo prometido** (contra el control de barreras fijas):

| salida | hold | DD@f=0.25% | skew | Sharpe/trade | NETO | brecha |
|---|---|---|---|---|---|---|
| control (barreras fijas) | 1.95 d | **30.6%** | +1.84 | 0.0530 | +0.1087 | −0.0368 |
| **A trail k=0.50** | 1.06 d | **11.1%** | +1.75 | **0.0740** | +0.0950 | **−0.0531** |
| A trail k=0.33 | 0.91 d | 10.8% | +0.62 | 0.0681 | +0.0746 | −0.0372 |

- **H1 (concurrencia) CONFIRMADA:** hold −0.88 días, **DD de 30.6% a 11.1%** a la `f` viva.
- **H2 (perfil) CONFIRMADA:** Sharpe por trade **0.0530 → 0.0740** (+40%).
- **Y sin peaje de muestra:** `n = 3.565` idéntica al control. Es **la única palanca medida en
  meses que no mueve la vara** — toda la diferencia de brecha (+0.0163) es real.

**Por qué muere igual — dos avisos que el propio tool imprime:**
1. **EL CONTROL YA CRUZA (brecha −0.0368).** La salida **no es** lo que hace pasar esto. Lo que
   cambió frente al cementerio no es la salida: es el **UNIVERSO** — 3 símbolos con velas en vez
   de los 13 del pool. La concurrencia escala con el número de símbolos, así que restringir el
   universo baja el DD **por aritmética, no por hallazgo**. Es una afirmación de SUBCONJUNTO,
   con su propia carga de multiple-testing (13 → 3), y choca de frente con este mismo cementerio:
   *"concentrar en los mejores símbolos — el liderazgo rota; los rezagados ganan OOS"*.
2. **El DSR se cae al contarlo de verdad:** A k=0.50 da **0.986 con `n_trials=6`** y **0.366** con
   la cota paranoica (504 = 84 × 6), que es la que cuenta la rejilla de 84 de la que salió la
   celda. Ninguna regla sobrevive.

**Qué muere:** la salida dinámica **como vía a candidato por sí sola**. **Qué NO muere:** el
mecanismo, que está medido y es grande — si algún día aparece edge bruto, esta salida lo
convierte en un producto con la mitad del drawdown y 40% más de Sharpe por trade. Es una palanca
de RIESGO real, no de edge. Misma familia que V4: convierte un edge en producto, no la falta de
edge en edge.

**Degeneración de la propia pre-registración, encontrada al correr y NO borrada:**
`be_trail(m=1.0, k=0.50)` resultó **matemáticamente idéntica** a `trail(k=0.50, arm=1.0)` — al
armarse con mfe≥1.0 el `max(0, ·)` nunca muerde. Producían la misma columna hasta el último
decimal. Se deja en la tabla marcada como duplicado (borrarla a posteriori sería reescribir la
pre-registración) pero **no cuenta como trial ni como evidencia independiente**: 7 declaradas → 6
distintas.
**Invariantes nuevas:** `bt_labeler.label_event_dynamic` construye el nivel de trailing SOLO con
las velas `0..i-1` (`LookaheadExitError`, `tests/test_exit_rule.py` lo comprueba con una serie de
futuro espectacular); hereda el pesimismo intra-vela de la cosecha; y una salida **no cambia `n`**.
Además el DD se reporta a la **`f` viva (0.25%)**, no al mínimo de la rejilla de fracciones —
informar el mínimo es informar el de la más tímida (0.1%), que da 13.1% en vez de 30.6%.

### "Bajar comisiones vale +0.06 a +0.09R y no depende de ningún research" — la pared de V3 por el otro lado (2026-08-08)
`BRIEF_FRONTERA_2026-08.md` la puso de palanca **#1**, "del tamaño de la frontera entera".
Medido con `tools/frontier_report.py` sobre el universo VIP (tp4/h288, n=3.774):

**La mitad que SÍ es aritmética se confirma:** cada punto básico de fee taker vale **+0.0436R**
(`coste_R = (2·fee + 2·slip)/stop_frac`, stop mediano 0.51%).

**La mitad que no lo es, mata la palanca.** El brief mismo avisó: *"lo que NO es aritmética es
qué tier alcanza de verdad una cuenta pequeña"*. Respuesta:

| escalón | taker | NETO | brecha | ¿alcanzable? |
|---|---|---|---|---|
| Binance VIP0 (base de TODO el repo) | 5.00 | +0.0099 | +0.0599 | sí |
| **Hyperliquid + referral (−4%)** | **4.32** | **+0.0396** | **+0.0303** | **sí — el techo real** |
| Binance VIP1 | 4.00 | +0.0536 | +0.0164 | **NO: pide $15M/30d** |
| Binance VIP4-ish | 3.00 | +0.0972 | **−0.0273** | requisito sin verificar |

La estrategia emite **~45 señales/mes** en el VIP; a la capacidad NETA que midió V3 ($22k) eso
son **$970.973/30d — 15x por debajo de VIP1**. Y VIP1 aún no cruza: cruzar pide bajar de 4.00 bps,
o sea escalones aún más caros de volumen.

> **El edge no sostiene la cuenta que haría falta para abaratar el edge.** V3 (capacidad) y la
> palanca #1 (comisiones) son **la misma pared vista por los dos lados**. No es una tarea
> pendiente, es estructural.

**Qué muere:** contar "bajar comisiones" como palanca de tamaño-frontera. **Vale +0.030R
alcanzables, no +0.06–0.09R.** Corrige la tabla del brief.
**Qué NO muere:** los +0.030R son reales y gratis (cambiar de venue + un código de referral).
**Invariante:** `FeeTierUnreachableError` — un tier no se cuenta sin comprobar su puerta contra
el throughput/capital de la cuenta, y falla **cerrado** (puerta no evaluable ≠ puerta cruzada).
Es la tercera vez que el repo publica una cifra apoyada en un supuesto mayor que el margen
entero: fill al 100% (V2), liquidez de catálogo (V3), tier de comisiones (aquí).
**Ojo con el escalón de 4.10 bps:** se compra inmovilizando HYPE. Es exposición **direccional a
un token** para subvencionar una estrategia sin edge demostrado; su varianza es órdenes de
magnitud mayor que los +0.010R que compra. `MAX_CAPITAL_LOCK_FRAC` lo deja a la vista.

### "La frontera son +0.07R" — no es una constante, y filtrar la aleja (2026-08-08)
El mismo brief la escribió como número fijo contra el que medir cualquier propuesta. **La
frontera es `-IC_lo` y depende de la n**, así que toda palanca que FILTRA señales sube la media
y **encarece la vara a la vez**. Medido (tp4/h288, VIP, palancas #1+#2 apiladas):

| configuración | NETO | Δ media | brecha | n |
|---|---|---|---|---|
| punto de partida | +0.0099 | — | +0.0599 | 3.774 |
| + comisiones alcanzables (4.32bps) | +0.0396 | +0.0297 | +0.0303 | 3.774 |
| + corte del tercil bajo de convicción | +0.0320 | +0.0220 | +0.0551 | 2.510 |
| **+ las dos** | **+0.0620** | **+0.0521** | **+0.0250** | **2.510** |

La media subió **+0.0521**, la brecha solo bajó **+0.0349**: **+0.0172R se los comió la vara al
moverse**. O sea que **un tercio de lo que el corte de convicción aparenta ganar es
contabilidad**. Apilando todo lo alcanzable la brecha se cierra un **58% y sigue sin cruzar**.
**Qué muere:** comparar una configuración filtrada contra la vara de la configuración sin
filtrar. Sin esta invariante, la forma más fácil de "acercarse a la frontera" en este repo sería
**filtrar más** — que es justo la forma de no acercarse.
**Invariante:** `frontier_gap` calcula la vara sobre la n de cada fila; `require_own_bar` levanta
`FrontierBarMovedError` ante una fila publicada sin ella.
**Corolario sobre la palanca #2 (convicción), medida neta por primera vez:** en tp4 aporta
+0.022R de media, de los que ~+0.017R se los come la vara → aporte real a la brecha **+0.005R**.
Y **en la celda que el motor OPERA (tp1) no rescata nada**: −0.0589R, IC95% [−0.107, −0.006],
entero bajo cero. **Encender `FQ_CONVICTION_LONGS` no arreglaría el producto vivo.**

### Copy-trading por leaderboard ("copiar a los que más ganan") — 1 de 100 (2026-08-05)
Origen: un vídeo de TikTok que un **inversor del proyecto** mandó a RasDG — "$1.000 →
$426.000 copiando a Trump", "el insider de Trump, 100% de acierto" — en un momento de
presión por ver producto rentable. Idea derivada: copy-trading de políticos (Autopilot,
que tiene API) + wallets de Hyperliquid (registro on-chain), con dashboard para
inversores privados.

**Medido antes de construir nada** (`tools/copytrade_screen.py`, ~10 min, cero capital).
Cohorte **congelada ex-ante**: top 100 por PnL allTime de las **41.276** cuentas del
leaderboard de Hyperliquid, sellada `2026-08-05T08:20:28Z`
(`internal/copytrade_cohorte_2026-08-05.json`). Ventana común y cerrada de 30d.

| Filtro | Caen | Quedan |
|---|---|---|
| Sin un solo fill en 30 días | **59** | 41 |
| Inalcanzables (≥20 fills/día) | **35** | 6 |
| Sin PnL neto positivo | 3 | 3 |
| Top trade > 50% del PnL | 1 | **2** |

De las 2 supervivientes, una ganó **$42 en 30 días**. Queda **1 de 100**.

**Qué muere:** el método de selección por leaderboard bruto. Entre las 41 activas la
mediana es de **887 fills/día** (p90 70.781, máx 212.245): el top de un perp DEX no son
direccionales copiables, son **market makers** — su PnL es el rebate y el spread, y
replicarlo con latencia y fees retail es pérdida garantizada. Es la misma razón por la
que los rankings brutos "apuntan al trader equivocado".

**Qué NO muere:** la pregunta de si existe algún clúster copiable. Sigue abierta y su
espejo está especificado (sin capital) en `internal/EXPERIMENT_COPYTRADE_ONCHAIN.md`.
Con **un snapshot y n=100** esto no puede afirmar más.

**Tres cosas estructurales que el screen dejó fijadas:**
1. **Lo verificable y lo copiable no coinciden.** On-chain se verifica en segundos pero
   la identidad no es atribuible (el "insider de Trump" es folklore: el rastro apunta a
   un ex-CEO de BitForex que lo niega). Los trades de políticos sí son atribuibles pero
   la STOCK Act da **45 días** — Autopilot y todo tracker copian *filings*, no
   operaciones (~2 semanas de retraso medio; cobran $100/año y **no custodian**).
2. **Multi-wallet, documentado en la propia wallet del vídeo:** el 10-oct-2025 transfirió
   $30M a otra address que abrió shorts de ETH. La unidad de seguimiento es el **clúster**,
   no la address. Las 59 inactivas son evidencia indirecta de rotación.
3. **La enfermedad es la de casa, agravada.** `fill_quality.py` midió selección adversa
   **−1.039R**; copiar a una ballena seguida por miles es esa dinámica con la multitud
   empujando en contra.

**Sesgos declarados, todos optimistas** (la realidad es peor): el neto no imputa la fee
de apertura ni el funding; el corte de 20 fills/día es juicio, no medición; las cuentas
capadas reportan cota inferior de su cadencia.

> **Esto SÍ está cerrado**: `tools/copytrade_screen.py` (con `--self-test`) +
> `tests/test_copytrade_screen.py` fijan el signo de la fee en el neto, la frontera del
> 50% y que un lote capado dé cota inferior — que es lo que colaría un market maker como
> "copiable". Reproducir: `python tools/copytrade_screen.py --top 100 --days 30`.

### Quantum cognition / igualdad QQ — fascinante, no aplicable
Único resultado cuántico-adyacente con dientes (predicción a priori sin parámetros para efectos
de orden en preguntas binarias, confirmada en 70 encuestas de EE.UU.). PERO solo sirve para
preguntas binarias de encuesta; los modelos ricos fallan (Grand Reciprocity: 65 de 72 fallan).
**No es samplable en order-flow.** No es para el motor.

---

## Lo que el filtro NO alcanzó a adjudicar (honesto — ausencia ≠ evidencia en contra)
De `research/fisica_moderna_2026.md` §3. Temas sin las 3 verificaciones; nota de la fase de
extracción:
- **Random Matrix Theory / Marchenko-Pastur** — "probablemente el puente física→finanzas no
  examinado más fuerte". Real, pero limpia correlación de un cross-section de muchos activos; el
  motor es direccional por símbolo. Útil solo si se construye un feature cross-asset.
- **TDA / homología persistente, path signatures, termodinámica estocástica (irreversibilidad
  vía grafo de visibilidad + KL)** — matemática real, pero **retrospectivas** (detectan la
  inestabilidad *después*). Posibles descriptores de régimen, no señales líderes.

---

## La máquina de verdad — `tools/validation_gate.py`
Tres métodos que hay que PASAR juntos (no uno solo):
- `deflated_sharpe_ratio(returns, n_trials, sr_trials_std)` → P(Sharpe > vara) tras corregir
  multiple-testing. **Significativo si DSR > 0.95.** `n_trials` = configs realmente barridas (no 1);
  la vara sube con cada trial.
- `probabilistic_sharpe_ratio(...)` → no asume normalidad; usa skew + kurtosis reales.
- `pbo(perf_matrix)` → Probability of Backtest Overfitting. ¿La mejor in-sample queda bajo la
  mediana OOS? PBO alto = selección sobre-ajustada.

Pure stdlib + numpy, **sin scipy** (normal CDF vía `math.erf`, inverso por Acklam).

### Workflow estándar (espejo para todo candidato)
1. `fetch_binance_vision_*` (data GRATIS, causal) →
2. `validate_*.py` (feature causal, alineado al cube) →
3. cuadrante 2×2 (confirmado vs no-confirmado) →
4. **test de ortogonalidad** (¿suma DENTRO del CVD-confirmado? uplift > ~0.02 → apila; < → redundante) →
5. DSR del tier premium (CVD✓ & candidato✓): > 0.95 → CABLEADO; < → no pasa, honesto.

---

## Resumen de honestidad operacional
- **Pasó el gate y se cabla:** CVD (DSR ✓, cableado); F2-persistencia (DSR ✓, cableado dormido).
- **Pasó el gate pero es redundante:** F1 impacto (standalone fuerte, within-CVD negativo → no suma).
- **Falla el gate (cementerio científico):** quantum finance, LPPL, Khrennikov, early-warning,
  rough-vol — refutados o infalsables.
- **Esperando veredicto:** OI, global_ls, toptrader_ls, taker_ls — validadores y workflows listos.

**El principio: medida o muerte.** Si no pasas el gate honesto (DSR > 0.95 + ortogonalidad), no
entras al motor. Fin.

_Citas: `research/fisica_moderna_2026.md`, `research/fisica_moderna_2026_resultados.md` (run
28287771057), `tools/validation_gate.py`, `tools/validate_*.py`, workflows `physics_confirm.yml` /
`oi_validation.yml` / `global_ls_deepdive.yml` / `metrics_validation.yml`, `volume_profile.py`,
`tools/measure_vp_tier.py`. Actualizado 2026-06-29._
