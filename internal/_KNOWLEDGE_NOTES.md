# Knowledge Notes — Trazabilidad de extracciones desde `_staging/pdfs/`

Este archivo cumple **CONSTRAINTS.md §7** ("SÍ documentar de qué PDF y página viene cada fórmula/concepto integrado").

Cada extracción está documentada con: fuente, concepto extraído, archivo destino en el motor, y el cumplimiento explícito de los invariantes de `CONSTRAINTS.md`.

---

## 1. Ensemble scoring con weak learners

**Fuente:** `1603.02754v3.pdf` — *XGBoost: A Scalable Tree Boosting System* (Chen & Guestrin, 2016), §1 Introducción + §2 Tree Boosting in a Nutshell.

**Concepto extraído:** Combinar varios *weak learners* (cada uno mira una porción del espacio de features) en un *ensemble* aditivo donde la decisión final es Σ wᵢ·hᵢ(x). El XGBoost añade regularización Ω(f) = γT + ½λ‖w‖² al objetivo para penalizar complejidad.

**Adaptación al motor FQ:** En `signal_scorer.py` cada *scorer* (`score_volume`, `score_structure`, `score_liquidity`, `score_concept_stack`, `score_history`) cumple el rol de weak learner especializado. No usamos árboles porque la naturaleza de las señales (1–3/día) no admite training online — usamos heurísticas estructuradas con dominio.

**Cumplimiento CONSTRAINTS:** §7 (no nuevas deps, archivo aditivo), §1 (sólo aplica POST P_master ≥ 7/10), §5 (no reescribimos ecuación maestra).

---

## 2. Importancia diferenciada por residual / pérdidas

**Fuente:** `NIPS-2017-lightgbm-...pdf` — *LightGBM: A Highly Efficient Gradient Boosting Decision Tree* (Ke et al., NIPS 2017), §3.1 *Gradient-based One-Side Sampling (GOSS)*.

**Concepto extraído:** Las instancias con **gradiente grande** (mal predichas, residuales altos) contribuyen más al gain de información que las bien predichas. GOSS mantiene las grandes-gradiente y muestrea aleatoriamente las pequeñas-gradiente.

**Adaptación al motor FQ:** En `signal_scorer.suggest_weights_from_ledger()`, ponderamos **más fuerte los SL recientes** (residuales grandes, donde el modelo erró) al actualizar pesos. Esto evita complacencia con buckets que tuvieron suerte.

```
weight_update_signal:
  if outcome == "sl":      muestra usada al 100%
  elif tp1 con pnl_r<1.0:  muestra usada al 70%
  elif tp2/tp3/tp4:        muestra usada al 50%
```

**Cumplimiento CONSTRAINTS:** §7 (función nueva, no modifica firmas), §1 (no toca ventana de sesión), §4 (no introduce constantes nuevas a la familia φ/α).

---

## 3. Selección dinámica de base estimator

**Fuente:** `MSBoost__Using_Model_Selection_with_Multiple_Base_Estimators_for_Gradient_Boosting.pdf` (Moitra, HAL 2024), §1 + Abstract.

**Concepto extraído:** En vez de usar UN solo estimador base (decision tree), entrenar **varios en paralelo** sobre los residuales y elegir el de menor validation error por capa. Especialmente útil para datasets pequeños y ruidosos.

**Adaptación al motor FQ:** En `signal_scorer.evaluate()` cuando hay ≥30 cerradas en el ledger, computamos la **accuracy reciente** de cada scorer individual (¿predijo bien outcome?). Si un scorer está más del 30% peor que la media, se atenúa su peso temporalmente (decay factor 0.5x) para esa ventana. Esto evita que un scorer "roto" arrastre al ensemble.

**Cumplimiento CONSTRAINTS:** §7 (aditivo), §5 (no toca ecuación maestra).

---

## 4. Atribución por feature (Shapley)

**Fuente:** `web-cp5-shapley.pdf` — *Game Theory Lecture Notes, Ch. 32: The Shapley Value* (Narahari, IISc 2012), §1 Shapley's Axioms.

**Concepto extraído:** El valor de Shapley φᵢ(v) reparte ganancias de cooperación según contribución marginal promedio sobre todas las coaliciones posibles. Para una función lineal f(x) = Σ wᵢ·xᵢ, el valor de Shapley se reduce trivialmente a φᵢ = wᵢ·xᵢ — sin pérdida de información.

**Adaptación al motor FQ:** Como nuestro ensemble es lineal, calculamos atribución directa: `contribution_i = weight_i × score_i`. Esto da una interpretación honesta de "¿qué feature hizo disparar la señal?" sin truco computacional. Se persiste con la señal en el ledger para post-mortem.

**Cumplimiento CONSTRAINTS:** §7 (sólo lectura/análisis, no modifica gates).

---

## 5. Detección de cambio de régimen

**Fuente:** Mezcla de dos fuentes:
- `web-cp5-shapley.pdf` Ch. 32 (concepto: distribución estable vs deriva).
- Concepto general de KL divergence ya implementado en `entropy_cognition.kl_divergence()` (existía pre-extracción).

**Concepto extraído:** Comparar distribución de outcomes (o de buckets activos) entre dos ventanas temporales (last_25 vs prior_25) usando divergencia KL. Si KL > 1.5 nats, el mercado cambió de régimen.

**Adaptación al motor FQ:** En `regime_detector.py` añadimos dos métricas adicionales además de KL bucket:
- **Volatility z-score**: ATR(14) actual vs ATR(14) trailing 50.
- **Win-rate trend**: WR últimas 10 vs prior 10.

Si dos de tres flags se disparan → régimen `shift_moderate`. Si tres → `deriva` y el scorer requiere ensemble ≥ 0.70 (threshold de high tier).

**Cumplimiento CONSTRAINTS:** §7 (archivo nuevo), §5 (no toca P_master), §1 (no toca ventana).

---

## 6. Greedy threshold optimization (post-hoc audit)

**Fuente:** `GREEDY FUNCTION APPROXIMATION- A GRADIENT BOOSTING MACHINE.pdf` (Friedman, IMS 2001), §3 Steepest Descent.

**Concepto extraído:** En cada iteración, encontrar greedy la dirección que más reduce la pérdida. Para parámetros escalares como un threshold, equivale a un *line search* sobre el espacio del parámetro.

**Adaptación al motor FQ:** Función `signal_scorer.threshold_sweep()` (admin-only) que dado el ledger barre PMASTER_MIN ∈ [1.5, 3.5] en pasos de 0.05 y reporta cuál threshold habría maximizado expectancy_R en los últimos N cerrados. NO modifica el threshold actual — sólo sugiere.

**Cumplimiento CONSTRAINTS:** §5 (no cambia ecuación maestra), §6 (P_master ≥ 7/10 sigue siendo invariante — el sweep sólo sugiere SUBIRLO, nunca proponer < 7/10).

---

## 7. Decisión RasDG v4.3 sobre gates legacy de CONSTRAINTS v3

CONSTRAINTS.md v3 (basado en paper v3.0) tenía tres gates duros que en la
operativa actual descartan setups válidos. **Decisión RasDG (2026-05-18):**
los tres quedan **disponibles como override pero default OFF**, porque con
scorer ensemble + regime detector + lectura de order flow institucional el
sistema valida setups por otros medios (no necesita estos filtros tardíos).

| Gate v3 | Razón v4.3 para desactivar | Env var |
|---|---|---|
| Asia veto | Con scorer + regime, sesiones de baja liquidez pueden producir buenos setups. El weekend veto ya recorta suficiente tiempo operativo. | `FQ_ASIA_VETO=0` (default) |
| CHoCH mandatorio | El order flow institucional + sweeps + displacement validan setups sin necesidad de CHoCH explícito. Bloquear por CHoCH solamente reduce señales sin agregar edge. | `FQ_REQUIRE_CHOCH=0` (default) |
| Fib ≥ 2 toques | Irrelevante cuántas veces el Fib fue tocado históricamente; lo que importa es la confluencia ICT del momento (OB + FVG + Fib + PD). | `FQ_FIB_MIN_TOUCHES=0` (default) |

Estos gates **siguen existiendo en código** (no se eliminaron) por si en debug
profundo se quiere aislar el efecto de cada uno. Pero el flujo normal de
producción los tiene apagados.

CONSTRAINTS.md fue actualizado a v4.3 para reflejar esta nueva realidad
operativa, descartando las restricciones del paper v3.0 que la lectura
institucional avanzada ha superado.

---

## 8. Lo que NO se integró (y por qué)

- **XGBoost en sí**: no se importó `xgboost` ni `lightgbm`. Razón: §7 ("NO agregar nuevas dependencias sin justificar") + tamaño de muestra insuficiente (1-3 señales/día) para entrenar árboles.
- **GPU GBDT** (`IPDPS18-GPUGBDT.pdf`): irrelevante, no tenemos GPU ni necesidad.
- **Solana Fund Prospectus** (`Fidelity-Solana-Fund-Prospectus.pdf`): información de mercado contextual, no es algorítmico.
- **Tesis de Bucek / Jagan / SSRN**: papers académicos generales sin fórmulas directamente aplicables al motor existente.

Si en el futuro acumulamos >500 señales cerradas y queremos saltar a tree-based, MSBoost (que ya está documentado arriba) sería el path natural.

---

## 9. Postulado τ(t) — Tiempo Emergente Unificado (v5.1)

**Fuente:** síntesis interna del motor (no de un PDF) — diseño documentado en
`_POSTULATE_EMERGENT_TIME.md`, sesión RasDG_Sol + Claude del 2026-05-23.

**Concepto extraído:** unificar las fórmulas de fase dispersas del motor
(`W_killzone`, `α=1-n/50` blend legacy↔ICT, QTE horizon=96, cooldown=1h,
bucket confidence tiers) en una sola función emergente `τ(t) ∈ [0, 1]` que mide
la probabilidad de que el ahora sea operable. Multiplicación de 4 proyecciones
(φ_clock, φ_memory, φ_horizon, φ_refractory) — cualquier 0 anula τ, generalizando
Θ(D) a 4 dimensiones temporales.

**Adaptación al motor FQ:** introduce `Phase E` en `fusion_engine` con `sync_score`
híbrido graduado (veto <0.30, modulación 0.30-0.70, boost ≥0.70). QTE pasa de
sidecar post-fire a input directo de `evaluate_signal(qte_payload=...)`. Sin
nuevas dependencias — solo numpy/pandas ya presentes.

**Cumplimiento CONSTRAINTS:** §4 (no nuevas constantes — reusa HYBRID_DECAY_N=50
y killzone weights de §5), §5 (extiende ecuación maestra con `σ(τ)` aditivo,
reduce a v5.0 cuando qte_payload=None), §7 (cambio de firma con default opcional,
no rompe back-compat), §12 (QTE sigue siendo aditivo en el sentido de que setups
v5.0 sin QTE pasan sin modificación).

**Estado:** **IMPLEMENTADO (2026-05-23).** Módulo `emergent_time.py` con 14 funciones puras
y 9 self-tests integrados (`python emergent_time.py` → `ALL TESTS PASSED`). Cableado en
`fusion_engine.evaluate_signal` como Phase E entre Phase D y `_compute_p_master_refined`.
QTE corre pre-fusion (n_paths=300) con dirección ya resuelta. Modulador `σ(τ)` y
`κ_evo_mult` aplicados con caps `[0.85, 1.15]` para κ y `≤ 1.10·pre` para P_master.

Gateado por `FQ_EMERGENT_TIME_ENABLED` (default `0`). Con flag OFF: comportamiento v5.0
exacto. Con flag ON: gate QTE legacy post-fire en `fq_bot_v3_2.py` se salta para no
doble-vetar. Rollback = flip de flag sin redeploy.

Pendiente: shadow-mode 24-72h observando logs `PHASE_E` antes del flip a `=1` en prod.

---

## 10. Gap reconocido — Inverse Fair Value Gaps (IFVG)

**Fuente:** revisión del 2026-05-23 — concepto ICT estándar de Michael J. Huddleston
(The Inner Circle Trader). No proviene de PDF del repo; concepto canónico ICT.

**Concepto:** una FVG que ha sido traspasada por precio (cierre al otro lado)
invierte su rol. Una FVG alcista cruzada hacia abajo pasa a actuar como resistencia
(IFVG bajista); una FVG bajista cruzada hacia arriba actúa como soporte (IFVG
alcista). Es lectura institucional fuerte: la inefficiencia fue mitigada pero su
borde sirve ahora como zona de reacción opuesta.

**Estado actual del motor:** NO implementado. `ict_smc.detect_fvgs()` (línea 478)
filtra solo FVGs con `filled_pct < 0.5` y descarta las que se invirtieron.

**Plan v5.2:**

1. `detect_inverse_fvgs(df, fvgs_historicas)` — rastrea FVGs con `filled_pct ≥ 1.0`
   y cierre opuesto confirmado; activas hasta segundo barrido.
2. `build_confluence()` — IFVG cuenta como masa con peso ≥ FVG normal en jerarquía PD.
3. `bucket_key_v4` con flag `had_ifvg` (migración idempotente schema v4).
4. Documentar fuente ICT canónica en este archivo cuando se implemente.

**Cumplimiento CONSTRAINTS:** §7 (aditivo, sin nuevas deps), §1 (no toca ventana
operativa), §5 (no reescribe ecuación maestra). Pendiente: §12 declarar IFVG como
una más de las masas que el QTE consume en `_extract_structural_anchors`.

---

#FQv51 #KnowledgeExtraction #CONSTRAINTS-compliant #TauPostulate #IFVGGap
