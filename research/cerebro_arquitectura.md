# Cerebro FQ — arquitectura de analítica dedicada (diseño)
### RasDG + Claude · 2026-06-27 · blueprint para ejecutar por etapas

## 0. Por qué (el detonante)
Auditoría del registro forward (2026-06-27): es **asimétrico**. SOL se graba completo (ledger
rico SQLite, 4 TP, contexto). **BTC y ETH se broadcastean a clientes pero su único registro
es el motor paper de 1 TP** — el ledger rico es *SOL-only* (sin columna de símbolo). El
registro nació MVP single-symbol; el producto ya es 3 símbolos + edges graduados (CVD cableado,
F2-persist con luz verde). Necesitamos **analizar mejor nuestros propios datos, en tiempo real,
sin tocar el bot vivo**. Eso es el cerebro.

## 1. Principios (no negociables)
- **Desacoplado**: el cerebro corre en su PROPIO proceso/ecosistema. El bot de señales sigue
  lean — el análisis jamás puede frenar ni romper una señal.
- **Read-mostly**: el cerebro LEE los outputs durables del bot. No escribe en el path crítico.
  Si el cerebro se cae, el bot ni se entera.
- **Measure-first**: reusa el gate DSR/CPCV/PBO (validation_gate). Nada se "confía" sin pasar
  el gate; el cerebro AUTOMATIZA esa disciplina (incl. vigilar que lo ya cableado siga pagando).
- **Multi-símbolo desde el diseño.**
- **Una fuente de verdad**: "lo que el cliente recibió" = todo broadcast VIP (4 TP, los 3
  símbolos) grabado al momento del envío, independiente de los vetos internos de medición.

## 2. Estado actual (mapa de datos)
| Fuente | Qué es | Símbolos | Gap |
|--------|--------|----------|-----|
| `/data/fq_ledger.db` (SQLite `signals`) | señal VIP rica, **4 TP**, FieldState, conceptos | **SOL-only** (sin col. símbolo) | BTC/ETH NO entran |
| `/data/motor_paper_{SYM}.jsonl` | medición forward, **1 TP**, SHA-chain | SOL/BTC/ETH | solo 1 TP, vetos propios |
| `/data/cvd.parquet` | order-flow vivo (CVD) | multi | ok |
| `cosecha_cubes/*.parquet` | backtest histórico | por símbolo | ok |
| Telegram | interfaz | — | "ya está chica" |

## 3. Arquitectura objetivo
```
  BOT VIVO (Railway, lean)              CEREBRO (ecosistema dedicado, separado)
  ────────────────────────             ────────────────────────────────────────
  evaluate_signal                      ┌─ INGESTA (read-only, scheduled/tail)
    ├─ broadcast VIP ───┐              │    lee: fq_ledger.db, motor_paper_*.jsonl,
    ├─ registro VIP (4TP,símbolo) ───►─┤          cvd.parquet, cosecha_cubes/*
    ├─ motor_paper (1TP) ───────────►─ ┤
    └─ cvd collector ───────────────►─ ┤
                                       ├─ LAGO: store analítico unificado (DuckDB/parquet)
                                       │    normalizado, multi-símbolo, columnar
                                       ├─ CEREBRO: jobs background
                                       │    · mapa de convicción: R por símbolo×TP×regime×
                                       │      killzone×CVD✓×persist✓  (capa 3→motor 1 en tablero)
                                       │    · prometido vs realizado (¿pegan los 4 TP? slippage,
                                       │      qué tier paga)
                                       │    · edge-health: DSR rolling de CVD/F2 → alerta si decae
                                       │    · integridad: broadcast-sin-registro, símbolos, hash-chain
                                       └─ VISTA EN VIVO: Telegram rico + dashboard web read-only
```

## 4. Etapas (cada una entrega valor, reversible, se para donde quieras)

### Etapa 0 — Cimiento: registro forward multi-símbolo (el fix de confianza)
- Columna `symbol` al ledger (`ALTER TABLE signals ADD COLUMN symbol TEXT DEFAULT 'SOL/USDT'`
  — no-destructiva; filas viejas = SOL, que es correcto).
- Helper `_record_vip_signal(report, field, pair, tf_id, tf_label)` llamado en los **3 sitios**
  (SOL 3341 / BTC 3044 / ETH 3157) al momento del broadcast → graba 4 TP + contexto + símbolo.
- Graba "lo que el cliente recibió", independiente del veto del motor paper (hoy una señal
  BTC/ETH puede salir a VIP y no quedar en ningún registro con outcome).
- Bajo riesgo: additivo, en try/except, espeja el path probado de SOL. Con tests.
- **El bot sigue siendo el único que escribe el ledger** (no metemos componentes nuevos al
  path crítico todavía).

### Etapa 1 — El lago: ingesta read-only + store unificado
- Módulo nuevo que corre **separado del bot** (cron/servicio). Lee los durables y los normaliza
  a un store columnar multi-símbolo (**DuckDB sobre parquet** recomendado: analítico, rápido,
  cero servidor). Tablas: `signals_vip` (prometido), `outcomes` (motor paper, realizado),
  `flow` (CVD), `backtest` (cubes).
- Cero escritura hacia el bot. Aislamiento total.

### Etapa 2 — El cerebro: análisis background
- Jobs periódicos sobre el lago:
  - **Mapa de convicción graduada**: R por símbolo × TP × regime × killzone × CVD✓ × persist✓.
  - **Prometido vs realizado**: cumplimiento de los 4 TP, slippage maker, qué tier paga de verdad.
  - **Edge-health**: DSR rolling de CVD y F2-persist en ventana móvil → **alerta si un edge se
    degrada** (el guardián de que lo cableado SIGUE pagando, no solo pagó en el backtest).
  - **Integridad**: broadcasts sin registro, símbolos mal etiquetados, hash-chain del motor paper.
- Salida: resúmenes + alertas a Telegram admin; persistido para el dashboard. Reusa
  `validation_gate` (DSR/CPCV/PBO) — no reinventa el gate.

### Etapa 3 — La vista en vivo: interfaz que crece más allá del MVP
- Dashboard web **read-only** (servicio aparte) sobre el lago: registro forward por símbolo en
  vivo, edge-health, mapa de convicción, prometido vs realizado.
- Comandos Telegram enriquecidos como vista ligera (`/forward`, `/edges`, `/salud`).

## 5. Dónde corre cada cosa (Railway, honesto)
- **Bot**: como hoy (Railway, lean).
- **Cerebro (ingesta + jobs)**: proceso aparte. Opciones — (a) 2º servicio Railway; (b) GitHub
  Actions cron (gratis, como las validaciones, pero no "en vivo"); (c) el **Hetzner CCX33** que
  ya tienes (ideal para el background pesado). Recomendado: jobs ligeros en cron + análisis
  pesado en Hetzner.
- **Dashboard**: servicio web read-only (Railway o estático + API).
- **El lago**: store que el cerebro posee (no el `/data` crítico del bot; lo lee y copia).

## 6. Costo / riesgo
- Etapa 0: horas, riesgo bajo (migración no-destructiva, additivo). Cierra el hueco HOY.
- Etapas 1-2: el grueso del backend; read-only → no toca señales.
- Etapa 3: UI; el "ya no es MVP".
- Todo por etapas y reversible.

## 7. Decisiones abiertas (para RasDG)
1. Store del lago: **DuckDB/parquet** (recomendado) vs SQLite analítico.
2. Dónde corre el cerebro: 2º servicio Railway vs **Hetzner CCX33** (recomendado para lo pesado).
3. Vista: Telegram enriquecido primero (rápido) vs dashboard web directo.

> Arrancamos por **Etapa 0** (cimiento + fix de confianza) en cuanto des el OK; las decisiones
> 1-3 las cerramos al llegar a Etapa 1, no bloquean el cimiento.
