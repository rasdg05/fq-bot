# Investigación — obras de apertura del proyecto FQ

> Memoria de las obras de investigación/divulgación del proyecto. **Aquí va TODA obra
> que salga de esto** (presentaciones, reviews, papers) — directiva de RasDG (2026-06-29).

## Contenido

- **`review-fq.md`** + **`review-fq.pdf`** (+ `.html`) — *Review científico (preview).*
  Revisión del sistema FQ y su metodología anti-sobreajuste: el gate (DSR/CPCV/PBO,
  López de Prado), los edges validados (CVD, F2, KL, POC-distance), la distinción
  convicción vs edge validado, la extensión cross-asset (data/venue), y el cementerio.
  **Estado: PREVIEW** — completo en estructura, a endurecer (datos reproducibles,
  figuras, citas con DOI) antes de someter a revista.

- **`perfil-academico.pdf`** (+ `.html`) — *Presentación (8 láminas).* El perfil de
  quien desarrollaría esto (físico/matemático → quant), las piezas y sus fundadores
  (López de Prado, Bouchaud, Lillo/Farmer, Parrondo/Lacasa, Mantegna/Stanley), dónde se
  estudia (Cornell, Oxford, Princeton, CMU, ETH…), y el giro: hecho de forma autodidacta
  desde Ciudad de México, con un bot que **ES la tesis**.

- **`fig-poc-distance.png`** + **`tools/reproduce_gate_results.py`** — figura y script que
  **REGENERAN** los resultados del review (gate POC-distance sobre los 5 cubos cripto) desde el
  repo: tabla far/near por símbolo + veredicto pooled (DSR/CPCV/PBO). Es el Apéndice B del review,
  reproducible de punta a punta.

- **`preprint-fq-en.md` / `.pdf`** (+ `.html`) — *Preprint en INGLÉS, SSRN-ready.* Versión en inglés
  del review con los resultados reproducibles (Apéndice B + figura). Es el documento citable para
  someter a SSRN / arXiv q-fin. Mismo contenido, listo para audiencia académica internacional.
- **`tools/numerai_signals_features.py`** (+ test) — *Scaffold ruta A.* `build_submission({símbolo:
  ohlcv_df})` → ranking [0,1] por símbolo. Sirve para **Numerai Signals** (acciones — reframe de
  KL/POC/momentum) **Y para Numerai Crypto** (CONFIRMADO, crypto.numer.ai — **fit DIRECTO** del bot,
  símbolos de tokens; en cripto CVD/F2 **también** aplican, versión más rica). Combinación = hipótesis
  a tunear con el OOS en vivo.
- **`tools/numerai_crypto_pipeline.py`** (+ test) — *Ruta A, ahora END-TO-END.* `data.binance.vision`
  (klines 5m, gratis) → `build_submission` → **CSV de submission `symbol,signal`**. Corre hoy
  (`--self-test` ✓, 5 tests verdes). Credential-free hasta el archivo; la última milla (universo real
  ≥100 + upload) va con `numerapi` + tu API key. **Es la pieza que vuelve a Ruta A algo ejecutable, no
  solo documentado.**
- **`rutas-nuevas-2026.md`** — *Ideación de rutas nuevas (encargo de RasDG, 2026-06-30).* Estructura /
  motor / premios / investigación / vanguardia — cada idea con su **experimento measure-first** para
  pasar el gate, y la honestidad de siempre (transfiere vs. humo; respeta lo ya medido: F2 gana,
  F1/Hurst-precio redundantes). Incluye el estado de Ruta A (activa) y Ruta B (parqueada).
- **`ejemplo-rendimiento-10k.pdf`** (+ `.html` + `fig-ejemplo-rendimiento.png`) — *Ejemplo práctico HONESTO
  (2026-06-30):* ¿qué hubiera rendido $10,000 MXN en el bot los últimos 2 meses arriesgando 3.6%/trade?
  Sobre el **set VIP REAL de 5 símbolos** (SOL/BTC/ETH/BCH/BNB — **sin LINK**, que el código tiene ON por
  default pero NO se broadcastea; RasDG confirmó). 3 pasos: 3.6% bruto **+401%** → 3.6% neto **+49%**
  (costos comen ~70%, DD −45% por sobre-apalancamiento) → **0.4% neto +6%** (el número creíble, n=137).
  Lección registrada: el número **depende del set** y la ventana de 2m **miente** (BCH lastre / LINK héroe
  en la ventana, al revés de por vida → se juzga forward). Reproducible: **`tools/sim_paper_return.py`** (+ test).
- **`ejemplo-rendimiento-10k-2pct-tp1.pdf`** (+ `.html` + `fig-ejemplo-2pct-tp1.png`) — *Config recomendada
  (RasDG eligió 2% · TP1, 2026-06-30):* sobre el VIP actual **SOL/BTC/ETH**, 2%/trade neto → **+79%**
  ($10k→$17,893), piso $8,234 (−18%); vs 3.6% (+177% pero DD −30%). **Aclaración clave en el PDF:** usa
  **TODAS las señales del motor paper** (el cube) = el VIP **si `FQ_KL_FILTER` está OFF** (default); con el
  filtro ON el VIP sería un subconjunto KL-bajo. Recomendación: 2% en TP1 (sobrevive para probar el edge forward).
- **`senales-vip-2meses-3.6pct.pdf`** (+ `.html` + `fig-vip-tps.png`) — *Señales VIP filtradas (2026-06-30,
  tras prender `FQ_KL_FILTER`).* Sobre los últimos 2 meses: **37 señales pasaron a VIP** (54% de las 68 del
  motor, ~18/mes) y su rendimiento a **3.6%** por los **4 TPs**: TP1 **+119% (DD −10%)** ⭐, TP2 +89%, TP3
  +68%, TP4 +69% (DD −25%). Reco: **TP1 + 2% sizing**; TP2/TP3 no aportan; menos señales = filtro funcionando.
  PAPER sobre racha buena (irrev del filtro = proxy de klines Binance); el real lo dará el forward en vivo.
- **`rutas-capital-operativas-2026.md`** — *Planes operativos de capital (decisión RasDG, 2026-06-30).*
  Las 3 rutas greenlit con plan concreto y capital-en-riesgo explícito: **Numerai Crypto** (GO, medir 3
  sem sin-stake → stakear), **Breakout** (estrategia para pasar el challenge: sizing 0.4% por el WR bajo
  + 6% DD, solo señales apiladas, paciencia gratis sin límite de tiempo), **Darwinex Zero** (cómo
  funciona + el caveat data/venue: ¿perps o CFD?). Academia deprioritizada hasta forward (no se regala
  la salsa).

## Cómo endurecerlo (paso a rigor pleno, después)
1. Tablas y figuras **reproducibles** desde el repo (DSR/CPCV/PBO, curvas forward, cubes).
2. **Referencias completas** con DOI; verificar cada cita primaria.
3. Versión en **inglés** para arXiv (q-fin) / SSRN; alinear con el formato de la revista
   objetivo (Quantitative Finance / Physica A / J. of Portfolio Management).
4. Sección de **resultados forward** cuando el ledger acumule ≥30–50 fills.

_El review y el deck citan el registro real de la memoria (`CEMENTERIO.md`,
`DECISIONES.md`, `ESTADO.md`) y `tools/validation_gate.py`. Una sola verdad para todos._
