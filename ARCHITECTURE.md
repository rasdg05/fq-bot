# FQ — Arquitectura y hoja de ruta de la reescritura

> Estado: **migración en curso**. El sistema funciona en producción (Railway).
> La reescritura se hace por **etapas verificadas y reversibles**, nunca de un
> solo golpe: cada paso preserva comportamiento y deja la suite de tests verde.

## Por qué por etapas y no de golpe

`fq_bot_v3_2.py` tiene ~4,900 líneas y el sistema completo ~18,000. Es un bot de
**trading + pagos en vivo** con suscriptores reales. Un "big-bang rewrite"
arriesga dinero y reputación. La estrategia es **strangler fig**: extraer piezas
cohesivas del monolito hacia módulos puros/testeables, dejando el monolito
delegando en ellas, hasta que el monolito quede como un orquestador delgado.

Regla de oro de cada etapa:
1. Extraer una pieza con frontera clara.
2. El monolito la importa (y reexporta símbolos si hace falta para no romper
   referencias/tests existentes).
3. `pytest` verde antes de commitear.

## Topología de procesos (hoy)

`launcher.py` arranca 4 procesos hijos en el mismo contenedor (Railway no
comparte volúmenes entre servicios):

- **vip** (`entry_vip.py` → `fq_bot_v3_2.py`): motor de señales, gate QTE,
  radar/alertas tácticas, comandos VIP, ledger (escritura).
- **public** (`entry_public.py`): bot de marketing. Lee el ledger VIP en
  **read-only** y anuncia cierres, teasers y celebraciones de TP3.
- **maintenance** (`ops.maintenance`): backups, heartbeat.
- **web** (`entry_web.py` → `webapp/`): Mini App de Telegram (panel admin + app
  cliente). Lee ledger y `vip.db` en **read-only**, sirve `$PORT`. Diseñado para
  **nunca salir** (idle ante cualquier fallo) para no gatillar el restart del
  container. Off en caliente con `FQ_WEBAPP_ENABLED=0`. Ver `webapp/README.md`.

Comunicación entre procesos: **solo** vía los archivos SQLite (RO desde public y
web). Sin acoplamiento de código entre procesos.

## Mapa de módulos

### Núcleo de decisión (puro, testeable)
- `fq_radar.py` — **(extraído v5.3)** lógica pura del radar: cooldowns por TF,
  gate de convicción, anti-flip. Sin I/O ni estado.
- `fq_market_data.py` — **(extraído v5.3)** acceso a velas (`fetch_ohlcv`) +
  indicadores (`add_indicators`). El exchange entra por parámetro → mockeable
  sin red.
- `battle_planner.py` — convierte contexto+paths en un veredicto operable.
- `signal_scorer.py`, `signal_engine_v2.py`, `fusion_engine.py` — scoring.
- `quantum_timelines.py` — motor de simulación (QTE).
- `ict_smc.py`, `market_context.py`, `regime_detector.py`, `volume_quality.py`,
  `killzones_pd.py`, `emergent_time.py`, `entropy_cognition.py` — features y
  estado de mercado / ledger.
- `session_bias.py` — **(v5.4)** modulador suave London/NY/Asia condicionado al
  sesgo diario (HTF). London es fake cuando barre contra el sesgo, real cuando
  corre con el; NY resuelve hacia el sesgo; Asia es rango. Puro, acotado, sin
  I/O. Lo consume `fusion_engine` como multiplicador (no veta).

### Presentación (cara al cliente)
- `vip_format.py`, `public_format.py`, `field_reports.py`, `branding.py`,
  `legal.py` — strings. Blindados por `tests/test_client_surfaces.py`.

### Bot público
- `public_outcome_announcer.py` (lee ledger RO + DB pública),
  `public_scheduler.py` (cron interno), `public_handlers.py`,
  `public_content_generator.py`.

### Pagos / suscripciones
- `vip_system.py`, `payments.py`.

### El monolito (a adelgazar)
- `fq_bot_v3_2.py` — todavía concentra: loop principal, fetch OHLCV +
  indicadores, `radar_check`, evaluación de setups, broadcast, routing de
  comandos, hooks de evolución.

## Hoja de ruta (extracciones siguientes, en orden de menor riesgo)

1. **[hecho] `fq_radar.py`** — decisión pura del radar.
2. **[hecho] `fq_market_data.py`** — `fetch_ohlcv` + `add_indicators` (I/O
   exchange + pandas-ta) detrás de una interfaz pequeña; mockeable en tests.
3. **`fq_broadcast.py`** — `broadcast_to_subscribers` + `telegram_send` +
   `telegram_get_updates`, desacoplado de los globals del monolito (recibe
   config por parámetro / objeto).
4. **`fq_commands/`** — router de comandos de Telegram (un handler por comando),
   hoy un gran `if/elif` dentro del monolito.
5. **`fq_signal_loop.py`** — el loop principal y los hooks (evolución,
   progreso, reconcile) como orquestador que llama a los módulos anteriores.
6. **paquete `fq/`** — una vez estables las piezas, agruparlas en un paquete y
   dejar `fq_bot_v3_2.py` como shim de arranque.

## Convenciones

- Módulos planos en la raíz (estilo actual del repo) hasta la etapa 6.
- Toda constante de tuning es **override-able por env** (defaults en el módulo).
- Nada de jerga interna del motor en superficies de cliente (lo caza
  `test_client_surfaces.py`).
- Cada extracción reexporta desde el monolito los símbolos que tests o código
  legacy referencien, para mantener compatibilidad durante la transición.
