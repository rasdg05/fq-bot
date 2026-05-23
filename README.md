[README_DEPLOY.md](https://github.com/user-attachments/files/27770355/README_DEPLOY.md)
# FQ v5.1 — Mistral · Emergent Time Edition

Motor de trading probabilístico para SOL/USDT. Simula líneas de tiempo futuras bajo restricciones ICT/SMC, las sincroniza con un postulado de tiempo emergente τ(t), y opera sólo cuando el Valor Esperado supera 1R y la fase del sistema cruza el umbral.

> **v5.1 (mayo 2026)**: introduce el **postulado τ(t) de tiempo emergente** que unifica las fórmulas dispersas de fase (killzone weighting, decay legacy↔ICT, horizonte QTE, refractario post-emisión) en una sola función ∈ [0, 1]. Cablea el QTE como **input** a la fusión (no como sidecar veto). Añade **Phase E** con sync_score híbrido graduado: veto duro <0.30, modulación 0.30-0.70, boost ≥0.70. Documentación del postulado en `_POSTULATE_EMERGENT_TIME.md`. **Estado: diseño aprobado, implementación en módulo inerte pendiente.**

## Cambios v5.1 (sobre v5.0)

1. **Postulado τ(t) unificado** — `_POSTULATE_EMERGENT_TIME.md` define `τ(t) = φ_clock · φ_memory · φ_horizon · φ_refractory` como la probabilidad emergente de que el ahora sea operable. Reusa constantes existentes (HYBRID_DECAY_N=50, killzone weights de §5, QTE horizon=96, SIGNAL_COOLDOWN=1h). Sin nuevas dependencias.
2. **Contrato QTE → Fusion** — `evaluate_signal()` aceptará `qte_payload=None` como parámetro opcional. Con payload presente, el QTE pasa de "veto post-fire" a "input al P_master". Back-compat preservada con default None.
3. **Phase E — sync_score híbrido** — gate graduado:
   - sync_score < 0.30 → veto absoluto (P_master = 0)
   - 0.30-0.50 → atenuación f_conf · 0.85, κ_evo · 0.95
   - 0.50-0.70 → paso neutro
   - 0.70-0.85 → boost f_conf · 1.05
   - ≥ 0.85 → boost fuerte f_conf · 1.10, κ_evo · 1.05
4. **Ecuación maestra v5.1** — `P_master = Θ(D) · κ_evo' · φⁿ · W_eff · H_lap · f_conf' · f_ict · σ(τ)`. Reduce a v5.0 exacta cuando `qte_payload=None`.
5. **Gap reconocido (IFVG)** — las **Inverse Fair Value Gaps** todavía NO están implementadas. `ict_smc.detect_fvgs()` filtra solo FVGs no rellenas (`filled_pct < 0.5`) y descarta las invertidas, que actúan como zonas opuestas fuertes (resistencia tras break alcista, soporte tras break bajista). Pendiente para v5.2: `detect_inverse_fvgs()` con tracking de FVGs traspasadas, integración en `build_confluence()` y bandera `had_ifvg` en bucket_key_v4.

## Cambios v5.0 (sobre v4.3)

1. **Quantum Timelines Engine (`quantum_timelines.py`)** — módulo nuevo, cuántico-inspirado clásico (numpy puro, cero qiskit/D-Wave). Antes de cada señal, simula 500 paths Monte Carlo sobre 96 velas (24h en 15m) con:
   - drift de mean-reversion a EMA50
   - vol_shock estocástico calibrado al ATR
   - magnetic_pull a pools de liquidez **no barridos** (∝ 1/dist²)
   - sweep_bias cerca de wicks de stop hunt
2. **Probabilidades reales** — sobre los paths se mide P(TP1), P(TP2), P(TP3), P(SL), EV en múltiplos de R y win_rate. Se clasifican los paths en 5 regímenes (bull_continuation / bear_reversal / chop / sweep_and_reverse / range) y se reporta el dominante.
3. **SL anti-stop-hunt** — `calculate_levels_v2` reemplaza al cálculo legacy. SL anclado por **jerarquía**: Order Block bullish → liquidity pool → swing low → FVG bottom → EMA50 (fallback). Buffer ATR-adaptativo (`max(0.6*ATR, 0.15%*entry)`) en lugar de fijo 0.2%.
4. **TPs en liquidez real** — anclados a P-Space resistances, pools no barridos (BSL/SSL targets), Order Blocks opuestos, FVGs opuestos y extensiones Fib 1.272/1.618. Se elige la combinación con mayor EV simulado.
5. **QAOA-inspired optimizer** — grid search clásico sobre candidatos de (SL, TP1, TP2, TP3) que maximiza EV sobre los paths, sujeto a `P(SL) ≤ 35%` y `EV ≥ 1R`. Si encuentra mejora, sustituye los niveles F1.
6. **Routing tier-aware `/analisis`** — admin recibe lectura multi-TF completa con bloque QTE detallado y Claude Sonnet (700 tokens); VIP recibe formato Mistral curado con bloque QTE compacto y Claude breve (4 bullets, 320 tokens).
7. **Comando `/timelines` (admin)** — análisis profundo con n_paths=2000, ASCII histogram de cierres finales 24h, comparativa baseline vs optimized.

La capa v4.3 (ensemble scorer, regime detector, ICT/SMC 14 conceptos, Thompson sampling, weekend veto, audit Opus cada 25 cierres) sigue funcionando intacta como sustrato del QTE — es **aditivo**, no reemplaza.

## Cambios v4.2 (sobre v4.1.1)

1. **7 detectores ICT nuevos** en `ict_smc.py` (Breaker Block, MSS, Inducement, Power of 3,
   Balanced Price Range, Displacement, OTE estricto 62-79%).
2. **Thompson sampling** sobre `bucket_key_v3` con flags por concepto ICT (env `FQ_USE_THOMPSON=1` por default).
3. **Schema v3 migration** (idempotente) — agrega columnas `bucket_key_v3`, `concepts_flags`,
   `had_breaker`, `had_mss`, `had_inducement`, `had_pwr3`, `had_bpr`, `had_ote_strict`,
   `had_displacement`, `weekend_flag`, `kappa_method`.
4. **Persistencia automática**: `FQ_LEDGER_PATH` default detecta `/data` montado (Railway
   Volume) y cae a `/tmp` con warning. **Monta un Volume en `/data` para que la memoria sobreviva.**
5. **Weekend veto** (env `FQ_WEEKEND_VETO=1` por default) — corta señales viernes 22:00 UTC
   → domingo 22:00 UTC.
6. **Silver Bullet recalibrado** al estándar ICT: London SB 2-3 CDMX, NY AM SB 9-10 CDMX,
   NY PM SB 13-14 CDMX.
7. **Audit Opus enriquecido** (`build_audit_prompt_v3`) — desglose por concepto ICT:
   "¿cuáles del PDF aportan edge real?".
8. **Comandos nuevos**: `/concepts`, `/weekend`.
9. **Auto-enable** de la capa ICT cuando los módulos cargan (ya no hace falta poner
   `FQ_ENABLE_ICT=1` a mano — solo úsalo para desactivar con `0`).

## Archivos del refactor

| Archivo | Acción |
|---|---|
| `ict_smc.py` | **Nuevo.** Subir a la raíz del repo Railway. |
| `killzones_pd.py` | **Nuevo.** Subir a la raíz. |
| `fusion_engine.py` | **Nuevo.** Subir a la raíz. |
| `field_reports.py` | **Nuevo.** Subir a la raíz. |
| `fq_bot_v3_2.py` | **Reemplaza el actual.** Tiene `_evaluate_setup_v411` y delegate condicional. |
| `entropy_cognition_patch.py` | **Patch.** Pegar el bloque al final de `entropy_cognition.py` existente. |

## Despliegue por fases (feature flags)

Todas las variables de entorno arrancan en `0`. El bot mantiene comportamiento legacy hasta que enciendas un flag.

### Modo 1 — Producción intacta (default)
```
FQ_ENABLE_ICT=0
FQ_ENABLE_FIELD=0
```
El bot opera exactamente como v3.2. Cero cambio.

### Modo 2 — ICT layer ON, sin reportes de campo
```
FQ_ENABLE_ICT=1
FQ_ENABLE_FIELD=0
```
- `evaluate_setup` delega a `fusion_engine.evaluate_signal`.
- Las 4 fases A/B/C/D filtran antes de calcular `P_master`.
- Si pasa: dispara señal con plantilla Capa 5 (`build_signal_report`).
- Si falla: silencio (como v3.2 cuando los gates no pasan).

### Modo 3 — Lectura de campo activa
```
FQ_ENABLE_ICT=1
FQ_ENABLE_FIELD=1
```
- Igual al Modo 2, pero además emite **reportes de campo** cuando fase A/B/C/D falla.
- Reportes solo a admin/VIP (no al free tier).
- Permite ver QUÉ está mirando el bot incluso cuando no dispara.

### Modo 4 — Comando manual `/campo`
Disponible siempre que `FQ_ENABLE_ICT=1`. Devuelve lectura on-demand del estado del campo sin disparar señal.

## Migración del schema SQLite

Idempotente. En `main()` se llama `ev.migrate_schema_v2()` automáticamente al arrancar. Agrega columnas v2 (`killzone`, `pd_zone`, `pd_hierarchy`, `confluence_count`, `bias_4h`, `bias_1h`, `bucket_key_v2`, etc.) sin tocar las viejas. Si las columnas ya existen, no falla.

## Híbrido `w_clock` ↔ `w_killzone`

Decisión adoptada del Punto 3. El sistema arranca usando 100% `w_clock_legacy` (asia/london/ny/overlap) y migra gradualmente a `w_killzone` (silver_bullet_lo/ny, london_open_kz, ny_am_kz, etc.) conforme acumula señales cerradas con bucket key v2:

```
alpha = max(0, 1 - n_closed_v2 / 50)
w_effective = w_clock_legacy * alpha + w_killzone * (1 - alpha)
```

Cuando llegues a 50 cerradas con buckets v2, `alpha = 0` y el bot opera 100% por killzones. **No requiere intervención manual.**

## Cierre del loop — memoria de outcome

Fase D del agente carga `BucketMemory` del bucket actual (killzone × tier × dirección × pd_zone × hierarchy) y rechaza la señal si:
- `confidence == "active"` (≥16 cerradas) AND `win_rate < 30%`
- O hay racha de 4+ pérdidas consecutivas

El sistema ahora **usa** su historia, no solo la guarda.

## Riesgos / mitigación

- **Si fusion_engine falla** → `_evaluate_setup_v411` captura la excepción y devuelve `False`. El bot continúa sin disparar pero no crashea.
- **Si los módulos nuevos no se encuentran** → `ICT_MODULES_AVAILABLE = False`, el delegate no se activa, flujo legacy intacto.
- **Si las columnas v2 ya existen** → `migrate_schema_v2` ignora silenciosamente y continúa.
- **Si bucket v2 está vacío** → `kappa_evo = 1.0` neutral, no afecta P_master.

## Próximas señales

Cuando enciendas `FQ_ENABLE_ICT=1`, recibirás en Telegram el formato Capa 5 completo con:
- Estado del campo (sesgo 4H+1H, zona PD, alineación)
- Liquidez (pools sup/inf, sweeps recientes con/sin reacción)
- Nodo en observación (confluencia ICT listada elemento por elemento, jerarquía PD, tipo colapso/superposición)
- Matemática cuántica (W_killzone, W_legacy, W_effective con alpha, f_confluencia, kappa_evo)
- Veredicto de fase + memoria del bucket
- Acción con SL anclado a EMA50 y TPs por φ

## Comandos nuevos

| Comando | Función |
|---|---|
| `/campo` | Lectura on-demand del estado del campo |
| `/concepts` | Edge por concepto ICT del PDF (con vs sin) |
| `/weekend` | Estado del filtro fin de semana |

Los demás (`/metrics`, `/entropy`, `/ledger`, `/evolve`, `/audit`) siguen funcionando como antes — y los buckets v3 empezarán a alimentarlos automáticamente.

## Deploy v4.2 en Railway — 3 cosas

1. **Crea un Volume** en tu servicio Railway, monta en `/data` (5GB gratis).
2. (Opcional) Setea `FQ_LEDGER_PATH=/data/fq_ledger.db` si quieres ser explícito; si no, lo detecta solo.
3. Redeploy. El bot migra el schema v3 automáticamente y empieza a registrar concept flags
   en cada señal. Tras 8 cerradas por bucket v3, Thompson sampling toma el control de kappa_evo.

## Env vars v4.2

| Var | Default | Función |
|---|---|---|
| `FQ_ENABLE_ICT` | auto | `1`=usa fusion_engine, `0`=legacy |
| `FQ_ENABLE_FIELD` | auto | `1`=field reports en fallos |
| `FQ_LEDGER_PATH` | `/data` si existe | Path del SQLite ledger |
| `FQ_WEEKEND_VETO` | `1` | `0` para desactivar veto sáb-dom |
| `FQ_USE_THOMPSON` | `1` | `0` para usar kappa_evo lineal v2 |
| `FQ_REQUIRE_OTE` | `0` | `1` requiere OTE estricto en Fase C |

#FQv51 #MistralEmergentTime #QTE #TauPostulate #RasDG
