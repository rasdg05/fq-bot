# Estado del proyecto — fq-bot (foto HOY)

> La página que más caduca. Qué está vivo, qué duerme, qué mide, qué espera veredicto, qué
> es plan en papel. Si la fecha de abajo es vieja, confírmala contra `git log` y `research/*.md`
> antes de confiar. Fecha de corte: **2026-06-30** (HEAD: `ead6809`).

---

## Las 3 capas de edge — dónde está cada una

| Capa | Edge | Números (validados, no prometidos) | Estado |
|---|---|---|---|
| **1 — Direccional** | motor maker + veto | +0.10R OOS, Deflated Sharpe ✓ (BTC 1.00 / SOL 0.97) | **VIVO en clientes** |
| **2 — Carry** | short-perp funding, delta-neutral | +12.5% APY net, Sharpe 13.6 bruto, positivo 6 años incl. bear | **Midiendo forward** (`carry_paper`, 0% real) |
| **3 — Order-flow** | CVD firmado (imb≥0.50) | +0.27R (SOL) / +0.34R (BTC), 5 años tick data | **Cableado, midiendo forward** |

Graduación de la capa 3: **≥30 fires confirmados forward + uplift ≥ +0.1R + DSR ✓** → recién ahí
sube conviction client-facing. Hoy mide, no decide.

---

## Por símbolo

- **SOL/USDT** — pilar. Ledger SQLite rico (4 TP, contexto, conceptos). Motor paper a 5m. CVD validado.
  F2-persist **no aplica** (SOL no apila — firma retail/momentum).
- **BTC/USDT** — broadcasting a clientes (commit `8a5c11d`). Motor paper a 5m. CVD validado (DSR ✓).
  **F2-persist con luz verde** (cableado dormido, `FQ_PERSIST_BOOST=BTC`). En el ledger rico **solo
  vía motor_paper** (1 TP), no en el SQLite de 4 TP — gap conocido (ver cerebro).
- **ETH/USDT** — cableado (motor paper, broadcast gated, vetos, regime tag) **pero no certificado**.
  Pendiente: cosechar su cube + correr DSR completo + CVD signed-flow. Si pasa → `FQ_ETH_VIP_BROADCAST=1`.

---

## Qué está vivo / dormido / midiendo / pendiente

**VIVO (en clientes / capital):**
- Motor direccional capa 1 (+0.10R, DSR ✓). Vetos de régimen/sesión (default ON, validados 5 años).
- Gate de validación (`tools/validation_gate.py`). Colectores forward (read-only, no-críticos).
- Ejecución taker + maker en motor paper (mide R neto: fees + slippage).

**CABLEADO DORMIDO (OFF, byte-idéntico cuando off):**
- CVD a conviction/size (`FQ_CVD_VIP_CONVICTION`, `FQ_CVD_BOOST_TIER`).
- F2-persistencia (`FQ_PERSIST_BOOST=BTC`) — luz verde tras re-confirm n_trials=44 (commit `c355d25`).
- **Regime tags KL + POC-distance** (`FQ_REGIME_TAGS`, 2026-06-29): sella `kl_low`/`kl_irrev` (KL fiel,
  ventana 64) + `poc_dist` (developing) en `MOTOR_OPEN_META`; el reporte agrega `by_kl`/`by_poc`. Mide
  forward el edge KL (DSR ✓ cube) y POC-distance (gate ✓ cube, #125). El POC-distance ESTRICTO del día
  previo se mide offline con `gate_poc_distance.py` sobre el ledger (el live es proxy del día en curso).

**MIDIENDO FORWARD (0% capital):**
- Motor paper SOL + BTC (+ ETH). CVD filter/tag (`FQ_CVD_FILTER`, pendiente encender en Railway).
- Carry market-neutral (`carry_paper`, basket CLEAN).

**ESPERANDO VEREDICTO (validador armado, sin run reportado):**
- OI, global_ls, toptrader_ls, taker_ls. Workflows listos para dispatch (ver `CEMENTERIO.md`).

**PLAN EN PAPEL:**
- Cerebro (analítica dedicada multi-símbolo). Etapa 0 lista para arrancar al OK de RasDG.
- OFI verdadero (Tardis L2): solo si el CVD validado lo justifica forward.
- A vivo (FASE 2): `FQ_EXEC_MODE=live` en sub-cuenta chica cuando el fill-rate maker selle.

---

## TradFi híbrido + features nuevos (2026-06-29)

**Híbrido data/venue (DECISIONES §11):** validar TradFi sobre la historia profunda de Dukascopy
(gratis, años) y ejecutar en el perp de MEXC. El motor **DIGIERE** la OHLCV sin order-flow (verify:
45 eventos en XAU). **Cosecha 5y × 5 símbolos CERRÓ** (run 28413719153, 2026-06-30, ~6h en Hetzner;
XAU/NQ/ES/WTI/plata). Transfieren KL/ICT/precio; CVD/F2 **no** (son del venue). **Veredicto POC-distance
TradFi: NO PASA** (n=1992, `far>near` consistente en 5/5 y DSR ✓, pero **PBO 0.76**; en cripto SÍ pasa,
PBO 0.17). **KL-standalone TradFi TAMPOCO transfiere** (2026-06-30: inconsistente, solo NQ pasa y en el
lado OPUESTO a cripto; 4/5 no separan). → **NINGÚN edge de régimen (POC ni KL) transfiere a TradFi: el
bot es cripto-específico.** Útiles al paper (cross-asset), **NO tier** en TradFi. Ver `CEMENTERIO.md`.

**Volume Profile (POC/VA) — `volume_profile.py` (PR #121):** la pata de "volumen" de la confluencia
triple, construida (puro, 7 tests, crypto+TradFi). Medida sobre crypto (`measure_vp_tier.py`, #123):
zona premium/discount **REFUTADA** (inconsistente), rev-aligned **ESPEJISMO** (n=39). **POC-distance
PASA el gate** (#125: DSR + ortogonal a KL + CPCV/PBO) y queda **cableado dormido para forward**
(`FQ_REGIME_TAGS`, junto a KL). Ver `CEMENTERIO.md`.

**TJR/ICT:** el bot YA implementa el framework ICT (sweeps/OB/FVG/PD/killzones/`session_bias`). Es
capa de **convicción+gating**, no el edge validado (ese es CVD/F2/KL). `session_bias.py` ES la tesis
"Asia rango → London fake → NY continuación". MSS/CHoCH se detectan pero **NO gatean** (a propósito).

---

## El roadmap (de `research/plan_evolucion_2026.md`)
- **FASE 1 — MAX EDGE (~30-45 días, sin capital extra):** encender + medir el CVD filter; sellar el
  fill-rate maker (a 30-50 fills); poner a punto ETH (cube + validación).
- **FASE 2 — A VIVO:** ejecución real en sub-cuenta chica (OKX, sizing ≤25x); carry a vivo.
- **FASE 3 — ESCALA:** multi-símbolo (XRP/LTC/DOGE/ADA — el carry ya probó perps sanos); OFI si se
  justifica; distribución.

---

## Auditoría del registro forward (el detonante del cerebro, 2026-06-27)
El registro es **asimétrico**: SOL se graba completo (ledger SQLite rico, 4 TP, contexto); **BTC y ETH
se broadcastean a clientes pero su único registro es el motor paper de 1 TP** — el ledger rico es
SOL-only (sin columna de símbolo). Una señal BTC/ETH puede salir a VIP y no quedar en ningún registro
con outcome. El plan **cerebro** (`research/cerebro_arquitectura.md`, commit `f0cce80`) lo cierra:
- **Etapa 0** (siguiente): `ALTER TABLE signals ADD COLUMN symbol` (no-destructiva, filas viejas = SOL)
  + helper `_record_vip_signal` en los 3 sitios de broadcast (graba 4 TP + símbolo). Additivo, con tests.
- **Etapas 1-3:** lago DuckDB read-only → jobs background (mapa convicción, prometido vs realizado,
  edge-health DSR-rolling, integridad) → dashboard web + Telegram enriquecido.

---

## Trabajo reciente (últimos commits, contexto)
- **TradFi híbrido + Volume Profile (2026-06-29):** cosecha unsharded XAU+NQ + alias de índices
  (PR #122); `measure_vp_tier` (PR #123); módulo Volume Profile (PR #121); fetcher Dukascopy
  (#117/#118/#120); probes Dukascopy/MEXC (#114/#115/#116).
- `f0cce80` blueprint del cerebro (analítica por etapas).
- `7197ede` F2-persist re-confirm n_trials=44 + cableado dormido (PR #85); `c355d25` registra la luz verde.
- `4176dd6` F1 impacto + F2 persistencia, validadores measure-first (PR #84).
- `6fc2f09` global_ls deep-dive 6 años + ortogonalidad (PR #82); `943aaaf` validador generalizado de
  metrics (PR #81); `0995f57` ortogonalidad OI×CVD (PR #80); `2bde2d2` pipeline OI con DSR (PR #79).
- `8c9187e` CVD sube +1 tier (PR #77); `0e89321` badge VIP (PR #75); `fbce1e9` cablea CVD filter (PR #73).

---

## Cosas a no olvidar (trampas de contexto)
- **F2 es BTC-only.** No intentes prenderlo en SOL: no apila (está medido, ver `CEMENTERIO.md`).
- **F1 NO se cabló** aunque su DSR standalone es altísimo — es redundante con el CVD (within-CVD negativo).
- **El +1.47R del CVD estricto (n=17) es un espejismo** que el gate descartó. El R real es +0.27/+0.34.
- **El carry NO es arbitraje sin riesgo** — es prima de régimen; el bruto resta ~2-4pp al neto; en 2026
  la prima se comprime a ~0.
- **BTC/ETH aún no están en el ledger rico de 4 TP** — solo en motor_paper. No asumas que el SQLite
  tiene los 3 símbolos hasta que Etapa 0 del cerebro esté hecha.
- **El +2.4R/54%WR del "rev-aligned" de Volume Profile en ETH es ESPEJISMO (n=39).** El motor es de
  momentum: el bucket contrarian es chico. La zona premium/discount NO da edge consistente cross-símbolo;
  lo único que aguanta es **POC-distance** (lejos>cerca), y aun ése está PENDIENTE del gate.
- **CVD/F2 NO transfieren a TradFi** (order-flow del venue; Dukascopy da solo OHLCV). En oro/NASDAQ
  solo cuentan KL + precio + ICT. No asumas el "motor premium" completo fuera de cripto.
- **"0 disparos" puede ser DEPLOY, no el motor — revisa Railway ANTES de asumir "selectivo".** El
  2026-06-30 el bot no disparó en todo el día y yo lo expliqué como comportamiento selectivo normal;
  la captura de Railway mostró la verdad: un **deploy fallido** (`Heartbeat timeout / Infra Error`).
  Raíz: los `.pdf/.html/.png` de `MEMORY/`+`presentaciones/` NO estaban en la blacklist de
  `watchPatterns` (solo `*.md`), así que **cada commit de docs re-desplegaba el worker** → reseteaba
  contadores ("Total: 0") y lo exponía a blips transitorios. Fix: blacklist `MEMORY/`,
  `presentaciones/`, `*.pdf/*.html/*.png` (**PR #138**, `funding_paper.py` sigue runtime al final).
  **Lección:** ante 0 cadencia, primero confirma uptime/deploy en Railway; sólo después sospecha del edge.
- **No apagues un símbolo por UN stop-out — el "stop dentro del ruido" es de COLA y UNIVERSAL.** El
  2026-06-30 una señal de BCH tocó SL al instante (stop 0.249% < vela 5m mediana 0.265%). Medido cross-símbolo
  (`tools/sl_noise_screen.py`): el stop MEDIANO está bien en TODOS (ratio stop/vela 1.7–2.8; BCH 2.04, a media
  tabla), pero el **p10 (~0.24–0.31%) roza el ruido en todos** → en baja vol cualquier símbolo emite un stop de
  cola dentro del ruido (esa señal cayó bajo el p10 de BCH). BCH **tiene edge** (positivo en todas las celdas);
  no se apaga. **MEDIDO (mismo día, pooled n=13429): el stop apretado ES el edge, NO el bug.** Por cuartil de
  stop%: Q1-apretado WR 23% pero **expR +0.316R** vs Q4-ancho WR 28% y **expR +0.147R** (monótono). El stop
  comprimido baja el WR (más ruido) pero su R-múltiplo lo paga con creces. → **un piso/ensanche de stop BAJARÍA
  la expectativa — NO hacerlo.** (Mi intuición de "floor the stop" la refutó el dato.) La palanca para la
  *experiencia* (no la expectativa) es **gestionar a TP1** (WR ~29%→~50%), no tocar el stop. Caveat: es
  correlacional (el stop% es endógeno al setup); el causal per-trade confirmaría, pero la dirección es clara.

---

_Fuente de verdad: `git log`, `research/plan_evolucion_2026.md`, `research/cerebro_arquitectura.md`,
`research/fisica_moderna_2026_resultados.md`, `research/carry_regime.md`, `motor_paper.py`,
`fq_bot_v3_2.py`, `railway.toml`. Actualizado 2026-06-30._
