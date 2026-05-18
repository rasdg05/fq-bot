# FQ Public Bot — Guía de Deploy

Bot de marketing/propaganda separado del VIP. Vive en el **mismo repo** pero
corre como un **segundo servicio Railway** apuntando a `entry_public.py`.

> **Filosofía:** el bot público no opera — emite. No conversa con LLM por usuario.
> Solo lecturas programadas, CTAs rotativos, y anuncios de cierres +1R del ledger VIP.

---

## 1. Arquitectura

```
                ┌────────────────────────────────────┐
                │      Railway Project (1 solo)      │
                │                                    │
   ┌────────────┴─────────────┐    ┌────────────────┴─────────────┐
   │  Service 1: VIP          │    │  Service 2: PUBLIC           │
   │  startCommand:           │    │  startCommand:               │
   │    python entry_vip.py   │    │    python entry_public.py    │
   │                          │    │                              │
   │  TELEGRAM_TOKEN          │    │  TELEGRAM_TOKEN_PUBLIC       │
   │  ANTHROPIC_API_KEY       │    │  ANTHROPIC_API_KEY           │
   │  FQ_LEDGER_PATH=/data/.. │    │  FQ_VIP_LEDGER_PATH (RO)     │
   │  ─────────────────────   │    │  FQ_PUBLIC_DB_PATH=/data/..  │
   │  Volume montado en /data │◄───┤  Volume MISMO o separado     │
   └──────────────────────────┘    └──────────────────────────────┘
                        │                          │
                        │ escribe                  │ lee read-only
                        ▼                          │
                    fq_ledger.db ◄─────────────────┘
```

**Ledger VIP es la única fuente de verdad de outcomes.** El bot público lo abre
con `mode=ro` vía URI (no puede escribir, garantizado por SQLite). El bot público
tiene su **propia BD** para subscribers y tracking de anuncios enviados.

---

## 2. Antes de empezar — checklist

- [ ] Tienes ya el bot VIP funcionando en Railway (entry_vip.py o fq_bot_v3_2.py)
- [ ] Tienes un Volume montado en `/data` (el VIP graba su ledger ahí)
- [ ] Vas a crear **un nuevo bot Telegram** en BotFather para el público
- [ ] Sabes el `@username` del bot VIP (sin @) para configurar deep-links

Si no tienes alguno de los anteriores, ve al paso correspondiente abajo antes de continuar.

---

## 3. Paso a paso

### 3.1 — Crear el bot Telegram público en BotFather

1. Abre Telegram, chatea con `@BotFather`
2. `/newbot`
3. Nombre visible: `FQ · Propaganda` (o como quieras)
4. Username: algo como `RasDG_FQ_publico_bot` (debe terminar en `bot`)
5. Guarda el TOKEN que te da. Esto será `TELEGRAM_TOKEN_PUBLIC`
6. (Opcional) `/setdescription`, `/setabouttext`, `/setuserpic` para personalizar
7. (Opcional) `/setcommands` con la lista pública:
   ```
   start - Suscribirse al canal de reportes
   info - Conocer el sistema FQ
   precio - Ver tarifas del VIP
   unirme - Acceso al VIP
   stripe - Pagar con tarjeta
   crypto - Pagar con USDT
   codigo - Canjear codigo de activacion
   desuscribir - Dejar de recibir reportes
   ```

### 3.2 — Crear el segundo servicio en Railway

1. En tu proyecto Railway existente (el del bot VIP), click **+ New** → **Empty Service**
2. Nómbralo `fq-public`
3. **Source** → conecta al mismo repo de GitHub (mismo branch que el VIP)
4. **Settings → Service** → **Start Command**:
   ```
   python entry_public.py
   ```
5. **Settings → Volumes** → opciones:
   - **Opción A (recomendada):** monta el MISMO volume del VIP en `/data`. El bot público
     escribe a `/data/fq_public.db` y lee `/data/fq_ledger.db` (RO). Sin duplicar storage.
   - **Opción B:** monta un volume nuevo en `/data` para el público. Pero entonces
     no podría leer el ledger VIP a menos que copies el path. Más complicado. **No lo recomiendo.**

### 3.3 — Env vars del servicio público

En **Settings → Variables** del servicio público:

| Variable | Valor | Obligatorio |
|---|---|---|
| `TELEGRAM_TOKEN_PUBLIC` | token de BotFather del bot público | **sí** |
| `FQ_VIP_BOT_USERNAME` | `RasDG_FQ_VIP_bot` (sin `@`) | **sí** (para deep-links) |
| `FQ_PUBLIC_DB_PATH` | `/data/fq_public.db` | recomendado |
| `FQ_VIP_LEDGER_PATH` | `/data/fq_ledger.db` | recomendado |
| `ANTHROPIC_API_KEY` | el mismo que usa el VIP | sí (para lecturas Sonnet) |
| `TELEGRAM_CHAT_ID` | tu chat de admin (para notificaciones internas) | opcional |
| `FQ_STRIPE_LINK` | `https://buy.stripe.com/xxxxx` | opcional |
| `FQ_USDT_ADDRESS` | tu wallet USDT | opcional |
| `FQ_USDT_NETWORK` | `TRC20`, `ERC20`, `POLYGON` etc. | opcional (default TRC20) |

**Nota:** el bot público no necesita `TELEGRAM_TOKEN` ni `FQ_LEDGER_PATH` (esos son del VIP).
Si no defines `TELEGRAM_TOKEN_PUBLIC`, intentará usar `TELEGRAM_TOKEN` como fallback (útil para testing).

### 3.4 — Deploy

1. Push a tu branch (o merge a main)
2. Railway deployea automáticamente el nuevo servicio
3. Verifica los logs del servicio público:
   ```
   FQ PUBLIC BOT - Mistral propaganda edition
   VIP ledger (RO): /data/fq_ledger.db
   Public DB:       /data/fq_public.db
   VIP bot @:       RasDG_FQ_VIP_bot
   Command listener iniciado
   Scheduler iniciado (tick cada 60s)
   ```

### 3.5 — Test de aceptación

Desde tu Telegram personal:

1. **Encuentra tu bot público** (busca su @username)
2. Escribe `/start` → debes recibir el **welcome card** con glyphs
3. Verifica en los logs del servicio: `Nuevo subscriber publico: chat_id=...`
4. Escribe `/info` → debes ver el card del sistema
5. Escribe `/precio` → tabla de tarifas
6. Escribe `/codigo ABCD-1234` → debes recibir un link `t.me/RasDG_FQ_VIP_bot?start=ABCD-1234`
7. Tap ese link → debe abrir tu bot VIP con `/start ABCD-1234` precargado
8. Escribe `/claude analiza` → debe responder con el **welcome card** (NO con LLM — esto es crítico)
9. Escribe `/comando_falso` → mismo welcome card

Si todo lo anterior funciona, el bot está listo.

---

## 4. Cómo funciona el contenido programado

### 4.1 — Anuncios de cierre +1R

Cada 8 minutos el scheduler revisa el ledger VIP read-only. Si hay un cierre con
`pnl_r >= 1.0` que no ha sido anunciado, lo broadcasts a todos los subscribers:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ◆ FQ · Cierre confirmado
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ▴ LONG SOL/USDT
  ▸ Disparada    08:00 CDMX
  ▸ Cerrada      10:30 CDMX
  ▸ Resultado    TP3  ·  +2.60R
  ▸ Duracion     2h 30m
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ...
```

Los cierres TP1 con pnl_r < 1.0 NO se anuncian (refuerza la narrativa "el sistema saca
trades grandes, no scalps mediocres").

### 4.2 — Lecturas del día (Sonnet)

Dos veces por día (08:30 y 15:00 CDMX), el scheduler genera una lectura editorial
con **Sonnet 4.6**. Tema rota deterministicamente según el día del año — 12 temas
diferentes, ciclo mensual.

Cuesta ≈ 2 llamadas/día × ~400 tokens output = **centavos por mes**.

### 4.3 — CTAs rotativos

Dos veces por día (11:00 y 20:00 CDMX), broadcast un CTA del array `CTA_VARIANTS`
(5 variantes en `public_format.py`). Rotan secuencialmente. Sin LLM — texto plano
templated.

### 4.4 — Stats semanales

Domingos 18:00 CDMX, broadcast el reporte de la semana (win rate, expectancy,
profit factor, mejor cierre, etc.) leyendo el ledger VIP.

---

## 5. Comandos del bot público

| Comando | Función |
|---|---|
| `/start` | Suscribirse y recibir welcome |
| `/info` | Conocer el sistema FQ |
| `/precio` | Tarifas del VIP |
| `/unirme` | Menu de acceso (stripe/crypto/codigo) |
| `/stripe` | Link directo a Stripe |
| `/crypto` | Address USDT |
| `/codigo XXXX` | Deep link al bot VIP con código pre-llenado |
| `/desuscribir` | Opt-out de los reportes |
| `/help` | Alias de `/info` |

**Cualquier otro comando** → welcome card (con redirección al VIP).

---

## 6. Tuning del scheduler

Variables que puedes ajustar en `public_scheduler.py`:

```python
SLOTS_LECTURA = [(8, 30), (15, 0)]     # hora CDMX
SLOTS_CTA     = [(11, 0), (20, 0)]
SLOT_STATS_SEMANAL = (6, 18, 0)        # domingo 18:00
CLOSURE_POLL_MIN   = 8                  # poll cada 8 min
```

Si quieres más agresividad: más slots de CTA, polls más frecuentes. Si quieres
más editorial: menos CTAs, más lecturas.

---

## 7. Troubleshooting

| Síntoma | Causa probable | Fix |
|---|---|---|
| Logs "VIP ledger no existe" | El path está mal o el volume no está montado | Verifica `FQ_VIP_LEDGER_PATH` y que ambos servicios compartan `/data` |
| `/start` no responde | Token Telegram inválido | Revisa `TELEGRAM_TOKEN_PUBLIC` |
| Lecturas no se envían | API key Claude inválida o sin créditos | Revisa `ANTHROPIC_API_KEY` |
| Cierres del VIP no se anuncian | Bot público apunta a otro path | Verifica `FQ_VIP_LEDGER_PATH` |
| `/codigo XXXX` da link sin username | `FQ_VIP_BOT_USERNAME` vacío | Setea esta env var con el username del VIP (sin `@`) |
| Subscribers fantasma (bloquearon el bot) | Telegram devuelve 403 | El bot los desactiva automáticamente en el siguiente broadcast |

---

## 8. Cosas que el bot público NO hace (intencionalmente)

- **No conversa con LLM por usuario** — `/claude`, `/analisis`, `/ia` no existen como comandos públicos. Sólo el scheduler interno llama a Claude.
- **No da señales accionables en vivo** — sólo anuncia cierres ya cerrados. Esto preserva el incentivo a pagar VIP.
- **No expone formulas internas** — no menciona φ, κ_evo, Θ(D), P_master. Las lecturas educativas hablan de conceptos generales (PD zones, killzones, OTE) sin exponer la arquitectura del motor.
- **No procesa pagos directamente** — los comandos `/stripe` y `/crypto` solo dan el link/address. El flujo de activación es:
  1. Usuario paga (Stripe checkout o transferencia USDT)
  2. Tú generas código manualmente con `/gencode` en el bot VIP (admin)
  3. Le envías el código al usuario
  4. Usuario hace `/codigo XXXX` en el bot público → recibe deep-link al VIP → canjea

---

## 9. Costos estimados

- **Telegram API:** gratis (rate limits razonables para <10K usuarios)
- **Railway Service:** ~$5-10/mes (mismo tier que el VIP)
- **Claude API:** ~$0.50-2/mes para las lecturas (2 Sonnet/día = ~30 mensajes/mes)
- **Storage Volume:** sin costo extra si comparte con el VIP

Total marginal: < $15/mes para tener el bot público corriendo.

---

## 10. Próximos pasos (no en esta entrega)

- Integración Stripe real (webhook → auto-generación de código → DM al user)
- Auto-DM cuando un subscriber lleva 7 días suscrito sin convertir
- A/B testing de variantes de CTA (track conversión por variante)
- Track del funnel: `/start` → `/precio` → `/unirme` → conversión

Estas mejoras son opcionales — el sistema actual ya es funcional end-to-end.

#FQv42 #PublicBot #Mistral
