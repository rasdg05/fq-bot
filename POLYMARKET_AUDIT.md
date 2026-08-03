# Polymarket — auditoría de la tesis y plan de trabajo

> Fecha de la medición: **2026-08-03**. Todos los números de este documento salen
> de consultas reales a `https://clob.polymarket.com` y de la documentación
> oficial, no de memoria. Reproducibles con el script de la Fase 0.

## TL;DR

1. La librería que propuso el prompt (`py-clob-client-v2`) **es real, oficial y
   está viva** (v1.1.0, jul-2026). Los imports del prompt coinciden exactamente
   con el README del paquete.
2. **El arb puro no existe.** Medido sobre 400 mercados binarios abiertos:
   cero oportunidades. Ni una. El libro está arbitrado hasta el tick.
3. Lo que sí existe y es medible son los **Maker Rebates** y las **Liquidity
   Rewards** — justo lo que el prompt puso como estrategia *secundaria*.
   Hay que invertir el orden: eso es el plato fuerte, el arb es la guarnición.
4. El prompt omite dos cosas que rompen el bot en silencio: `signature_type` /
   `funder`, y que el colateral hoy es **pUSD**, no USDC.e.

---

## 1. Lo que el prompt acertó

| Afirmación | Verificación |
|---|---|
| `py-clob-client-v2` es la librería oficial | ✅ PyPI, autor `Polymarket Engineering`, v1.1.0 subida 2026-07-17 |
| Los imports (`ClobClient, ApiCreds, OrderArgs, OrderType, PartialCreateOrderOptions, Side, MarketOrderArgs`) | ✅ Todos existen y son el patrón textual del README |
| Auth L1 (wallet) → `create_or_derive_api_key()` → L2 (HMAC) | ✅ Exacto |
| Host `https://clob.polymarket.com`, chain 137 | ✅ `constants.POLYGON = 137`, endpoint responde `OK` |
| `get_order_book`, `get_open_orders`, `get_balance_allowance` | ✅ Existen |
| DRY_RUN por defecto, secretos por env, kill switch | ✅ Postura correcta, se conserva |

**Ojo con una nota del propio paquete:** el README de `py-clob-client-v2` dice
que Polymarket recomienda su nuevo SDK unificado (`Polymarket/py-sdk`) para
proyectos nuevos. Ese paquete **no está publicado en PyPI** con nombre obvio
(`py-sdk`, `polymarket-py-sdk` → 404). Decisión: seguimos con
`py-clob-client-v2`, que está mantenido y publicado, y revisamos el SDK
unificado antes de ir a real.

---

## 2. Lo que mata el plan: el arb puro no está ahí

### Medición

400 mercados binarios abiertos (`/sampling-markets`, filtrados por
`accepting_orders && enable_order_book && !closed`), libros traídos por lotes
vía `/books`:

| Métrica | Resultado |
|---|---|
| `min(yes_ask + no_ask)` | **1.0010** |
| Mediana `yes_ask + no_ask` | 1.0110 |
| Mercados con suma < 1.00 | **0 de 400** |
| Mercados con suma < 0.99 | **0 de 400** |
| `max(yes_bid + no_bid)` (arb espejo: split & sell) | **0.9990** |
| Mediana `yes_bid + no_bid` | 0.9890 |
| Mercados con suma de bids > 1.00 | **0 de 400** |
| Spread mediano (lado YES) | 0.011 (1.1¢) |

El detalle que lo dice todo: el mínimo del lado ask es **1.0010** y el máximo del
lado bid es **0.9990**. Exactamente **un tick** (0.001) fuera de la paridad, por
los dos lados. Eso no es casualidad: son bots más rápidos que nosotros que ya
comprimieron el libro hasta el mínimo incremento de precio que la plataforma
permite. La frontera no es nuestra estrategia, es la resolución del tick.

### Y encima, las comisiones

La doc oficial confirma la fórmula (idéntica a la del código del cliente,
`fees.adjust_buy_amount_for_fees`):

```
fee = C × feeRate × p × (1 - p)      # C = nº de shares, p = precio
```

- **Solo paga el taker. Los makers nunca pagan comisión.**
- `feeRate` depende de la categoría:

| Categoría | Taker fee rate | Maker fee | Maker rebate |
|---|---|---|---|
| Crypto | 0.07 | 0 | 20% |
| Sports | 0.05 | 0 | 15% |
| Finance / Politics / Mentions / Tech | 0.04 | 0 | 25% |
| Economics / Culture / Weather / Other | 0.05 | 0 | 25% |
| **Geopolitics** | **0** | 0 | — (sin fee) |

Verificado en vivo: un mercado Crypto devuelve `fd: {r: 0.07, e: 1, to: true}`
(rate 0.07, exponente 1, taker-only).

**Consecuencia directa sobre el `MIN_EDGE = 0.018` del prompt:** es un número
fijo para un costo que no es fijo. El costo real de cruzar el spread en las dos
patas es `2 × rate × p(1-p)`:

| Precio | Costo del par (Crypto, 0.07) | Costo del par (Politics, 0.04) |
|---|---|---|
| 0.50 | **7.0%** | 4.0% |
| 0.25 | 5.3% | 3.0% |
| 0.10 | 2.5% | 1.4% |
| 0.02 | 0.55% | 0.31% |

Con `MIN_EDGE` fijo en 1.8% el bot habría aprobado como "rentables" operaciones
que pierden 5 puntos en el centro del libro. En la práctica da igual, porque no
hay ninguna oportunidad que aprobar — pero muestra que el número salió de la
intuición, no de la fórmula de la plataforma.

### Veredicto

El arb puro se queda como **watcher barato dentro del scanner** (dos restas por
ciclo, coste ~cero), no como tesis central. Si algún día un mercado se descuadra
—típicamente por una resolución rara o una caída de un market maker grande— lo
vemos y lo tomamos. Construir tres módulos y arriesgar $500 alrededor de eso, no.

---

## 3. Lo que sí es real: el lado maker

Aquí es donde hay dinero medible, y son **dos programas independientes que se
cobran a la vez**:

### 3.1 Maker Rebates (financiado por las fees de los takers)

- Se paga **diario en pUSD**, mínimo acumulado **$1** para que haya pago.
- Se cobra **solo cuando tu orden pasiva es tomada** (te ejecutan).
- Reparto ponderado por la misma curva de fees:
  `rebate = (tu_fee_equivalent / total_fee_equivalent) × pool`, **por mercado**.
- `fee_equivalent = C × feeRate × p × (1-p)` — es decir, **el rebate es máximo
  cerca de p=0.50 y en categorías con rate alto (Crypto 0.07)**.

Esto tiene una implicación de estrategia que no estaba en el prompt: **cotizar
cerca de 50¢ en Crypto paga más rebate por share ejecutado que cotizar en las
colas**, aunque el riesgo direccional también sea mayor ahí.

### 3.2 Liquidity Rewards (órdenes en reposo, aunque no te ejecuten)

- Se pagan **diario a las 00:00 UTC**, mínimo **$1**.
- Puntúan las órdenes **descansando** en el libro, no hace falta que se ejecuten.
- Función de puntuación cuadrática: `S(v, s) = ((v - s) / v)² · b`
  donde `v` = max spread configurado del mercado, `s` = tu distancia al midpoint.
  → **estar al doble de distancia te da un cuarto de los puntos.** La tightness
  se paga de forma no lineal.
- Bonifica cotizar los **dos lados**; un solo lado también puntúa pero menos.
- Cada mercado publica su config: `min_size`, `max_spread`, `rewards_daily_rate`.

Medido en vivo: **333 de 400** mercados tienen `rewards_daily_rate ≥ $1/día`.
Muestra de los pools más gordos:

| Pool diario | Spread actual | Mercado |
|---|---|---|
| $200 | 1.0¢ | Fed rate hike in 2026? |
| $134 | 0.1¢ | Will Harry Kane win the 2026 Ballon d'Or? |
| $128 | 0.1¢ | Will J.D. Vance win the 2028 Republican nomination? |
| $116 | 0.1¢ | Will no Fed rate cuts happen in 2026? |
| $100 | 1.0¢ | varios (US strike on Cuba, McConnell, etc.) |

Config típica: `min_size: 20–30` shares, `max_spread: 4.5¢`.

### 3.3 El truco de capital que hay que aprovechar

De la doc de market making: *"comprar NO a 0.48 es económicamente equivalente a
vender YES a 0.52"*. Es decir, **se puede cotizar los dos lados de un mercado
usando solo pUSD, sin inventario de shares**: pones un bid en YES y un bid en NO.
Con $500 eso importa muchísimo — no hay que comprar shares primero para poder
poner asks.

### 3.4 Expectativa honesta con $500

No te voy a vender humo. Con `min_size` de 20–30 shares a precios de ~0.50 son
**$10–15 de capital comprometido por orden**. Con $500 caben del orden de
15–20 órdenes qualifying simultáneas, repartidas en 7–10 mercados.

El reparto es **proporcional a tu share del scoring del mercado**. Si en un
mercado con pool de $100/día hay $200k de profundidad qualifying compitiendo y
tú pones $150, tu parte es del orden de **$0.07/día en ese mercado**. Debajo del
mínimo de pago de $1.

**Por eso la Fase 0 es medir, no codear.** La única pregunta que decide si este
bot vale la pena es: *¿existen mercados con pool decente y poca profundidad
qualifying compitiendo?* Esa pregunta se contesta con datos, gratis, sin
arriesgar un peso — y es exactamente lo que ningún prompt puede contestar.

---

## 4. Errores técnicos concretos a corregir en el código

| # | Problema | Corrección |
|---|---|---|
| 1 | **`signature_type` / `funder` ausentes.** Es el fallo silencioso nº1: si el capital está en el smart wallet de la cuenta y el bot firma con la EOA, el bot ve balance 0 y todas las órdenes rebotan. | Ver §4-bis: la respuesta cambió en mayo de 2026 y merece sección propia. |
| 2 | `cancel_order(order_id: str)` | La firma real es `cancel_order(payload: OrderPayload)`. También existen `cancel_orders`, `cancel_market_orders`, `cancel_all`. |
| 3 | Colateral descrito como **USDC.e** | La doc actual habla de **pUSD** (Polymarket USD). Rebates y rewards se pagan en pUSD. Verificar el flujo de fondeo antes de depositar. |
| 4 | No se menciona `post_only` | `create_and_post_order(..., post_only=True)`. **Imprescindible para MM**: garantiza estatus maker (fee 0 + elegible a rebate) y evita cruzar el spread por accidente. |
| 5 | Tick size y tamaño mínimo hardcodeados/ignorados | Por mercado: `get_tick_size()` devuelve uno de `0.1 / 0.01 / 0.005 / 0.0025 / 0.001 / 0.0001`, y cada mercado publica `minimum_order_size` (visto: 5). Redondear precios al tick o la orden se rechaza. |
| 6 | Sin manejo de reintentos ni deriva de reloj | El propio cliente lo trae: `ClobClient(..., retry_on_error=True, use_server_time=True)`. El segundo evita fallos de HMAC por desfase de reloj. |
| 7 | Sin mención de neg-risk | `get_neg_risk(token_id)`. Los mercados multi-resultado usan otro contrato y otra mecánica; hay que excluirlos explícitamente en la v1. |
| 8 | `/books` sin trocear | Con >~40 tokens por request devuelve `400 Payload exceeds the limit`. Hay que chunkear. |
| 9 | Los tres prompts asumen "auditamos cuando esté hecho" | Escribir 7 módulos antes de saber si hay edge es el orden inverso. Ver plan. |

**Elemento nuevo que ni Grok ni yo teníamos en el radar:** el cliente expone un
sistema **RFQ** completo (`/rfq/request`, `/rfq/quote`, `/rfq/best-quote`) y
endpoints de scoring en vivo (`is_order_scoring`, `are_orders_scoring`,
`get_current_rewards`, `get_earnings_for_user_for_day`). Ese último grupo es oro:
permite **verificar desde el bot si nuestras órdenes están puntuando para
rewards**, en vez de adivinar.

---

## 4-bis. ¿Dónde vive el dinero? (y por qué la respuesta cambió)

Esta era la pregunta abierta del plan. La documentación oficial la contesta, y
el dato importa más de lo que parecía:

| Tipo de wallet | Cuándo aplica |
|---|---|
| **Deposit Wallet** | **Todas las cuentas de Polymarket desplegadas a partir del 4 de mayo de 2026.** |
| Proxy Wallet | *Legacy*: cuentas creadas con Magic Link / Google en polymarket.com |
| Safe Wallet | *Legacy*: cuentas creadas con firmante externo (MetaMask, Rabby) |

Hoy es agosto de 2026. **Una cuenta creada ahora es Deposit Wallet, no hay
opción.** Los proxies y Safes ya no se pueden elegir; solo existen si tu cuenta
es vieja.

Y aquí está el detalle que hay que ver antes de escribir el cliente:

- `py_clob_client_v2.SignatureTypeV2` = `EOA(0)`, `POLY_PROXY(1)`,
  `POLY_GNOSIS_SAFE(2)`, `POLY_1271(3)`. **No tiene Deposit Wallet.**
- El SDK nuevo (`polymarket-client`) usa
  `WalletType = EOA(0) | POLY_PROXY(1) | GNOSIS_SAFE(2) | DEPOSIT_WALLET(3)`.

El entero **3 significa cosas distintas en las dos librerías**. Un bot que mande
`signature_type=3` creyendo "Deposit Wallet" contra la librería vieja estaría
firmando como EIP-1271. Trampa perfecta para perder un fin de semana.

### El flujo moderno

Cuenta en polymarket.com → copiar la **dirección del wallet** del menú de perfil
→ **Settings → API Keys → Relayer API Keys** → crear una, que devuelve un
**Signer Address** y una **API Key**. Con eso:

```python
from polymarket import SecureClient, RelayerApiKey

client = SecureClient.create(
    private_key=os.environ["SIGNER_PRIVATE_KEY"],
    wallet=os.environ["POLYMARKET_WALLET_ADDRESS"],
    api_key=RelayerApiKey(key=..., address=...),
)
```

La Relayer API key **autoriza operaciones de wallet sin gas**. Eso resuelve solo
dos dolores de cabeza: no hay que tener POL para gas, y no hay que mandar las
aprobaciones on-chain a mano.

### Recomendación

**Cuenta creada desde polymarket.com (Deposit Wallet) + Relayer API key**, y para
la capa autenticada de la Fase 1, el SDK nuevo `polymarket-client`.

Los cuatro motivos, en orden de peso:

1. **No es realmente una elección.** Una cuenta nueva hoy es Deposit Wallet.
   Elegir "EOA pura" significa renunciar a la cuenta de Polymarket, no elegir
   otra variante de ella.
2. **Sin gas y sin aprobaciones manuales.** El relayer se encarga. Con una EOA
   pura hay que fondear POL y mandar las aprobaciones de los contratos a mano:
   más piezas que se atoran, y se atoran en producción a las 3 AM.
3. **Kill switch manual gratis.** Las posiciones se ven y se cierran desde la web
   o el celular. Para un bot de $500 corriendo solo, poder matarlo desde el
   teléfono sin SSH vale mucho.
4. **La llave firmante no es la llave del dinero.** El signer firma; los fondos
   viven en el smart wallet. La Relayer API key se revoca y se rota sin mover
   un peso.

Higiene, sin negociar: **cuenta dedicada al bot**, solo el capital de operación
(arrancar con $50, no con $500), la llave únicamente en variables de entorno o
GitHub Secrets, nunca en el repo. `.env` ya está en `.gitignore`.

### Y lo mejor: no bloquea nada

**La Fase 0 no necesita wallet, ni llaves, ni un peso.** Solo lee endpoints
públicos. La decisión de la cuenta se puede tomar tranquilo mientras el
recolector junta datos.

### Pendiente de verificar en la Fase 1

`polymarket-client` publicó su primera versión estable el 22-jul-2026 (0.1.0),
la 0.2.0 el 24-jul y ya iba en 0.3.0b2 el 31-jul. Se mueve **muy** rápido. Por
eso la Fase 0 usa `py-clob-client-v2` (estable, verificado, solo lectura) y la
migración se decide al escribir el cliente autenticado, con una orden de prueba
de $5 antes de cualquier otra cosa.

---

## 5. Lo que ya tenemos en este repo (no arrancamos de cero)

El prompt pedía escribir `config.py`, `client.py`, `risk.py`, `monitor.py`
desde cero. Tres de esos cuatro ya existen aquí, mejores y con tests:

| Lo que pedía el prompt | Lo que ya está en el repo | Estado |
|---|---|---|
| `risk.py` (exposición, PnL diario, kill switch) | **`execution.py`** → `RiskGovernor` + `GovernorConfig` (riesgo/trade, pérdida diaria, máx posiciones, riesgo total, kill switch, halt por drawdown) + `Account` | Ya hace todo lo pedido y más. Solo hay que traducir los topes de $ a fracciones: $35/$500 = 7% por trade, $150/$500 = 30% expuesto, -$35/$500 = -7% diario. |
| Registro de operaciones auditable | **`execution.py`** → `HashLedger` / `DurableHashLedger` / `SqliteHashLedger`, cadena SHA-256 commit-then-reveal | Muy por encima del "in-memory for now" del prompt. |
| Kill switch por deriva del edge | **`reconciler.py`** → integridad de cadena + drawdown diario + drift de expectancy vs backtest (IC bootstrap) | No estaba ni contemplado en los prompts. |
| `monitor.py` (logging estructurado) | **`fq_logging.py`** → una línea JSON por evento con `FQ_JSON_LOGS=1` | Hecho. |
| Alertas Telegram | Infraestructura de Telegram ya en producción (`fq_bot_v3_2.py`, `centinela.py` manda con urllib sin dependencias) | Reutilizable tal cual. |
| Modo paper / DRY_RUN | **`execution.py`** → `PaperBroker`, y **`exchange_adapter.py`** → `CcxtBroker` con `mode="paper"\|"live"` y **la misma interfaz** | El patrón exacto a copiar para el bróker de Polymarket. |
| Backtest de la estrategia | **`bt_engine.py`** ya modela **fills maker** (`maker_entry_fill_mask`, `maker_fee`, TTL de la orden pasiva) + `bt_walkforward.py`, `deflated.py` | Justo lo que hace falta para evaluar market making offline. |
| Despliegue y cron | `launcher.py`, `railway.toml`, `Procfile`, 30+ workflows de GitHub Actions | La Fase 0 se monta sobre esto sin infra nueva. |

**Propuesta de ubicación:** paquete `pm/` dentro de este mismo repo, importando
`execution.RiskGovernor`, `execution.HashLedger`, `reconciler.Reconciler` y
`fq_logging` directamente. Repo aparte = duplicar el gobernador de riesgo y el
ledger, que es justo lo que no queremos volver a escribir.

---

## 6. Plan de trabajo

### Fase 0 — Medir (esta semana, $0 de capital, sin claves)

Un recolector read-only, sin autenticación, corriendo por GitHub Actions cada
5–10 min durante 5–7 días sobre los ~50 mercados con mejor `rewards_daily_rate`.
Registra por muestra: libro completo, midpoint, profundidad dentro de
`max_spread`, y `rewards_daily_rate`.

**Entregables:**
- Profundidad qualifying real que compite en cada mercado.
- Estimación de **nuestro share de rewards** con $500, por mercado, ya
  descontando el mínimo de pago de $1/día.
- Cuántos mercados superan el umbral de rentabilidad → **si son cero, aquí nos
  bajamos y no gastamos ni un peso.** Ese es el punto de la fase.
- De regalo: serie temporal de libros para la Fase 2, y el watcher de arb
  midiendo si alguna vez la suma baja de 1.00.

**Riesgo: cero.** No hay claves, no hay órdenes, no hay dinero.

### Fase 1 — Adaptador y riesgo (solo si la Fase 0 da verde)

- `pm/client.py` — wrapper de `ClobClient` con `signature_type`/`funder`,
  `post_only`, tick size y `minimum_order_size` por mercado, chunking de `/books`,
  `retry_on_error`, `use_server_time`.
- `pm/broker.py` — `mode="paper"|"live"`, misma interfaz, sellando en el
  `HashLedger` que ya existe. Copia del patrón de `exchange_adapter.py`.
- `pm/config.py` — settings + traducción de los topes de $ a fracciones del
  `GovernorConfig` existente.
- **No** se escribe `risk.py`. Se usa `RiskGovernor`.
- Tests con el cliente inyectado (sin red), como ya se hace en el repo.

### Fase 2 — Estrategia contra los datos de la Fase 0

Replay de la política de cotización contra los libros grabados, usando la
maquinaria de fills maker de `bt_engine.py`. Sale una expectativa de
rewards + rebates − pérdida por selección adversa (te ejecutan cuando el precio
se mueve en tu contra: **ese es el costo real del market making**, y es lo que
ningún prompt mencionó).

### Fase 3 — Vivo con $50, no con $500

Un mercado, tamaño mínimo, 2 semanas. El `Reconciler` compara lo vivo contra la
Fase 2. Si no hay drift, se escala gradual. Los $500 completos entran cuando el
track record sellado lo justifique, no antes.

### El arb

Watcher pasivo dentro del scanner desde la Fase 0. Si aparece una oportunidad
real, ya tendremos los datos para saber cuánto dura y si es tomable. Cero
módulos dedicados hasta entonces.

---

## 7. Estado y siguiente paso

| Decisión | Estado |
|---|---|
| ¿Dónde vive el dinero? | **Resuelto** (§4-bis): Deposit Wallet + Relayer API key. No hace falta crearla todavía. |
| ¿Repo aparte o aquí? | **Aquí**, en `pm/`, reusando `RiskGovernor`, `HashLedger` y `Reconciler`. |
| Fase 0 | **Implementada.** `pm/probe.py`, `pm/rewards.py`, `pm/analyze.py` + 44 tests. |

### Cómo correr la Fase 0

```bash
pip install -r pm/requirements.txt

python -m pm.probe --once --top 25          # una muestra, prueba rápida
python -m pm.probe --minutes 20 --top 40    # una corrida normal
python -m pm.analyze --bankroll 500         # el veredicto acumulado
```

En automático lo corre `.github/workflows/pm_probe.yml` cada 3 horas. **Ojo con
la misma trampa de `centinela.yml`: el trigger `schedule` solo dispara desde la
rama por defecto**, así que el cron no arranca hasta mergear a `main`. Mientras
tanto se dispara a mano con `workflow_dispatch` desde cualquier rama.

### Primera foto (25 mercados, una muestra, 2026-08-03)

Una sola muestra no decide nada — el análisis lo dice solo y pide 100
observaciones mínimo. Pero ya se ve la forma del problema:

| Mercado | Pool/día | Profundidad calificada compitiendo |
|---|---|---|
| will-the-us-invade-iran-before-2027 | $1,000 | $633,124 |
| fed-rate-hike-in-2026 | $200 | $142,686 |
| will-the-us-confirm-that-aliens-exist | $100 | $417,755 |
| **will-mitch-mcconnell-resign-from-the-senate** | **$100** | **$5,764** |

Los pools gordos están saturados: con $500 contra $633k nos tocarían ~$0.79/día,
debajo del piso de pago. Pero el de McConnell tiene un pool de $100 con solo
$5.7k compitiendo — ahí $296 de capital estimarían **$5.28/día**. Ese es
exactamente el tipo de mercado que la Fase 0 tiene que encontrar, y la pregunta
que faltan los datos para contestar es si esos huecos **duran** o se llenan en
minutos.

El recolector también trae un guardarraíl que ya se ganó su lugar en el primer
smoke test: un mercado con pool de $30 y libro calificado vacío hacía que el
estimador nos asignara el 100% del pool. Ahora se marca **DUDOSO** y queda fuera
del total. Un pool que nadie reclama casi nunca es un regalo.
