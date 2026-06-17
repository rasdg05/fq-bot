# FQ — Plan de la capa de RETRIEVAL (expectancy por analogía sobre turbovec)

> Estado: **planeación, sin código**. Documento de diseño para una capa de
> recuperación k-NN (estimador LOCAL no-paramétrico) que se enchufa al harness
> `bt_*` existente, symbol-agnóstica, evaluada en paralelo sobre **SOL/USDT** y
> **BTC/USDT** para decidir con números una eventual migración de capital a BTC.
>
> Tesis a VALIDAR (no asumir): codificar cada estado de mercado como vector,
> indexar el histórico con su desenlace forward adjunto, y en cada señal nueva
> recuperar los `k` análogos → *expectancy* empírica + WR + dispersión +
> confianza del vecindario. Complementa al LightGBM global. Si la expectancy OOS
> **colapsa** al hacer el índice estrictamente causal, **la tesis es falsa** y se
> mata la línea (eso es un resultado válido del F0, no un fracaso).

---

## 0. Decisiones de alcance cerradas

| Decisión | Elección | Implicación de diseño |
|---|---|---|
| **TF del vector/labels** | **5m señal** + 15m/1h/4h como contexto **dentro** del vector | Más densidad para el k-NN; obliga a re-rejillar el replay y a alinear HTF de forma estrictamente causal (un bar 1h/4h sin cerrar = leakage). Cambia las unidades de la barrera vertical. |
| **Historia BTC** | **48+ meses** | Máxima densidad pero mete régimen 2020–2022 → **obliga** a recencia/decaimiento/evicción agresivos. La no-estacionariedad pasa de "deseable" a "make-or-break secundario". |
| **k / bit_width** | **Práctica recomendada** → arranque `k=50`, `4-bit`, con barrido de calibración | 4-bit por recall (~0.4–1 pt vs FAISS). `k=50` da estimación estable y a la vez sensible a la esparsidad de SOL (clave para abstención). Se calibra en F1, no se asume. |
| **Topología del índice** | **Por-símbolo (separado)** | Un `IdMapIndex` por `símbolo/exchange`, persistido aparte. Código symbol-agnóstico; sólo cambia la ruta del artefacto. Encaja con "separación de datos, no de código". |

### Huecos del enunciado vs. realidad del repo (declarados por honestidad)

1. **No existe** un módulo de "frontera TP×horizonte" como artefacto. Hoy hay
   una **escalera TP1–TP4** (`calculate_levels`) + **barrera vertical** `max_bars`
   en `bt_labeler`. El "selector de TP/horizonte" (F3) requiere **construir
   primero** ese cubo de desenlaces (extender `bt_labeler` a multi-TP × multi-horizonte).
2. **El modelo de costos es estático**, no per-símbolo (`bt_engine.CostModel`:
   `taker_fee=5bps`, `slippage=1bp`, `funding_8h=1bp`). Hay que **re-tunear por
   símbolo** (BTC más fino que SOL) — es un parámetro, no código nuevo.
3. **No hay `--seed` global**. `bt_train` fija `random_state=42`. La capa de
   retrieval debe **hilar un `--seed`** por las partes con aleatoriedad
   (calibración por muestreo, cualquier bootstrap, LightGBM con features extra).
4. **Fricción del TF 5m con el motor**: `fusion_engine.evaluate_signal` espera
   `(df_15m, df_1h, df_4h, df_1m)` y está tuneado para disparar en 15m
   (`TF_PROFILES`). **Resuelto** (§3.0): se adopta la **Opción A** — motor en 15m
   nativo, label/query snapeados a la rejilla 5m; Opción B (motor a cadencia 5m)
   queda como respaldo si la densidad no alcanza.

---

## 1. Pipeline de datos BTC y convivencia multi-símbolo

### 1.1 Descarga (reutiliza `bt_data` / `tools/build_dataset.py`)

El layout en disco YA es por símbolo/exchange:
`data/<exchange>/<symbol>_<tf>.parquet` (p.ej. `data/okx/BTC-USDT_5m.parquet`).
No hay que tocar `bt_data`; sólo correr el descargador con `--symbol BTC/USDT`.

```
# BTC: 48 meses, mercado swap, en TFs 5m (señal) + 15m/1h/4h (contexto)
for TF in 5m 15m 1h 4h; do
  python tools/build_dataset.py --symbol BTC/USDT --timeframe $TF \
      --market swap --years 4 --exchanges okx
done
```

- **Exchange**: `okx` por defecto (Binance da HTTP 451 en runners; ya es el
  default del workflow). BTC en swap perpetuo para casar funding con SOL.
- **5m a 48 meses** es el dataset pesado (~500k velas). `bt_data` ya pagina,
  deduplica y audita gaps (`check_continuity`); **registrar el reporte de gaps**
  como artefacto (un gap no detectado en 5m corrompe la alineación causal HTF).
- **Costo BTC**: re-tunear `CostModel` con spread/slippage/funding reales de BTC
  (más finos). Defaults adoptados: `taker_fee = 5 bps` (igual), `slippage_bps = 0.4`
  (BTC más líquido que el `1.0` de SOL), `funding_8h` desde el histórico real del
  par. Sensibilidad a `slippage` hasta `2×` exigida en el criterio de migración (§6.3).

### 1.2 Convivencia de datasets

- Los datos **nunca se mezclan**: cada símbolo vive en su carpeta de exchange.
- Artefactos de retrieval **paralelos** a los datos (ver §4.4):
  `retrieval/<exchange>/<symbol>/{index.turbo, scaler.pkl, outcomes.parquet, meta.json}`.
- `.gitignore`: `data/` y `retrieval/` quedan fuera del repo (como hoy `data/`);
  son artefactos locales/CI, no fuente.

---

## 2. Especificación del vector de estado (symbol-agnóstica)

Objetivo: un vector que (a) capture el estado del motor en la vela de señal, (b)
respete el **contexto/régimen** para que los vecinos sean comparables, y (c) sea
**symbol-agnóstico** (las mismas features se computan idénticas en SOL y BTC).

### 2.1 Bloques de features (todas ya emitidas por `evaluate_signal`)

| Bloque | Features (claves reales del `report`/`field`) | Tipo |
|---|---|---|
| **Convicción motor** | `p_master`, `p_master_raw`, `kappa_evo`, `alpha_hybrid`, `w_effective`, `h_factor`, `f_confluence`, `f_ict`, `n_concepts` | continuo |
| **Scorer ensemble** | `scorer_total`, `scorer_volume`, `scorer_structure`, `scorer_liquidity`, `scorer_concept_stack`, `scorer_history` | continuo |
| **Régimen / volumen** | `regime_score`, `vol_score`, `session_bias_mult`, `sync_score`, `sigma_tau` | continuo |
| **Estructura (field)** | `confluence_count`, `pd_pct` | continuo |
| **Contexto HTF (nuevo, derivado de OHLCV)** | retornos y ATR-normalizados de 5m/15m/1h/4h, pendiente EMA50/EMA200, distancia a EMA, posición en rango | continuo |
| **Categóricas** | `killzone`, `tier`, `direction`, `bias_4h`, `bias_1h`, `regime_state`, `node_type` | one-hot acotado |

El **bloque HTF** es la clave para que la distancia "respete el régimen": sin él,
dos estados con idéntico `p_master` pero en tendencia vs. rango caen como vecinos.
Se computa en el replay 5m con los `htf_window` causales ya existentes.

### 2.2 Escalado, whitening y normalización (anti-leakage)

Orden de transformaciones, **ajustado SOLO con datos pasados** (rolling, por fold):

1. **Robust-standardize** (mediana/IQR, no media/std → resistente a colas de cripto)
   de los bloques continuos. `fit` sobre la ventana de entrenamiento del fold.
2. **Categóricas** → one-hot con **escala fija pequeña** (p.ej. ±0.5) para que no
   dominen el producto interno (un one-hot de norma 1 aplastaría a las continuas).
3. **PCA/ZCA-whitening opcional** (decorrelaciona; muchas features del motor están
   correlacionadas y se "doble-cuentan"). Se introduce como **ablación en F1**
   (test #2), no por defecto. `fit` sobre pasado.
4. **L2-normalize** del vector final → el producto interno de turbovec = **coseno**.

**Regla dura de no-leakage por normalización**: el `scaler`/`PCA` se ajusta con
las velas cuyo desenlace ya cerró antes del inicio del fold de test. Nunca con el
test. Se persiste el `scaler` del fold para reproducir la query exactamente.

### 2.3 Dimensión

- Continuas (~25) + HTF (~12) + one-hot (~15) ≈ **~50 dims** crudas.
- Con PCA-whitening → comprimir a **~32 dims** (ablación F1).
- `IdMapIndex(dim=~32–52, bit_width=4)`. La dim se congela en `meta.json` por símbolo.

### 2.4 ¿Régimen/tiempo dentro del vector?

- **Régimen**: SÍ, vía el bloque HTF + `regime_state` one-hot (distancia consciente
  de contexto).
- **Tiempo absoluto**: **NO** en el vector (sesga la geometría y empuja a "el vecino
  más reciente" por construcción). La no-estacionariedad se trata por **decaimiento
  + evicción** en el estimador y el ciclo de vida del índice (§3), no metiendo `t`
  en la distancia. (Se podrá testear una coordenada de régimen-coarse como ablación.)

---

## 3. Ciclo de vida del índice en walk-forward (ingest causal + embargo + evicción)

### 3.0 TF de señal 5m — decisión: **Opción A** (práctica recomendada)

Se adopta la **Opción A** como diseño por defecto y la B queda como experimento de
respaldo, no como bloqueante:

- **Opción A (ADOPTADA)**: el motor sigue **disparando en 15m** (su TF nativo,
  `TF_PROFILES` intactos), pero el **entry/label se resuelve en la rejilla 5m** y
  la query del vector se **snapea al bar 5m** del fire → más resolución temporal y
  densidad **sin re-tunear el motor ni arriesgar regresión**. Es la opción de menor
  letalidad y preserva la comparabilidad con el track SOL existente.
- **Opción B (respaldo)**: re-correr el motor a **cadencia 5m** (pasar `df_5m` como
  primario). Más señales pero exige **revisar `TF_PROFILES`** (`PMASTER_MIN`,
  cooldowns) y re-validar que el motor no se degrada. Sólo se explora en F1 **si**
  la densidad de A resulta insuficiente para BTC (riesgo #6).

Racional: la densidad extra de B no compensa el riesgo de mover el TF nativo del
motor antes de probar la tesis. Primero validamos retrieval con el motor intacto
(A); si la densidad limita, escalamos a B. **Sin tocar `fusion_engine`** en ningún
caso (sólo cómo lo alimenta `bt_features`).

### 3.1 Causalidad estricta (make-or-break)

En la query del tiempo `t`, el índice **sólo** puede contener estados `s` cuyo
desenlace **ya cerró** antes de `t`:

```
available_at(s) = exit_index(s) + embargo      # exit_index = bar real de
                                               # resolución (TP/SL/timeout)
condición de elegibilidad:  available_at(s) < t
```

- Se usa el **bar real de salida** (`exit_index`), no `max_bars`, porque el
  desenlace ya es histórico y conocido — pero **siempre** con `embargo` de margen
  contra autocorrelación/solape (consistente con `bt_walkforward` que ya purga +
  embarga).
- **Doble enforcement de causalidad**:
  - **Grueso (por fold)**: el walk-forward **crece** el índice añadiendo sólo
    eventos resueltos antes del inicio del fold de test menos embargo ("ingest
    online", `add_with_ids`). El índice nunca se construye "de golpe".
  - **Fino (por query)**: dentro del fold, la **allowlist** de `search` restringe a
    los `ids` con `available_at < t` (y, opcionalmente, a régimen compatible).

### 3.2 Desenlace forward adjunto (side-table)

turbovec guarda **sólo** `(vector, id:uint64)`. El desenlace vive en una tabla
lateral `outcomes.parquet` indexada por el mismo `id`:

```
id → { entry_index, exit_index, available_at, regime_state,
       pnl_r@tp1, pnl_r@tp2, pnl_r@tp3,          # por nivel TP
       pnl_r@h{H1,H2,H3} ,                        # por horizonte (barrido)
       outcome, mfe_r, mae_r }
```

Este cubo `(TP × horizonte)` es el que **F3** consume y el que hay que construir
extendiendo `bt_labeler` (ver §1, hueco #1).

### 3.3 No-estacionariedad: decaimiento + evicción (crítico con 48m)

- **Ventana rodante + evicción dura** (default `W = 12 meses`): `IdMapIndex.remove(id)`
  para `ids` más viejos que `W`. Mantiene el índice en régimen vivo y acota memoria.
  Barrido `W ∈ {6, 12, 18, ∞}` como test #3.
- **Decaimiento de recencia** en el estimador (default **half-life = 90 días**, i.e.
  `τ ≈ 130 días`): el peso de cada vecino decae `exp(-age/τ)` al promediar
  expectancy/WR (no en la distancia). Barrido de `τ` como test #3.
- **Filtro de régimen** por allowlist: opción de recuperar sólo vecinos de
  `regime_state` compatible (ablación; cuidado con vaciar el vecindario en SOL).

### 3.4 Estimador del vecindario (lo que produce la query)

Para cada señal en `t`: `scores, ids = index.search(q, k, allowlist)` →

```
expectancy_r   = Σ w_i · pnl_r_i / Σ w_i      # w_i = recencia × similitud
wr             = Σ w_i · 1[win_i] / Σ w_i
dispersion     = std ponderada de pnl_r_i
n_in_radius    = nº de vecinos con score ≥ umbral de similitud
confidence     = f(n_in_radius, dispersion)   # alta n + baja dispersión = alta
best_tp, best_H= argmax sobre el cubo (TP×horizonte) del pnl_r del vecindario
```

**Abstención** cuando el vecindario es ralo (default: `n_in_radius < k/2 = 25`
vecinos con `coseno ≥ 0.6`): la capa **no opina** y deja pasar la decisión base del
motor+LightGBM. Esto es clave para la comparabilidad y para SOL. El piso de
similitud (`0.6`) y de conteo (`k/2`) se calibran en F1 (test #4).

### 3.5 Persistencia por símbolo

`retrieval/<exchange>/<symbol>/`:
- `index.turbo` — `IdMapIndex.write/.load` (estado final de producción).
- `scaler.pkl` — scaler/PCA ajustado (por fold en research; final en producción).
- `outcomes.parquet` — side-table id→desenlace.
- `meta.json` — `dim`, `bit_width`, `k`, lista/orden de features, ventana de fit,
  `W`, `τ`, versión del vector (para detectar drift de esquema).

---

## 4. Diseño de integración (empezar read-only) — módulo `bt_retrieval.py`

Módulo **nuevo, symbol-agnóstico**, que envuelve turbovec y se enchufa al harness
**sin tocar `fusion_engine`** ni el motor de producción.

API conceptual (no código): `build_vector(field, report, htf_ctx) → vec`;
`fit_scaler(past_df)`; clase `StateIndex(add, query_causal(vec, t, regime, k) →
stats, persist/load)`. Se llama desde `run_research_real.py` tras `replay_events`.

### Las 4 integraciones, en orden de menor letalidad (diagnóstico → decisión)

| Uso | Qué hace | Cómo entra | Fase |
|---|---|---|---|
| **(d) FEATURE** | añade `expectancy_r/wr/dispersion/n/confidence` como columnas extra al `X` del LightGBM | columnas en `bt_train`; ablación mide lift de AUC/expectancy | F4 (read-only puro) |
| **DIAGNÓSTICO** | loguea los stats del vecindario junto a cada evento; **no altera** fire/size/TP | columna extra en el DataFrame de eventos | **F1** |
| **(a) GATE** | veta señales con `expectancy_r < umbral` **y** `confidence` suficiente; **abstiene** si ralo | filtro post-replay, pre-engine | F2 |
| **(b) SIZING** | multiplicador kappa-like ∈ `[lo, hi]` desde expectancy/confianza | factor sobre `risk_frac` en la **capa de decisión** (no en el motor) | F2 |
| **(c) SELECTOR TP/H** | elige `(TP, horizonte)` que pagó en estados similares | usa el cubo §3.2; requiere extender `bt_labeler` | F3 |

**Principio**: nada decide hasta que el **diagnóstico read-only (F1)** demuestre
edge condicional OOS. El gate/sizing (F2) sólo se activa si F1 es positivo y pasa
los tests de leakage.

### 4.5 CI (`research.yml`) — nuevos inputs

Mismo flujo que SOL, se añaden inputs `workflow_dispatch` (con defaults benignos):
`retrieval_enabled` (bool), `retrieval_mode` (`diagnostic|gate|sizing|selector|all`),
`retrieval_k`, `retrieval_bit`, `retrieval_window_months` (`W`), `retrieval_decay`
(`τ`), `seed`. El job corre **por símbolo** (matriz SOL/BTC) para la tabla comparativa.

---

## 5. Registro de riesgos — cada uno con el TEST que lo falsea

| # | Riesgo (letalidad) | TEST que lo falsea | Señal de FALLO |
|---|---|---|---|
| **1** | **Leakage/causalidad** (make-or-break) | (a) **A/B oracle vs causal**: índice con futuro vs estrictamente causal → comparar expectancy OOS. (b) **Placebo de etiqueta**: barajar `id→outcome` → debe colapsar a ~breakeven. (c) **Barrido de embargo** 0→grande → expectancy estable, no decreciente. | Edge sólo existe en el oracle; placebo conserva edge (bug); expectancy decae al subir embargo. |
| **2** | **Vector domina por varianza / coseno mal escalado** | Ablación de escalado: raw vs robust-standardize vs +PCA-whitening; medir expectancy OOS y "feature dominance" (varianza explicada por dim). | Una feature/one-hot acapara la similitud; whitening no cambia nada o empeora. |
| **3** | **No-estacionariedad** (vecinos de régimen muerto) | Barrido de `W` (ventana) y `τ` (decaimiento): expectancy OOS vs tamaño de ventana. Comparar índice "todo el histórico" vs "rodante". | Expectancy mejor con ventana corta ⇒ los viejos contaminan; o monotonía rara que delata régimen. |
| **4** | **Confianza/esparsidad** (clave en SOL) | Curva expectancy OOS vs `n_in_radius`; política de abstención con piso variable. Medir % de abstención por símbolo. | Expectancy plana respecto a confianza (el estimador no discrimina) o SOL abstiene ~siempre ⇒ capa inútil en SOL. |
| **5** | **Aproximación de turbovec** | Comparar vecinos turbovec (4-bit / 2-bit) vs **exacto** (brute-force coseno / FAISS flat) en una muestra: recall@k y **Δexpectancy estimada**. | Δexpectancy fuera del ruido ⇒ la cuantización degrada la señal; bajar a 4-bit o subir dim. |
| **6** | **Migración SOL→BTC sin densidad real** | Medir densidad efectiva (mediana `n_in_radius`) y volumen de señales por símbolo; condición de migración §6. | BTC no alcanza el piso de densidad ⇒ la ventaja teórica no se materializa. |

El **test #1 es la puerta de F0**: si la expectancy OOS colapsa al hacer el índice
estrictamente causal, **se documenta y se mata la tesis**. Es el resultado más
valioso posible de la fase.

---

## 6. Evaluación, ablación y criterio de migración

### 6.1 Ablación por símbolo (vara idéntica)

Variantes, corridas con OOS y costes reales, **por símbolo**:

```
motor-solo
+ lightgbm
+ retrieval-feature        (d)
+ retrieval-gate           (a)
+ retrieval-sizing         (b)
+ retrieval-selector       (c)
+ todo
```

Métricas OOS **idénticas** (lenguaje de `bt_metrics`/`ledger_stats`):
`expectancy_r, win_rate, profit_factor, Sharpe, Sortino, Calmar, maxDD, n_trades,
turnover, % abstención, ruin`. Con **IC bootstrap** (semilla fija) sobre el lift
de retrieval frente a motor+lightgbm.

### 6.2 Tabla comparativa BTC vs SOL

Una tabla con las mismas columnas para ambos símbolos, en ventanas OOS
equivalentes (mismo nº de folds y equivalente en barras), incluyendo densidad
(`mediana n_in_radius`, % abstención) y costes retuneados por símbolo.

### 6.3 Criterio explícito de migración SOL→BTC (umbrales adoptados)

Mover capital a BTC **sólo si TODO** se cumple OOS (umbrales por defecto; se
re-anclan una sola vez tras F1 con la dispersión real observada):

1. **Edge neto**: `expectancy_r(BTC, +todo)` ≥ `expectancy_r(SOL, +todo)` **y**
   `expectancy_r(BTC, +todo) ≥ +0.05 R` neto de costes **y** `PF(BTC) ≥ 1.3`.
2. **Lift atribuible**: el límite **inferior del IC bootstrap al 90%** del lift de
   retrieval sobre motor+lightgbm en BTC es **> 0** (el edge viene de la capa, no
   del azar). Semilla fija (`--seed`), `n_boot ≥ 2000`.
3. **Densidad fiable**: `mediana n_in_radius(BTC) ≥ k/2 = 25` **y**
   `% abstención(BTC) < 30 %` (la ventaja de densidad de BTC es **real**, no
   teórica) — riesgo #6.
4. **Robustez a costes**: con `CostModel` de BTC retuneado (`slippage 0.4 bps`) el
   edge neto sobre-vive a `2× slippage` (sigue cumpliendo el punto 1).
5. **Sin leakage**: BTC pasa los tests #1–#5 igual que SOL (en particular, el
   barrido de embargo no muestra decaimiento de expectancy).

Resultado posible: si BTC gana en (1)–(2) pero **falla densidad (3)**, la
conclusión es "la tesis escala con datos pero aún no hay señal accionable" → seguir
ingiriendo (o escalar a la Opción B del §3.0), **no migrar capital todavía**.

---

## 6.4 Estado de implementacion (F0 + F1 CONSTRUIDOS)

> Construido y verde en CI sintetico (89 tests). Falta el pase con datos reales
> de mercado (lo dispara el dueno del repo: este entorno no llega a exchanges y
> la integracion no tiene permiso de Actions:write).

- **`bt_retrieval.py`** — backend enchufable `ExactBackend` (numpy, fuente de
  verdad) / `TurbovecBackend` (IdMapIndex 2/4-bit, padding a multiplo de 8) tras
  el mismo contrato; `StateVectorizer` (robusto + L2-norm, fit causal); estimador
  de vecindario (expectancy/WR/dispersion/confianza/abstencion con recencia);
  `retrieval_oos` (modos causal/oracle/placebo) + `retrieval_ablation`.
- **`tests/test_bt_retrieval.py`** — TEST DE LEAKAGE como puerta (causal recupera
  senal real; placebo colapsa; sin-senal no inventa edge; embargo estable) +
  aproximacion turbovec≈exacto. 12 tests; suite total 89 verde.
- **`tools/run_research_real.py`** — paso `[5]` retrieval read-only (no decide) +
  `--seed` global + costos por simbolo (BTC slippage 0.4bps vs SOL 1.0) + volcado
  `--retrieval-json`.
- **`tools/compare_retrieval.py`** — tabla SOL-vs-BTC + criterio de migracion §6.3.
- **`.github/workflows/research.yml`** — inputs `retrieval/_backend/_k`, cache de
  Parquet por exchange+symbol+meses (descarga 48m una vez), instala turbovec.

### Como correr F0+F1 (datos reales)

**Via CI** (Actions -> "Research" -> Run workflow, branch
`claude/turbovec-retrieval-planning-62SLU`):
- SOL: exchange=okx, symbol=SOL/USDT, months=24, step=1, retrieval=true.
- BTC: exchange=okx, symbol=BTC/USDT, months=48, step=2 (replay dentro de 90min).
El artefacto `research-report` trae la tabla de ablacion + veredicto de leakage.

**Via Railway/local** (sin timeout; recomendado para BTC 48m):
```
for TF in 15m 1h 4h; do
  python tools/build_dataset.py --symbol BTC/USDT --timeframe $TF --market swap --years 4 --exchanges okx
done
python tools/run_research_real.py --exchange okx --symbol BTC/USDT \
    --max-bars 96 --n-splits 7 --embargo 8 --seed 42 \
    --retrieval --retrieval-k 50 --retrieval-json retrieval_BTC.json
# idem SOL/USDT --years 2 -> retrieval_SOL.json
python tools/compare_retrieval.py retrieval_SOL.json retrieval_BTC.json
```

---

## 6.5 BTC — veredicto SELLADO con baseline honesto (run #30, 12-jun-2026)

> **SELLO (run #30, id 27415283709, post-fix de reloj §6.7, commit a8b092c):**
> **BTC NO es candidato a gate ORO** — pero por la razón CORRECTA, no la del
> run #26. Con killzones reales el motor **SÍ dispara en BTC** (223 señales /
> 48m, 8.6× las 26 del #26): el diagnóstico bug-era "el motor casi no dispara
> en BTC" era un artefacto del reloj. El problema real es el mismo de SOL:
> **edge bruto positivo que los costes en R se comen** (+0.207R pre-coste →
> −0.068R neto OOS), y un retrieval denso sin edge causal limpio (REVISAR →
> índice no persistido, correcto). El no-persist sigue siendo el sistema
> funcionando.

**Números del run #30 (BTC/USDT 48m, 5m, step 3, seed 42, inputs default):**
- Cadencia: **223 fired / 48m** evaluando 1 de cada 3 velas (~4.6/mes en
  replay ≈ ~1.1/sem; en vivo algo más). La Fase D ya no estrangula: mata
  2.56% de las velas, no la historia entera.
- Funnel: pre_check 53.0% + direction 37.1% (≈90% muere en el campo, sano),
  C 5.14%, D 2.56%, B 1.67%, p_master 0.23% (317 near-miss: mediana 1.264,
  p90 1.805 vs `PMASTER_MIN=1.95`), vol_veto 84, rr 75 → fire 223 (0.16%).
- Etiquetadas (in-sample, pre-coste): WR 55.2%, **+0.244R**.
- **OOS con costes** (n=191, fees+slip 0.4bps+funding): expectancy
  **−0.0679R**, WR 55.0%, **PF 0.865**, maxDD −26.2%, Sharpe −0.44.
- Pre-coste pooled OOS: **+0.207R** → la carga media de costes es
  **≈0.28R/trade** (stops apretados de BTC convierten ~10bps round-trip en
  ~0.3R). El edge bruto existe; muere en la unidad R del stop, no en el motor.
- Grid TP×H OOS con costes: el óptimo es `tp1/h288 = −0.068R` — **la config
  actual ya es la mejor celda y aún así es negativa**; grid SL×ATR: ninguna
  celda OOS positiva. No hay rescate por TP/SL estático.
- LightGBM: AUC OOF **0.408** (no discrimina en BTC fired); VIP modelo top5%
  +0.51R con n=10 (anécdota).
- Retrieval denso: `causal +0.0067` (≈0) · `placebo −0.090` · `oracle +1.462`
  → **REVISAR** → índice NO persistido. El esparso (fired-only) dio "OK" con
  causal +0.166 pero `gate_pass n=8` — anécdota; **no habilita** reconstruir
  artefacto (eso exige el DENSO en `leakage_ok`, §6.7 paso 2).
- Quantum (Eje A): lift **−0.288R, NO SUMA** (2ª vez consecutiva);
  `qt_sync_score` sigue siendo dimensión 100% NaN (muerta) incluso con el
  bloque ON → si algún día se reintenta el bloque, revisar el extractor antes
  (nota técnica; prioridad baja porque el bloque no suma).

**Números del run #26 (bug-era, solo historial):** 26 fired/48m, exp_r OOS
+0.0229R n=22, denso causal +0.0453 REVISAR. Medidos con killzone vacía toda
la historia (§6.7): **no comparables**; se conservan como forense del bug.

**Causa de los warnings "All-NaN slice" (`bt_retrieval.py:301`):** bug de
ESQUEMA, no específico de BTC. `extract_features` leía `regime["score"]`,
pero `regime_detector.detect_regime()` nunca emite esa clave (emite
`state/flags_fired/n_flags/recommend/details`) → `regime_score` llegaba
**100% NaN en TODOS los símbolos**. Verificado en el artefacto SOL del mismo
run: `scaler.pkl` con `center_=NaN` SOLO en `regime_score` (y 98 warnings en
el log de SOL, 96 en BTC). Fix jun-2026: fallback `regime_score = n_flags`
(0..3 votos de deriva) en `bt_features.extract_features`, con test de
regresión usando la forma REAL del detector. Notas:
- El artefacto SOL **desplegado** es inmune al fix: su `center_=NaN` anula esa
  dimensión en `transform` (NaN→0) con o sin valor vivo → el vector de la
  query en producción NO se desalinea del índice.
- En el fit DENSO `regime_score` seguirá esparso (~99.9% NaN): el motor solo
  computa la capa ML cerca del fire (diseño, no bug). Donde revive de verdad
  es en los fits sobre señales FIRED (ablación Eje A, gate VIP), con cobertura
  100%. La telemetría del vectorizer ahora separa "100% NaN exacto = dimensión
  MUERTA" del esparso por diseño para que esto no se confunda otra vez.
- Los `qt_sync_score`/`qt_sigma_tau` 100% NaN bajo `emergent_time=false` son
  comportamiento documentado del bloque quantum (§2.4/bt_retrieval), no bug.

**Evaluación contra §6.3 (run #30, SELLADA):**

| Criterio §6.3 | BTC run #30 (honesto) | ¿Pasa? |
|---|---|---|
| 1. Edge neto ≥ +0.05R y PF ≥ 1.3 | −0.068R, PF 0.87 (n=191 OOS) | NO |
| 2. Lift IC90 > 0 atribuible | causal denso +0.0067 ≈ 0 | NO |
| 3. Densidad fiable | 223 fired/48m (mejor que #26) pero retrieval esparso sigue ralo (`gate_pass n=8`) | NO |
| 4. Robustez a costes | el edge bruto +0.21R no sobrevive ni a 1× costes en R | NO |
| 5. Sin leakage (tests #1–#5) | denso REVISAR (placebo no colapsa del todo, oracle ≫ causal) | NO |

**Decisión (sellada):** NO desplegar nada de BTC; SOL sigue siendo el único
gate vivo (§9.2.1, con su caveat de §6.7). La verificación post-fix pedida por
la versión anterior de esta sección **se ejecutó** (run #30): `regime_score`
ya NO aparece como dimensión muerta (fix verificado; queda esparso ~99.8% por
diseño en el denso) y el denso siguió REVISAR → veredicto sellado. El camino
F4 para BTC se **reformula**: su problema NO es densidad de disparo (eso era
el bug) sino **calidad neta en unidades R** — las palancas reales son el mapa
de segmentos de sesión (§6.8: ny_am_kz +0.455 OOS pre-coste es su mejor
franja), el selector F3 (TP/horizonte por estado) y/o stops menos apretados
(la carga de costes baja proporcionalmente al ancho del stop).

**Fractal cruzado SOL #30 vs BTC #30 (la prueba anti-espejismo de §6.7):**
ver el veredicto completo en §6.8. Resumen: la franja **corta/bajista de SOL
NO replica en BTC — se INVIERTE** (BTC: LONG +0.294 vs SHORT +0.134; bias
alcista ≥ bajista) → dirección/bias es **beta del período** de cada símbolo,
no alpha del motor. Lo que SÍ replica es estructura de **sesión**:
`london_open_kz` no paga en ninguno (SOL −0.066 n=43 / BTC +0.038 n=33,
pre-coste ≈0 = claramente negativo neto, y en ambos es bucket grande),
`silver_bullet_lo` paga en ambos (+0.310/+0.275), viernes fuerte en ambos
(+0.372/+0.464), lunes flojo en ambos (−0.204/+0.028), madrugada 00-08utc
negativa en ambos (n chico).

---

## 6.6 F2.5 — CADENCIA: poda de módulos + funnel (jun-2026)

> **✅ 12-jun-2026 — números RE-MEDIDOS con el run #30 (post-fix §6.7).** Los
> del run #26 (629 fired, gate_pass 20…) eran ficción de reloj y quedan solo
> como historial. El método y los criterios de esta sección no cambian.
> La poda en sí corre en el **run #31** (`ablation=true`, lanzado 12-jun
> ~15:45Z): veredictos VIVE/MATAR pendientes de ese run.

> Problema: la cadencia de señales es demasiado baja para el negocio Y para
> los datos que F3 necesita. Palanca elegida (la segura): **poda de módulos
> OOS** — subir cadencia quitando peso muerto, NO bajando umbrales a ciegas.
> El umbral ORO no se toca: más fired ⇒ más candidatos ORO en proporción,
> con la calidad del gate intacta.
> **Lente del #30 (baseline OOS NEGATIVO):** multiplicar señales con
> expectancy negativa multiplica pérdida. El hallazgo valioso de la poda ya
> no es "qué quitar para disparar más" sino **qué módulo DAÑA** (retirarlo
> MEJORA expectancy, delta<0 en su variante sin-él). Calidad primero,
> cadencia después.

**Números honestos (run #30):**
- SOL: **183 fired / 24m a step=2** ≈ 7.6/mes en replay (**~1.8/sem**; en
  vivo algo más, cooldowns aparte). In-sample +0.136R pre-coste; **OOS
  −0.095R neto (n=156, PF 0.84)**. Near-miss p_master: n=273, mediana 1.337,
  p90 1.843 vs `PMASTER_MIN=1.95` (hay pila bajo el umbral, pero con OOS
  negativo NO se abre el grifo — regla de oro).
- BTC: **223 fired / 48m a step=3** (~1.1/sem). Ya no está fuera por
  cadencia (§6.5 sellado); su poda no corre en CI (la matriz de `ablation`
  deja solo SOL por presupuesto de minutos).
- ORO en vivo: el techo teórico del #26 (confident 8.6%, ~4/sem brutas) se
  midió con el gate de la ficción NY; se re-deriva cuando un denso dé
  `leakage_ok` y se reconstruya el artefacto (§6.7 paso 2 — aún NO ocurre:
  #30 dio REVISAR en ambos símbolos).

### ✅ SELLO de la poda — run #31 (id 27426619247, SOL 24m step 3, 12-jun-2026)

> Baseline del #31 (step 3, otra muestra): 124 fired/24m, **OOS +0.0182R
> (n=106, PF 1.02, WR 54.7%, Sharpe 0.12, maxDD −12.5%)** — primer baseline
> NO-negativo. In-sample +0.234R. Ojo: el run vive para los DELTAS de la
> ablación, no por el absoluto (step distinto al #30).

**Veredictos `[ablacion]` (re-replay fires-only con cada módulo OFF):**

| módulo OFF | exp_r sin él | delta | n fired | label log | DECISIÓN real |
|---|---|---|---|---|---|
| `scorer` | +0.0182 | **0.0000 exacto** | 124 (=base) | MATAR | **NO matar** |
| `regime` | +0.0182 | **0.0000 exacto** | 124 (=base) | MATAR | **NO matar** |
| `session_bias` | −0.0028 | **+0.0210** | 112 (<base) | VIVE | **VIVE (crítico)** |

**Interpretación (el label crudo del runner ≠ la regla de §6.6):**

1. **session_bias VIVE y es el módulo que SOSTIENE el edge.** Quitarlo hunde
   el baseline de **+0.0182 a −0.0028** (a negativo). Aporta +0.021R, MÁS que
   el baseline entero. Sale de la cuarentena del ENGINEERING_PLAN confirmado
   como el activo más valioso del motor en este período, no como candidato a
   poda. (Y baja cadencia al quitarlo: 124→112, porque su multiplicador
   empuja señales sobre `PMASTER_MIN`.)

2. **scorer y regime NO se matan, por DOS razones independientes:**
   - **(a) `delta=0.0000` EXACTO con n idéntico = additivos inertes para el
     DISPARO, no peso muerto removible.** `fusion_engine:704` lo dice: la capa
     ML "scorer ensemble + regime (additivos, **no afectan P_master**)". Su
     única palanca sobre la decisión es el downgrade combinado
     (`regime==deriva` Y `scorer<ENSEMBLE_MIN`, `fusion_engine:727`), que **no
     se activó en ninguna de las 124 señales** del período (si lo hubiera
     hecho, apagarlos habría cambiado n o expectancy). El label `[MATAR]` del
     log es binario (`delta>0`→VIVE, else→MATAR) y NO incorpora la condición
     de cadencia de §6.6: **MATAR exige `delta≤0` Y `+20%` de n**. Aquí
     `Δn=0%` (124→124, no compran NADA de cadencia) → **no califican**.
   - **(b) Apagarlos en prod ROMPERÍA el gate ORO.** 7 de las 13 features del
     vector de retrieval (`DEFAULT_NUMERIC`) vienen de ahí: `scorer_total`,
     `scorer_volume`, `scorer_structure`, `scorer_liquidity`,
     `scorer_concept_stack`, `scorer_history`, `regime_score`.
     `FQ_USE_SCORER=0`/`FQ_USE_REGIME=0` dejaría esas columnas NaN en el
     state-row vivo → el vector de la query se desalinea del índice → el
     clasificador ORO se degrada en silencio. `delta=0` sobre el MOTOR no
     implica `delta=0` sobre el GATE.

**Conclusión: la poda NO mata ningún módulo. Cero cambios de prod.** Resultado
válido y tranquilizador: el motor no tiene peso muerto removible por env, y su
edge magro (+0.018R) descansa en `session_bias`. La cadencia NO se compra
apagando ML (no mueven n). Las palancas reales de calidad quedan donde ya
están medidas: **veto de sesión (§6.8 F2.6)** y **ejecución maker (§6.10, la
más grande)** — ninguna es "matar un módulo". El near-miss del #31 (n=172,
mediana 1.405, p90 1.879 vs `PMASTER_MIN=1.95`) sigue mostrando pila bajo el
umbral, pero con baseline +0.018R la regla de oro manda: calidad primero.

**Las dos herramientas (ya cableadas en esta rama):**
1. **Funnel de decisiones** (gratis, en CADA run): el replay denso ahora
   registra `(decision, failed_at)` por vela y el runner imprime
   `[1.4/4] Funnel del motor` + quantiles de `p_master` de los near-miss vs
   `PMASTER_MIN`. Dice DÓNDE mueren las velas candidatas (fases A–D, killzone,
   vol_veto, p_master, RR…) — el mapa para elegir qué relajar.
2. **Poda OOS** (`ablation=true`, opt-in): re-replay fires-only con cada
   módulo OFF (`scorer` / `regime` / `session_bias`) y veredicto VIVE/MATAR
   por delta de expectancy OOS, con `n` por variante (= cuánta cadencia
   compra quitarlo).

**Runbook de la poda (SOL primero, como se decidió) — UN solo checkbox:**
- Actions → Research → Run workflow → branch
  `claude/turbovec-tp-cube-hardening-fvzdx7` → marcar **solo `ablation`** →
  Run. El workflow de la rama hace TODO lo demás en modo poda: la matriz
  dinámica deja **solo SOL** (4 replays de BTC 48m no caben en el techo de
  350min), el step efectivo sube a **3** (~55min/replay → ~4h las 4
  variantes; ~420 señales por variante bastan para el veredicto) y los
  extras (`retrieval`/`tp_sl_grid`/`quality_gate`/`vector_ablation`) se
  fuerzan OFF para que todo el presupuesto vaya a los replays. El funnel
  [1.4/4] y el cubo TP×H siguen ON (no cuestan replays).
- Leer en el log: `[ablacion] ... [VIVE|MATAR] <modulo> sin_el expectancy_r=…
  delta=… (n=…)` + el funnel para el siguiente candidato.

**Criterio de decisión (antes de tocar producción):**
- **REGLA DE ORO (fijada por el usuario, jun-2026): si elevar la cadencia
  empeora la expectancy OOS (o degrada WR sin que la expectancy lo compense),
  NO se hace.** La cadencia nunca se compra con calidad.
- **MATAR** un módulo solo si `delta ≤ 0` (quitarlo NO empeora expectancy OOS)
  **y** sube `n` de forma material (≥ +20%). Aplicación en prod = env del
  worker (`FQ_USE_SCORER=0` / `FQ_USE_REGIME=0` / `FQ_SESSION_BIAS=0`),
  reversible, con confirmación explícita del usuario.
- Si los 3 módulos ML VIVEN, el siguiente candidato sale del **funnel**
  (p.ej. `PMASTER_MIN` del TF profile si los near-miss se apilan bajo el
  umbral; o el gate A–D que más mate). Eso ya es re-tunear el motor: mismo
  estándar — re-run de research con el cambio, comparar OOS y **re-validar el
  gate ORO (leakage_ok) antes de redeployar el artefacto**.
- `gold_top_pct` NO se toca en esta fase: primero cadencia del motor; el
  umbral ORO se revisa con el digest y 2–4 semanas de paper (regla del plan:
  si ORO < 2–3/semana sostenido, replantear umbral).

**Edge por SEGMENTO — localizar el fractal explotable (jun-2026):**
El runner imprime `[2.5/4] Edge por segmento` y persiste
`segments_<sym>.csv`: expectancy/WR/n/maxDD condicional por **killzone,
bloque horario UTC (4h), día de semana, tipo de nodo, dirección y bias 4h**,
sobre la cartera OOS pooled (o in-sample etiquetado como tal). Es la versión
LEGIBLE del retrieval: dónde (sesión/horario/setup) el sistema es
consistentemente rentable, para explotarlo de forma comprobada y replicable.
- **Estándar anti-espejismo**: con tantos cortes siempre hay un grupo "bueno"
  por azar. Un segmento se considera candidato si `ok_n` (n ≥ 10 OOS) y
  expectancy claramente > 0; se **explota** (p.ej. gate por killzone/horario)
  solo tras (1) repetirse en una segunda corrida con datos frescos, y
  (2) sobrevivir el mismo estándar que la poda (OOS + gate ORO re-validado).
  El retrieval k-NN ya es el explotador GENERAL de estos fractales (el gate
  ORO condensa "estados similares pagaron"); el segmento legible sirve para
  entenderlo, comunicarlo y endurecer reglas de sesión si el dato lo respalda.

**Datos para F3 (selector TP/horizonte por vecindario) — "meter más señales
concluidas":**
1. **Cubo por evento persistido** (nuevo, en cada run): el runner vuelca
   `tp_cube_<sym>.parquet` — formato largo evento × {tp1..tp4} × horizonte
   con outcome/pnl_r/MFE/MAE **+ features del motor** (la tabla de
   entrenamiento del selector, §3.2). Con los números del run #26 SOL:
   ~629×4×3 ≈ 7.5k filas.
2. **Corrida de cosecha** (post-poda, config ya estabilizada): editar la
   matriz del workflow — SOL `months: 24→36`, `step: 2→1` (~3-4h de job) →
   ~1.4–1.9k eventos ≈ 17–23k filas de cubo. (No es input del form: son 2
   líneas en `research.yml`, se cambian cuando la poda esté decidida para no
   cosechar con una config que va a cambiar.)
3. **Ledger paper ORO**: fuente lenta (techo ~4/sem) — NO bloquea entrenar el
   selector (eso usa el cubo de research), pero SÍ es la vara de validación
   forward: F3 no se promueve sin ≥40–50 trades forward dentro del IC (igual
   que F4/VIP).
- **Gate para construir F3**: ≥~1000 eventos fired en el cubo de UNA config
  post-poda estable + gate ORO de esa config re-validado (`leakage_ok`).
  Antes de eso, el vecindario k=50 sobre fired es demasiado ralo para que el
  argmax del cubo sea estimable (lo vimos: retrieval esparso de BTC murió por
  exactamente esto).

---

## 6.7 BUG DE RELOJ EN RESEARCH (12-jun-2026) — hallazgo, alcance y re-medición

**Hallazgo.** `killzones_pd.current_killzone()` y `get_legacy_session()` leen
`datetime.now(CDMX)`. En el replay de research, TODA la historia heredaba la
killzone/sesión de la hora a la que corría el CI; eso alimenta la Fase D
(`w_killzone`/`w_clock_legacy` → `w_effective` → `p_master`) → el set de
señales era función de la hora del click. El harness ya parcheaba el reloj de
`volume_quality` (mismo bug, descubierto antes); faltaba `killzones_pd`.

**Prueba (mismos datos, mismo código de motor, misma semilla):**
| Run | Hora CDMX del job | Régimen ficticio | fired SOL | leakage denso |
|---|---|---|---|---|
| #26 | 08:57–10:51 (NY am) | `silver_bullet/ny_am` w=1.40/1.20 toda la historia | **629** | causal **+0.353**, OK |
| #28 | 01:09–03:06 (madrugada) | asia/london_open w=0.50–1.20 | **226** | causal **−0.208**, REVISAR |

Forense adicional: el vocab one-hot de killzone del artefacto #26 de SOL solo
contiene `['ny_am_kz','silver_bullet_ny_am']`, y el de BTC (#26, corrió
17–21h CDMX) quedó **vacío** → BTC evaluó 48 meses prácticamente sin
killzone: sus 26 fired y su veredicto §6.5 estaban **estrangulados por el
bug**, no (solo) por el mercado.

**Fix (jun-2026):** el harness inyecta `_BarClockDatetime` también en
`killzones_pd` → cada vela se juzga en SU killzone histórica; backtest = bot
en vivo e independiente de la hora del click. Test de regresión:
`tests/test_replay_clock.py`. `is_weekend_closed` (UTC) queda intacto a
propósito (`WEEKEND_ADMIN_ONLY` ya lo neutraliza en research). **El bot en
VIVO nunca tuvo este bug** (su reloj de pared es el correcto).

**Qué queda invalidado / qué sobrevive:**
- Invalidado como comparable: TODO research previo al fix (#26, #28, #29):
  cadencias, edges, umbral ORO, veredicto BTC, poda. Eran backtests de
  regímenes ficticios ("todo NY", "todo madrugada").
- El **artefacto SOL desplegado** (gate ORO vivo) se construyó con el sesgo
  "todo NY": `gold_threshold=4.1226` y su edge no son fiables. El paper sigue
  corriendo (es papel y su ledger forward mide la verdad), pero el artefacto
  se **reconstruye** con el primer run post-fix que dé `leakage_ok` y se
  reemplaza en el Volume.
- Sobreviven: los fixes de `regime_score`, 409, reconcile, topología; el
  funnel/segmentos/cubo (instrumentación que destapó esto); el dato de que el
  edge puede CONCENTRARSE por sesión (la diferencia #26 vs #28 lo sugiere —
  el mapa de segmentos post-fix lo medirá de verdad, por vela y sin ficción).

**Secuencia de re-medición (post-fix, en orden) — estado al 12-jun tarde:**
1. ✅ **HECHO** — run #30 (id 27415283709): baseline honesto de SOL y BTC
   (abajo y §6.5). BTC recibió su prueba justa; §6.5 re-sellado.
2. ✗ **NO disparado** — el denso dio `REVISAR` en AMBOS símbolos (SOL causal
   −0.0098 / BTC +0.0067) → ningún artefacto se reconstruye. El gate vivo del
   Volume sigue siendo el de la ficción NY: el paper corre admin-only como
   ledger forward, pero **NO leerlo como validación** y NO reemplazar nada.
3. ✅ **HECHO** — run #31 (id 27426619247, `ablation=true`, terminó 12-jun
   21:01Z): poda sobre base honesta. **Veredicto sellado en §6.6: NO se mata
   ningún módulo** (scorer/regime additivos inertes y acoplados al gate ORO;
   session_bias VIVE y sostiene el edge). Cero cambios de prod.
4. Pendiente de (3): §6.3/F4 para BTC quedó reformulado en §6.5 (calidad
   neta, no densidad); el siguiente diseño accionable es F2.6 (§6.8) y la
   ejecución maker (§6.10). La **corrida de confirmación** es ahora un run
   NORMAL (sin `ablation`, defaults) sobre el sha 7e7ac12: trae frontera maker
   `[2.2/4]` + leakage denso + segmentos sobre la base honesta, sin tocar
   ningún toggle de módulo (la poda ya dijo que no hay nada que apagar).

**Primer baseline honesto — run #30, SOL (12-jun-2026, post-fix):**
- Cadencia: **183 fired / 24m** (~1.8/sem a step=2). In-sample +0.136R;
  **OOS −0.095R** (n=156, PF 0.84). El motor global NO tiene edge OOS en SOL
  en este período con costes.
- Denso: `causal −0.0098 ≈ 0` → REVISAR → **índice NO persistido** (el gate
  vivo sigue siendo el de la ficción NY; no reemplazar; no leer su paper como
  validación).
- **Mapa de segmentos OOS (n=156)** — el edge existe pero CONCENTRADO:
  SHORT **+0.274** (n=87) vs LONG −0.032 (n=69) · bias_4h bajista **+0.314**
  (n=71) vs alcista −0.130 (n=61) · bloque **12-16 UTC +0.361** (n=38) ·
  silver_bullet ny_am/londres +0.32/+0.31 (n=18/15) · london_open_kz
  **−0.066 con n=43 (el bucket más grande dispara donde NO paga)** · vie/sab/
  dom +0.37/+0.26/+0.27 vs lun −0.204.
- ⚠ Caveat: el período es un mega-bear de SOL (~150→62): "los shorts pagan"
  puede ser beta del período, no alpha. Estándar anti-espejismo vigente: el
  mapa se explota solo si (1) replica en BTC #30 / corrida fresca y
  (2) sobrevive forward. NUNCA degradando el gate ORO para "aprovechar hoy".
- Lectura de la poda (#31) con baseline OOS negativo: el hallazgo más valioso
  sería un módulo cuyo retiro **MEJORE** la expectancy (módulo dañino), no
  solo la cadencia. Regla de oro aplica: multiplicar señales con expectancy
  negativa multiplica pérdida — calidad primero (segmentos), cadencia después.

**Segundo baseline honesto — run #30, BTC (12-jun-2026, post-fix):**
- 223 fired/48m (step 3), OOS −0.068R neto (n=191, PF 0.87), pre-coste
  +0.207R, denso REVISAR → no persist. Detalle completo y evaluación §6.3:
  **§6.5 (sellado)**.
- **Veredicto del fractal (SOL vs BTC, ambos post-fix):** la concentración
  del edge POR SESIÓN replica (london_open_kz malo en ambos, silver_bullet_lo
  bueno en ambos, viernes fuerte / lunes flojo en ambos, madrugada mala);
  la concentración POR DIRECCIÓN/BIAS se **invierte** (SOL paga short/bajista,
  BTC paga long/alcista) → confirmado el caveat: "los shorts pagan" en SOL es
  **beta del mega-bear**, no alpha. El candidato explotable que sobrevive la
  prueba anti-espejismo es el de **sesión** (→ §6.8 F2.6); el veto
  direccional queda rechazado como regla universal.
- El bug de reloj queda **CERRADO**: fix a8b092c + test de regresión
  (`tests/test_replay_clock.py`) + verificación en #30 (vocab de killzones
  con diversidad real en ambos símbolos; `regime_score` ya no es dimensión
  muerta). Regla permanente: cualquier `datetime.now()` nuevo en el path del
  motor es sospechoso — el replay debe inyectar `_BarClockDatetime`
  (`tools/run_research_real.py`) en todo módulo que lea reloj.

---

## 6.8 F2.6 — GATE POR SEGMENTO de sesión (CÓDIGO, 13-jun-2026)

> Estado: **CÓDIGO en producción (default OFF)**, 13-jun-2026. La poda (#31)
> dijo que no se mata nada (§6.6) → F2.6 se construye ENCIMA del motor. Se
> valida con el protocolo de abajo ANTES de activar en vivo. Paper primero,
> 0% real. El gate ORO NUNCA se degrada para esto.
>
> **Implementado** (`segment_veto.py`, módulo puro, default OFF
> `FQ_SEGMENT_VETO_KILLZONES=""`): predicado que veta por killzone / bloque-UTC
> / día, juzgando el TIMESTAMP DE LA VELA (nunca `datetime.now()`; en la guarda
> `tests/test_no_wallclock.py` con baseline 0). MISMO predicado en los TRES
> consumidores → cero divergencia:
> - **research** (`run_research_real`): filtra la población etiquetada tras
>   `label_events`, antes de OOS/[2.2/4]/[2.5/4]/retrieval (cubo `events`
>   INTACTO para el regrade); el run mide el veto INTEGRADO.
> - **offline** (`tools/regrade_events._veto_mask`): delega en `segment_veto`
>   → sus números reproducen lo que mide la corrida integrada.
> - **vivo** (`fq_bot_v3_2`): capa de decisión post `evaluate_signal` (junto al
>   gate QTE), JAMÁS dentro de `fusion_engine`; veta la señal VIP. Default OFF.
>
> El protocolo paso 2 (corrida de confirmación) ya es LANZABLE: input
> `segment_veto_killzones` en `research.yml` → `FQ_SEGMENT_VETO_KILLZONES` del
> replay (ver runbook §9.4).

**Evidencia (la que sobrevivió la prueba anti-espejismo SOL #30 × BTC #30,
OOS pooled, pnl_r PRE-coste; los netos restan ~0.23R en SOL / ~0.28R en BTC):**

| Corte | SOL #30 (n=156) | BTC #30 (n=191) | ¿Replica? |
|---|---|---|---|
| `london_open_kz` | **−0.066** (n=43) | **+0.038** (n=33) | SÍ — ≈0 pre-coste ⇒ claramente negativo NETO en ambos; y es bucket grande en ambos (el motor insiste donde no paga) |
| `silver_bullet_lo` | +0.310 (15) | +0.275 (26) | SÍ — paga en ambos |
| viernes | +0.372 (31) | +0.464 (32) | SÍ — mejor día en ambos |
| lunes | −0.204 (17) | +0.028 (26) | SÍ — (casi) peor día en ambos |
| 00-08 UTC | −0.319 (9) | −0.171 (12) / −0.505 (5) | SÍ direccional, n chico |
| dirección / bias_4h | short/bajista paga | long/alcista paga | **NO — INVERTIDO** (beta del período de cada símbolo) |
| ny_am_kz, `fuera`, 20-24utc, sab/dom, mie/jue | dispares entre símbolos | dispares | NO — tratarlos como ruido local hasta nueva evidencia |

**Decisiones de diseño:**
1. **Veto direccional RECHAZADO** ("veto longs con bias alcista"): se invierte
   entre símbolos ⇒ es exposición al drift del período. Si algún día se
   quiere, es una capa de REGIME-FOLLOWING explícita y consciente, no un
   hallazgo del motor.
2. **El candidato es el veto de SESIÓN**, y de UNA sola regla para empezar
   (anti-overfit): `london_open_kz` — el único corte grande (n=43+33),
   replicado y accionable. Lunes y 00-08utc quedan como candidatos
   SECUNDARIOS: solo se consideran si el primario sobrevive forward (apilar
   vetos = re-overfit por la puerta de atrás).
3. **Dónde corta**: capa de decisión (post-`evaluate_signal`, junto a los
   gates existentes), **jamás dentro de `fusion_engine`**. El mismo predicado
   corre en el replay de research y en vivo (mismo código, cero divergencia
   backtest/live).
4. **Reloj**: el predicado juzga el **timestamp de la VELA** (en vivo y en
   replay), nunca `datetime.now()` — lección §6.7 grabada a fuego.
5. **Reversible**: env del worker, default OFF.
   `FQ_SEGMENT_VETO_KILLZONES=""` (CSV de killzones vetadas; p.ej.
   `london_open_kz`) y, si el secundario se gana su lugar,
   `FQ_SEGMENT_VETO_UTC_BLOCKS=""` (p.ej. `00-04,04-08`). Módulo puro
   `segment_veto.py` con tests de timestamps históricos.
6. **Relación con la poda #31**: `session_bias` (multiplicador continuo) está
   bajo ablación. Si MUERE, F2.6 es su sucesor más honesto (regla discreta,
   replicada cross-symbol, medible). Si VIVE, F2.6 se mide ENCIMA de él y
   solo entra si el delta OOS neto adicional lo justifica.

**Protocolo de validación (en orden, sin saltarse pasos):**
1. ✅ **Offline MEDIDO (12-jun-2026, `tools/regrade_events.py` sobre los cubos
   del #30; folds reconstruidos y verificados exactos):**

   | OOS pooled (neto ~) | SOL | BTC |
   |---|---|---|
   | base | −0.095R (n=156) | −0.068R (n=191) |
   | **veto primario** `london_open_kz` → restantes | **−0.017R** (n=113) | **−0.033R** (n=158) |
   | señales vetadas (lo que dejamos de operar) | −0.299R (n=43) | −0.237R (n=33) |
   | info: veto apilado (+lun, +00-08utc) → restantes | +0.036R (n=97) | +0.007R (n=134) |

   El primario mejora ambos símbolos y lo vetado es claramente tóxico neto;
   aún ≤0 (el veto solo no compra el verde — no venderlo como salvación).
   El apilado pondría el OOS en verde en ambos, PERO: (a) los 3 cortes
   salieron de estos mismos datos (multiple comparisons), (b) cuesta −38% de
   cadencia en SOL (156→97, ya escasa, y aleja el gate de F3), (c) la columna
   neta usa la carga MEDIA de costes — el neto real por subset lo da la
   corrida de confirmación. Decisión de diseño intacta: primario primero;
   el apilado solo si el primario sobrevive forward.

   ✅ **Replicación cross-muestra (13-jun-2026, `regrade_events` sobre el cubo
   del #31 = SOL step 3, muestra DISTINTA al #30/#32 step 2; n=106 vs 156):**
   el veto **primario REPLICA**, el **secundario NO**. Matriz maker real:

   | SOL, lift del veto london | #30 (step2, n=156) | #31 (step3, n=106) |
   |---|---|---|
   | bucket london (pre-coste) | −0.066 (tóxico) | −0.083 (tóxico) ✓ |
   | taker base → +veto | −0.095 → −0.003 (**+0.092**) | +0.018 → +0.098 (**+0.080**) |
   | entrada+TP maker base → +veto | +0.021 → +0.109 (**+0.088**) | +0.144 → +0.224 (**+0.080**) |
   | secundario: bucket extra (lun/00-08) | −0.076 (tóxico) | **+0.011 (NO tóxico)** |

   Lectura: el **lift del primario es ~+0.08R estable** en ambas muestras (taker
   Y maker) y su bucket es tóxico en ambas → sobrevive "replicar en datos
   frescos". El **secundario NO replica**: en #31 corta trades ~breakeven (no
   tóxicos) ⇒ su +0.036R del #30 huele a multiple-comparisons. Refuerza la regla:
   solo el primario; el secundario NO se apila. (Nota: #31 base es +0.018, no
   −0.095: step 3 es muestra más favorable; lo que replica es el LIFT, no el
   absoluto.)
2. ✅ **CONFIRMACIÓN INTEGRADA CROSS-SÍMBOLO — run #33 (13-jun-2026,
   `segment_veto_killzones=london_open_kz`).** El replay aplicó el veto integrado
   en AMBOS símbolos (`caen 47/183` SOL · `caen 41/223` BTC) y re-foldeó la
   población restante. Reproduce la matriz offline §6.10.1 end-to-end:

   | OOS post-veto (folds re-pooled) | SOL (n=116) | BTC (n=156) |
   |---|---|---|
   | base (sin veto, §6.10.1) | −0.095 | −0.068 |
   | **taker/taker +veto** | **+0.0122** (WR 0.543) | **−0.0273** (WR 0.558) |
   | entrada maker +veto | +0.0857 | +0.0585 |
   | **entrada+TP maker +veto** | **+0.1245** (PF 1.21) | **+0.1046** (PF 1.19) |

   **Veredicto §6.6: PASA en ambos.** El veto sube expectancy OOS y WR sin
   degradar; killzones restantes ≥0 (london eliminado en los dos; mejor franja
   BTC = `ny_am_kz +0.455`). **Caveats que lo mantienen TECHO:** (a) el taker
   sigue ≤0 (SOL +0.012 breakeven, **BTC −0.027 NEGATIVO**) → el +0.10R EXIGE
   maker con fill 100% asumido → la vara real es el fill-rate del motor paper;
   BTC depende MÁS del maker que SOL. (b) **Leakage denso = REVISAR en ambos**
   (SOL causal −0.0098 / BTC +0.0067; placebo no colapsa) → el gate k-NN NO se
   reconstruye → la espada es **motor base + veto + maker**, NO el gate (§6.10.1
   #3). (c) Lunes tóxico en #33 pero NO en #31 (fresca) → secundario frágil, no
   apilar. **Hito: primera config con +0.10R OOS positivo INTEGRADO y replicado
   cross-símbolo** — pendiente solo el fill-rate forward.
3. **Paper forward 2–4 semanas** con el ledger del **motor paper** (`/paper`).
4. Prod por env, con confirmación explícita del usuario y rollback de una
   línea. Cada paso documenta sus números aquí.

---

## 6.9 CVD proxy — radar NEGATIVO (12-jun-2026)

> Pregunta del usuario: ¿sirve "precio en nivel de interés + divergencia de
> CVD = entrada"? Lo que el bot ya tiene (niveles ICT, espera, patrón de
> divergencia) y lo que no (CVD real: el OHLCV no trae lado agresor) está en
> el análisis de sesión; aquí el RESULTADO del diagnóstico barato.

**Método (cero replays):** `cvd.py` (proxy de delta por vela: posición del
cierre en el rango × volumen; detector espejo de `detect_rsi_divergence`) +
`tools/regrade_cvd.py` (reconstruye labels tp1/h288 y folds 7/embargo 8 del
run #30 desde el cubo persistido — verificado EXACTO contra los números
sellados: SOL n=156 +0.138658 / BTC n=191 +0.207435 — y clasifica cada evento
por la ventana causal de velas previas a la entrada, bajada de OKX).

**Resultado (OOS pooled, exp_r PRE-coste vs base; `alineada` = divergencia a
favor del trade, el playbook; `contra` = en contra):**

| | SOL lb=96 | SOL lb=48 | BTC lb=96 | BTC lb=48 |
|---|---|---|---|---|
| base | +0.139 (156) | +0.139 (156) | +0.207 (191) | +0.207 (191) |
| alineada | **+0.223 (18)** | −0.074 (31) | +0.001 (16) | +0.145 (21) |
| contra | +0.082 (35) | +0.604 (17) | +0.328 (48) | +0.246 (29) |

**Veredicto: el playbook NO sobrevive el anti-espejismo.** "Alineada > base"
solo en 1 de 4 celdas (SOL/96, n=18) y se INVIERTE al cambiar lookback o
símbolo. Curiosamente "contra > base" sale en 3 de 4 — pero con n=17–48,
proxy (no CVD real) y 4 cortes escaneados, es exactamente el patrón de azar
que el estándar §6.6 existe para no perseguir. Decisión:
- NO se cablea gate/feature de CVD; NO se paga el dato real (taker/tick) con
  esta evidencia.
- Si el ledger forward o un run futuro reaviva la hipótesis, el primer paso
  vuelve a ser este regrade (gratis), no un replay.
- Subproducto que SÍ queda: el patrón de regrade offline (medir cualquier
  veto/filtro sobre eventos persistidos sin replay) — semilla del
  `regrade_events` genérico del ENGINEERING_PLAN N5; es la herramienta con la
  que F2.6 §6.8 hará su paso 1.

---

## 6.10 Frontera de ejecución MAKER (techo) + fill-model shadow (12-jun-2026)

> Hallazgo §6.5: el edge bruto de ambos símbolos muere en costes en unidades R
> (stops apretados ⇒ ~10bps round-trip ≈ 0.23–0.28R). La palanca más grande no
> es estrategia: es EJECUCIÓN. El sistema entra cuando el precio LLEGA a un
> nivel y el TP es un precio conocido — territorio natural de orden LÍMITE
> (maker 2bps OKX vs taker 5bps, y sin slippage en la pierna maker).

**Techo medido (offline sobre el pool OOS del #30; fill 100% asumido):**

| neto/trade | BTC | BTC+veto london | SOL | SOL+veto |
|---|---|---|---|---|
| taker/taker (hoy) | −0.063R | −0.026R | −0.086R | +0.006R |
| entrada maker | **+0.024R** | **+0.061R** | −0.008R | +0.079R |
| entrada+TP maker | +0.066R | **+0.102R** | +0.021R | +0.108R |

(Validación: el escenario "hoy" reproduce el neto sellado del run a ~0.01R;
el residuo es funding/compounding.)

**El caveat que gobierna esta sección: ADVERSE SELECTION.** Una límite en el
nivel no se llena en los trades que se escapan (que tienden a ser ganadores)
y se llena siempre en los que te atraviesan. El techo NO es la promesa; la
captura realista se mide, no se asume. Dos instrumentos (jun-2026, cableados):

1. **Research — `[2.2/4] Frontera de ejecución`** en cada run:
   `bt_engine.CostModel` ahora soporta piernas maker (`maker_entry`,
   `maker_tp_exit`; stop y timeout SIEMPRE taker; slippage 0 en pierna maker)
   y el runner imprime los 3 escenarios sobre el mismo pool OOS. Gratis
   (re-simulación, cero replays).
2. **Paper — shadow maker (`FQ_GOLD_MAKER_SIM=1`)**: por cada ORO que el
   paper abre taker (como siempre), registra en el ledger si una límite en el
   precio de la señal se habría llenado — fill solo por PENETRACIÓN
   (`FQ_GOLD_MAKER_EPS_BPS`, default 1bp; touch NO llena = peor caso de cola)
   con TTL (`FQ_GOLD_MAKER_TTL_BARS`, default 6 velas) → eventos
   `MAKER_FILL`/`MAKER_MISS` por `pid`, joinables con el outcome del gemelo
   taker. NO toca las posiciones: instrumentación pura, default OFF.

**Regla de decisión (se fija con ~30–50 eventos forward):** la ejecución
maker solo se adopta si la sub-cartera `MAKER_FILL` (con fees maker) supera a
la cartera taker completa Y el fill-rate × techo justifica el cambio. Si los
fills se concentran en losers (adverse selection dura), la línea muere y nos
quedamos taker — resultado válido. Nota: el fill-rate es propiedad de la
microestructura (nivel→penetración), no del gate: la medición sirve aunque el
artefacto ORO se reconstruya después (§6.7 paso 2).

### 6.10.1 — LAS DOS PALANCAS JUNTAS (run #32, sha 94d415f, 13-jun-2026)

> El run #32 (confirmación, motor honesto, código nuevo) confirma la frontera
> maker `[2.2/4]` de cada símbolo y reproduce los cálculos offline del #30.
> `tools/regrade_events.py --maker-matrix` mide la combinación **veto de
> sesión × ejecución maker** con `bt_engine` real por pierna sobre el cubo OOS.

**Matriz (expectancy_r OOS, bt_engine real; base = cartera completa, +veto =
sin `london_open_kz`):**

| ejecución | SOL base (n=156) | SOL +veto (n=113) | BTC base (n=191) | BTC +veto (n=158) |
|---|---|---|---|---|
| taker/taker (hoy) | −0.095 | −0.003 | −0.068 | −0.031 |
| entrada maker | −0.017 | +0.070 | +0.019 | +0.055 |
| **entrada+TP maker** | +0.021 | **+0.109** | +0.066 | **+0.102** |

**Hito: primera config con +0.10R OOS positivo en AMBOS símbolos, replicada
cross-symbol.** El filo = **motor base + veto `london_open_kz` + ejecución
maker**. Ni el TP estático ni el modelo ni el retrieval lo lograron; las dos
palancas legibles sí.

**Los 4 caveats que lo mantienen como TECHO, no promesa (orden de letalidad):**
1. **Maker asume fill 100%** (adverse selection no modelada). El shadow maker
   en paper (§6.10) lo está midiendo AHORA; sin su fill-rate real, +0.109 es
   el techo. ESTA es la incógnita que decide si el filo es de verdad.
2. **El veto + maker se apilan sobre la MISMA muestra** del #32. El veto ya
   replicó SOL×BTC (anti-espejismo parcial), pero la vara real es forward.
3. **El retrieval denso sigue REVISAR en ambos** (SOL causal −0.0098, BTC
   +0.0067) → el gate ORO NO se reconstruye. Esta espada es del **motor base**,
   NO del gate k-NN — que lleva varios runs sin dar `leakage_ok`. Implicación
   estratégica: el producto operable que los datos respaldan HOY es el motor
   base + palancas legibles, no el gate de retrieval.
4. **Cadencia baja con el veto** (SOL 156→113, −28%). Calidad por cadencia:
   aceptable para el objetivo, pero acerca el problema de densidad para F3.

**Implicación para el camino a vivo — RESUELTO en CÓDIGO (13-jun-2026):** el
paper ORO mide fills sobre el gate de la ficción NY (población incorrecta). Para
validar ESTA espada forward se cableó `motor_paper.py` (`MotorPaperRuntime`,
default OFF `FQ_MOTOR_PAPER`): un track PARALELO al ORO que abre en paper el
**motor base** (el `fire` CRUDO de `evaluate_signal`, misma población que el
replay) filtrado por su **veto propio** (default `london_open_kz`, independiente
del veto VIP en vivo → desacopla la validación del impacto a clientes) y mide el
**shadow maker** (fill por penetración). `tools/motor_paper_stats.py` reporta el
fill-rate maker REAL + adverse selection (FILL vs MISS). Es cableado del runtime
paper, NO del motor; 0% real, reversible. El edge neto = matriz §6.10.1 escalada
por el fill-rate realizado. Runbook §9.4. Meta: ≥30-50 fills (regla §6.10).

---

### 6.11 — STEP1 GATED + OOT + FILL-SIM HONESTO (runs #58/#59, sha 57594bf, 17-jun-2026)

> Primer gateado+OOT a densidad MÁXIMA (step1) en Hetzner, con el fill-sim maker
> honesto (`bt_engine.maker_entry_fill_mask`, misma regla penetración>eps que el
> paper) ya cableado en la frontera `[2.2/4]`. Cierra la incógnita #1 de §6.10.1.

**Frontera de ejecución BTC (48m, step1, 594 trades OOS):**

| ejecución | exp_R | nota |
|---|---|---|
| taker/taker (hoy) | −0.1066 | realidad |
| entrada+TP maker **[techo]** | +0.0286 | fill 100% (optimista) |
| entrada+TP maker **[fill-sim]** | **−0.0254** | fill-rate 89% real |

`R_fill=+0.119` vs `R_miss=+0.616` → **ADVERSE SELECTION confirmada**: la límite
se queda los flojos, los ganadores se escapan sin llenar. **Cierra el caveat #1
de §6.10.1: el +0.10R era techo; el número honesto NO cruza cero con maker naive.**
Maker recorta el sangrado (−0.107→−0.025) pero no basta solo.

**OOT forward (BTC, 137 trades nunca vistos, corte 2025-09-01):** exp_R −0.05,
−7.6% total. NEGATIVO en promedio — PERO el bin superior de score del modelo dio
**+0.784R** forward (bin2 +0.38). SOL forward peor (−15.7%). El promedio pierde;
**el tope de la selección gana.**

**Dónde está el edge (todos los lentes coinciden, OOS):**
- Score del modelo: umbral 0.70 → +0.218R; bin forward top +0.78R.
- Retrieval denso (gate ORO): decil top-10% **+0.53 edge** (BTC), top-25% +0.38.
- Killzones: asia_kz +0.57, ny_pm +0.33, ny_am +0.27; `fuera` −0.14, `asia_open` −0.25.
- Bloque quantum: lift **+0.0123 [SUMA]** AUNQUE `qt_sync_score` está 100% NaN
  (extractor MUERTO) → arreglarlo es upside gratis.

**TESIS (sello): el edge del motor está en la SELECCIÓN, no en el promedio.** El
libro all-in es negativo neto de costes; el tope de cada ranking (score, decil de
retrieval, killzone líquida) es netamente positivo. Ganar la temporada = ser
selectivos + bajar coste sobre lo seleccionado.

**Planeación (próximos pasos, por puntos esperados):**
1. **P2 — Gate de selectividad (EN CONSTRUCCIÓN):** disparar solo si
   `score_modelo ≥ top-quantil` (OOF walk-forward) Y `killzone ∉ {fuera, asia_open}`
   (prior estructural). Medido OOS + **OOT forward del subset seleccionado** (la
   vara anti-leakage). Extiende F2.6. Es la palanca que puede cruzar el signo NETO.
2. **P1b — Maker consciente de adverse selection:** no postear límite pasiva en
   señales de momentum que se escapan; postear maker solo donde el fill no es
   adversamente seleccionado. Rescata el hueco −0.107→0 que el maker naive deja.
3. **Paso 3 — arreglar `qt_sync_score` (100% NaN, extractor muerto):** el bloque
   quantum ya suma +0.012 con esa feature muerta; repararla = más lift sin coste.
4. **ETH al mismo harness:** poda #55 dio baseline ungated **−0.0382** (el MENOS
   negativo de los 3 → mejor candidato a cruzar a positivo con selectividad).
   Faltan su gated/OOT/maker/segmentos: se añade ETH 48m step1 a la matriz gated_shard.

---

## 7. Roadmap por fases

### F0 — Datos BTC + harness de índice causal + **test de leakage** (puerta)
- Descargar BTC 48m en 5m/15m/1h/4h; reporte de gaps como artefacto.
- Implementar la **Opción A** (§3.0): motor en 15m, label/query en rejilla 5m.
- Esqueleto de `bt_retrieval.py`: vector, scaler causal, `StateIndex` sobre
  turbovec, ingest online en walk-forward, allowlist causal + embargo.
- Extender `bt_labeler` al cubo `(TP × horizonte)` (necesario para side-table y F3).
- **Ejecutar los tests #1 y #5** (leakage y aproximación). **Si #1 colapsa → STOP**
  y documentar. Añadir `turbovec` a `requirements` (extra) y `--seed` global.

### F1 — Expectancy de retrieval como **diagnóstico read-only** (SOL y BTC)
- Loguear stats del vecindario por evento, sin decidir nada.
- Calibrar `k`, `bit_width`, escalado (test #2), `W`/`τ` (test #3), confianza/
  abstención (test #4).
- Medir **edge condicional** OOS: ¿filtrar por `expectancy_r` del vecindario
  mejora la expectancy vs incondicional? Tabla SOL vs BTC inicial.

### F2 — **Gate** + **Sizing** (sólo si F1 positivo y tests verdes)
- Activar (a) gate con abstención y (b) sizing kappa-like acotado.
- Ablación: motor+lightgbm vs +gate vs +sizing vs +ambos, por símbolo.

### F2.5 — **Cadencia**: poda de módulos + funnel (ver §6.6)
- Diagnóstico: funnel de decisiones del replay denso (gratis, cada run).
- Poda OOS (`ablation=true`, SOL primero): MATAR solo módulos con `delta ≤ 0`
  y ganancia material de `n`. Producción cambia por env, reversible.
- Acumular datos F3: cubo por evento (`tp_cube_<sym>.parquet`) en cada run +
  corrida de cosecha (months 36 / step 1) cuando la config quede estable.

### F2.6 — **Gate por segmento de sesión** (ver §6.8; post-poda)
- Veto de calidad killzone-aware (primario: `london_open_kz`), replicado
  SOL×BTC en #30. Dirección/bias rechazados (beta del período).
- Orden: offline sobre cubos → corrida de confirmación + `leakage_ok` del
  ORO → paper forward → prod por env con confirmación del usuario.

### F3 — **Selector de TP/horizonte**
- Usar el cubo §3.2 para elegir `(TP, horizonte)` que pagó en estados similares.
- Comparar contra la escalera TP1–TP4 fija y `max_bars` único.
- Gate de entrada: ≥~1000 eventos fired en el cubo post-poda + gate ORO
  re-validado de esa config (§6.6); validación forward ≥40–50 trades.
- ✅ **CÓDIGO construido (13-jun-2026): `bt_tp_selector.py`** — k-NN causal
  walk-forward sobre el cubo (reusa `StateVectorizer` + folds purgados),
  elige la celda `(tp,horizonte)` de mayor expectancy del vecindario, abstiene
  a baseline si es ralo. 5 tests (lift +0.40R en cubo sintético estructurado).
  **Smoke sobre el #33 (183 eventos): lift −0.053R (WR 50→40%)** → confirma
  EMPÍRICAMENTE el gate §6.6: con <1000 eventos el vecindario k=50 es ruido y
  el argmax sobreajusta. La máquina está lista; falta la **cosecha**
  (`cosecha=true` → SOL 36m/step1, ~1.4–1.9k eventos) para tener señal real.

### F4 — Comparativa y **decisión de migración**
- Ablación completa (`+todo`) y tabla BTC vs SOL con métricas idénticas.
- Aplicar el criterio §6.3 → recomendación explícita: migrar / seguir ingiriendo /
  matar. Persistir artefactos finales por símbolo.

---

## 9. F2 EN PRODUCCION — gate ORO en vivo (paper primero)

> Estado: piezas puras CONSTRUIDAS y verdes. `retrieval_gate.py` (gate + persist),
> `tools/build_retrieval_index.py` y `--build-index` en `run_research_real`
> (un solo replay) construyen el artefacto; `gold_live.py` lo consume en el loop.

### 9.1 El artefacto del gate (por símbolo)
`retrieval/<exchange>/<symbol>/`: `scaler.pkl` + `index.pkl|index.turbo` +
`outcomes.parquet` + `meta.json` (umbral oro, k, sim_floor, n_floor, dim, leakage).
Lo produce la corrida de research (`build_index=true`) **solo si el leakage pasa**.
`turbovec` ya está en `requirements.txt` (wheel; sin compilar) para cargar el
índice turbovec en Railway; el backend `exact` (numpy) no necesita nada extra.

### 9.2 Deploy en Railway
1. Descargar el artefacto `research-report-<sym>` del run, extraer `retrieval/`.
2. Colocarlo en el **Volume** de Railway (persistente), p.ej. `/data/retrieval/...`,
   y apuntar `FQ_RETRIEVAL_DIR=/data/retrieval/okx/BTC_USDT`.
   (El índice está gitignored — es artefacto, no fuente.)

Envs del runtime paper (todos opcionales salvo `FQ_RETRIEVAL_DIR`):
- `FQ_GOLD_LIVE=1` enciende el hook (default OFF).
- `FQ_GOLD_SYMBOL` / `FQ_GOLD_TF` símbolo y TF del gate (default `SOL/USDT` / `5m`).
- `FQ_GOLD_LEDGER_PATH` ledger durable (default `/data/gold_ledger_<slug>.jsonl`,
  **en el Volume** para sobrevivir restarts; cuélgalo del backup de `ops/maintenance`).
- `FQ_GOLD_BASELINE_R` baseline OOS **en unidades de trade** → enciende el
  Reconciler (kill-switch si la viva diverge). Sin él, el reconcile queda OFF a
  propósito (el forward-label del research no es la misma unidad que el TP1).
- `FQ_GOLD_DIGEST_EVERY` velas entre digests ORO/BASE/ABSTAIN al admin (0=off).

#### 9.2.1 Runbook SOL — run #26 (VERIFICADO, jun-2026)

Gate ORO de SOL construido y validado (artefacto `research-report-SOL_USDT`):
`gold_threshold=4.1226` · `n_states=104826` · `n_confident=8984` · backend
`turbovec` (dim 30, bit_width 4). Edge **causal +0.353R / placebo −0.022R /
leakage_ok** (denso); sobre señales fired `gate_pass` da **+0.41R, WR 55%, PF
1.91** (n=20). La carga del artefacto con el código de producción está
**verificada end-to-end** (turbovec load → query densa → tier).

Pasos (una vez):
1. Actions → run #26 → artefacto `research-report-SOL_USDT` → descargar y
   descomprimir. Tomar la carpeta `retrieval/SOL_USDT/` (trae `index.turbo`,
   `scaler.pkl`, `meta.json`, `outcomes.parquet`).
2. Subirla al **Volume** de Railway en `/data/retrieval/SOL_USDT/`.
3. Envs (símbolo y TF ya son default `SOL/USDT` / `5m`; el bot primario es
   `SOL-USDT-SWAP` → el gate clasifica estados de SOL, que es justo su dominio):
   ```
   FQ_GOLD_LIVE=1
   FQ_RETRIEVAL_DIR=/data/retrieval/SOL_USDT
   ```
   (El ledger durable cae por default en `/data/gold_ledger_SOL_USDT.jsonl`, ya
   en el Volume.) **No** setear `FQ_GOLD_BASELINE_R` aún: el reconcile arranca OFF
   a propósito hasta tener expectancy en unidades de trade del propio paper.
4. Confirmar en logs al primer 5m: `[gold] runtime paper ORO activo (SOL/USDT,
   dir=/data/retrieval/SOL_USDT)` y `[gold] reconciler OFF: sin baseline`.
5. Tras ~2-4 semanas de paper: correr `python tools/gold_baseline.py` (lee el
   ledger del Volume, verifica la cadena y reporta expectancy/WR/PF + la línea
   `FQ_GOLD_BASELINE_R=…` lista para copiar). Fijar ese env → el kill-switch del
   Reconciler queda armado en la unidad correcta. Por debajo de 20 cierres no
   sugiere baseline (es el mismo umbral que `Reconciler.min_trades`).

> `turbovec>=0.7.0` debe estar en la imagen de prod (ya está en
> `requirements.txt`). `TurbovecBackend.load` reconstruye el padding del vector
> (fix jun-2026); sin él el primer `classify` en vivo caía.

### 9.3 Cableado del loop (paper primero)
En cada vela, tras `fusion_engine.evaluate_signal` (ya se llama), el monolito:
```
eng = gold_live.GoldLiveEngine.from_dir(os.environ["FQ_RETRIEVAL_DIR"], symbol,
          calculate_levels_fn=calculate_levels)
sig, verdict = eng.evaluate(field, report, df_15m, price)   # ORO/BASE/ABSTAIN
if sig:  # solo ORO + direccion de campo
    # PAPER: governor.decide -> PaperBroker.open (sella en HashLedger) -> Reconciler audita
```
Default **OFF** (`FQ_GOLD_LIVE=0`) hasta validar cadencia/calidad en paper. La
señal sale en el formato del `PaperBroker`/`live_driver` — sin adaptaciones.

### 9.4 Runbooks F2.6 (veto de sesión + motor paper) — 13-jun-2026

Tres acciones, en orden de seguridad. El código ya está en producción (default
OFF). Paper primero; nada de dinero real.

**A) Corrida de CONFIRMACIÓN del veto (§6.8 paso 2) — CI, 0% impacto.**
Actions → Research → Run workflow → branch
`claude/turbovec-tp-cube-hardening-fvzdx7` → setear input
`segment_veto_killzones = london_open_kz` (dejar el resto por default) → Run.
El replay filtra la población etiquetada por el veto ANTES de medir → el
REPORTE trae OOS [2/4] + frontera maker [2.2/4] + segmentos [2.5/4] +
`leakage_ok` del ORO de la población restante. Vara §6.6: el veto se queda solo
si mejora la expectancy OOS sin degradar WR de forma no compensada.
> Nota GitHub: el form renderiza inputs desde `main`. Si `segment_veto_killzones`
> no aparece al seleccionar la rama, hay que mergear esta rama a `main` primero
> (o, fallback puntual, hardcodear `FQ_SEGMENT_VETO_KILLZONES` en el `env:` del
> workflow como se hizo con `BUILDIDX`).

**B) MOTOR PAPER forward (§6.10.1, mide el fill-rate REAL) — Railway, 0% real,
admin-only.** worker → Variables: `FQ_MOTOR_PAPER=1` (+ opcional
`FQ_MOTOR_PAPER_TF=15m`, `FQ_MOTOR_PAPER_VETO_KILLZONES=london_open_kz` ya es
default). Redeploy. Confirmar en logs: `[motor] runtime paper MOTOR BASE
activo`. Tras 2-4 semanas: `python tools/motor_paper_stats.py` (lee el ledger
del Volume) → fill-rate maker + adverse selection + muestra vs la meta ≥30-50.
NO toca VIP ni dinero; es el juez del techo +0.10R. Rollback: borrar la env.

**C) VETO LONDON EN VIVO (provisional, §6.8 paso 4) — Railway, IMPACTA CLIENTES.**
worker → Variables: `FQ_SEGMENT_VETO_KILLZONES=london_open_kz`. Redeploy.
⚠️ Esto VETA señales VIP a CLIENTES en la franja london (1:00-5:00 CDMX), no
solo paper → CONFIRMAR con el usuario (captura del dashboard) antes de activar.
Confirmar en logs: `VETO sesion [killzone=london_open_kz] - señal NO difundida`
en la franja. Rollback de una línea: borrar la env. Idealmente solo tras (B)
dar fill-rate y/o el forward respaldar el veto.

**Siguiente (post-confirmación, NO antes):** cosecha F3 — editar la matriz de
`research.yml` (SOL `months: 24→36`, `step: 2→1`) para ≥~1000 eventos del cubo
de la config estable, base de F3 (selector TP/horizonte). Es el camino a ≥0.133R.

---

## 8. Qué se reutiliza (sin tocar) y qué se añade

**Se reutiliza tal cual**: `fusion_engine.evaluate_signal` (intacto), `bt_data`
(descarga), `bt_features.replay_events` (replay causal — sólo cambia el primario a
5m), `bt_walkforward` (purga+embargo), `bt_engine`/`bt_metrics` (costes+riesgo),
`bt_train` (LightGBM), `bt_ablation` (poda OOS), `research.yml` (flujo CI).

**Se añade**: `bt_retrieval.py` (nuevo, symbol-agnóstico), dependencia `turbovec`,
extensión multi-TP×horizonte de `bt_labeler`, `CostModel` per-símbolo, `--seed`
global, inputs de retrieval en `research.yml`, artefactos `retrieval/<ex>/<sym>/`.

**Invariante**: la separación SOL/BTC es de **DATOS** (índice/scaler/outcomes/
modelo en disco por símbolo), **no de código**. El mismo `bt_retrieval.py` corre
en ambos; sólo cambia la ruta del artefacto.
