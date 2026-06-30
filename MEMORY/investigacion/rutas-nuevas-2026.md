# Rutas nuevas de investigación — FQ (ideación 2026-06-30)

> Encargo de RasDG: *"idea rutas nuevas que aporten desde estructura, motor, premios,
> investigación, vanguardia."* Esto es **ambición con disciplina**: cada idea trae su
> **experimento measure-first** (qué computar causalmente por barra, qué hipótesis, qué data
> —idealmente gratis—) para que pase por el **mismo gate** que validó el CVD (DSR/CPCV/PBO,
> `tools/validation_gate.py`). Regla de la casa: **lo que transfiere vs. el humo**. "Medida o muerte."
>
> **Antes de proponer, leí el CEMENTERIO** (como manda `00-INDICE`). Por eso aquí **NO** re-propongo
> lo ya muerto — y lo digo explícito en §0.B para no volver a caer. Lo de abajo es lo que **sigue
> vivo** o **nunca se adjudicó**. Nada es promesa; son hipótesis a gatear.

---

## §0.A — Estado de las rutas de premios (lo que pediste recuperar/parquear)

- **Ruta A — Numerai Crypto: ACTIVA, ahora con pipeline real.** `tools/numerai_crypto_pipeline.py`
  (5 tests verdes): `data.binance.vision` (klines 5m, gratis) → `build_submission` (KL+POC+momentum) →
  **CSV de submission `symbol,signal`**. Corre end-to-end hoy (`--self-test` ✓). Fit DIRECTO del bot,
  sin reframe a acciones. **Última milla (con credenciales):** bajar el universo real (≥100 tokens) y
  subir con `numerapi` + tu API key; confirmar columnas vs docs.numer.ai/numerai-crypto.
- **Ruta B — académica (preprint SSRN + grants EF): PARQUEADA, no olvidada.** Preprint en inglés listo
  (`preprint-fq-en.pdf`); SSRN da la bienvenida a independientes → va directo al botón. EF Grants exige
  *prior research* → SSRN primero. Ver `premios-competencias-2026.md`. **En la fila, prioridad media.**
- **2ª pasada de deep-research — EN VUELO** (`premios-gap-research`): competencias, funded-traders
  cripto, allocators forward, journals. Actualiza el §3 al cerrar.

## §0.B — Lo que NO re-propongo (ya en el cementerio, con su razón)

| Idea muerta | Por qué murió (CEMENTERIO.md) |
|---|---|
| **Rough volatility / Hurst H~0.1** | **Artefacto de estimación** (Cont-Das 2022): el sesgo del estimador inventa la rugosidad; la vol real ~H 0.5. No pasaría DSR. |
| **Critical slowing-down / early-warning** | Sin tendencia pre-crack en 5 mercados / 4 cracks; los cracks **no son** transiciones críticas físicas. |
| **Quantum-cognition / interferencia en el flujo** | El único resultado con dientes (igualdad QQ) **solo** sirve para preguntas binarias de encuesta — **no es samplable en order-flow**. |
| **Quantum finance (Baaquie) · LPPL (Sornette) · Khrennikov** | Refutados 3-0: el path-integral útil es clásico (ya lo es `quantum_timelines.py`); LPPL es diagnóstico no predicción; Khrennikov es infalsable por diseño. |
| **F1 impacto · Hurst-de-precio** | Reales pero **redundantes within-CVD** (sustituyen, no suman). F2-persist es la versión que apila. |

> Si una idea de abajo roza una de estas, lo marco. **Lo nuevo no re-abre lo cerrado sin dato nuevo.**

---

## §1 — ESTRUCTURA (cómo el proyecto compone conocimiento)

**1.1 Meta-labeling (López de Prado) — el puente RIGUROSO de "convicción" → "edge validado".**
Hoy la convicción (P_master, φ/κ/σ_τ, overlay ICT) es **heurística**; los edges validados son
CVD/F2/KL/POC. Meta-labeling los une bien: **primario** = el fire del motor; un **meta-modelo**
predice P(este fire gana) desde {CVD, F2, KL, POC-dist, régimen}. Modo honesto de graduar convicción.
- *Measure-first:* etiqueta triple-barrier sobre el cube; entrena con **CPCV** (no IID); juez = uplift
  en R y DSR del meta-modelo, no accuracy. Data: ledger/cube. *Transfiere:* sí (misma escuela del gate).

**1.2 Cerebro como monitor de DSR-rolling (edge-decay early-warning) — el gate CONTINUO.**
El gate hoy es de una vez. El cerebro (Etapas 1-3) puede correr **DSR rodante por edge** sobre el ledger
vivo y **auto-degradar convicción** al deflactarse. "Validado una vez" → "vigilado siempre".
- *Measure-first:* DSR/CPCV rodante por edge; alerta de decaimiento. Barato, defensivo, alto valor.

**1.3 Ensemble régimen-condicional de edges (no la suma naive).**
CVD/F2/KL/POC pagan cada uno en su régimen (F2 en BTC/XRP/BCH/LTC —**nunca ETH**—; KL en irrev-bajo;
POC lejos del valor —**nunca BNB**). Aprende **pesos condicionados al régimen**, no plano.
- *Measure-first:* pesos por bucket sobre el cube, CPCV; vs. baseline de suma. *Humo-flag:* sobreajuste
  fácil → pocos regímenes, mucha CPCV.

---

## §2 — MOTOR (features causalmente samplables; SOLO lo vivo / no-adjudicado)

**2.0 Lo más barato primero: 4 candidatos con validador YA ARMADO esperan un run.** Antes de la
frontera, el cementerio lista **OI, global_ls (contrarian), toptrader_ls, taker_ls** con validador +
workflow listos — veredicto pendiente de **ejecución**, no de investigación. *La "ruta nueva" de mayor
ROI es correr esos 4 y gatearlos.* (Esfuerzo: dispatch + lectura. Posible edge inmediato o cementerio.)

**2.1 √-impact para SIZING (Donier-Bonart) — no señal, TAMAÑO de clip.**
La ley raíz-cuadrada (que ya fundamenta el CVD) predice slippage por participación → úsala para
**dimensionar** el clip óptimo. *Distinto* a F1 (que murió como *señal* redundante); aquí es ejecución.
- *Measure-first:* slippage realizado vs. √-law sobre los fills maker/taker del ledger; calibra el clip
  que maximiza R **neto**. Data: el ledger. *Transfiere:* microestructura establecida; plomería con base.

**2.2 RMT / Marchenko-Pastur — "el puente física→finanzas no examinado MÁS FUERTE" (palabras del propio
research).** Limpia la matriz de correlación de un cross-section (autovalores de ruido vs. señal). Hoy no
aplica porque el motor es direccional por-símbolo; **se vuelve real con un feature CROSS-ASSET** (lo
natural cuando el cerebro tenga multi-símbolo).
- *Measure-first:* sobre retornos de N tokens, separa el espectro Marchenko-Pastur (ruido) del resto;
  el "modo de mercado" + factores limpios → régimen cross-asset / co-movimiento como feature gateable.
- *Transfiere:* **sí, robusto** (Bouchaud-Laloux-Potters). Requisito: construir el cross-section primero.

**2.3 Path signatures (Lyons) — features de CONTEXTO para el meta-labeler (NO señal líder).**
La firma truncada del camino (precio, CVD) codifica la *forma* del flujo en features deterministas.
**Honesto (nota de extracción del propio research):** firma/TDA/termo son **descriptores
RETROSPECTIVOS** — detectan inestabilidad *después*, sirven como **régimen/contexto**, no como señal
adelantada. Por eso su lugar es alimentar el meta-labeler (§1.1), no disparar.
- *Measure-first:* términos de firma nivel-2 sobre la ventana pre-fire; uplift incremental en el
  meta-modelo bajo CPCV. *Humo-flag:* explosión de dimensiones → truncar bajo, regularizar, OOS.

**2.4 Profundizar KL (familia entropía-producción) — el beachhead YA validado.**
KL-irreversibilidad (visibility-graph) es el edge de régimen cross-símbolo validado (DSR ✓ cube, vive en
irrev-BAJO). *Honesto:* KL ya captura el núcleo; esto es **deepening** (una medida continua de lo mismo),
no edge nuevo. Bajo riesgo, retorno incremental. Pendiente: ETH + forward + n_trials honesto.

---

## §3 — PREMIOS (capital / competencia)  ·  _se enriquece al cerrar el deep-research_

- **Numerai Crypto (Ruta A) — ACTIVA**, pipeline listo. Submit sin stake (paper) → OOS vivo → stake NMR
  solo cuando el edge se vea forward. ⭐ menor fricción.
- **Kaggle quant comps (Jane Street RT, Optiver Close/Vol) — candidata fuerte.** Credential-blind,
  medible, con premio; el feature-engineering + el harness compiten directo. *Confirmar en la 2ª pasada.*
- **Funded-traders cripto + allocators forward** — track record → capital, con bandera roja (≈7% cobran;
  80+ firmas cayeron en 2024). *Detalle en vuelo.*
- **Lead/copy-trading de exchange (Binance/Bitget/BingX)** — publicar la estrategia = track record público
  + comisiones. Fit directo para un signal bot.

---

## §4 — INVESTIGACIÓN (publicable; la metodología, no "un bot que gana")

**4.1 Ruta B (parqueada):** preprint SSRN (listo) → luego EF Academic Grants.
**4.2 El edge KL como paper empírico novel:** irreversibilidad temporal por visibility-graph que predice
régimen mean-reverting en cripto-perps — limpio y novedoso para **Physica A / Quantitative Finance**.
Medido cross-símbolo (`research/cross_asset_kl_2026-06.md`).
**4.3 El gate con LEDGER FORWARD real como contribución de método:** casi ningún paper retail trae un
registro OOS forward con DSR/CPCV/PBO. **El forward es el activo escaso.**
**4.4 Estudio de transferencia cross-asset:** qué edges son universales (KL/precio/ICT) vs. del venue
(order-flow CVD/F2 — F2 paga en 4/6, nunca ETH; POC nunca BNB). Empírico, honesto, citable.

---

## §5 — VANGUARDIA (moonshots; con bandera de humo donde toca)

- **RL para EJECUCIÓN (no para señal)** — timing/sizing maker-taker con reward = R **neto** de fees. Real
  y usado en la industria; la señal sigue gateada, esto optimiza el *cómo*. **Frontera aterrizada.**
  *Measure-first:* simular políticas sobre el ledger de fills; reward R neto; vs. la regla taker+maker actual.
- **Optimal transport / Wasserstein como coordenada de régimen** — distancia entre la distribución de
  retornos reciente y una referencia. *Honesto:* cae en la familia **descriptor retrospectivo** (como
  path-sig/TDA) → contexto para el meta-labeler, no señal líder. *Measure-first:* W-distance rodante;
  uplift dentro de CVD.
- **Tensor-networks / "ventaja cuántica" para correlación multi-símbolo** — 🚩 **ilusorio a esta escala:**
  RMT/Marchenko-Pastur (§2.2) ya hace el de-noising real, barato y robusto. Usar RMT; tensor-networks solo
  con cientos de símbolos, si acaso.
- *(Quantum-cognition / interferencia en el flujo: **descartado** — §0.B, no es samplable en order-flow.)*

---

## §6 — Priorización (qué tocar primero)

| # | Idea | Eje | Prob. de pasar gate | Esfuerzo | Estado |
|---|---|---|---|---|---|
| 1 | Correr los 4 candidatos armados (OI/global_ls/toptrader/taker) | Motor | Variable (validador listo) | **Bajo** | esperando run |
| 2 | Meta-labeling (convicción→edge) | Estructura/Motor | **Alta** | Medio | propuesto |
| 3 | DSR-rolling edge-decay (cerebro) | Estructura | **Alta** | Medio | propuesto |
| 4 | Numerai Crypto (Ruta A) | Premios | — (competencia) | **Bajo** (pipeline ✓) | **ACTIVO** |
| 5 | √-impact sizing | Motor/Ejecución | Media-alta | Bajo | propuesto |
| 6 | RMT cross-asset de-noising | Motor/Estructura | Media (req. cross-section) | Medio | propuesto |
| 7 | Ensemble régimen-condicional | Estructura | Media | Medio | propuesto |
| 8 | Path signatures → meta-labeler (contexto) | Motor | Media-baja (descriptor) | Medio-alto | propuesto |
| 9 | Paper KL / gate-forward | Investigación | — (publicable) | Medio | Ruta B-adyacente |
| 10 | RL ejecución · OT régimen | Vanguardia | Incierta | Alto | moonshot |

**El hilo conductor:** todo enchufa al **gate** (medir antes de creer) y al **ledger FORWARD**, que es
el activo que abre —a la vez— allocators (performance live), research (resultados forward) y capital
(track record). Construir el forward es construir las tres puertas. Lo barato-y-alto-valor primero
(#1, #2, #3, #5); los moonshots (#10) solo cuando el measure-first los respalde. **Y nada re-abre el
cementerio sin dato nuevo.**

---

_Fuentes: `MEMORY/CEMENTERIO.md` (lo muerto y lo armado), `research/fisica_moderna_2026_resultados.md`
(F2/F1/Hurst medidos), `research/fisica_moderna_2026.md` §3 (RMT = puente más fuerte sin examinar;
firma/TDA = descriptores retrospectivos), `research/cross_asset_kl_2026-06.md`, `tools/validation_gate.py`,
`tools/numerai_crypto_pipeline.py` + `tools/numerai_signals_features.py` (Ruta A),
`MEMORY/investigacion/premios-competencias-2026.md`. Ideación 2026-06-30; hipótesis a gatear, no promesas.
Actualizar §3 al cerrar `premios-gap-research`._
