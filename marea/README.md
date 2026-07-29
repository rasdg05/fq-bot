# Marea — app de mercados de predicción

Mobile-first, español Latam. El diferenciador es el **Edge visible**: la
probabilidad del mercado y la de Marea, lado a lado, cuando la diferencia
supera 4 puntos porcentuales.

**Antes de lanzar**, lee [`vault/SOFT_LAUNCH.md`](vault/SOFT_LAUNCH.md): qué
está listo, qué se automatizó y qué hace falta de tu parte.

**Para publicar:** `npm run deploy`. Todo corre desde tu máquina, sin CI —
el runbook completo está en [`vault/LANZAMIENTO.md`](vault/LANZAMIENTO.md).

```bash
npm install
npm run dev          # desarrollo
npm run ci           # tipos + validación + build (lo que haría un CI)
npm run deploy       # verifica, construye y publica
npm run settle       # liquida los mercados que ya resolvieron y autoriza el pago
npm run roll         # repone el catálogo con los mercados de la semana
npm run daily        # las tres tareas de mantenimiento, en orden
npm run cron:install # y que corran solas cada hora
npm run build        # build de producción
npm run test         # pruebas
npm run validate     # VALIDATION_REPORT (V1–V24 + red-team + S1/T1/C1)
npm run perf         # medición de rendimiento en laboratorio (necesita `vite preview`)
npm run probe:live   # sonda contra las APIs reales de los venues
npm run probe:supply # mide la oferta real de mercados relevantes
npm run calibrate    # calibra el modelo de precio contra historia real
```

## Cómo está armado

```
src/
  domain/      contratos y reglas: Edge, liquidación, probabilidad, elegibilidad, país
  adapters/    puertos + implementaciones: mock, agregación real, sinks HTTP
    venues/    Polymarket y Kalshi normalizados a un contrato común
    oracles/   lectura de las fuentes que resuelven los mercados
    ownMarkets/ catálogo propio, plantillas que se reponen y motor de pozo
    wallet/    wallet conectada por el usuario (EIP-1193)
  state/       store único (reducer + acciones) con adapters inyectables
  components/  primitivas de UI y piezas compartidas
  screens/     una pantalla por destino + hojas (depósito, post-operación)
  styles/      tokens.css — la única fuente de color y tipografía
  lib/         strings (todo el copy), flags, formato
vault/         PRODUCT · VOICE · PLAYBOOKS · RULINGS · COMPLIANCE · ESTRATEGIA
               DATA_SOURCES · MODEL · CRYPTO_LIVE · HANDOFF · locks de tokens
scripts/       validate.mjs · settle.mts · roll.mts · daily.mjs · perf.mjs · sondas
```

Reglas estructurales: UI ≠ datos ≠ wallet ≠ analítica ≠ errores. Las pantallas
sólo hablan con el store; el store sólo habla con los adapters.

## Configuración

Todo entra por variables `VITE_*` (ver `.env.example`). Lo que no está
configurado degrada a su camino simulado y la app lo declara — nunca finge
haber hablado con un proveedor (R-022).

| Variable | Efecto |
|---|---|
| `VITE_DATA_SOURCE=aggregated` | Mercados reales de Polymarket + Kalshi |
| `VITE_ANALYTICS_ENDPOINT` | Enciende el sink real de analítica |
| `VITE_ERROR_ENDPOINT` | Enciende el reporter real de errores |
| `VITE_KALSHI_SERIES` | Series curadas; sin ellas Kalshi devuelve combinadas sin liquidez |

Antes de conectar la fuente real, lee `vault/DATA_SOURCES.md`: está medido que
la agregación sola deja el feed en inglés y sin Edge.

## Qué es real y qué es simulado

Declarado en `src/lib/flags.ts`:

| Flag | Valor en esta build | Qué significa |
|---|---|---|
| `market_engine` | `"parimutuel_points"` | Mercados propios de Latam con motor de pozo, jugando con puntos. `parimutuel_money` usa el mismo motor con dinero y exige la puerta de elegibilidad |
| `mock_data` | `true` | Los mercados salen del adapter mock, con el mismo contrato que va a usar la agregación real |
| `deposit_provider` | `"onramp"` | Hay camino de tarjeta y de transferencia; si el proveedor cae, la UI lo dice y deja la transferencia abierta |
| `trade_execution_mode` | `"aggregated"` | La operación se completa en el mercado con más liquidez. Marea **no** es la contraparte, y el copy del detalle lo declara |
| `error_reporting` | `false` | El reporter está desconectado; nada sale del dispositivo |

No hay order book propio, ni market maker, ni custodia propia en esta build.

## Cripto en vivo

Velas de 5 y 15 minutos de BTC y ETH, alineadas al reloj, que nacen y se pagan
solas dentro del servidor. Siempre hay una de cada horizonte abierta por activo.

El spot se lee cada 3 s (motor propio si `MAREA_FQ_PRECIOS_URL` está puesta,
Kraken si no) y **la liquidación siempre lee el cierre de la vela pública de
Kraken**, que es la fuente que cita el criterio. Las decisiones —cierre exacto
en vez de promedio, ventana de disputa de 60 s, y qué pasa con el empate— están
escritas en [`vault/CRYPTO_LIVE.md`](vault/CRYPTO_LIVE.md).

## Validación

`npm run validate` corre las verificaciones de la suite más los 10
escenarios de red-team y emite un `VALIDATION_REPORT` con `passed[]`,
`failed[]` y veredicto. Cuatro checks son estáticos (tokens, lenguaje
prohibido, desbordes, drift del design system); el resto se ejerce contra la
app renderizada.

El contraste de todos los pares texto/superficie se calcula en
`tests/contrast.test.ts`: ningún par baja de 4.5:1 en tema claro ni oscuro.

`scripts/shots.mjs` levanta la build en un viewport de 390×844 y captura el
camino completo, verificando que `scrollWidth === innerWidth` en cada pantalla.

`npm run perf` mide LCP, INP, CLS y TTFB con CPU 4× más lenta y 4G lenta, en
los dos recorridos que importan —usuario nuevo y recurrente—, y falla si algún
presupuesto se rompe. Es medición de laboratorio: detecta regresiones, no
sustituye datos de campo.

## El ciclo de vida de un mercado

Un mercado no es una pantalla: es un ciclo, y los pasos que la gente olvida son
los que rompen la confianza (R-040).

```
se crea → se usa → se cierra → se resuelve → se paga → se repone
  roll      app       app        settle       app       roll
```

`npm run settle` lee la fuente citada de cada mercado cerrado. Lo que se puede
leer por programa —precios— se resuelve solo contra el endpoint público de
Kraken. Lo que publica una institución en un boletín queda marcado como
`atorado`, con la liga a la mano, para que una persona lo confirme: **nunca se
inventa un resultado**. Después viene la ventana de disputa, y sólo cuando
cierra se autoriza el pago.

`npm run roll` escribe los mercados de la semana con el precio de hoy, para que
el feed no se vacíe. La verificación `M1` falla si quedan menos de 6 mercados
abiertos, y `L1` falla si el liquidador lleva más de 36 h sin correr — un
proceso que depende de que alguien se acuerde no existe.

## El Edge y su modelo

El Edge sólo se muestra cuando hay una lectura independiente del precio. Hoy
existe para las preguntas que también cotizan en una casa global; para los
mercados de Latam puro hace falta modelo propio, y el que construimos **no pasa
su propia puerta de calibración** — medido, no supuesto, en `vault/MODEL.md`.

`npm run calibrate` reproduce la medición contra velas diarias públicas. La
puerta se abre bajando el error, nunca bajando el umbral (R-031).

## Vault

`vault/RULINGS.md` es append-only: cada corrección de audit que sea de producto
o recurrente se vuelve una regla permanente. Violar una regla existente es un
hallazgo crítico automático, no una discusión.
