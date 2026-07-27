# VOICE — copy en español (Latam)

Hereda de `marca/cultura_y_tono.md` §5. Este doc es la versión operativa para
la app de mercados de predicción.

## Principios (los cinco, sin cambios)

1. Claro antes que listo.
2. Honesto hasta cuando duele.
3. Calma con autoridad (Marea = mar; no gritamos).
4. Cálido, latino, sin caer en payaso.
5. Muestra el porqué: todo número trae su razón al lado.

## Copy cerrado (no se reescribe sin pasar por AUDIT)

| Superficie | Texto |
|---|---|
| Sección caliente del feed | `Hot ahora` |
| Edge en card | `Marea +X%` |
| Edge en detalle | `Mercado XX% · Marea YY% · Edge +Z%` |
| CTA de fondos | `Depositar` |
| Badge en vivo | `LIVE` |
| Badge de tracción | `HOT` |
| Badge regional | `LATAM` |
| Empty del feed | `No hay mercados calientes en este momento. Vuelve en un rato.` |
| Promesa de onboarding | `Predice. Opera. Con edge.` |
| CTA de arranque | `Empezar` |
| Explorar sin fondos | `Explorar mercados` |

## Prohibiciones duras (violación = hallazgo crítico)

- `copiloto`, `co-piloto`
- `FQ`, `Fibonacci`, `ecuación`, `metodología`, `DSR`, `Deflated Sharpe`
- `garantizado`, `secreto`, `fácil`, `rápido`, `100%`, `señal ganadora`,
  `millonario`, `a un clic de`
- Emojis de cohete / fuego / dinero en copy de producto
- `lorem`, `TODO`, texto de relleno
- Prometer matching nativo, order book propio o market making cuando la
  ejecución es agregación

## Honestidad de ejecución

Si `trade_execution_mode = "aggregated"`, el copy dice que la operación se
completa en el mercado con más liquidez y que Marea no es la contraparte.
Nunca "operamos tu orden" ni "nuestro libro".

## Errores

Siempre en español, sin stack trace, sin código técnico visible como mensaje
principal. Si es reintentable, hay botón `Reintentar`.
