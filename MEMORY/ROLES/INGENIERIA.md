# ROL: INGENIERÍA / BACKEND — vista sobre la memoria

> Antes de tocar código, abrir un PR o proponer una idea: **pasa por aquí**. El contexto que te
> falta ya está escrito — no lo re-descubras (ni repitas un error ya enterrado).

## Antes de construir, en este orden
1. `../CONSTITUCION.md` — las invariantes que **NO se rompen** (el gate no se degrada; dormido por
   defecto; colectores no-críticos; el ledger es inmutable; el veto juzga la vela, no `now()`).
2. `../CEMENTERIO.md` — **¿tu idea ya se probó?** Probablemente sí. Mira el veredicto antes de codear.
3. `../DECISIONES.md` — el *por qué* de la arquitectura (muchas decisiones son contraintuitivas a propósito).
4. `../ESTADO.md` — qué está vivo / dormido / midiendo / pendiente HOY.

## Las reglas de build (no-negociables)
- **Measure-first:** nada a vivo sin pasar `tools/validation_gate.py` (DSR>0.95 + ortogonalidad).
- **Dormido por defecto:** feature nueva nace OFF tras un `FQ_*`, señal byte-idéntica cuando off,
  reversible. El path crítico jamás depende de un colector ni de un experimento.
- **Ledger crash-safe e inmutable:** `append` con fsync + `os.replace` atómico; hash-chain SHA-256;
  backup off-host (incluye `fq_motor.db`). Es la fuente de verdad del track record.
- **Flujo:** rama feature → PR → merge. **Tests con cada cambio.** Commits honestos (qué y por qué).

## Mapa de arquitectura (dónde vive qué)
- **Bot vivo** (Railway) + `/data`: ledgers `fq_motor.db` (SQLite multi-símbolo del motor, tras
  `FQ_LEDGER_SQLITE=1`) y `fq_ledger.db` (VIP). Colectores read-only (CVD, OI, carry).
- **Cerebro** (diseño): `research/cerebro_arquitectura.md` — 2 tracks, read-only, measure-first.
- **Runner pesado:** Hetzner CCX33 (cosecha / validación densa). `ops/SELF_HOSTED_RUNNER.md`.
- **Validadores + workflows:** `tools/validate_*.py` + `.github/workflows/*` (1-tap, gratis).
- **La ecuación del motor:** `../ingenieria/` — P_master de la vela al disparo (PDF + texto). Léela antes de tocar `fusion_engine`.

> Recuerda: el **registro forward que valida edges es el MISMO** que le da a Marketing sus números
> reales. Una sola verdad para todos. Si tocas el ledger o el gate, lees `CONSTITUCION.md` primero.
