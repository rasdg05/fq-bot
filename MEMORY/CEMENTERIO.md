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
- **Status:** **VALIDADO en cube, PENDIENTE forward.** No cableado. Falta ETH + forward + n_trials honesto.

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
- **Status (POC-distance):** **VALIDADO en cube (gate ✓), PENDIENTE forward** — mismo estatus que KL.
  NO cableado. Próximo: medir forward (flag dormido) antes de subir conviction. Zona y rev-aligned: muertos.

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
