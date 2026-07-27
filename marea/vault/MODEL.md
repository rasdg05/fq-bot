# MODEL — la lectura propia de Marea

El Edge necesita una probabilidad independiente del pozo. Este doc dice qué
modelo propio construimos, qué mide, y por qué **no se usa**.

> **Decisión tomada (27 de julio de 2026).** El Edge sale **sólo de referencia
> externa**: el precio de la misma pregunta en una casa global con liquidez.
> El modelo propio queda como investigación, con su banco de pruebas, hasta
> que baje de 2 pp (R-038). No es una espera pasiva: la superficie de
> volatilidad por vencimiento ya se está guardando a diario para poder
> recalibrarlo — ver `data/iv/README.md`.

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

`npm run calibrate` contra 721 velas diarias de BTC-USD y ETH-USD (Kraken) más
el índice DVOL de Deribit, horizontes de 7/14/30 días y umbrales de ±10 %
alrededor del precio. Evaluación **walk-forward** de 5 pliegues con ventana
expansiva: cada bloque se prueba con parámetros ajustados sólo con lo anterior.
17,430 predicciones fuera de muestra.

### El resultado

| Configuración (preguntas de cierre) | Error agrupado fuera de muestra |
|---|---|
| Volatilidad realizada, normal | 3.49 pp |
| **Volatilidad implícita, colas t(12)** | **3.29 pp** |
| Máximo admisible | 2 pp |
| | **No pasa** |

Por horizonte, con la mejor configuración: 7 días 2.97 pp · 14 días 3.33 pp ·
30 días 4.74 pp. Ninguno pasa por separado.

Para preguntas de "toca" lo mejor es 6.24 pp con colas t(4). Muy lejos.

### De dónde vino cada mejora

Partimos de 6.28 pp. Atribución honesta de la bajada:

| Cambio | Aporte |
|---|---|
| Arreglar la medición (agrupar regímenes, quitar Platt) | −2.79 pp |
| Volatilidad implícita en vez de realizada | −0.18 pp |
| Colas de t de Student sobre lo anterior | −0.02 pp |

**La volatilidad implícita ayudó poco.** Casi toda la mejora vino de medir
bien, no de modelar mejor. Decir que "la implícita bajó el error de 6.28 a
3.29" sería cierto en la aritmética y falso en la causa.

## Por qué falla

Dos cosas, y ninguna es la volatilidad.

**Régimen.** El sesgo es casi siempre en una dirección: el modelo dice "arriba"
más seguido de lo que pasa. El tramo de ajuste subió 58 % (BTC) y 27 % (ETH);
el de prueba cayó 26 % y 35 %. Un modelo sin deriva medido en una ventana
direccional falla ahí por construcción — y **agregarle deriva sería apostar
dirección**, que es justo lo que no hacemos. Por eso la medición correcta
agrupa subidas y bajadas en lugar de promediar pliegues cortos: medido por
pliegues de tres meses el error sube a 14.5 pp, pero eso mide si adivinamos la
tendencia del trimestre, no si estamos calibrados.

**Plazo.** DVOL es un índice a 30 días constantes, y nuestras preguntas vencen
a 7, 14 y 30. Usar una volatilidad de 30 días para una pregunta de 7 es un
desajuste de plazo, y se nota: con volatilidad realizada el horizonte de 7 días
sale mejor (2.78 pp) que con implícita (2.97 pp), mientras que a 14 y 30 días
gana la implícita. La superficie histórica por vencimiento no está en ningún
endpoint público simple.

El escalado de Platt **empeora**: 3.49 pp crudo → 6.22 pp corregido. Dos
parámetros ajustados en un régimen no transfieren a otro. Quedó desactivado en
el lock (`a=1, b=0`) y la herramienta sólo lo aplica si mejora (R-034).

## Por qué no se muestra

El Edge aparece a partir de 4 pp. Un modelo que se equivoca 6 pp en promedio
haría que **el Edge fuera más error del modelo que señal**. Mostrarlo sería
exactamente lo que la marca dice no hacer.

La puerta está en el código, no en este documento: `isUsable()` compara el
error medido contra `MAX_USABLE_ECE_PP`, y `createPriceModelProvider` devuelve
`null` mientras no pase. Con la calibración congelada en
`vault/calibration.lock.json`, hoy devuelve `null` (R-031).

Para abrir la puerta hay que **bajar el error medido**, no bajar el umbral.

## Qué queda por intentar

Ya se probaron y quedaron en el código: volatilidad implícita, colas gruesas,
evaluación walk-forward, y descartar el escalado de Platt. Lo que falta:

1. **Volatilidad implícita del plazo que corresponde**, no el índice a 30 días.
   Es el desajuste más claro que quedó. La superficie por vencimiento no está
   en un endpoint público histórico: hay que empezar a guardarla a diario desde
   hoy, o pagar por historia. Es la apuesta con más probabilidad de mover la
   aguja, y es la que no se puede hacer en una tarde.
2. **Más activos y más historia.** Dos activos y dos años son, en la práctica,
   un régimen y medio. El error agrupado sobre seis u ocho años y una decena de
   activos diría mucho más que este.
3. **Aceptar que 2 pp puede ser inalcanzable** para un modelo sin deriva a este
   tamaño de muestra, y decidir el producto en consecuencia: subir el umbral de
   Edge por encima de 4 pp para que el error del modelo sea una fracción chica,
   o dejar el Edge sólo donde hay referencia externa. Es decisión de producto,
   no de ingeniería.

Lo que **no** se va a intentar: agregar una deriva ajustada a la historia
reciente. Bajaría el error medido y sería una apuesta direccional disfrazada de
calibración.

## Cómo funciona el Edge hoy

La referencia externa está enchufada en producción: al listar mercados, el
adapter propio consulta Polymarket y Kalshi y empareja las preguntas que
existen en las dos partes. Donde hay pareja, hay Edge, y el copy nombra a quien
da la lectura (R-027). Donde no la hay —la mayoría del catálogo de Latam— no
hay Edge, y se ve como ausencia, no como un número inventado.

Tres reglas de la referencia, todas probadas:

- **Se refresca sola**, con caché corta para no golpear los venues en cada
  listado.
- **Si el venue se cae, el Edge se apaga.** No se muestra la referencia previa:
  un precio viejo presentado como fresco es peor que ninguno.
- **Nunca rompe el feed.** Un fallo de referencia se reporta y los mercados
  siguen listándose sin Edge.

`npm run validate` verifica que el modelo de precio no esté enchufado al camino
de producción y que la referencia sí lo esté — si alguien enchufa el modelo por
distracción, la validación falla.
