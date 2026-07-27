# Marea — app de mercados de predicción

Mobile-first, español Latam. El diferenciador es el **Edge visible**: la
probabilidad del mercado y la de Marea, lado a lado, cuando la diferencia
supera 4 puntos porcentuales.

```bash
npm install
npm run dev        # desarrollo
npm run build      # build de producción
npm run test       # pruebas
npm run validate   # VALIDATION_REPORT (V1–V24 + red-team)
```

## Cómo está armado

```
src/
  domain/      contratos y reglas: Market, Position, Wallet, AppError, regla de Edge
  adapters/    marketData · wallet · analytics · errorReporter (mock intercambiable)
  state/       store único (reducer + acciones) con adapters inyectables
  components/  primitivas de UI y piezas compartidas
  screens/     una pantalla por destino + hojas (depósito, post-operación)
  styles/      tokens.css — la única fuente de color y tipografía
  lib/         strings (todo el copy), flags, formato
vault/         PRODUCT · VOICE · PLAYBOOKS · RULINGS · tokens.lock.json
scripts/       validate.mjs (suite V) · shots.mjs (capturas móviles)
```

Reglas estructurales: UI ≠ datos ≠ wallet ≠ analítica ≠ errores. Las pantallas
sólo hablan con el store; el store sólo habla con los adapters.

## Qué es real y qué es simulado

Declarado en `src/lib/flags.ts`:

| Flag | Valor en esta build | Qué significa |
|---|---|---|
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

## Vault

`vault/RULINGS.md` es append-only: cada corrección de audit que sea de producto
o recurrente se vuelve una regla permanente. Violar una regla existente es un
hallazgo crítico automático, no una discusión.
