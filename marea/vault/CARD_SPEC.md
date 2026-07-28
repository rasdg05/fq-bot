# CARD_SPEC — medidas de la tarjeta de mercado

Medido el 28 de julio de 2026 en Chromium real a 390×844 con DPR 2, contra el
`dist` construido y el servidor propio. La puerta que verifica esto es
`npm run densidad`.

Este documento existe porque la card es el único componente que se ve 29 veces
en una pantalla: un píxel de más se multiplica, y una envoltura de texto se ve
veintinueve veces.

---

## El problema que resuelve

Con los dos lados a la vista (R-063) la card pasó de 196 px a 214 px y la fila
de decisión dejó de caber en 390 px. Medido antes del cambio:

| Métrica | Antes | Presupuesto | Medido después |
|---|---|---|---|
| Cards visibles enteras | 2 | ≥ 4 | **4** |
| Cromo antes del primer mercado | 179 px | ≤ 130 px | **119 px** |
| Nodos de texto envueltos (8 cards) | 24 | 0 | **0** |
| Alto de card | 214 px | — | **159 px** |
| Alto del documento (29 mercados) | 6 631 px | — | **4 688 px** |

A 320 px y a 430 px las envolturas de texto también quedan en cero.

**A 320 px la card mide 193 px en vez de 159, y está bien.** La fila de
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
│ [badges]                        categoría   │  fila 1 · 18 px
│ ¿Pregunta del mercado en dos líneas?        │  fila 2 · 2 × 21 px
│ 54%   Sí 1.8×  │  46%   No 2.11×            │  fila 3 · 34 px
│ Pozo 2,240 pts · Cierra en 4 d              │  fila 4 · 15 px
└─────────────────────────────────────────────┘
```

| Zona | Medida |
|---|---|
| Padding de la card | 12 px arriba/abajo, 14 px a los lados |
| Separación entre filas | 6 px |
| Separación entre cards | 8 px |
| Radio | 16 px |

### Fila 1 — badges y categoría

- Marca de categoría: punto de 6 px con **color y forma** propios por
  categoría, con la palabra al lado. El color nunca es el único portador
  (R-005), y la forma cubre a quien no distingue rojo de verde.
- Escudos de los equipos, 22×22 px, sólo en mercados de futbol y sólo desde
  360 px de ancho. `width`/`height` explícitos y `loading="lazy"`: una imagen
  sin dimensiones reserva cero y empuja el layout cuando llega.
- Alto de badge: 18 px. Texto 10 px, peso 700, mayúsculas, `tracking` 0.04em.
- Como mucho **dos** badges antes de la categoría. El tercero se descarta:
  con HOT, LATAM y el país la fila se come el ancho y empuja la categoría.
- La categoría va a la derecha, 11 px, color `muted`.

### Fila 2 — la pregunta

- 15 px, peso 600, `line-height` 1.35 → 21 px por línea.
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

| Elemento | Antes | Ahora |
|---|---|---|
| Header | 57 px | 57 px (sin tocar) |
| Tira de categorías | 56 px | 50 px |
| Encabezado `Hot ahora` | 36 px | 0 px (sólo lector) |
| **Total antes del primer mercado** | **179 px** | **119 px medidos** |

- La tira de categorías lleva un degradado de 24 px en el borde derecho y deja
  medio chip asomando: tiene que verse que hay más.
- El primer encabezado de sección se queda para el lector de pantalla
  (`sr-only`) y desaparece de la pantalla: el badge HOT de cada card ya dice lo
  mismo, y 36 px son un quinto de un mercado. El segundo (`Todos los mercados`)
  sí se ve, en 12 px y mayúsculas: ahí sí separa dos bloques distintos.

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

## Cómo se verifica

```bash
npm run build
PORT=8100 npx tsx server/index.mts &
npm run densidad
```

Mide a 320, 390 y 430 px. El presupuesto de densidad se exige a 390; en 320 se
exige que el texto no se rompa, que es lo que de verdad se degrada al estrechar.
