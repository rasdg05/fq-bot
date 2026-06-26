# Plan de evolución FQ — de edge validado a producto desplegado (jun 2026)

> Estado: **tres capas de edge VALIDADAS** (DSR ✓). Esto deja de ser experimento. El plan
> es ejecutar y escalar lo probado — con el gate de validación cuidando cada paso.

## Dónde estamos (validado, no prometido)
- **Motor 1 direccional:** +0.10R OOS, Deflated Sharpe ✓ (BTC 1.00, SOL 0.97).
- **Motor 2 carry market-neutral:** +12.5% APY, Sharpe 13.6, positivo 6 años incl. bear.
- **Capa 3 order-flow (CVD firmado):** DSR ✓ en SOL (0.98) y BTC (1.00) a umbral 0.50, sobre
  **5 años de tick data real** — ~87 señales/año, R confirmado SOL +0.27 / BTC +0.34 (bruto).
  Y el +1.47R estricto (n=17) descartado por el gate (espejismo).
- **Infra:** colectores forward (OI agregado, CVD, carry) + máquina de validación (DSR/CPCV/PBO)
  + pipeline de data histórica gratis (Binance) + ejecución paper→live cableada (`FQ_EXEC_MODE`).

---

## FASE 1 — MAX EDGE (próximos ~30-45 días, sin capital extra)

### 1.1 Cablear el filtro CVD validado (la prioridad) — ✅ CABLEADO (midiendo)
El CVD-confirmado (imb≥0.50) pasó el DSR → es legítimo. **Disciplina: medición-primero.**
1. **Integrado a `motor_paper`** (`_cvd_confirm` → `tools/fetch_cvd.cvd_confirmation`): cada
   fire se taguea con order-flow confirmado/no, **CAUSAL** (ventana de barras con `ts<entrada`),
   tag PARALELO al de regime. Hoy mide; mañana sube conviction/sizing (no veto: la cadencia
   no se corta). ✅
2. **Fuente en vivo:** lee el parquet del colector `FQ_CVD_COLLECT` (`cvd.parquet`) en el
   instante de la señal. `FQ_CVD_IMB_MIN` (default 0.50 = el umbral validado). ✅
3. **Gate `FQ_CVD_FILTER` (default OFF):** OFF → ledger byte-idéntico al histórico (sin claves
   `cvd_*`). ON → `MOTOR_OPEN_META` sella `cvd_confirmed`; `ledger_report` agrega `by_cvd`
   (confirmado vs no) y `/paper` imprime el uplift forward. ✅
4. **Pendiente — encender y medir:** poner `FQ_CVD_COLLECT=1` + `FQ_CVD_FILTER=1` en Railway
   (no-crítico, no toca al VIP). **Criterio de graduación:** ≥30 fires confirmados forward,
   uplift ≥ el del cube (+0.1R), DSR ✓ → recién ahí sube conviction client-facing.

### 1.2 Sellar el fill-rate maker
El +0.10R es un techo gated por adverse selection. `motor_paper` lo mide; **a 30-50 fills**
se decide si el edge es real al 100%. No es research nuevo — es leer el medidor.

### 1.3 ETH — puesta a punto (3er símbolo)
ETH ya está cableado (motor paper, broadcast, vetos, regime tag) pero le falta su **cube**
(validación a la par de SOL/BTC). Pasos:
1. **Cosechar el cube de ETH** (`eth_cosecha` → Hetzner, job pesado de cómputo, ~1 corrida).
2. **Correr sobre ETH todo el stack de validación** (ya auto-incluye ETH cuando aparece su cube):
   - `cube_report` (celdas/veto/conviction) + el **Deflated Sharpe** del +0.10R en ETH.
   - El **workflow CVD signed-flow** ya loopea símbolos → agregar `ETH` al sweep (¿el order-flow
     valida en ETH como en SOL/BTC?).
3. **Si ETH pasa el DSR** → ETH a clientes (`FQ_ETH_VIP_BROADCAST=1`), 3er símbolo full.
   Si no → ETH queda en measure-only hasta afinar.

---

## FASE 2 — A VIVO (paper → real, cuando el fill-rate selle)
- **Ejecución real en sub-cuenta chica:** `FQ_EXEC_MODE=live` sobre OKX, sizing ≤25x (la
  disciplina del historial MEXC), arrancando con capital mínimo.
- **Carry a vivo:** delta-neutral real (short-perp + hedge) sobre el basket CLEAN, el 2do motor
  generando yield real.
- **Monitoreo:** ledgers durables + alertas; el track LIVE es lo que re-ratea la valuación.

---

## FASE 3 — ESCALA (con capital / colaboradores)
- **Multi-símbolo:** cosechar cubes + validar DSR en más nombres líquidos (XRP/LTC/DOGE/ADA —
  el carry ya probó que son perps sanos). Cada uno que pase el DSR = más cadencia al mismo edge.
- **OFI verdadero (Tardis L2):** SÓLO si el CVD validado lo justifica — subir de order-flow de
  trades (CVD) a imbalance de libro (OFI), el signal más fuerte del research. Se paga sólo lo
  que el dato gratis ya demostró.
- **Distribución:** escalar la base de suscriptores (el producto ya tiene 3 capas de edge).

---

## El principio que no se negocia
**Nada se despliega a clientes ni a capital real sin pasar el gate** (DSR multi-régimen +
forward). El CVD lo pasó en backtest de 5 años; ahora la integración EN VIVO se mide forward
antes de client-facing. Esa disciplina es el moat — y lo que convierte "leads lindos" en
edge desplegable.

_Plan vivo. Se actualiza con cada medición forward. Jun 2026._
