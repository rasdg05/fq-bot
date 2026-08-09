# BRIEF V5 — ¿El techo son $22k o son millones? (2026-08-09)

> **Encargo para una sesión NUEVA, desde arranque en frío.** `CLAUDE.md` y
> `MEMORY/ESTADO.md` cargan el estado, los números y las 15 invariantes: **no los
> repitas ni los re-derives**.
>
> Rama: `claude/v1-v4-evaluation-frontier-ibkw12`.
> **Nada a `main` sin decírselo a RasDG** — despliega a producción con
> suscriptores de pago.
>
> **Esto es una PRE-REGISTRACIÓN.** Hipótesis, rejilla, `n_trials` y criterio
> están fijados **antes de correr**. Si al ejecutar hace falta cambiar alguno, se
> cambia **por escrito y contando de nuevo**, no en silencio.

---

## 0. Por qué esto es lo único que importa ahora

El 2026-08-09 se hizo por primera vez la multiplicación que faltaba: **R es
adimensional; la cuenta vive en dólares.** Con la capacidad neta medida por V3
($22k), 45 señales/mes y la `f` viva (0.25%):

| E[R] | qué es | $/año | APY sobre $22k |
|---|---|---|---|
| +0.0099 | **medido hoy** | **$294** | 1.3% |
| +0.0620 | mejor alcanzable (4.32bps + terciles) | $1.841 | 8.4% |
| +0.0700 | **en la frontera — si TODO saliera** | **$2.079** | **9.5%** |

**La tasa no es el problema (9.5% neto es respetable). El problema es que la base
está tapiada en $22k.** Ningún avance de edge cambia eso, porque el premio es
`edge × capacidad × frecuencia` y la capacidad manda ~20x más que el edge.

### El hallazgo que abre esta sesión

V3 midió la capacidad **sobre tp4/h288, con stop 0.51%**. Pero despejando el
capital de la propia ley que `capacity_analysis.py` implementa
(`impact_R = Y·σ·√q / stop_frac`, con `notional = capital·f/stop_frac`):

```
capacidad  ∝  stop_frac³
```

Con la liquidez **MEDIDA** de ETH (V3: `bar_notional` 1.428e7, `σ_bar` 20.3bps) y
un presupuesto de impacto de 0.02R:

| geometría | stop | capital | vs hoy |
|---|---|---|---|
| tp4/h288 — la que midió V3 | 0.51% | $73.547 | 1x |
| kSL=2 | 1.02% | $588.378 | **8x** |
| **kSL=5 — la celda ANCHA** | **2.55%** | **$9.193.411** | **125x** |
| kSL=8 | 4.08% | $37.656.210 | 512x |

**Doblar el stop da 8x de capacidad. El exponente es 3, no 1.**

> **El techo de $22k no es una propiedad del sistema: es una propiedad de la
> geometría más apretada, que es justo la que el bot opera por accidente
> histórico.**

Y la celda ancha es la que pasó **seis controles independientes** (óptimo
interior, control de inversión, CPCV 13/15 y 15/15 contra la actual, PBO 0.198,
holdout por símbolo 8/8, fill resuelto a favor con entrada taker). La mataron dos
cosas, y **una ya está arreglada**: la concurrencia (el trailing k=0.50 bajó el
DD de 30.6% a 11.1% a la `f` viva, con `n` constante). Queda el DSR.

**Todo lo de arriba es una DERIVACIÓN, no una medición.** Eso es lo que hay que
cerrar aquí.

---

## 1. Las hipótesis PRE-REGISTRADAS

Sobre la celda **pre-fijada** por el cementerio (`kSL=5.0, tpR=6.0, h=1152`),
universo VIP, con la **salida dinámica `A trail k=0.50`** puesta (medida el
2026-08-08, `n` idéntica al control).

- **H1 — capacidad.** La capacidad neta de la celda ancha con trailing es **≥10x**
  la de tp4/h288 medida por V3 ($22k). Umbral pre-fijado: **≥$220k**. Menos de
  eso y la derivación del exponente 3 no se sostiene en la práctica.
- **H2 — el edge sobrevive al tamaño.** A **$250k** de capital, el E[R] neto de la
  celda ancha (con impacto aplicado) **sigue siendo positivo**.
- **H3 — la que decide.** Existe un capital ≥$220k donde, **a la vez**: E[R] neto
  con impacto > 0, `screen_cell` pasa (DD < 35% sin cap, a la `f` viva), y el
  **DSR > 0.95** contado honestamente.

**H1 y H2 tiran en sentidos opuestos.** Más capital = más capacidad usada = más
impacto = menos edge. El experimento es si existe una ventana donde las dos se
cumplen. **Puede que no exista, y ése es un desenlace legítimo.**

### La rejilla, declarada entera (esto ES el `n_trials`)

**Eje único: el capital.** No se cruza con nada.

| eje | valores | n |
|---|---|---|
| capital | $22k, $100k, $250k, $500k, $1M, $2M | 6 |

**`n_trials = 6`.** La geometría **no se busca** (viene del cementerio, con
fecha). La salida **no se busca** (viene de la medición del 2026-08-08). El
símbolo se reporta por separado, no se elige.

**Divulgación paranoica obligatoria:** imprimir **también** el DSR con
`n_trials = 84 × 6 × 6 = 3.024` (rejilla de geometría × reglas de salida ×
capitales). No es el criterio; es la cota. Que se vea.

**Prohibido:** cruzar el capital con la geometría, con la regla de salida o con
el tercil de convicción. Si el marginal lo sugiere, es **otra pre-registración
desde cero**.

---

## 2. Criterio de decisión, fijado antes de mirar

- **Coste primario: 5.00 bps taker + 1 bp slip** — el coste con el que están
  medidas TODAS las cifras del repo. Pasar aquí es pasar sin ambigüedad.
- **Coste secundario, al lado: 4.32 bps** (HL + referral, el techo alcanzable
  medido). Pasar solo ahí es **pase CONDICIONADO** al cambio de venue, y se
  etiqueta así. No cuenta como pase.
- **`Y` se publica como CURVA (0.5–1.5), no como punto.** Es lo único declarado
  que queda en la ley de impacto — mismo trato que `queue_frac` en V2.
- **Liquidez MEDIDA de las velas locales** (`require_measured`). Sin velas el
  informe se para; no contesta con el default de catálogo (que estaba 8x fuera).
- Todo **neto**, toda fila con **su propia vara** (`require_own_bar`), **cartera
  antes que candidata** (`screen_cell`, sin cap), **desglose por año** (E9),
  y **`g`/`f*`/P(acabar arriba)** junto al E[R] (V4).
- **Y la cifra en DÓLARES al lado de cada R** (ver §4).

---

## 3. Las puertas anti-espejismo de ESTE experimento

Además de las 11 generales de `BRIEF_FRONTERA_2026-08.md`:

1. **El stop ancho NO regala edge por escala.** Reescalar stop y objetivo a la
   vez es **invariante en el t-estadístico** (R es un cociente: bruto y coste
   escalan los dos por `1/s`). Lo único que puede mover el neto es que la
   **resolución por barreras cambie de FORMA**. Si el neto sube proporcional al
   stop, es aritmética, no hallazgo. Reportar **brecha**, no solo neto.
2. **La capacidad NO es el edge.** Capacidad grande sin edge demostrado solo
   significa **perder más rápido y en mayor cantidad**. H1 sin H2 no es
   buena noticia.
3. **El confundido del subconjunto sigue ABIERTO.** El control de la celda ancha
   ya cruza sobre 3 símbolos (VIP) y NO cruzaba sobre los 13 del pool. La
   concurrencia escala con el número de símbolos, así que restringir el universo
   baja el DD **por aritmética**. Choca con `CEMENTERIO.md` ("el liderazgo rota;
   los rezagados ganan OOS"). **Se cierra bajando las velas de los 10 símbolos
   que faltan** (`--interval 5m`, ~40 s cada uno) y re-corriendo el control sobre
   el pool entero. **Hacerlo ANTES de creerse cualquier resultado de aquí.**
4. **El DSR ya se cayó una vez.** La salida dinámica dio 0.986 con `n_trials=6` y
   **0.366** con la cota paranoica. No repetir el error de leer solo la primera.
5. **Impacto sobre serie bruta = TECHO.** `require_measured` lo etiqueta.
   El fill de la ENTRADA sigue sin modelar: todo es cota superior.
6. **Máximo en la esquina.** Si el mejor capital es el último de la rejilla, el
   rango se acabó y no hay óptimo demostrado.
7. **Una métrica demasiado limpia es un bug.** Si la capacidad sale exactamente
   125x, buscar el error antes de celebrar: la derivación asume `σ_ventana`
   invariante y eso hay que comprobarlo, no suponerlo.

---

## 4. Entrega esperada

Regla de la casa: *un hallazgo sin invariante que lo haga cumplir es una nota.*

- **Extender `tools/capacity_analysis.py`** (ya tiene `--stop-frac` y la liquidez
  medida) — **no crear un tool nuevo**. Necesita poder tomar la serie de R de la
  celda ancha **con la salida dinámica aplicada** (`geometry_sweep.relabel_exits`
  + `net_r_vectorized` ya la producen).
- **INVARIANTE NUEVA, y es la más importante de todo el repo:
  ninguna afirmación de edge sale sin su cifra en DÓLARES a la capacidad
  medida.** Mismo choke point que `format_expectancy` (V4) y misma familia de
  error: R esconde el tamaño del premio. Que sea **imposible** publicar un
  `+0.02R` sin ver al lado que son ~$50/mes. Nombre sugerido:
  `RWithoutMoneyError`. Test que falle si alguien imprime un E[R] sin
  `$/mes @ capacidad`.
- **Tests:** que la capacidad escale con `stop_frac³` bajo la ley (fija la
  derivación de este brief), y que la cifra en dólares sea consistente con
  `capacidad × f × E[R] × frecuencia`.
- **Si sale que no:** a `MEMORY/CEMENTERIO.md` con su n, su rejilla y su
  `n_trials`, y actualizar `MEMORY/ESTADO.md`.
- Suite completa verde (~60 s) antes de cada commit.

---

## 5. Los desenlaces legítimos

1. **H1+H2+H3** → el techo real son cientos de miles, no $22k. La conversación
   pasa de $2k/año a decenas de miles y **el proyecto tiene una tesis de
   negocio**. Entonces: CPCV/PBO, forward, `n≥100`, y **nada a vivo** hasta que
   pase el gate entero (`CONSTITUCION.md`).
2. **H1 sí, H2 no** (hay capacidad pero el edge muere al tamaño) → la capacidad
   nunca fue el cuello de botella. Cierra la línea y ahorra meses.
3. **Ni H1 ni H2** → el exponente 3 no sobrevive a la práctica, el techo es real,
   y **el trading no puede ser el negocio a ninguna escala alcanzable**. Es el
   desenlace más valioso de los tres para decidir qué hacer con el proyecto.
4. **Malo:** que salga "casi" y se maquille bajando la vara, capeando la
   concurrencia, contando el pase condicionado a 4.32 bps, o ignorando el
   confundido del subconjunto (puerta 3).

---

## 6. Contexto de negocio que NO hay que re-derivar

- **Lo que cinco meses compraron no es el upside, es el downside evitado.** En
  julio el repo publicaba `WR 60% · E[R] +1.84R · PF 7.23` — falso. La realidad
  medida del mismo motor con fees es **−0.510R**. Ir a vivo con aquello sobre
  $22k habría dado **−$15.147/año (−69% de la cuenta)** a f=0.25%, y −275%
  (reventada) a f=1%. **El instrumento evitó 7x más de lo que el edge podía
  ganar.** Ésa es la contabilidad correcta.
- **Regla de decisión hacia adelante:** si operar esto cuesta más de ~$170/mes
  (agentes, infra, tiempo), el trading es EV-negativo **incluso en la frontera**.
  Los cinco meses son coste hundido; la pregunta es solo el mes que viene.
- **El riesgo más grande del proyecto no es quant, es de producto:** hay
  suscriptores pagando por una señal cuya geometría viva está medida en
  **−0.069R, IC95% [−0.112, −0.028], n=3.774 — entero bajo cero**. Eso no es zona
  gris. `ledger_stats` es el choke point único y el `n=12` lleva asterisco, pero
  **el producto se sigue vendiendo**. Decisión de RasDG, no de research.
- **El hueco quant real, si se quiere nombrar uno:** todo es **UN alpha**. 13.429
  señales, un generador, un estilo, Sharpe/trade 0.053. Las docenas de features
  (CVD, F2, KL, POC, funding, convicción) son **condicionadores del mismo motor**,
  no alphas distintos — por eso apilarlos da menos que la suma. La capa 2 (carry)
  era la única no correlacionada y `research/carry_regime.md` dice que **en 2026
  la prima se comprime a ~0** (basket +0.5%). Un segundo alpha no correlacionado
  es otro proyecto de meses, no un "ASAP".

---

## 7. Cómo arrancar (todo local, gratis, ya descargado)

```
git fetch origin claude/v1-v4-evaluation-frontier-ibkw12
git checkout claude/v1-v4-evaluation-frontier-ibkw12
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest scipy

# Las velas NO están en el repo (.gitignore). 5m y 1m de BTC/ETH/SOL ya se han
# bajado antes con esto (~40 s por símbolo el 5m, unos minutos el 1m):
python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance
python tools/fetch_binance_vision_klines.py ETHUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance
python tools/fetch_binance_vision_klines.py SOLUSDT --start 2020-08-11 --end 2026-06-30 --out-dir data/binance

# PUERTA 3 primero — cerrar el confundido del subconjunto (los 10 que faltan):
#   ADA AVAX BCH BNB DOGE DOT LINK LTC TRX XRP  (mismo comando, --interval 5m)

# Lo que ya está medido y NO hay que re-correr:
python tools/frontier_report.py                     # la frontera y los tiers
python tools/geometry_sweep.py --exits --vip        # la regla de salida
python tools/geometry_sweep.py --intrabar --vip     # el 1m (cerrado: +0.0045R)
python tools/capacity_analysis.py --vip             # la capacidad de tp4/h288

pytest tests/ -q     # 1612 pasan, 5 skip
```

**Coste estimado: una sesión.** Nada que comprar, nada que pedir.
