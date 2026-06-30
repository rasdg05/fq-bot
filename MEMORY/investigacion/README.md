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
