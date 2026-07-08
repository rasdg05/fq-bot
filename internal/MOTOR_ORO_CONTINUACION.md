# Motor de ORO — continuación/momentum: FUNDACIÓN (el primer pulso)

> RasDG 2026-07-08, 1AM ("el camino así es"): tras cerrar que el motor de REVERSIÓN cripto no
> transfiere al oro, arrancamos el motor de oro PROPIO. Tesis (de ORO_SESION_KILLZONES +
> RESEARCH_MOMENTUM): el oro intradía es de CONTINUACIÓN en la sesión NY, no de reversión.
> **Hallazgo: la tesis tiene PULSO — momentum real, maker-viable, débil.** Este doc es la
> fundación pre-registrada + resultados; el motor es reusable a cripto/NASDAQ (por eso se
> desarrolla aunque el EV del oro solo sea medio).

## El camino recorrido esta noche (measure-first, todo pre-registrado)

**v0 — breakout crudo en KL-alto + killzone.** ❌ Sin edge.
- Breakout de N barras dentro de killzone, gateado por KL-irreversibilidad ALTA (trending, la
  INVERSIÓN del gate de reversión — mismo detector, lado opuesto). n=5,853, avgR −0.012, SR
  −0.013, DSR 0.000, 53 fires/mes. El breakout se sobre-dispara y se fadea. Los TP lejanos dieron
  +213R (susurro de que dejar correr la tendencia tiene algo), pero ahogado en ruido.

**v1 — momentum intradía de SESIÓN (intraday TSM).** ✅ PULSO.
- Del claim VERIFICADO 3-0: "el retorno de apertura predice el resto de la sesión" (BTC t=4.38,
  S&P500). Adaptado: opening move NY (08:00→09:30 ET) define la dirección; entrada 09:30 ET;
  salida al settlement (13:30 ET); barrera 3R/1.5×ATR.
- **Validación del claim (regresión pura, sin trading): corr(rest, first)=+0.040, slope +0.059 →
  MOMENTUM CONFIRMADO EN ORO.** El movimiento de apertura sí predice el resto de la sesión.
- **Tradeable: n=2,345, avgR +0.035, DSR 0.751** (vs 0.000 de reversión y breakout). Primer
  config del oro que respira en el Sharpe deflactado.

**Prueba de costos (decisiva):**
| ejecución | costo/trade | avgR neto | SR | totR 9yr |
|---|---|---|---|---|
| bruto | — | +0.0347 | 0.022 | — |
| **MAKER** (~$4 rt) | 0.014R | **+0.021** | 0.013 | **+48R** |
| TAKER (~$24 rt) | 0.084R | −0.050 | −0.031 | −116R |

**Sobrevive maker, muere taker** — exactamente la sentencia de la literatura de momentum intradía
(edge real, breakeven 3-10bps, solo con maker/sin cruzar spread). Dos caminos convergen otra vez.

## Estado honesto

- **El oro TIENE un edge de continuación real y maker-viable** — pero débil (SR 0.013 neto, +48R
  en 9 años ≈ 5R/año). Es una FUNDACIÓN, no un producto. No pasa el gate todavía (DSR bruto 0.751,
  neto más bajo).
- El pivote reversión→continuación fue el correcto, validado por datos: reversión DSR 0.000,
  continuación DSR 0.751 bruto. La dirección del oro es momentum, no mean-reversion.

## Roadmap v2 (dónde concentrar el edge — pre-registrar antes de correr)

Ejes con motivación de la research (NO tunear hasta pasar — contar trials):
1. **Vol/actividad**: la research dice momentum más fuerte en días de alto volumen/vol. El filtro
   |move|>k·ATR no ayudó en v1 (raro) — probar filtro por vol REALIZADA de sesión o por volumen.
2. **Timing fino**: el paper halló que "fadear la penúltima media hora" fue MEJOR que el momentum
   puro (reversión corta dentro del momentum). Estructura horaria intradía a mapear.
3. **Señal**: opening-range BREAKOUT (romper el rango de apertura) vs dirección-de-open cruda.
4. **Exit**: trailing stop / salida por debilitamiento de tendencia vs barrera fija 3R.
5. **Régimen**: cruzar con KL-alto (v0) — v1 no lo usó; el momentum gateado por trending podría
   concentrar.
6. **Features gold-específicas** (de la deep-research): Amihud illiquidity, variance-ratio W-shape,
   ventanas de evento (08:30/14:00 ET), PM fix 10:00 ET.

## Reciclaje (la razón estratégica de desarrollarlo — RasDG)

Un motor de continuación validado NO es solo para oro:
- **Cripto**: el motor actual es de reversión (KL-bajo). Un motor de continuación (KL-alto) sería
  el COMPLEMENTO que hoy falta — cubre el régimen donde la reversión se calla (las sequías VIP).
  π_blade falló porque reciclaba señales de reversión; un motor de continuación PROPIO es lo que
  π_blade no era.
- **NASDAQ (MNQ)**: índices son más tendenciales que el oro — el momentum intradía debería ser
  MÁS fuerte ahí (la research: TSM documentado en S&P500 con R² mayor que en BTC).
- La infra (killzones ET, KL-detector, triple-barrier, gate DSR/CPCV/PBO) ya está — el motor de
  continuación se porta entre mercados cambiando data y killzones.

## Reproducibilidad
`/tmp/cme/gold_momentum_v0.py` (breakout), `/tmp/cme/gold_momentum_v1.py` (TSM sesión + costos).
Data: `data/cme/GC-USDT_5m.parquet` (GC.v.0 full-density). Resultados en
`/tmp/cme/gold_momentum_v0.parquet`. Gate: DSR/CPCV con n_trials declarado por versión.
