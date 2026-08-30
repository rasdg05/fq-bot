# CLAUDE.md — fq-bot

> Este archivo se carga en CADA sesión. Por eso es corto: **rutea, no repite**.
> El contexto largo vive en `MEMORY/` y se lee bajo demanda.
> Compatible con cualquier agente (Claude Code, OpenCode, Aider, Cline): es
> markdown plano sin dependencias. `AGENTS.md` es un enlace a este mismo archivo.

## Qué es esto

Bot de señales cripto de order-flow, **vivo en producción** (Railway, rama `main`)
con suscriptores de pago. SOL (pilar), BTC, ETH. Cada push a `main` redeploya.

## Antes de tocar nada

1. `MEMORY/00-INDICE.md` — la puerta (60 s).
2. `MEMORY/CONSTITUCION.md` — invariantes no-negociables. **El gate DSR>0.95 /
   CPCV / PBO no se degrada jamás.**
3. `MEMORY/CEMENTERIO.md` — antes de proponer algo, mira si ya se mató.
4. `MEMORY/ESTADO.md` — qué está vivo / dormido / midiendo hoy.
5. `internal/BRIEF_INSTRUMENTO_2026-08.md` — **el encargo vigente** (E7/E8 primero).

> ⚠️ El contexto más fresco vive en la rama `claude/instrumento-2026-08`,
> **no mergeada a `main`**. Sale de `claude/polymarket-trading-tools-grx05x` (que tampoco
> está mergeada) y le añade E7 y E8 contestados. Arrancar desde `main` re-propondría
> Polymarket (cerrada y medida) y volvería a leer mal la excursión del cube.
>
> ```bash
> git fetch origin claude/instrumento-2026-08
> git checkout -b <tu-rama> origin/claude/instrumento-2026-08
> git log origin/main --oneline | grep -i excursion   # ¿vacío? entonces NO está mergeada
> ```

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
| Ni la suite lee el reloj | `test_no_wallclock.py::test_ningun_test_se_salta_segun_la_hora` | Que un test desaparezca a ciertas horas y el resumen siga diciendo "passed" |
| Procedencia sellada | `bt_data.stamp_venue` + `require_same_venue` | Cruzar velas de un venue con un cube de otro: mueve el bar de la barrera y con él la vida del trade |
| Alcance de la excursión | `bt_labeler.CUBE_SCHEMA` + `require_life_scoped` | Leer el recorrido de la VENTANA del horizonte como si fuera el del trade |
| Una sola definición de MFE/MAE | `tests/test_cube_excursion_scope.py` | Que las dos rutas de etiquetado vuelvan a divergir bajo el mismo nombre; barre `tools/` exigiendo la guarda |
| Nada de separación circular | `tests/test_geometry_separacion.py` | Dictar "la señal separa" comparando ganadores contra perdedores, que no pueden solaparse |
| Placebo obligatorio | `tools/cube_fixed_window.py` | Publicar un AUC de separación sin su entrada de control |
| El sobrepaso solo empeora | `tests/test_cube_net_expectancy.py` | Que un signo invertido haga "rentable" el fill pesimista del stop |

## Números vigentes (agosto 2026) — no inventes otros

- **Track record publicado**: n=12 · WR 41.7% · E[R] +0.208 · PF 1.76.
  (Antes decía n=35 / +1.835R; las 23 filas del fantasma están excluidas por
  invariante, no borradas.)
- **Motor paper, 90 cierres CON fees**: E[R] **−0.510**, IC95% [−0.785, −0.205],
  P(E[R]≥0)=0.001. WR 21.1% contra un **WR de equilibrio de 36.9%**.
- **Cube 7 años, bruto**: +0.224R (re-medido: +0.231R sobre las 13.429 con costes
  aplicados por `bt_engine`).
- **Cube CON costes** (E8, ago-2026, n=13.429): **NETO −0.023R**, IC95% [−0.060, +0.014],
  P(E[R]≤0)=0.893 — y eso **suponiendo fill exacto en `stop_price`**, que es imposible.
  Con la mitad del sobrepaso medido del stop: **−0.170R**, P=1.000. El hueco entre el
  bruto y el −0.510R vivo **es el coste de ejecución**: pregunta abierta 6, contestada.
- **La entrada SÍ distingue** (E7): +3.6 pp de WR sobre un placebo emparejado,
  IC95% [+2.5, +4.7], n=13.429. **La trayectoria no**: 8 de 8 celdas indistinguibles.
- **Fees = 0.215R** no porque sean altos, sino porque **el stop es estrecho**. R ≈ 0.3%
  del precio y 10 bps ida y vuelta sobre ~300x de notional dan ~0.2R. Apretar el stop
  lo encarece en R.

> Ninguna configuración medida tiene el IC95% de la expectancy por encima de cero.
> No hay edge demostrado. Hay **señal** (la entrada bate al azar) y **no alcanza**
> (el coste se la come entera). Decirlo no es pesimismo: es el estado del arte del repo.

> ⚠️ **GHOST_MAP H5 está corregido.** "MFE +6.66R / MAE −5.65R" era la excursión de la
> VENTANA del horizonte, no la del trade. En vida el MAE de los ganadores es **−0.364R**
> y su peor caso **−1.000R** (no puede ser otra cosa: el stop está en −1R). La lectura
> publicada —"los ganadores pasan MUY en contra primero"— estaba invertida.
> Ver `internal/EXCURSION_2026-08.md`.

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
internal/POLYMARKET_*.md LÍNEA CERRADA (ago-2026). 4 pasos: oferta ✓, horquilla ✓,
                         Brier ✗, neg_risk ✗. El venue es bueno y no tenemos qué
                         venderle. Recalibración y arb de conjunto completo, al
                         CEMENTERIO — con el triaje de los 10 repos. No re-proponer.
tools/validation_gate.py el gate DSR/CPCV/PBO — la vara
tools/geometry_report.py juzga geometría TP/SL con el recorrido (MFE/MAE). La lectura
                         de separación se RETIRÓ por circular (ago-2026)
tools/cube_regrade_excursion.py re-etiqueta un cube con la excursión EN VIDA, sin replay
tools/cube_fixed_window.py  separación NO circular, contra placebo obligatorio
tools/cube_net_expectancy.py E8: el cube con costes + barrido del fill del stop
tools/fetch_okx_klines.py   velas 5m de OKX SPOT — el venue con el que se cosechó el cube
internal/EXCURSION_2026-08.md  E7: la excursión, la circularidad y el veredicto
internal/E8_BRUTO_NETO_2026-08.md  E8: no sobrevive nada, y por cuánto
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
