# CLAUDE.md — fq-bot

> Este archivo se carga en CADA sesión. Por eso es corto: **rutea, no repite**.
> El contexto largo vive en `MEMORY/` y se lee bajo demanda.
> Compatible con cualquier agente (Claude Code, OpenCode, Aider, Cline): es
> markdown plano sin dependencias. `AGENTS.md` es un enlace a este mismo archivo.

## Qué es esto

Bot de señales cripto de order-flow, **vivo en producción** (Railway, rama `main`)
con suscriptores de pago. SOL (pilar), BTC, ETH. Cada push a `main` redeploya.

## ⚠️ LA RAMA (léelo antes que nada)

**`main` está en JUNIO. La rama viva es
`claude/v3-capacidad-velas-rp3v9u`.** Si arrancas en `main` vas a leer un estado
caducado y volver a concluir cosas ya medidas. Empieza siempre con:

```
git fetch origin claude/v3-capacidad-velas-rp3v9u && git checkout claude/v3-capacidad-velas-rp3v9u
```

Contiene `claude/instrumento-2026-08-of95si` entero (E1–E9) y **V1, V2, V3 y V4**
(el nombre de la rama dice "v3" y se quedó corto: V4 está dentro). Las ramas
anteriores (`...-v1-kqa7w0`, `...-v2-q1obx4`, `instrumento-...`) ya no se tocan:
son historia, no punto de partida. Si abres una sesión nueva, apunta a la de
arriba y no fusiones nada — está por delante, no en paralelo.

Nada se mergea a `main` sin decírselo a RasDG: despliega a producción con
suscriptores de pago.

## Antes de tocar nada

1. `MEMORY/00-INDICE.md` — la puerta (60 s).
2. `MEMORY/CONSTITUCION.md` — invariantes no-negociables. **El gate DSR>0.95 /
   CPCV / PBO no se degrada jamás.**
3. `MEMORY/CEMENTERIO.md` — antes de proponer algo, mira si ya se mató.
4. `MEMORY/ESTADO.md` — qué está vivo / dormido / midiendo hoy.

## La lección más cara del proyecto

En julio, `internal/GHOST_MAP_2026-07.md` (H1) documentó que la racha direccional
de mayo era un espejismo: 16/16 shorts ganando en vivo, pero **SHORT +0.225R vs
LONG +0.223R sobre 7 años y 13k señales — un volado**.

El repo lo sabía. El código siguió publicando `WR 60% · E[R] +1.84R · PF 7.23`
hasta agosto, cuando se encontró que 23 de 35 cierres se habían escrito en 763
milisegundos por un tracker sin horizonte.

**El fallo no fue de conocimiento sino de cableado.** De ahí la regla que gobierna
este repo: *un hallazgo sin invariante que lo haga cumplir es una nota, no un
arreglo.* Cuando cierres un hallazgo, pregúntate qué test o qué gate impide que
vuelva — si la respuesta es "acordarse", no está cerrado.

## Invariantes que ya están cableadas (no las rompas)

| Invariante | Dónde | Qué impide |
|---|---|---|
| Horizonte de outcome | `entropy_cognition.check_outcome_against_candles` | Acreditar un TP tocado después de que la señal debió morir |
| Auditabilidad | `ledger_stats.is_auditable` + `AUDITABLE_SQL` | Que una vida > horizonte entre en métricas **o en el aprendizaje** |
| Reconciler → ledger de señales | `reconciler.SignalLedgerView` | Publicar un track record que nadie audita |
| Sizing neto | `execution.PaperBroker.open` | Que `risk_frac` mienta (arriesgaba 19% de más) |
| Equity continua | `execution.resume_equity_from_ledger` | Drawdown invisible y halt `FQ_MOTOR_MAX_DD` muerto |
| Frescura de CVD | `tools/fetch_cvd.cvd_confirmation` | Un colector parado contestando como si midiera |
| Sin relojes de pared | `tests/test_no_wallclock.py` | Que el replay herede la hora del click |
| Cartera antes que candidata | `vip_report.screen_cell` + `require_screened` | Publicar como hallazgo una celda con buen R por trade que arruina la cuenta |
| Universo medido = publicado | `vip_report.vip_universe` vs `fq_bot_v3_2.VIP_PAIRS` | Medir un producto distinto del que se difunde, con los dos números correctos |
| Fill maker con procedencia | `bt_engine.maker_expectancy` + `require_fill_modeled` | Publicar una cifra maker con fill 100% asumido (el supuesto que volteó +0.060R → −0.0350R) |
| Liquidez medida, no supuesta | `capacity_analysis.require_measured` | Publicar una capacidad calculada con el default de catálogo (estaba **8x** fuera en BTC) o sobre serie bruta sin etiquetarla TECHO |
| La ventana no elige la cifra | `test_capacity_is_invariant_to_fill_bars` | Que `fill_bars` mueva la capacidad ×24 sin que nada lo delate (σ por barra contra liquidez por ventana) |
| Crecimiento junto a la media | `ledger_stats.format_expectancy` + `growth.ArithmeticWithoutGrowthError` | Publicar un E[R] aritmético sin `g`, `f*` y P(acabar arriba) — el E[R] es del ensemble, la cuenta vive UNA trayectoria |
| Una sola `f` | `execution.GovernorConfig` ← `growth.configured_risk_frac` | Que el gobernador arriesgue una fracción y el informe juzgue otra (ninguna otra métrica del repo depende de `f`) |

## Números vigentes (agosto 2026) — no inventes otros

- **Track record publicado**: n=12 · WR 41.7% · E[R] +0.208 · PF 1.76.
  (Antes decía n=35 / +1.835R; las 23 filas del fantasma están excluidas por
  invariante, no borradas.)
- **Motor paper, 90 cierres CON fees**: E[R] **−0.510**, IC95% [−0.785, −0.205],
  P(E[R]≥0)=0.001. WR 21.1% contra un **WR de equilibrio de 36.9%**.
- **Cube 7 años, E8 (n=13.429)**: bruto **+0.2305R** → **neto −0.0258R**, IC95%
  [−0.059, +0.013]. **El coste de ejecución es −0.256R/trade**: más grande que el
  edge bruto entero. Ningún subconjunto (13 símbolos × 8 años × 2 lados × 5
  quintiles de stop) clarea DSR > 0.95.
- **E7 — la buena noticia, y está medida**: la entrada **SÍ separa**. Asimetría de
  recorrido **+1.011R, IC95% [+0.825, +1.199]**, en ambos lados y los ocho años.
  **El problema no es la señal**: son las barreras, el coste y el capital simultáneo.
- **El VIP (BTC/ETH/SOL), neto sobre el cube, n=3.774**: la **selección de símbolos
  se sostiene** (+0.010R vs −0.040R del resto del pool), pero la **geometría que
  opera en vivo no**: **tp1/h288 = −0.069R, IC95% [−0.112, −0.028]** — entero bajo
  cero. Por símbolo: ETH +0.059 · BTC +0.003 · **SOL −0.054**.
  **V1 cerró el eje TP entero** (h288, universo VIP): tp1 −0.069 · tp2 −0.053 ·
  tp3 −0.018 · tp4 +0.010. **Ninguna celda es candidata** — ninguna tiene el IC95%
  entero sobre cero. Reproducir: `python tools/vip_report.py`.
  Dos matices que hay que llevar puestos, porque cambian a dónde va el trabajo:
  **(a)** estas celdas **no caen por cartera** — hold ~0.1 días, concurrencia ~1.3,
  DD 26–27% *dentro* de la cota del 35% y aun así hunden la cuenta: no sobra
  riesgo, **falta edge**. No es el fallo de la geometría ancha (13.7 simultáneas),
  así que un mecanismo de concurrencia no arreglaría ninguna.
  **(b)** el neto **sube monótonamente hasta tp4**, el último peldaño etiquetado
  del cube: **máximo en la esquina**. La tabla NO dice que tp4 sea el óptimo; dice
  que el gradiente apunta fuera del rango medido. Resolverlo exige **re-etiquetar**
  con objetivos más lejanos (`geometry_sweep`, que necesita velas locales — **hoy
  no hay `data/binance` en el repo**), no extrapolar. Y alejar el objetivo alarga
  la vida del trade, o sea que devuelve el problema de concurrencia ya cementado.

- **V2 — la cola, medida (n=12.941 del pool; la vía maker cerrada por ejecución)**:
  el fill deja de ser binario. `maker_fill_probability` da **P(fill) según el flujo
  FIRMADO** que imprimió en el nivel, con la cola en `queue_frac` (múltiplos del volumen
  mediano de barra). **`queue_frac=0` ES la binaria de siempre** — o sea que la regla
  vieja era la esquina de *estar siempre el primero*. Neto maker por cola: **0.00
  −0.0350 [−0.076, +0.004] · 0.05 −0.0635 [−0.104, −0.025] · 0.25 −0.1549 · 1.00
  −0.3294**. **Con 0.05 barras de cola el IC ya está entero bajo cero**: el último número
  maker que rozaba el cero deja de rozarlo. Mecanismo medido, no argumentado:
  **corr(P(fill), R) = −0.2267** (p<0.25 → +0.8548R; **p=1 → −0.3784R**, n=7.757) — la
  cola te deja justo las señales en las que el precio te atravesó. VIP (n=3.565): 0.00
  +0.0282 → 0.25 **−0.0845** [−0.161, −0.007]. `queue_frac` es **supuesto declarado**, no
  medición (aquí no hay L2): por eso se publica la curva y se cita el **umbral**.
  Reproducir: `python tools/fill_quality.py --klines data/binance`.

- **V3 — la capacidad, con la liquidez MEDIDA: la cifra es de CINCO dígitos.**
  El tool existía desde N8.4 contestando con parámetros de catálogo: su default
  `avg_bar_notional=3e6` estaba **8x por debajo del BTC real** (2.563e7 USD/barra 5m) y
  `fill_bars=24` multiplicaba la capacidad **por 24** (σ iba por barra contra liquidez
  por ventana; con σ escalada la ley raíz es invariante y hay test).
  Medido (tp4/h288, VIP, risk 1%, Y=1): bruto BTC C½ $308k / C0 $1.2M · ETH $162k/$650k ·
  SOL $15k/$60k. **Neto: solo ETH tiene algo — C½ $5k, C0 $22k**; BTC (+0.0027R) y SOL
  (−0.0539R) no tienen capacidad que medir. **Todo el edge neto del producto cabe en ETH
  por debajo de ~$22k** → es un **servicio de señales, no un vehículo de capital**.
  La frontera donde el impacto iguala al coste fijo: **BTC $1.2M · ETH $434k · SOL $106k**
  — por debajo manda el coste fijo y **encoger la cuenta no arregla nada**.
  **Y la causa no es falta de libro** (BTC mueve 2.6e7/barra): es el **stop apretado**
  (0.45–0.63%), que divide el impacto en R — y el stop apretado **ES el edge** (medido
  2026-06-30: Q1 +0.316R vs Q4 +0.147R). Lo que hace rentable a la señal es lo que la
  hace frágil al tamaño. Reproducir: `python tools/capacity_analysis.py --vip`.

- **V4 — el crecimiento, no la media (2026-08-05).** E[R] es el promedio del
  *ensemble*; una cuenta vive UNA trayectoria y compone. Con `f` = fracción por trade,
  `g = E[ln(1+f·R)] ≈ f·μ − f²σ²/2`. Medido sobre el VIP: **tp1/h288 tiene f\* = 0**
  (ninguna fracción positiva hace crecer esa celda) y **P(acabar arriba) = 21%** a 200
  trades; tp4 llega a **51%** con f\* = 0.20%. La cuenta viva arriesga **0.25%**, o sea
  **1.2x f\*** — correcto por poco, y hasta hoy nadie podía saberlo: **E[R], IC95% y DSR
  son invariantes a `f` por construcción**, así que el sistema de medición entero era
  incapaz de ver una sobre-apuesta. Ojo con el texto de ergodicidad: `μ − σ²/2` aplica a
  apostar el 100%; en múltiplos de R a f=0.25% el arrastre es `f²σ²/2` ≈ 1e-5.
  **Medir en R ya era la vacuna** — lo que faltaba era mirar `f`.

> Ninguna configuración medida tiene el IC95% de la expectancy por encima de cero.
> No hay edge demostrado. Decirlo no es pesimismo: es el estado del arte del repo.
>
> **No uses el `n=12` para afirmar nada** (ni con clientes ni con inversores): está
> bajo el `MIN_N=30` del propio repo y no concluye en ninguna dirección.

## Contexto vivo que no es código (ago-2026)

- **Encargo CERRADO**: `internal/BRIEF_VIP_2026-08.md`, las tres entregas hechas —
  **V1** (`tools/vip_report.py`), **V2** (`bt_engine.maker_fill_probability` +
  `tools/fill_quality.py`) y **V3** (`tools/capacity_analysis.py --vip`).
  **Ninguna de las tres abrió una puerta**: la geometría no tiene celda operable, la
  ejecución no tiene dónde ponerse en la cola, y el tamaño se acaba antes de que el edge
  empiece. **Lo que falta no es otra medición del mismo cube: es una señal con más edge
  BRUTO, o un coste de ejecución estructuralmente menor.** Un encargo nuevo que no ataque
  una de esas dos cosas está decorando.
  **V4 se añadió después** (`growth.py`), y no es una cuarta entrega del brief sino la
  respuesta a un texto de ergodicidad que trajo RasDG: cableó `g`/`f*`/P(acabar arriba).
  No cambia el veredicto — lo traduce al idioma en el que un suscriptor lo entiende.
  **Ojo con las velas**: `data/` está en `.gitignore`, así que V2 y V3 no se re-corren en
  un clon nuevo hasta bajarlas
  (`python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end
  2026-06-30 --out-dir data/binance`, ~40 s por símbolo, gratis, sin API key).
- **Encargo SIGUIENTE, ya escrito**: `internal/BRIEF_FRONTERA_2026-08.md` — dónde está
  la frontera en una cifra, las palancas vivas con su prior medido, y la lista
  anti-espejismo. Léelo ANTES de proponer nada nuevo.
- **Presión de inversor**: un inversor del proyecto lleva meses viendo gasto sin
  producto rentable. Propuso pivotar a copy-trading (Trump/políticos, Autopilot +
  Hyperliquid). **Se midió antes de construir: 1 candidata de 100** → muerto en
  `CEMENTERIO.md`; el espejo sin capital queda especificado en
  `internal/EXPERIMENT_COPYTRADE_ONCHAIN.md` por si se retoma. **No se pivota**: el
  pivote sube la quema justo cuando la queja es la quema. **V3 (capacidad) es la
  respuesta a su ansiedad** — convierte "confía en mí" en una cifra. Detalle y qué
  decirle: `MEMORY/ESTADO.md`, bloque de agosto.

## Reglas de trabajo

- **Measure-first.** Nada a vivo sin pasar el gate. Lo que no pasa → `CEMENTERIO.md`.
- **n < 30 no concluye.** Ni a favor ni en contra. Con muestra chica, ordenar por
  resultado selecciona ruido. Cita la n en cada afirmación.
- **Una métrica demasiado limpia es un bug**, no un hallazgo. Distribución
  imposible (cero tp1/tp2/tp3, separación perfecta por una variable) → fallo de
  medición **antes** que lectura de edge.
- **Prefiere editar a crear.** Este repo ya tiene mucho; duplicar es deuda.
- **Cierra el lazo**: hallazgo → test que lo fija → invariante que lo hace cumplir.
- Sé conciso. Los tokens se pagan.

## Rutas que importan

```
MEMORY/                  bitácora de proceso (constitución, decisiones, cementerio, estado)
internal/GHOST_MAP_*.md  radiografía del motor sobre 7 años de cube
internal/EXPERIMENT_*.md experimentos measure-first planificados
tools/validation_gate.py el gate DSR/CPCV/PBO — la vara
tools/geometry_report.py juzga geometría TP/SL con el recorrido (MFE/MAE)
tools/vip_report.py      "¿funciona el VIP?" — universo + eje TP con cartera (V1)
tools/fill_quality.py    fill maker real: P(fill) por cola y flujo firmado (V2)
tools/capacity_analysis.py  --vip: a qué tamaño se muere, con liquidez medida (V3)
growth.py                g / f* / P(acabar arriba) — lo que E[R] no dice (V4)
execution.py             PaperBroker: sizing, costes, recorrido, ledger hash-chain
entropy_cognition.py     ledger de señales, outcomes, κ, entropía, auditoría
ledger_stats.py          ÚNICO punto por el que sale el track record público
```

## Entorno

- CI: GitHub Actions, Python 3.12, `pytest tests/` + `requirements.lock`.
  Local: `python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest`.
- Suite completa ~40 s. **Córrela antes de cada commit.**
- Despliegue: merge a `main` → Railway. `railway.toml` excluye `marea/**`,
  `MEMORY/**` y `tools/` (salvo excepciones listadas) de los watchPatterns.
