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

## 6.5 BTC — diagnóstico del gate DEGENERADO (run #26, jun-2026)

> Veredicto (provisional, a sellar con UNA re-corrida post-fix): **BTC NO es
> candidato** a gate ORO con la evidencia del run #26. El framework rechazando
> un símbolo sin edge limpio es el sistema funcionando, no un fallo de CI: el
> artefacto BTC de 13KB (sin `retrieval/`) es el no-persist correcto del gate
> de leakage, no un bug.

**Números del run #26 (BTC/USDT 48m, 5m, seed 42, inputs default):**
- Denso: `causal +0.0453R` (≈0, ruido) · `placebo −0.1578` · `oracle +1.1357`
  → `leakage_verdict=REVISAR` → índice **no persistido** (correcto).
- Fired: **26 señales en 48 meses** (vs 629 de SOL en 24m). El retrieval
  esparso quedó con n=6 por fold (todo nan) y la frontera/modelo con n=22 OOS:
  `exp_r +0.0229R`, `PF 1.03`. El motor casi no dispara en BTC con los
  `TF_PROFILES` actuales — la "ventaja de densidad" de BTC (riesgo #6) no
  existe en el subset accionable.

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

**Evaluación contra §6.3 (run #26, pre-fix):**

| Criterio §6.3 | BTC run #26 | ¿Pasa? |
|---|---|---|
| 1. Edge neto ≥ +0.05R y PF ≥ 1.3 | +0.0229R, PF 1.03 (n=22 OOS) | NO |
| 2. Lift IC90 > 0 atribuible | causal +0.045 ≈ 0 | NO |
| 3. Densidad fiable | denso abstained=0, pero 26 fired/48m | NO |
| 4. Robustez a costes | n/a (cae antes) | — |
| 5. Sin leakage (tests #1–#5) | veredicto REVISAR | NO |

**Decisión:** NO desplegar nada de BTC; SOL sigue siendo el único gate vivo
(§9.2.1). Re-evaluar BTC solo si la re-corrida post-fix diera `leakage_ok` y
causal materialmente > 0 — poco probable: la dimensión reparada es esparsa en
el denso. El camino realista para BTC es densidad de señales (Opción B §3.0 o
re-tunear `TF_PROFILES`), no el vector; eso es F4, con su propio criterio.

**Re-corrida de verificación (la dispara el dueño; ~4h el job BTC):**
Actions → "Research (backtest / walk-forward / poda)" → Run workflow → branch
`claude/turbovec-tp-cube-hardening-fvzdx7` → inputs por DEFECTO (idénticos al
#26; la matriz ya trae BTC 48m/step 3 y SOL 24m/step 2). Qué mirar en el log
del job BTC (step "Research real"):
1. `[vectorizer] features 100% NaN (dimension MUERTA…)` — post-fix NO debe
   aparecer `regime_score` (la línea de cobertura `NaN>=50%` sí puede listarlo
   con ~99.9%: eso es lo esparso por diseño).
2. `[leakage] veredicto=…` del bloque `[denso]` — si sigue `REVISAR` (o causal
   ≈0), el veredicto de arriba queda SELLADO y BTC fuera hasta F4.

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

### F3 — **Selector de TP/horizonte**
- Usar el cubo §3.2 para elegir `(TP, horizonte)` que pagó en estados similares.
- Comparar contra la escalera TP1–TP4 fija y `max_bars` único.

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
