# POSTULADO τ(t) — Tiempo Emergente Unificado
## FQ v5.1 — Quantum Time Synchronization Edition

**Fecha:** 2026-05-23
**Autor:** RasDG_Sol + Claude
**Estado:** **IMPLEMENTADO (2026-05-23)** en `emergent_time.py` + cableado en `fusion_engine.evaluate_signal` como Phase E. Gateado por `FQ_EMERGENT_TIME_ENABLED` (default `0`). Self-tests pasan: `python emergent_time.py`.
**CONSTRAINTS:** §4 (constantes), §5 (ecuación maestra), §7 (no nuevas deps), §12 (QTE aditivo), §13 (postulado documentado).

---

## 0. Tesis

El motor FQ ya posee TODAS las piezas para una sincronización cuántico-temporal coherente, pero hoy operan como módulos desacoplados:

| Pieza temporal existente | Ubicación | Rol actual |
|---|---|---|
| `W_clock_legacy · α + W_killzone · (1-α)` | `fusion_engine` → `_compute_p_master_refined` | Blend sesión→killzone |
| `α = max(0, 1 − n_closed_v3/50)` | misma fórmula, parametrizado | Decay legacy→ICT |
| Killzone weights (1.40 → 0.60) | `CONSTRAINTS §5` | Modulador de fase de sesión |
| `HYBRID_DECAY_N = 50` | `fusion_engine` | Horizonte decay |
| QTE horizon = 96 velas 15m | `quantum_timelines.DEFAULT_HORIZON` | Predicción 24h |
| Bucket confidence tiers (8/16) | `_load_bucket_memory` | Maduración memoria |
| `SIGNAL_COOLDOWN_HOURS_V2 = 1` | `signal_engine_v2` | Refractario post-emisión |
| `EVAL_EVERY_N_MINUTES = 2` | `signal_engine_v2` | Cadencia de muestreo |

**Problema:** cada pieza usa su propio τ. No hay UN tiempo emergente del sistema. Si dos piezas discrepan (ej. killzone Silver Bullet 1.40 pero bucket toxic con WR<30%), la decisión se resuelve por compounding multiplicativo sin un postulado que diga **por qué** esa multiplicación es la correcta.

**Solución:** un postulado τ(t) ∈ [0, 1] que sea la **probabilidad emergente de que el ahora sea operable**. Todas las piezas existentes se reexpresan como proyecciones de τ. La señal sólo se emite cuando τ(t) ≥ umbral y QTE confirma sincronización.

---

## 1. Definición formal del postulado

### 1.1 Cuatro proyecciones de τ

```
τ(t) = φ_clock(t) · φ_memory(N) · φ_horizon(QTE) · φ_refractory(Δ)
```

Cada φᵢ ∈ [0, 1]. La elección multiplicativa (no aditiva) es deliberada: cualquier proyección que valga 0 anula τ — esto preserva el espíritu de `Θ(D)` como kill-switch absoluto generalizado a 4 dimensiones temporales.

#### φ_clock(t) — Fase de sesión (renormalizada de W_killzone)

```
φ_clock(t) = W_killzone(t) / W_killzone_max = W_killzone(t) / 1.40
```

Rango: 0.43 (asia, no killzone) → 1.00 (Silver Bullet). Reusa los pesos de `CONSTRAINTS §5` ya validados; sólo cambia la normalización para que vivan en [0, 1].

#### φ_memory(N) — Maduración del bucket

```
φ_memory(N) = 1 − exp(−N / HYBRID_DECAY_N)         si N ≥ 0
             0                                       si N < 0  (bucket toxic, ver §1.2)
```

- N = 0 → φ = 0.0 (bucket nuevo, sin información)
- N = 8 → φ ≈ 0.15 (apenas "watch")
- N = 16 → φ ≈ 0.27 (apenas "active")
- N = 50 → φ ≈ 0.63 (memoria madura)
- N → ∞ → φ → 1.0 (asintótico)

La forma exponencial es la **misma** que sustenta `α = max(0, 1 − n/50)` pero invertida: aquí "más memoria = más fase" (en lugar de "más memoria = menos legacy").

#### φ_horizon(QTE) — Convergencia probabilística cuántica

```
φ_horizon(QTE) = (1 − P_SL_qte) · clip(EV_R_qte / 2.0, 0, 1) · coherence_qte
```

donde `coherence_qte = 1 − path_divergence_normalized`. Las tres componentes ya existen en `compute_tp_sl_probabilities()` y `regime_modal_from_paths()`. Sólo se combinan.

Ejemplo: P_SL=0.20, EV=1.8R, coherence=0.85 → φ_horizon = 0.80 · 0.90 · 0.85 = **0.61**.

#### φ_refractory(Δ) — Recuperación post-emisión

```
φ_refractory(Δ) = clip(Δ_minutes / (60 · SIGNAL_COOLDOWN_HOURS_V2), 0, 1)
```

- Δ = 0 (señal recién emitida) → φ = 0
- Δ = 30min → φ = 0.5
- Δ ≥ 60min → φ = 1.0

Justificación: el sistema necesita "descoherencia" entre emisiones para no autocorrelacionar señales del mismo cluster.

### 1.2 Bucket toxic — caso especial

Si `bucket_memory.confidence == "active"` AND `WR < 0.30` AND `n_closed ≥ 16` → φ_memory = 0 **forzado**, independientemente del exponencial. Esto preserva el gate D.3 actual de `fusion_engine._execute_phase_d`.

---

## 2. Contrato QTE → Fusion (cableo nuevo)

### 2.1 Hoy (sidecar, problemático)

```
fusion_engine.evaluate_signal()  ──→  fire=True
                                          │
fq_bot_v3_2 (línea 2340+) ─── if fire:
                                  qte_paths = generate_paths(...)
                                  if P_SL > 0.40 or EV < 1.20: veto
```

**Problema:** QTE corre DESPUÉS de que `evaluate_signal` ya consumió ciclos en construir P_master, scorer ensemble, regime, bucket memory. Si el QTE veta, todo ese trabajo se desecha. Peor: QTE no influye en `κ_evo` ni en `f_conf`, sólo veta binariamente.

### 2.2 Propuesto (cableado, postulate-driven)

```
fq_bot_v3_2.evaluate_setup_for_timeframe()
    │
    ├─ qte_payload = qt.simulate_for_setup(...)        ← PRIMERO
    │   = {p_sl, p_tp1..tp3, ev_r, regime, uncertainty}
    │
    └─ fusion_engine.evaluate_signal(field, direction, qte_payload=...)
                            │
                            ├─ Phase A, B, C, D (existentes, sin cambio)
                            ├─ Phase E (NUEVA): sync gate τ(t) × QTE
                            └─ P_master_final = P_master · sync_modulator
```

`qte_payload` es opcional (default None) para compatibilidad. Si está presente:
- Influye en `f_conf` vía `sync_modulator` (ver §3)
- Influye en `κ_evo` si bucket está en "watch" (medio confiable + QTE confirma → bump)
- Decide veto/pass en Phase E

### 2.3 Cambio de firma

```python
# fusion_engine.py
def evaluate_signal(
    field, direction, masses, lap, config,
    p_master_provisional, tf_id=None,
    qte_payload=None,   # ← NUEVO, default None preserva back-compat
):
```

CONSTRAINTS §7: añadir parámetro opcional con default no rompe firma pública.

---

## 3. Phase E — Outcome Validation Gate (sync_score)

### 3.1 Composición del sync_score

```
sync_score = (
    0.30 · τ(t)                        # tiempo emergente
  + 0.25 · regime_consistency           # QTE regime ↔ bucket dominant
  + 0.20 · killzone_priority_alignment  # killzone tier ↔ direction
  + 0.15 · path_evr_quality             # EV_R · (1 - P_SL) suavizado
  + 0.10 · bucket_streak_health         # streak ≥ -1 → 1.0; streak ≤ -3 → 0.0
)
```

Cada componente ∈ [0, 1]. Pesos validables vía env (default los de arriba).

#### regime_consistency

```python
if qte.regime_modal == "bull_continuation" and direction == "long":   1.0
elif qte.regime_modal == "bear_reversal" and direction == "short":     1.0
elif qte.regime_modal in ("chop", "range"):                            0.4
elif qte.regime_modal == "sweep_and_reverse":                          0.7 (caso especial: el QTE espera sweep, podría favorecer entry)
else:                                                                   0.0
```

#### killzone_priority_alignment

```python
if field.killzone_priority == "alta" (Silver Bullet, London Open):     1.0
elif field.killzone_priority == "media" (NY full, London Close):       0.7
elif field.killzone_priority == "baja" (Asia, fuera de KZ):            0.3
```

### 3.2 Gate híbrido — RECOMENDACIÓN

| sync_score | Acción | Modulador aplicado |
|---|---|---|
| < 0.30 | **VETO** | P_master = 0 (igual que Θ(D)) |
| 0.30 ≤ s < 0.50 | Pasa atenuado | f_conf' = f_conf · 0.85; κ_evo' = κ_evo · 0.95 |
| 0.50 ≤ s < 0.70 | Pasa neutral | sin modificación |
| 0.70 ≤ s < 0.85 | Pasa con boost | f_conf' = f_conf · 1.05 |
| ≥ 0.85 | Pasa con boost fuerte | f_conf' = f_conf · 1.10; κ_evo' = κ_evo · 1.05 (cap 1.15) |

**Por qué híbrido (defensa de la decisión):**

1. **Hard-gate puro** comprimiría señales (ya 1-3/día) a un goteo insostenible. El motor pierde el edge de operar setups borderline donde múltiples factores se compensan.
2. **Modulador puro** elimina el escudo contra sincronizaciones catastróficas (P_SL > 70%, bucket toxic + regime mismatch). El sistema debería NEGARSE a operar en esos casos, no sólo "operar con menos confianza".
3. **Híbrido graduado** honra el postulado cuántico: la decoherencia es continua, pero existe un umbral debajo del cual la función de onda colapsó al ruido. 0.30 es ese suelo. Por encima, modulación suave.

### 3.3 Caps de seguridad

- κ_evo final SIEMPRE clipeado a [0.85, 1.15] (CONSTRAINTS §5).
- P_master final NO puede aumentar más de 10% sobre la versión sin Phase E (cap explícito para evitar inflación cuántica).
- Si `qte_payload is None` → Phase E NO corre, comportamiento idéntico a v5.0.

---

## 4. Compatibilidad con CONSTRAINTS

| Invariante | ¿Conflicto? | Justificación |
|---|---|---|
| §1.1-§1.7 (ventana, CHoCH, Fib, SL inmovible…) | ❌ NO | Phase E es aditivo, no toca gates previos. |
| §2 (SL anclaje estructural) | ❌ NO | QTE usa los SL que ya entrega `signal_levels.py`. |
| §3 (Θ(D) kill-switch) | ❌ NO | Θ(D) se sigue ejecutando ANTES; sync gate corre DESPUÉS. |
| §4 (constantes φ, α, etc.) | ❌ NO | No introducimos constantes nuevas. `HYBRID_DECAY_N` reusado. |
| §5 (ecuación maestra) | ⚠️ EXTENSIÓN | Se introduce `· sync_modulator` al final; documentado como extensión v5.1. Sigue conservando todos los factores anteriores. |
| §7 (no nuevas deps) | ❌ NO | Sólo numpy/pandas, ya presentes. |
| §12 (QTE aditivo) | ⚠️ REINTERPRETACIÓN | QTE pasa de "veto post-fusion" a "input a fusion". Sigue siendo aditivo en el sentido de que un setup que pasaba en v5.0 SIN QTE seguirá pasando con `qte_payload=None`. |

**Decisión recomendada:** subir CONSTRAINTS a v5.1 con un §13 nuevo que codifique el postulado τ(t) y la Phase E. No reescribir §5 ni §12 — añadir.

---

## 5. Ecuación maestra v5.1 propuesta

```
P_master_v51 = Θ(D) · κ_evo' · φⁿ · W_eff · H_lap · f_conf' · f_ict · σ(τ)

donde:
  σ(τ) = sync_modulator(sync_score)   ∈ [0.0, 1.10]
  κ_evo' = κ_evo · sync_modulator_kappa(sync_score)    ∈ [0.85, 1.15]
  f_conf' = f_conf · sync_modulator_conf(sync_score)   ∈ [1.00·0.85, 1.35·1.10]
```

Si Phase E veta (sync_score < 0.30): σ(τ) = 0 → P_master = 0. Comportamiento idéntico a Θ(D)=0 actual.

Si no hay QTE (`qte_payload=None`): σ(τ) = 1, κ_evo' = κ_evo, f_conf' = f_conf → ecuación reduce a v5.0 exacta.

---

## 6. Plan de implementación (post-aprobación de este diseño)

**Fase 0 — Aprobación.** Discusión sobre §1 (forma de las φᵢ), §3.2 (umbrales del híbrido). Modificaciones aquí, NO en código.

**Fase 1 — Módulo INERTE.**
- Crear `emergent_time.py` con funciones puras: `phi_clock`, `phi_memory`, `phi_horizon`, `phi_refractory`, `tau`, `sync_score`.
- Tests sintéticos: confirmar que con QTE óptimo + killzone Silver Bullet + bucket maduro WR=60% → τ ≈ 0.6+, sync_score > 0.7.
- Confirmar que con bucket toxic → φ_memory=0 → τ=0 → veto.
- **NO** importa nada del bot principal. Solo `numpy` (ya dep).

**Fase 2 — Wiring opcional.**
- `fusion_engine.evaluate_signal()` acepta `qte_payload=None`.
- Si presente y `FQ_EMERGENT_TIME_ENABLED=1`, corre Phase E. Si no, comportamiento idéntico a hoy.
- Logs estructurados de sync_score en cada evaluación para observability previa a producción.

**Fase 3 — Pre-cómputo del QTE.**
- `fq_bot_v3_2.evaluate_setup_for_timeframe()` corre `qt.simulate_for_setup()` ANTES de llamar a `fusion_engine.evaluate_signal()`.
- Pasa `qte_payload` directamente.
- Elimina el gate post-fire actual (líneas 2340-2369) UNA VEZ que la versión nueva esté validada con ≥50 señales históricas.

**Fase 4 — Producción.**
- `FQ_EMERGENT_TIME_ENABLED=1` por default.
- CONSTRAINTS bumped a v5.1.
- `_KNOWLEDGE_NOTES.md` actualizado documentando el postulado.

---

## 7. Métricas de éxito (qué medimos en backtest antes de activar)

Sobre el ledger histórico de las últimas 100 señales cerradas:

1. **Win-rate de las señales que habrían pasado Phase E** vs WR actual. Esperado: +5-10 pp.
2. **Expectancy R medio** post-Phase E vs actual. Esperado: igual o +0.15 R.
3. **Frecuencia de señales/día** post-Phase E. Esperado: NO menor a 0.8× la actual (si baja más, los umbrales están mal calibrados).
4. **Distribución del sync_score** sobre señales TP1+ vs SL. Esperado: separación visible (TP1+ centradas >0.6, SL centradas <0.5).

Si (3) viola la cota, RasDG ajusta umbrales de §3.2 antes de activar.

---

## 8. Preguntas abiertas para el siguiente turno

1. ¿Los pesos del sync_score (0.30/0.25/0.20/0.15/0.10) son arbitrarios? Sí, hay que validarlos con greedy sweep tipo `threshold_sweep()` ya existente, adaptado a vector de 5 pesos. ¿Lo hacemos en Fase 1 (módulo inerte) o Fase 4 (producción gateada)?
2. ¿El umbral inferior 0.30 para veto debería depender de tier? Ej: scalp acepta hasta 0.25, high-tier exige ≥0.40. Pendiente de discusión.
3. ¿`φ_refractory` debería ser por símbolo o global? Hoy `SIGNAL_COOLDOWN` es global. Si dos símbolos con baja correlación tienen setups simultáneos, los frenamos sin razón.
4. ¿La Phase E debería loguear su decisión en `field_reports.py` para post-mortem? Recomendado: sí, columna nueva `sync_score` en ledger v3.

---

#FQv51 #PostuladoEmergenteTau #QuantumSynchronization #CONSTRAINTS-pending-v51
