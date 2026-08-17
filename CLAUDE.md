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

## Números vigentes (agosto 2026) — no inventes otros

- **Track record publicado**: n=12 · WR 41.7% · E[R] +0.208 · PF 1.76.
  (Antes decía n=35 / +1.835R; las 23 filas del fantasma están excluidas por
  invariante, no borradas.)
- **Motor paper, 90 cierres CON fees**: E[R] **−0.510**, IC95% [−0.785, −0.205],
  P(E[R]≥0)=0.001. WR 21.1% contra un **WR de equilibrio de 36.9%**.
- **Cube 7 años, bruto**: +0.224R. La diferencia entre eso y el −0.51R vivo **es
  el coste de ejecución**, y responde la pregunta abierta 6 del GHOST_MAP.

> Ninguna configuración medida tiene el IC95% de la expectancy por encima de cero.
> No hay edge demostrado. Decirlo no es pesimismo: es el estado del arte del repo.

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
internal/POLYMARKET_*.md lead de Polymarket: la oferta SÍ existe, falta medir el spread
                         (triaje de los 10 repos en CEMENTERIO.md — no re-proponerlos)
tools/validation_gate.py el gate DSR/CPCV/PBO — la vara
tools/geometry_report.py juzga geometría TP/SL con el recorrido (MFE/MAE)
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
