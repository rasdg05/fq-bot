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

## v2 — momentum + gate de régimen KL-alto (¿concentra?)

Grid pre-registrado (4 configs, maker-net ~$4 rt), + estabilidad por año:

| config | n | avgR_net | SR | DSR |
|---|---|---|---|---|
| base (=v1) | 2345 | +0.0207 | 0.013 | 0.000 |
| **KL-alto (trending)** | 586 | **+0.0306** | 0.019 | 0.000 |
| [control KL-bajo] | 1759 | +0.0173 | 0.011 | 0.000 |
| vol-scaling (move≥1ATR) | 1617 | +0.0062 | 0.004 | 0.000 |
| KL-alto + vol-scaling | 398 | +0.0350 | 0.022 | 0.000 |

**La tesis se confirma: el gate KL-alto CONCENTRA el momentum** (+0.031 trending vs +0.017
KL-bajo — el momentum vive en régimen tendencial, opuesto exacto de la reversión). Vol-scaling
solo NO ayuda; combinado con KL-alto da el mejor per-trade (+0.035) pero n cae a 398.

**PERO: ni concentrado pasa el gate (DSR 0.000, SR 0.022), y es INESTABLE por año:**
`2017 -0.64 · 2019 -0.20 · 2022 +0.47 · 2024 +0.24 · 2025 -0.19` → 6/10 años positivos, dominado
por pocos años buenos. Un edge régimen-del-año-dependiente, no robusto para dinero real.

## Veredicto tras v0/v1/v2: el edge intradía del oro es REAL pero MARGINAL

Medido en dos motores (reversión y momentum): el edge intradía del oro existe, es maker-viable,
se concentra en trending — pero es **débil per-trade e inestable año-a-año**, no cruza el gate
honesto. Coincide con el prior de la deep-research: "el edge intradía de oro existe pero es chico
y frágil". Lo hemos MEDIDO ahora, no asumido.

**Qué NO haría:** seguir apilando knobs sobre el oro (timing, exit, features) persiguiendo DSR
0.95 — a partir de aquí cada refinamiento es casi coin-flip y el multiple-testing se acumula. El
oro nos dio su medida: motor de continuación con pulso real pero marginal.

**El hilo de mayor EV ahora es cross-market:** el MISMO motor de momentum en **NASDAQ (NQ/MNQ)**,
donde la research dice que el TSM intradía es MÁS fuerte (índices más tendenciales que el oro;
S&P500 R² > BTC). Es el sueño del dueño (oro Y nasdaq) y el test limpio de si el método de
continuación tiene juego real donde debería brillar. Preflight de data primero (measure-first).
El motor de oro queda como fundación documentada y reciclable; NASDAQ es el siguiente tejido.

## Reproducibilidad
`/tmp/cme/gold_momentum_v0.py` (breakout), `/tmp/cme/gold_momentum_v1.py` (TSM sesión + costos),
`/tmp/cme/gold_momentum_v2.py` (+ gate KL-alto, por año). Resultados `/tmp/cme/gold_momentum_v2.parquet`.
Data: `data/cme/GC-USDT_5m.parquet` (GC.v.0 full-density). Resultados en
`/tmp/cme/gold_momentum_v0.parquet`. Gate: DSR/CPCV con n_trials declarado por versión.
