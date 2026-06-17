# FQ

Senales SOL/USDT con disciplina sistematica. Cuando hay edge, dispara. Cuando no, calla.

## Stack

Python 3.11 · CCXT · pandas · SQLite · Telegram · Anthropic API.

## Run

```
pip install -r requirements.txt
python launcher.py
```

Despliegue por defecto: Railway (`railway.toml`). El launcher lanza el bot VIP y el bot publico como subprocesos.

## Configuracion

Variables minimas (ver `.env.example` para la lista completa):

| Variable | Proposito |
|---|---|
| `TELEGRAM_TOKEN` | Bot VIP |
| `TELEGRAM_TOKEN_PUBLIC` | Bot publico |
| `TELEGRAM_CHAT_ID` | Admin |
| `ANTHROPIC_API_KEY` | Lecturas y analisis |
| `FQ_LEDGER_PATH` | SQLite (default `/data/fq_ledger.db`) |
| `FQ_VIP_BOT_USERNAME` | Deep links del bot publico |

## Estructura

```
launcher.py            Spawn VIP + publico + web
entry_vip.py           Bot VIP
entry_public.py        Bot publico
entry_web.py           Mini App (Telegram WebApp): panel admin + app cliente
webapp/                API Flask + SPA de la Mini App (ver webapp/README.md)
fq_bot_v3_2.py         Loop principal y comandos
fusion_engine.py       Pipeline de decision
quantum_timelines.py   Simulacion Monte Carlo
emergent_time.py       Sincronizacion temporal
ict_smc.py             Detectores estructurales
entropy_cognition.py   Ledger y memoria
vip_system.py          Tiers y suscripciones
payments.py            Stripe + USDT
branding.py            Identidad visible
vip_format.py          Vistas VIP
public_format.py       Vistas publicas
```

Notas tecnicas internas y postulados teoricos en `internal/`.

## Tests

```
pytest                       # suite
python emergent_time.py      # self-test embebido
python quantum_timelines.py
python battle_planner.py
```
