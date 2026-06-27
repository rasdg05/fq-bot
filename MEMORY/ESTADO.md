# Estado del proyecto — fq-bot (foto HOY)

> La página que más caduca. Qué está vivo, qué duerme, qué mide, qué espera veredicto, qué
> es plan en papel. Si la fecha de abajo es vieja, confírmala contra `git log` y `research/*.md`
> antes de confiar. Fecha de corte: **2026-06-27** (HEAD: `f0cce80`).

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

---

_Fuente de verdad: `git log`, `research/plan_evolucion_2026.md`, `research/cerebro_arquitectura.md`,
`research/fisica_moderna_2026_resultados.md`, `research/carry_regime.md`, `motor_paper.py`,
`fq_bot_v3_2.py`. Actualizado 2026-06-27._
