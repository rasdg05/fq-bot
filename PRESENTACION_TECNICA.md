# FQ — Presentación técnica

> Señales SOL/USDT con disciplina sistemática.
> Documento interno para colaboradores y evaluación técnica.

A diferencia de la presentación comercial, este documento sí entra al motor:
arquitectura, pipeline de decisión, módulos y roadmap. No es material de
cliente.

---

## 1 · Resumen del sistema

FQ es un bot de **trading + pagos en vivo** sobre SOL/USDT que corre en
producción (Railway). Vigila el mercado en tiempo real, evalúa setups contra
un pipeline de varias fases y solo dispara señales cuando superan un gate de
convicción. Las señales se siguen hasta su cierre y cada outcome alimenta la
memoria estadística del sistema.

- **~18,000 líneas** en total; el monolito `fq_bot_v3_2.py` concentra ~4,900.
- **Dos caras**: bot VIP (motor + señales) y bot público (marketing, read-only).
- **Sin dependencias cuánticas ni ML pesado en runtime**: numpy + pandas + LLM on-demand.

---

## 2 · Topología de procesos

`launcher.py` arranca 3 procesos hijos en el **mismo** servicio Railway (no
permite volúmenes compartidos entre servicios), sobre el mismo volumen:

```
launcher.py
  ├─ vip          entry_vip.py  → fq_bot_v3_2.py
  │               motor de señales, gate QTE, radar/alertas,
  │               comandos VIP, ledger (escritura)
  ├─ public       entry_public.py
  │               marketing; lee el ledger VIP en READ-ONLY,
  │               anuncia cierres, teasers, celebraciones TP3
  └─ maintenance  ops.maintenance
                  backups, heartbeat
```

Comunicación **VIP → Público: solo** vía el archivo SQLite del ledger (RO).
Cero acoplamiento de código entre procesos. Si un hijo muere, el launcher sale
con `rc != 0` y Railway reinicia el contenedor.

---

## 3 · Stack

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.11 (ASCII-only en módulos de motor) |
| Datos de mercado | CCXT (`fetch_ohlcv`) + pandas / pandas-ta |
| Cómputo | numpy / pandas |
| Persistencia | SQLite (ledger append-only, RO para el público) |
| Mensajería | Telegram Bot API (long polling) |
| LLM | Anthropic — Sonnet (lecturas) + Opus (revisión / self-audit) |
| Web / health | Flask |
| Deploy | Railway (`railway.toml`, `Procfile`) |

---

## 4 · Pipeline de decisión

`fusion_engine.evaluate_signal()` es la **única** función pública del motor.
Reemplaza la lógica monolítica de `evaluate_setup()`. Evalúa en fases:

1. **Fase A — Sesgo estructural + PD.** Dirección y zona Premium/Discount.
2. **Fase B — Liquidez.** Sweeps, pools no barridos, calidad de reacción.
3. **Fase C — Confluencia ICT.** Requiere `CONFLUENCE_MIN ≥ 3` conceptos;
   bonus +4% por concepto (cap +16%).
4. **Fase D — Timing + CRT + memoria.** Carga el bucket de outcome y aplica
   `kappa_evo` (modulador suave ±15% sobre `P_master`).
5. **Fase E — Sync modulator.** Tiempo emergente `tau`; si `sync_score < 0.30`
   → **veto absoluto**.
6. **Volume quality** (v5.2) — modulador final sobre `P_master`.

**Gate de convicción:** `P_master ≥ phi²` (≈2.618). Para *fire/broadcast*,
CONSTRAINTS §6 exige `P_master ≥ 7/10` (~2.965). El gate `Theta(D)` es
**sagrado**: ningún modulador lo toca.

**Capa ML (v4.3, additiva y advisory):** ensemble de 5 scorers
(volume, structure, liquidity, concept_stack, history) + atribución Shapley.
Enriquece la decisión cuando `P_master` ya pasó el umbral; **no** sustituye al
motor.

---

## 5 · Mapa de módulos

**Núcleo de decisión (puro, testeable)**
- `fusion_engine.py` — orquesta las fases A–E + memoria de outcome.
- `quantum_timelines.py` — motor de simulación (QTE).
- `battle_planner.py` — campo + paths → veredicto operable.
- `signal_scorer.py`, `signal_engine_v2.py` — scoring / ensemble.
- `ict_smc.py`, `market_context.py`, `regime_detector.py`,
  `volume_quality.py`, `killzones_pd.py` — features de mercado.
- `emergent_time.py`, `entropy_cognition.py` — tiempo emergente + ledger/memoria.
- `fq_radar.py`, `fq_market_data.py` — **extraídos (v5.3)**, lógica pura + I/O mockeable.

**Presentación (cara al cliente, blindada por tests)**
- `branding.py`, `vip_format.py`, `public_format.py`, `field_reports.py`, `legal.py`.

**Bot público**
- `public_outcome_announcer.py`, `public_scheduler.py`,
  `public_handlers.py`, `public_content_generator.py`.

**Pagos / suscripciones**
- `vip_system.py` (tiers, códigos, panel admin), `payments.py` (Stripe + USDT).

**Monolito (a adelgazar)**
- `fq_bot_v3_2.py` — loop principal, fetch+indicadores, `radar_check`,
  evaluación de setups, broadcast, routing de comandos, hooks de evolución.

---

## 6 · Motor QTE (Quantum Timelines Engine)

Motor probabilístico **cuántico-inspirado** (sin qiskit ni dimod). Simula N
futuros (Monte Carlo paths) bajo restricciones estructurales y mide
`P(TP_i)`, `P(SL)`, valor esperado en R y régimen dominante.

| Concepto cuántico | Mapeo clásico |
|---|---|
| Superposición | N paths Monte Carlo coexistiendo |
| Función de onda | Distribución empírica de paths |
| Hamiltoniano | bias: drift + vol + magnetic_pull |
| QAOA | grid search sobre (SL, TP1, TP2, TP3) → max EV |
| Colapso / medición | régimen modal del ensemble |
| Decoherencia | divergencia de paths = incertidumbre |

- **300–2000 paths**, horizonte 96 velas de 15m (= 24h).
- Objetivo de performance: **< 1.5s con 500 paths** en Railway.
- Módulo **inerte**: solo computa, no envía ni toca DB.

---

## 7 · Memoria y autoevolución

**`entropy_cognition`** — el bot no recuerda outcomes individuales, los
**destila** en distribuciones:

- `SignalLedger` — SQLite append-only, con backup a Telegram.
- `OutcomeTracker` — monitorea señales abiertas hasta TP/SL/timeout.
- `EntropyEngine` — Shannon H sobre buckets (sesión × tier × dirección ×
  curvatura) + KL-divergence para detectar drift.
- `KappaEvo` — modulador suave ±15% sobre `P_master`. **Nunca toca `Theta(D)`.**
- `SelfAudit` — cada 25 cerradas, Opus audita el ledger y **propone** ajustes
  (sugerencias, no autoaplicadas).

**`emergent_time`** — postulado
`tau = phi_clock · phi_memory · phi_horizon · phi_refractory`. Módulo puro,
sin imports del bot.

**`battle_planner`** — combina campo ICT + paths del QTE y emite uno de:
`EJECUTAR_AHORA` / `ACUMULAR_EN_ZONA` / `ESPERAR_GATILLO` / `STAND_DOWN`.

---

## 8 · Co-pilot LLM

`claude_integration.py` — LLM táctico on-demand:

- **Sonnet** — lecturas VIP y análisis a pedido.
- **Opus** — revisión de señales auto-disparadas de alta convicción y self-audit.

Recibe payloads ricos (precio, QTE, niveles, eventos, walls, derivados). En
superficies de cliente el output es **cualitativo** (probabilidad alta / edge
claro), nunca fórmulas ni jerga del motor.

---

## 9 · Migración y roadmap

Estrategia **strangler fig**: extraer piezas cohesivas del monolito a módulos
puros/testeables, por **etapas verificadas y reversibles**. Regla de oro de
cada etapa: extraer → el monolito importa/reexporta → `pytest` verde antes de
commitear.

- [hecho] `fq_radar.py` — decisión pura del radar.
- [hecho] `fq_market_data.py` — `fetch_ohlcv` + `add_indicators` mockeables.
- [ ] `fq_broadcast.py` — envío Telegram desacoplado de globals.
- [ ] `fq_commands/` — router de comandos (hoy un gran `if/elif`).
- [ ] `fq_signal_loop.py` — loop principal + hooks como orquestador.
- [ ] paquete `fq/` — agrupar piezas; dejar el monolito como shim de arranque.

---

## 10 · Garantías y pruebas

- `pytest` como suite principal + self-tests embebidos
  (`python emergent_time.py`, `quantum_timelines.py`, `battle_planner.py`).
- `tests/test_client_surfaces.py` **blinda** las superficies de cliente: caza
  cualquier filtración de versión, modelo, framework o fórmula interna.
- Toda constante de tuning es **override-able por env** (defaults en el módulo).
- Módulos de motor en ASCII-only; sin side effects al importar.

---

*FQ · Documento técnico interno. No distribuir como material de cliente.*
