# CONSTRAINTS.md — Invariantes del Motor FQ v5.0 (Mistral · Quantum Timelines Edition)

Última actualización: 2026-05-21 — alineado con motor v5.0 post-integración del Quantum Timelines Engine.

Este archivo define las **reglas duras del motor Fibonacci Cuántico** vigentes para
la edición Mistral Quantum y preparación para venta al público.

Las versiones previas (v3.0 paper, v4.x mistral edition) definían restricciones que la
operativa real ha superado. Esta versión (v5.0) introduce el **Quantum Timelines Engine
(QTE)** como capa decisoria principal — simulación Monte Carlo bajo restricciones
estructurales reales — manteniendo TODOS los invariantes v4.3 como sustrato.

Cualquier propuesta de cambio que rompa una de estas reglas debe ser marcada
como CONFLICTO y requiere aprobación manual antes de implementarse.

---

## 1. Invariantes operativas vigentes (v4.3)

1. **Ventana 24/7 con sólo veto weekend.** El bot opera de domingo 22:00 UTC a
   viernes 22:00 UTC. Asia, London, NY y los intermedios están todos habilitados.
   El veto Asia previo (v3) se descartó: con scorer ensemble + regime detector,
   sesiones de baja liquidez pueden producir setups válidos.
2. **CHoCH es señal, no gate.** El motor lee CHoCH como una de varias confluencias
   institucionales, pero NO bloquea operativas que se validan por order flow,
   sweeps, displacement o Power-of-3 sin CHoCH explícito. (v3 lo requería, v4.3 lo
   considera evidencia entre otras.)
3. **Fibonacci toques no es gate.** El número de toques históricos al nivel Fib
   no determina validez. Lo que importa es la confluencia ICT actual (OB + FVG +
   Fib + PD) en el momento del setup. (v3 exigía ≥2 toques, v4.3 lo descartó.)
4. **SL inmovible.** El Stop Loss NUNCA se mueve una vez colocado. Ni trailing,
   ni breakeven manual, ni "darle chance". Nunca. (Conservado de v3.)
5. **Leverage cap escalonado.** Máximo 8x absoluto, sólo si P_master >= φ³.
   5x para tier estándar (φ² ≤ P < φ³). 3x para scalp (P < φ²). (Conservado.)
6. **Umbral de fire P_master >= 1.80.** PMASTER_MIN actual = φ ≈ 1.80, que en la
   escala de conviction (1-10) corresponde a ~4.25/10. El gate "P >= 7/10" (~2.965)
   queda como opt-in vía `FQ_ENFORCE_HIGH_GATE=1` para producción estricta. Default
   OFF en beta para permitir exploración del bucket histórico.
7. **Weekend veto.** Veto duro viernes 22:00 UTC → domingo 22:00 UTC. Override
   manual con `FQ_WEEKEND_VETO=0` solo para backtest.

## 2. Anclaje estructural del SL

- SL **debe** anclarse a nodos estructurales (EMA50, soportes confirmados, OB low).
- SL **nunca** se ancla a Bollinger Bands (lección 15 abr 2026: LONG $84.20 con
  SL en BB → hit $83.79, -$77 USDT).
- Fórmula vigente: `SL = entry × (1 − fib × (1 − φ⁻¹))` con anclaje preferente
  a EMA50/estructura cuando esté dentro del rango.

## 3. Kill-switch Θ(D) — v4.2 (refinado)

Tres decoherencias simultáneas validan el setup. Si alguna falla, **P_master = 0**:

- **Macro**: BTC y ETH alineados en 15m con la dirección propuesta (ventana
  deslizante 4 velas, threshold 0.05% post-calibración v4.1).
- **Técnica**: ≥5/7 indicadores alineados en 15m (RSI, EMAs, momentum).
- **Liquidez**: triple RSI(6/12/24) en regime alignment + sweep recientes válidos.

κ(p) requiere ≥2 confluencias de masa en P-Space (relajado de ≥3 en v3.0).

## 4. Constantes matemáticas (no redefinir)

- φ = 1.6180339887
- φ² = 2.6180
- φ³ = 4.2360
- φ⁻¹ = 0.618
- α = 1/137.507 = 0.00727
- B = φ²/α + e + π = 364.6247
- ∠φ = 137.507°
- h = φ√(3/4) = 1.401258

## 5. Ecuación maestra v4.2 (vigente)

```
P_master = Θ(D) · κ_evo · φⁿ · W_eff · H_lap · f_conf · f_ict
```

Donde:
- `Θ(D)` ∈ {0, 1}: kill-switch (3 decoherencias).
- `κ_evo` ∈ [0.85, 1.15]: modulador evolutivo Thompson sampling sobre bucket v3.
- `φⁿ` = φ con n=1 (base scalp), φ² (standard), φ³ (high conviction).
- `W_eff = W_clock_legacy · α + W_killzone · (1 − α)`, con
  `α = max(0, 1 − n_closed_v3 / 50)`. Migración hibrida sesión legacy → killzones ICT.
- `H_lap` ∈ {0.7, 1.0}: laplaciano activo / inactivo.
- `f_conf` ∈ [1.00, 1.35]: jerarquía PD + confluencia ICT.
- `f_ict` = `1.0 + n_concepts × 0.04` con cap n_concepts ≤ 4. Bonus por concepto
  ICT activo (Breaker, MSS, Inducement, Power-of-3, BPR, OTE estricto, Displacement).

**Pesos de killzone (post-recalibración v4.2):**
- Silver Bullet London/NY AM/NY PM: 1.40 (prioridad máxima)
- London Open / NY AM completo: 1.20
- NY PM completo: 1.10
- London Close: 1.00
- Asia: 0.70
- Fuera de killzone: 0.60

## 6. TPs

- TP1 = entry × (1 + fib × φ⁻¹)  · 30% size
- TP2 = entry × (1 + fib × φ)     · 30% size
- TP3 = entry × (1 + fib × φ²)    · 25% size
- TP4 = entry × (1 + fib × φ³)    · 15% size

## 7. Memoria autoevolutiva (v4.2+)

- **Ledger persistente** en SQLite (`/data/fq_ledger.db` Railway Volume).
- **Bucket key v3**: `killzone | tier | direction | pd_zone | hierarchy |
  concept_flags`. 7 flags ICT compactados (breaker, mss, inducement, pwr3, bpr,
  ote_strict, displacement).
- **Thompson sampling** para κ_evo: Beta(1+wins, 1+losses), sample → κ ∈ [0.85, 1.15].
- **Self-audit Opus cada 25 cerradas**, prompt enriquecido con desglose por
  concepto ICT (CON vs SIN).

## 8. Capa ML v4.3 (additiva, no modifica P_master)

- **Ensemble scorer** (5 weak learners: volume, structure, liquidity, concept_stack,
  history). Lineal con pesos env-configurables. Default uniforme.
- **Shapley attribution** trivial (linear ensemble) — feature importance honesta
  para post-mortem.
- **Regime detector** (KL drift + ATR z-score + WR trend) → estable / shift_moderate
  / deriva. En deriva + scorer bajo → veto adicional.
- **MSBoost-style** attenuation: scorers con accuracy <10% bajo la media reciente
  pierden 50% de peso temporalmente.
- **GOSS-inspired** weight update: SL pesan 1.0 (residual grande), TP1 pesan 0.7,
  TP2-4 pesan 0.5.
- **Greedy threshold sweep** post-hoc (admin /sweep), no modifica nada vivo.

Documentación de fuentes en `_KNOWLEDGE_NOTES.md`.

## 9. Reglas de integración para extracciones

- **NO** agregar dependencias sin justificar (sin `xgboost`, sin `lightgbm`,
  sin `sklearn`, sin `scipy`). Sólo Python stdlib + pandas/numpy ya presentes.



## 7. Reglas de integración para extracciones

Cuando se proponga incorporar contenido de los PDFs:

- **NO** agregar nuevas dependencias sin justificar.
- **NO** modificar firmas de funciones públicas del motor sin marcar como BREAKING.
- **NO** introducir constantes que choquen con §4.
- **NO** reescribir módulos completos. Sólo extender vía nuevos archivos o funciones
  aditivas.
- **SÍ** documentar fuente (PDF, página) de cada concepto integrado en `_KNOWLEDGE_NOTES.md`.
- **SÍ** mantener back-compat con ledger histórico (todas las migraciones de schema
  son idempotentes vía `migrate_schema_v2` y `migrate_schema_v3`).

## 10. Estilo de código

- Convención del motor actual: ASCII-only en source files; UTF-8 en comments.
- Comentarios en español para lógica de negocio, inglés para utilidades técnicas.
- Tests obligatorios para cualquier fórmula nueva (mínimo smoke test sintético).
- No emojis en código ni en mensajes Telegram salvo glyphs Unicode sólidos
  (▴ ▾ ◆ ▰ ▸ ▪ ━) usados en bot público y format VIP.

## 12. Capa Quantum Timelines (v5.0)

- **Simulación obligatoria** antes de emitir señal: 500 paths Monte Carlo bajo
  restricciones ICT/SMC reales (drift mean-reversion EMA50 + vol_shock ATR-calibrado
  + magnetic_pull a pools no barridos + sweep_bias en wicks de stop hunt).
- **Constraints de emisión**:
  - `P(SL) ≤ 0.35` — no aceptar setups con >35% probabilidad de stop primero.
  - `expected_R ≥ 1.0` — EV mínimo 1R o no se dispara.
  - `SL distancia ≥ 0.5 × ATR` del entry — no SL ridículamente cercanos.
- **SL anclado a estructura** — jerarquía Order Block → liquidity pool → swing low →
  FVG → EMA50 (fallback). NUNCA a buffer fijo. NUNCA a Bollinger.
- **TPs anclados a liquidez/estructura real** — P-Space resistances, pools no
  barridos (BSL/SSL targets), Order Blocks opuestos, FVG bearish bottoms,
  fib extensions 1.272 y 1.618.
- **Output en probabilidades** — el reporte VIP muestra P(TP_i), P(SL), EV en R,
  régimen dominante y coherencia (1 - uncertainty). NO se exponen formulas internas
  de generación de paths (gain de magnetic_pull, vol_normalization, sweep_bias_radius).
- **QAOA-inspired optimization** — admin puede correr `/timelines` con 2000 paths
  y ver la combinación óptima de niveles dentro de los candidatos estructurales.
- **Capa aditiva** — QTE NO reemplaza P_master ni Θ(D). Se aplica DESPUÉS de que
  ambos gates pasan. La señal sólo se emite cuando: `Θ(D)=1 ∧ P_master ≥ φ ∧ EV_QTE ≥ 1R ∧ P_SL_QTE ≤ 0.35`.

## 11. Beta final → producción

Para preparar venta al público:
- Schema v3 debe estar migrado en producción (`/data/fq_ledger.db`).
- Bot público (`entry_public.py`) corriendo como servicio independiente con su
  propio `TELEGRAM_TOKEN_PUBLIC` y BD local (`/data/fq_public.db`).
- VIP signals en formato Mistral (`vip_format.build_vip_signal`) — fórmulas
  internas DISFRAZADAS (P_master, κ_evo, Θ(D) no se exponen al VIP).
- Admin commands (`/audit`, `/entropy`, `/metrics`, `/ledger`, `/evolve`,
  `/concepts`, `/weekend`, `/campo`, `/atribucion`, `/regimen`, `/sweep`) gated
  por `chat_id == TELEGRAM_CHAT_ID`.
- VIP BotFather menu = 6 comandos (status / lectura / miestado / renovar /
  about / help). Público BotFather menu = 4 comandos.

#FQv5 #MistralQuantum #QTE #ProductionReady
