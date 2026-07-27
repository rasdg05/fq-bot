# Marea — app de mercados de predicción

Mobile-first, español Latam. El diferenciador es el **Edge visible**: la
probabilidad del mercado y la de Marea, lado a lado, cuando la diferencia
supera 4 puntos porcentuales.

```bash
npm install
npm run dev          # desarrollo
npm run build        # build de producción
npm run test         # pruebas
npm run validate     # VALIDATION_REPORT (V1–V24 + red-team + S1/T1/C1)
npm run perf         # medición de rendimiento en laboratorio (necesita `vite preview`)
npm run probe:live   # sonda contra las APIs reales de los venues
npm run probe:supply # mide la oferta real de mercados relevantes
```

## Cómo está armado

```
src/
  domain/      contratos y reglas: Edge, errores, probabilidad propia, elegibilidad
  adapters/    puertos + implementaciones: mock, agregación real, sinks HTTP
    venues/    Polymarket y Kalshi normalizados a un contrato común
  state/       store único (reducer + acciones) con adapters inyectables
  components/  primitivas de UI y piezas compartidas
  screens/     una pantalla por destino + hojas (depósito, post-operación)
  styles/      tokens.css — la única fuente de color y tipografía
  lib/         strings (todo el copy), flags, formato
vault/         PRODUCT · VOICE · PLAYBOOKS · RULINGS · COMPLIANCE · DATA_SOURCES · HANDOFF
scripts/       validate.mjs · perf.mjs · shots.mjs · sondas de red
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

## Validación

`npm run validate` corre las 24 verificaciones de la suite más los 10
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

## Vault

`vault/RULINGS.md` es append-only: cada corrección de audit que sea de producto
o recurrente se vuelve una regla permanente. Violar una regla existente es un
hallazgo crítico automático, no una discusión.
