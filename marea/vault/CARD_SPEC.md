# CARD_SPEC — medidas de la tarjeta de mercado

Medido el 29 de julio de 2026 en Chromium real a 320, 390 y 430 px de ancho
por 844 de alto con DPR 2, contra el `dist` construido y el servidor propio.
La puerta que verifica esto es `npm run densidad`.

Este documento existe porque la card es el único componente que se ve 29 veces
en una pantalla: un píxel de más se multiplica, y una envoltura de texto se ve
veintinueve veces.

---

## El problema que resuelve

Con los dos lados a la vista (R-063) la card pasó de 196 px a 214 px y la fila
de decisión dejó de caber en 390 px. Medido antes del cambio:

| Métrica | V5 | Presupuesto | V6 medido |
|---|---|---|---|
| Cards visibles enteras (lista) | 4 | ≥ 4 | **6** |
| Cromo antes del primer producto | 119 px | ≤ 130 px | **111 px** |
| Banda de destacados | no existía | ≤ 200 px | **167 px** |
| Nodos de texto envueltos (8 cards) | 0 | 0 | **0** |
| Alto de card `default` | 159 px | ≤ 148 px | **143 px** |
| Alto del documento (29 mercados) | 4 566 px | — | **4 417 px** |

A 320 px y a 430 px las envolturas de texto también quedan en cero.

**A 320 px la card mide 177 px en vez de 143, y está bien.** La fila de
decisión envuelve en dos líneas porque el contenido real —`61%` en 44 px, su
etiqueta y su pago, dos veces— pide unos 310 px y el ancho interior es 292. La
alternativa sería recortar un número, y el número no se toca (R-063). Siguen
entrando 4 cards enteras, así que la densidad no se pierde: se paga con alto,
no con información.

Los escudos desaparecen por debajo de 360 px (`angosto:`). Son adorno, y el
adorno es lo primero que se va cuando la fila de badges empieza a envolver.

La envoltura no se detecta comparando `scrollWidth` con `clientWidth`: un texto
que salta de línea **crece en alto, no en ancho**. Se mide comparando el alto
del nodo contra su propio `line-height`. La comprobación ingenua da cero
siempre, y por eso el defecto vivió tanto.

---

## Anatomía, de arriba abajo

```
┌─────────────────────────────────────────────┐
│ [CRIPTO] [LIVE] [HOT]              [LATAM]  │  fila 1 · 18 px
│ ¿Pregunta del mercado en dos líneas?        │  fila 2 · 2 × 19 px
│ 54%  ⬤ Sí 1.8×  │  46%  ⬤ No 2.11×          │  fila 3 · 44 px
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │  fila 4 ·  3 px
│ Pozo 2,240 pts · 3 jugando · Cierra en 4 d  │  fila 5 · 14 px
└─────────────────────────────────────────────┘
```

| Zona | Medida |
|---|---|
| Padding de la card | 8 px arriba/abajo, 14 px a los lados |
| Separación entre filas | 2 px |
| Separación entre cards | 8 px |
| Radio | 18 px |

La suma: `16 + 18 + 38 + 44 + 3 + 14 + 4×2 = 141`, más 2 px de borde = **143 px
medidos**. El suelo aritmético con la probabilidad en 44 px (R-004) y el
título en dos líneas está en 141: bajar de ahí exige romper uno de los dos, y
ninguno se paga por densidad.

### Fila 1 — categoría y urgencia

- **La categoría abre la fila**, en píldora con relleno de su propio acento:
  `color-mix(in srgb, --acento 14%, --panel)` de fondo y el acento puro en el
  texto. Antes era un punto de 6 px con la palabra en `muted` a la derecha —
  el sistema de color existía y no se veía, y de ahí venía casi toda la
  sensación de feed plano.
- Sigue llevando **palabra y forma** además del color (R-005). La forma cubre
  a quien no distingue rojo de verde.
- El tinte del 14 % no es de gusto: por encima del 18 % el texto del acento
  deja de pasar 4.5:1 sobre su propio relleno en el tema claro. Lo verifica
  `tests/contrast.test.ts` sobre los cinco acentos y los dos temas.
- `otros` no lleva relleno. Es la única categoría cuyo color es `--muted`, que
  no es un acento sino la ausencia de uno, y medido da 4.02:1 — por debajo de
  AA. La categoría que significa "sin señal clara" no puede gritar como las
  que sí dicen algo.
- LIVE y HOT también van con relleno; LATAM y el país, sólo con borde. Si los
  cinco tonos se pintan igual, ninguno significa urgencia.
- Alto de badge: **18 px fijos con `leading-none`**. Con el interlineado por
  defecto medían 23, y cinco píxeles repetidos 29 veces son media card.
- Como mucho **tres** piezas antes del país. La cuarta hace envolver a 320 px.

### Escudos

Los escudos **salieron de la fila de badges y se pegaron a su resultado**. Dos
escudos sueltos arriba a la izquierda no decían de quién eran, y la decisión
que la card ayuda a tomar es "¿de qué lado me pongo?" — el lado se lee abajo.

- 20×20 px, junto a la etiqueta del resultado que nombra a ese equipo.
- El vínculo se busca por nombre dentro de la etiqueta, sin acentos y en
  minúscula: `Gana el América` casa con `América`. Si no hay coincidencia
  clara —`Empatan`, `4 o más goles`— **no se pinta nada**: mejor un hueco que
  colgarle a un resultado el escudo del equipo equivocado.
- Sin monograma de relleno. Una inicial en un círculo junto a `Sí` no es
  información, es ruido con forma de avatar. Y no se genera ninguna cara.
- `width`/`height` explícitos y `loading="lazy"`: una imagen sin dimensiones
  reserva cero y empuja el layout cuando llega. Lo verifica la puerta.

### Fila 2 — la pregunta

- 15 px, peso 600, `line-height` **declarado en píxeles: 19**. Con
  `leading-tight` medía 22.5 px por línea y no los 18.75 que promete el 1.25:
  dentro de un `-webkit-box` el interlineado se resuelve contra las métricas
  de la serif, no contra el múltiplo. Declararlo en píxeles quitó 7 px de
  card y la sorpresa.
- `line-clamp: 2`. Dos líneas es el techo: con tres, la card no baja de 150 px.
- Es el único nodo al que se le permite ocupar dos líneas.

### Fila 3 — la decisión (la que se rompía)

Es una sola línea con dos grupos, uno por resultado. **Nunca envuelve.**

- Probabilidad: token `text-prob` (44 px), peso 600, `tabular-nums`. Es el nodo
  dominante y **no se toca**: cambiarlo rompería `tokens.lock.json` y, sobre
  todo, la jerarquía — la densidad no se compra degradando la jerarquía
  (R-004). El `%` va como superíndice a 0.4em.
- Etiqueta y pago en la **misma línea** que la probabilidad, no debajo:
  `Sí 1.8×`, 12 px, peso 600.
- La palabra `paga` se va. Cuesta cuatro caracteres en la línea más apretada y
  no dice nada que `1.8×` no diga ya. En el detalle, donde hay ancho, se queda.
- Etiqueta larga (`Gana el América`, `4 o más goles`) → `text-overflow: ellipsis`
  sobre `min-width: 0`. Se corta el texto, nunca se envuelve ni se corta el
  número.
- Los dos grupos van en `flex` con `gap: 10px` y `min-width: 0` en cada uno,
  que es lo que permite al `ellipsis` funcionar dentro de un flex.

Con N resultados se muestran **los dos más probables** con la misma forma, y el
resto se lee en el detalle. Dos grupos siempre: la fila tiene ancho para dos y
para dos nada más.

### Fila 4 — meta

- 11 px, color `muted`, **una sola línea**, `white-space: nowrap` con
  `text-overflow: ellipsis`.
- Orden: `Pozo <monto> · <N> jugando · Cierra <cuándo>`. Se cuentan **personas
  distintas**, no apuestas: veinte apuestas de una sola persona no son un
  mercado, y R-059 ya anula ese caso al liquidar. Si no cabe, se corta por el final —
  el pozo importa más que el cierre.
- La `d` huérfana de `Cierra en 4 d` salía de dejar que este nodo envolviera.

---

## Cromo del feed

| Elemento | V5 | V6 |
|---|---|---|
| Header | 57 px | 57 px (sin tocar) |
| Tira de categorías | 50 px | 54 px |
| **Cromo antes del primer producto** | **119 px** | **111 px medidos** |
| Banda de destacados | no existía | 167 px (producto, no cromo) |

- La tira de categorías lleva un degradado en el borde derecho y deja medio
  chip asomando: tiene que verse que hay más. El chip activo va con relleno
  sólido, no con tinte — una fila donde el elegido apenas se distingue obliga
  a leerlos todos para saber qué filtro está puesto.
- **El carrusel no cuenta como cromo.** Cromo es lo que hay que atravesar para
  llegar al producto; el carrusel *es* producto, y meterlo en ese presupuesto
  habría obligado a elegir entre tenerlo y respetar el tope. Tiene su propio
  techo (200 px) y se mide aparte.
- Por la misma razón, las cards enteras se cuentan **desde el primer mercado**
  y no desde el borde de la pantalla: la banda de destacados se recorre una vez
  y se va, y contarla haría que un carrusel más alto se leyera como lista menos
  densa. Lo que ese presupuesto protege es el ritmo del feed.
- Los encabezados `Hot ahora` y `Todos los mercados` se fueron con la lista
  continua. El feed se agrupa por categoría y cada bloque se nombra con la
  suya, con el número de mercados y un `›` que filtra. El chevron no es
  adorno: un `›` que no lleva a ningún lado enseña a no tocar los encabezados,
  y esa lección después cuesta.

---

## Lo que no se negocia

- La probabilidad es el único nodo en escala `text-prob` (R-004). Ganar
  densidad encogiéndola es mover el problema, no resolverlo.
- Los dos lados se ven, cada uno con su probabilidad y su pago (R-063).
  Comprimir no es amputar: se corta la etiqueta, nunca el número ni el lado.
- Jugando con puntos no aparece símbolo de moneda, tampoco en la card (I7).
- Target táctil ≥ 44×44 pt: la card entera es un solo target, así que su alto
  mínimo lo cumple de sobra.

---

## La puerta de densidad, por dentro

`scripts/densidad.mjs`. Chromium real contra el servidor real: jsdom no tiene
layout, no mide alturas y no sabe que una etiqueta cae en dos líneas a 390 px.

### Qué mide y con qué presupuesto

| Métrica | Presupuesto | Cómo se mide |
|---|---|---|
| Cards enteras en la lista | ≥ 4 a 390 px | `getBoundingClientRect()`, contando desde el primer mercado |
| Cromo antes del producto | ≤ 130 px | `top` del carrusel, o de la primera card si no hay |
| Banda de destacados | ≤ 200 px | alto del carrusel con sus puntos |
| Alto **por variante** | ver tabla | el **máximo** de cada `data-variant` en pantalla |
| Nodos de texto envueltos | 0 | tapas distintas de `Range.getClientRects()` |
| Probabilidad | ≥ 30 px | `fontSize` computado |
| Esqueleto vs card | ± 2 px | alto y hueco de los dos |
| Imágenes | 0 sin medidas, 0 sin `lazy` | atributos del `img` |

### El techo por variante

Antes la puerta medía **sólo la primera card**. Una card normal gorda pasaba
escondida detrás del promedio, que es exactamente el agujero que un tope
global no ve. Ahora cada tipo declara su techo y lo defiende solo, y el fallo
dice qué tipo y cuánto se pasó.

| Variante | ≥ 360 px | < 360 px | De dónde sale |
|---|---|---|---|
| `default` | 148 | 182 | 143 medidos + margen de una línea de meta |
| `edge` | 166 | 200 | +18: el badge de Edge puede caer a una segunda línea |
| `live` | 148 | 182 | su badge cabe en la fila 1, no añade filas |
| `compact` | 130 | 164 | −19: el título va clampeado a una línea |

Dos tablas y no una con excepciones: a 320 px la fila de decisión **envuelve
por diseño** —el contenido pide ~310 px y el ancho interior es 292, y
comprimir no es amputar (R-063)—, así que cada clase de ancho declara lo suyo.

### Qué pasa cuando se viola

`process.exit(1)` con la lista de fallos y `verdict: FAIL`. Es una puerta, no
un aviso: `npm run ci` no la corre —necesita servidor levantado— pero un
cambio de spacing que la rompa se ve en la primera ejecución, con el número
exacto y el tope contra el que chocó.

### Reglas para moverla

1. Nunca subir un techo sin medición y sin razón escrita aquí.
2. Después de cualquier cambio de padding, gap, tipografía o filas: reconstruir,
   volver a medir y reportar los nuevos números por variante.
3. Si el esqueleto deja de medir lo que la card, se arregla el esqueleto — no
   se afloja la tolerancia.
4. Legibilidad antes que densidad extrema. El objetivo es "denso como Kalshi y
   todavía cómodo", no "lo más apretado que aguante el gate".

### Cómo se detecta una envoltura

Ni con `scrollWidth` ni dividiendo alto entre `line-height`. Las dos fallan y
las dos fallaron aquí:

- `scrollWidth`: un texto que salta de línea **crece en alto, no en ancho**. La
  comprobación ingenua da cero siempre, y por eso el defecto vivió tanto.
- `alto / line-height`: en cuanto un badge lleva alto fijo y `leading-none`
  —18 px de caja para 11 px de línea— la división da 1.6 y redondea a dos.
  Marcaba "HOT" y "LATAM" como envueltos sin que nada envolviera.

Se cuentan las **tapas distintas** de `Range.getClientRects()`. Una caja por
fragmento de texto, agrupadas por `top`: la fila de meta se arma con tres
expresiones —pozo, participantes, cierre— y daba tres cajas en una sola línea.

---

## Cómo se verifica

```bash
npm run build
PORT=8100 npx tsx server/index.mts &
npm run densidad
```

Mide a 320, 390 y 430 px. El presupuesto de densidad se exige a 390; en 320 se
exige que el texto no se rompa, que es lo que de verdad se degrada al estrechar.
