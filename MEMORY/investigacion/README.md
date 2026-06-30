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
- **`tools/numerai_signals_features.py`** (+ test) — *Scaffold ruta A.* Reframea los features
  VALIDADOS que TRANSFIEREN (KL-irreversibilidad, POC-distance, momentum) a una submission de
  **Numerai Signals** (ranking [0,1] por acción). `build_submission({ticker: ohlcv_df})`. La
  combinación es una hipótesis a tunear con el OOS en vivo de Numerai (CVD/F2 NO transfieren).

## Cómo endurecerlo (paso a rigor pleno, después)
1. Tablas y figuras **reproducibles** desde el repo (DSR/CPCV/PBO, curvas forward, cubes).
2. **Referencias completas** con DOI; verificar cada cita primaria.
3. Versión en **inglés** para arXiv (q-fin) / SSRN; alinear con el formato de la revista
   objetivo (Quantitative Finance / Physica A / J. of Portfolio Management).
4. Sección de **resultados forward** cuando el ledger acumule ≥30–50 fills.

_El review y el deck citan el registro real de la memoria (`CEMENTERIO.md`,
`DECISIONES.md`, `ESTADO.md`) y `tools/validation_gate.py`. Una sola verdad para todos._
