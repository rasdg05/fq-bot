# MODEL — la lectura propia de Marea

El Edge necesita una probabilidad nuestra, independiente del pozo. Este doc
dice qué modelo construimos, qué mide, y por qué **hoy no se muestra**.

## Qué es

Para preguntas de precio con umbral —"¿BTC cierra la semana arriba de 71,000?",
"¿el dólar cierra abajo de 19 pesos?"— la probabilidad sale de tres datos
públicos: el precio de hoy, la volatilidad de los últimos 30 días y los días
que faltan. Supuesto lognormal sin deriva: no pronosticamos dirección, sólo
medimos cuánto espacio hay entre el precio y el umbral en relación al
movimiento típico del activo.

Es una cuenta que cualquiera puede rehacer. No es una señal ni una opinión.

Para preguntas que no son de precio —"¿Banxico baja la tasa?", "¿un equipo
brasileño gana la Libertadores?"— este modelo no dice nada, y decir que sí
sería inventar.

## Qué se midió

`npm run calibrate` contra 721 velas diarias de BTC-USD y ETH-USD (Kraken),
28,308 predicciones, horizontes de 7/14/30 días y umbrales de ±10 % alrededor
del precio. Partición temporal **por activo**: el 70 % más viejo de la historia
de cada uno para ajustar, el 30 % más nuevo para medir.

| | Error de calibración (fuera de muestra) | Brier | ¿Sirve? |
|---|---|---|---|
| Cierre | 5.86 pp crudo · 6.28 pp recalibrado | 0.206 | **No** |
| Toca | 10.47 pp crudo · 7.63 pp recalibrado | 0.131 | **No** |
| Máximo admisible | 2 pp | | |

Dentro de muestra el modelo de cierre daba 2.38 pp, que parecía publicable.
Fuera de muestra da 5.86 pp. **Esa diferencia es el hallazgo.**

## Por qué falla

El sesgo es casi siempre negativo: el modelo dice "arriba" más seguido de lo
que pasa. Un modelo sin deriva aplicado a un tramo de historia con tendencia
tiene que fallar en esa dirección, y el tramo de prueba fue justo eso. La cola
lo muestra crudo: en el tramo 90-100 % predice 94.9 % y ocurre el 72 %.

El de "toca" está peor. El principio de reflexión —duplicar la probabilidad
terminal— supone monitoreo continuo y cero deriva; contra precios reales
sobreestima entre 3 y 32 pp según el tramo.

La recalibración de Platt no lo arregla: dos parámetros ajustados en un régimen
no transfieren a otro. Eso también es información.

## Por qué no se muestra

El Edge aparece a partir de 4 pp. Un modelo que se equivoca 6 pp en promedio
haría que **el Edge fuera más error del modelo que señal**. Mostrarlo sería
exactamente lo que la marca dice no hacer.

La puerta está en el código, no en este documento: `isUsable()` compara el
error medido contra `MAX_USABLE_ECE_PP`, y `createPriceModelProvider` devuelve
`null` mientras no pase. Con la calibración congelada en
`vault/calibration.lock.json`, hoy devuelve `null` (R-031).

Para abrir la puerta hay que **bajar el error medido**, no bajar el umbral.

## Qué intentar después, en orden

1. **Volatilidad implícita en vez de realizada.** La realizada mira atrás; el
   mercado de opciones ya cotiza lo que espera. Para BTC y ETH hay superficie
   pública; para el peso mexicano, en el mercado de opciones OTC.
2. **Deriva del basis de futuros.** El futuro perpetuo ya contiene la deriva
   que el modelo asume en cero. Es un dato, no un pronóstico.
3. **Historia más larga, con varios regímenes.** Dos años son un régimen y
   medio. Con seis a ocho años el ajuste no queda pegado a la última tendencia.
4. **Calibración por horizonte.** 7 y 30 días no se comportan igual y hoy
   comparten un solo par de parámetros.
5. **Distribución de colas gruesas** (t de Student) en vez de la normal, que es
   donde el error se concentra.

Ninguno es especulativo: los cinco son medibles con el mismo `npm run
calibrate` que produjo esta tabla. El criterio de éxito está fijado de
antemano: error fuera de muestra ≤ 2 pp.

## Mientras tanto

El Edge sigue existiendo donde hay una lectura independiente de verdad: las
preguntas que también cotizan en una casa global. Ahí la lectura es de ella y
el copy la nombra (R-027). En los mercados de Latam puro no hay Edge, y eso se
ve en el producto como ausencia, no como un número inventado.
