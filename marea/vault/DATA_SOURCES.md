# DATA_SOURCES — qué encontramos al conectar las fuentes reales

Los adapters de agregación están implementados y verificados contra las APIs
públicas vivas de Polymarket (Gamma) y Kalshi. Al medirlos aparecieron tres
hechos que cambian el plan, y quedan aquí porque son de producto, no de código.

Medición del 27 de julio de 2026 (`npm run probe:supply`, `npm run probe:live`).

## Hallazgo 1 — la agregación no trae Latam

| Medición | Resultado |
|---|---|
| Mercados binarios usables en Polymarket (500 pedidos por volumen 24 h) | 500 |
| De ésos, relevantes para Latam | **2** |
| Cuáles | Ambos sobre el liderazgo de Venezuela |
| Kalshi, series curadas de cripto y macro | 214–254 mercados, todos de EE. UU. |
| Títulos en español en el feed agregado (200 mercados) | 6 |

La casa con más liquidez del mundo tiene, en la práctica, cero inventario para
el público que Marea eligió. Agregarla nos da un producto global en inglés:
exactamente lo que `PRODUCT.md` dice que **no** somos.

## Hallazgo 2 — con agregación sola, el Edge es cero

El Edge necesita una lectura propia. La implementación honesta que se puede
sostener sin modelo propio es el consenso entre casas: si la misma pregunta
cotiza en dos lugares, el consenso ponderado por liquidez es mejor estimación
que cualquiera de los dos precios, y la diferencia es un Edge explicable.

**Preguntas emparejadas entre Polymarket y Kalshi: 0 de 544.**

No es un defecto del emparejador —se corrigieron dos errores reales que sí lo
eran: los separadores de millar partían `71,000` en `71` y `000`, y el
clasificador era ciego a los acentos—. Es que las dos casas listan inventarios
distintos: Polymarket va a eventos globales y Kalshi a macro y deportes de
EE. UU. Casi no hay la misma pregunta en las dos.

Consecuencia: sobre la agregación actual, `mareaProbability` queda vacía, el
dominio devuelve `edge: null` y **ninguna card muestra Edge**. El código hace
lo correcto; lo que falta es la lectura.

## Hallazgo 3 — el idioma no es un detalle de presentación

Los títulos llegan en el idioma del venue. Traducirlos en el cliente no es
aceptable para este producto: la pregunta *es* el producto, y una traducción
automática de "Will X close above Y?" arruina justo lo que nos diferencia
—que la pregunta se entienda sin esfuerzo—. Hace falta una capa de traducción
con revisión, no un `translate()`.

## Qué significa esto para el plan

`marca/vision_apuestas_wallet.md` proponía el camino B (integrarse a
Polymarket/Kalshi) como la vía rápida a liquidez. La medición dice que ese
camino da liquidez pero **no da el producto**: ni Latam, ni español, ni Edge.

Lectura honesta de las tres opciones:

1. **Mercados propios de Latam** (camino A del doc de visión, parimutuel).
   Es lo único que entrega las tres cosas. Reabre custodia y regulación como
   bloqueantes, no como pendientes — ver `COMPLIANCE.md`.
2. **Modelo propio de probabilidad** sobre inventario agregado. Devuelve el
   Edge sin crear mercados, pero deja el problema de Latam y de idioma intacto.
3. **Agregación como suministro complementario**: cripto y macro global en
   español curado, junto a mercados propios de Latam. Es la combinación que
   más se parece al producto descrito, y usa los adapters ya construidos.

La recomendación es 3, con 1 como núcleo. Ninguna de las tres se decide desde
el código: es decisión de producto y de marco legal.

**Decidido (27 de julio de 2026): opción 1 como núcleo.** Marea crea sus propios
mercados de Latam con motor parimutuel, arrancando con puntos. La agregación
queda como referencia externa para el Edge de las preguntas que también cotizan
afuera, y como suministro complementario más adelante.

## Estado del código

- `VITE_DATA_SOURCE=aggregated` enciende la agregación real. Funciona hoy.
- El default sigue en `mock` **a propósito**: con datos reales el feed queda en
  inglés y sin Edge, que es peor producto aunque sea dato verdadero.
- Los adapters, el cliente HTTP, el emparejador y el proveedor de consenso
  están cubiertos por pruebas contra payloads reales grabados
  (`tests/fixtures/`), y por dos sondas de red manuales:
  `npm run probe:live` y `npm run probe:supply`.
