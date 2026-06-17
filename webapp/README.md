# FQ Mini App (Telegram WebApp)

Interfaz visual del bot: **panel admin** (métricas del motor, salud,
suscriptores) y **app cliente** (señales filtradas por tier). Corre dentro de
Telegram; la identidad y las notificaciones reusan tu bot existente.

## Principios

- **Aditiva y de solo lectura.** No toca el motor, el broadcast ni los pagos.
  Lee el mismo `fq_ledger.db` y `fq_vip.db` que ya existen.
- **No tumba el bot en vivo.** El launcher reinicia el container si un hijo
  muere; `entry_web.py` está diseñado para **nunca salir**: ante cualquier fallo
  queda en idle (latiendo). Un bug de la web jamás afecta al motor de señales.
- **Auth sin contraseñas.** Cada request lleva el `initData` firmado por
  Telegram; el servidor valida el HMAC-SHA256 contra el token del bot
  (`webapp/auth.py`) y resuelve el rol del lado servidor.
- **Sin fugas de motor en cara-cliente.** Las vistas de cliente pasan por
  whitelist estricta (sin `p_master`, `kappa`, `bucket_key`, `snapshot`…),
  blindado por `tests/test_webapp_server.py` y `tests/test_webapp_data.py`.

## Arquitectura

```
entry_web.py            Entrypoint resiliente (lo lanza launcher.py como 4º proceso)
webapp/
  auth.py               Validación HMAC del initData (pura, testeable)
  data.py               Capa de datos RO + shaping por rol (admin vs tier)
  notify.py             Mensajes con botón "Abrir app" (deep-link a una vista)
  server.py             App Flask: sirve la SPA + API JSON
  static/
    index.html          Shell de la Mini App
    app.js              Lógica (vanilla JS, sin build step)
    styles.css          Estética "Terminal" (oscura, hairline, sobria)
```

Endpoints (todos exigen `initData`; `/api/admin/*` exige rol admin):

| Ruta | Rol | Devuelve |
|---|---|---|
| `GET /api/me` | cualquiera | identidad + tier + días restantes |
| `GET /api/signals` | cualquiera | señales filtradas por tier (free = teaser) |
| `GET /api/track-record` | cualquiera | win-rate/expectancy 30/90/total |
| `GET /api/admin/overview` | admin | salud del motor + conteos |
| `GET /api/admin/signals` | admin | abiertas + recientes con la matemática |
| `GET /api/admin/stats` | admin | métricas globales + por tier |
| `GET /api/admin/subs` | admin | suscriptores, ingresos, pagos pendientes |
| `GET /healthz` | — | healthcheck (sin auth) |

## Configuración (Railway / prod)

1. **Variables de entorno** (ver `.env.example`, sección MINI APP):
   - `FQ_WEBAPP_URL` = la URL pública https del servicio Railway (la usa el
     botón "Abrir app" y BotFather).
   - `FQ_WEBAPP_BOT_TOKEN` opcional (vacío = usa `TELEGRAM_TOKEN`, el bot VIP).
   - `FQ_WEBAPP_ENABLED=1` (poné `0` para apagarla sin redeploy).
   - Railway inyecta `PORT` automáticamente.

2. **BotFather** (una sola vez), con tu bot VIP:
   - `/setmenubutton` → elige el bot → pega la `FQ_WEBAPP_URL` y un texto
     (p.ej. "Abrir panel"). Esto pone el botón de Mini App en el chat.
   - (Opcional) `/newapp` para registrar la Mini App con nombre e icono.

## Desarrollo local (sin Telegram)

El modo dev impersona un usuario para poder abrir la app en el navegador:

```
FQ_WEBAPP_DEV=1 \
FQ_WEBAPP_DEV_USER=<tu_chat_id_admin> \
FQ_LEDGER_PATH=/ruta/fq_ledger.db \
FQ_VIP_DB_PATH=/ruta/fq_vip.db \
TELEGRAM_CHAT_ID=<tu_chat_id_admin> \
python entry_web.py
# abre http://localhost:8080
```

`FQ_WEBAPP_DEV` **nunca** debe estar activo en producción (saltea la auth).

## Tests

```
pytest tests/test_webapp_auth.py tests/test_webapp_data.py tests/test_webapp_server.py
```

## Notificaciones

Las notificaciones son los mensajes normales del bot que **ya existen**, ahora
con un botón inline **"Abrir app"** (`web_app`) que abre la Mini App en la vista
relevante. `notify.app_button(view=...)` construye el markup; los puntos de
envío lo pasan como `reply_markup`.

Eventos cableados:

| Evento | Dónde | Llega a | Abre vista |
|---|---|---|---|
| Nueva señal | `fq_bot_v3_2.py` (broadcast de señal) | VIP/trial/admin | `signals` |
| TP/SL alcanzado | `fq_bot_v3_2.py` (progress + táctico) | VIP/trial/admin | `signals` |
| Pago confirmado | `fq_bot_v3_2.py` (polling crypto) | admin | `subs` |
| Salud del motor | `ops/maintenance.py` (watchdog) | admin | `health` |

**Red de seguridad (best practice):** un botón `web_app` exige que el dominio de
`FQ_WEBAPP_URL` esté dado de alta en BotFather. Si no lo está, Telegram responde
400 — así que `telegram_send` y `_dm_admin` **reintentan el mismo mensaje sin el
botón**. Un botón mal configurado nunca bloquea una señal ni una alerta de salud.
Y sin `FQ_WEBAPP_URL`, `app_button()` devuelve `None`: cero cambios de
comportamiento (las notificaciones salen como siempre).

Activación: define `FQ_WEBAPP_URL` y registra el dominio en BotFather
(`/setmenubutton` ya lo hace). Nada más que cablear.

> Nota: "nuevo suscriptor" sin pago (canje de código de regalo) aún no emite DM
> al admin — no había un punto de envío existente y añadirlo es más invasivo. El
> evento de **pago confirmado** cubre el caso de dinero. Queda como mejora.
