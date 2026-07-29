# FINAL SPECIFICATION

**Marea — rediseño v6 · especificación de producto lista para implementar**
Fecha: 29 de julio de 2026 · Alcance: shell global, sistema de tarjetas, arquitectura de mercados, interacción.
Base medida: `vault/CARD_SPEC.md` (card actual = 159 px), `src/styles/tokens.css`, `tokens.lock.json`.

Esta especificación es de mano a mano: cada medida está en píxeles, cada color es un token que ya existe, y cada regla de mercado dice de qué fuente sale el dato. Donde v6 contradice una decisión previa del repo, la contradicción está declarada en §7 con su archivo.

---

## 0 · Contexto bloqueado (confirmado)

| # | Decisión | Estado |
|---|---|---|
| 0.1 | Identidad: **Marea** · *"Predice. Opera. Con edge."* · logo fuerte · teal/verde elevado · segura y viva | Confirmada |
| 0.2 | Header: logo dominante a la izquierda · `Entrar` / `Crear cuenta` sin sesión · saldo + avatar con sesión | Confirmada |
| 0.3 | Nav inferior: **exactamente 4** — Mercados / Buscar / Portafolio / Perfil | Confirmada · rompe los 5 destinos actuales (§7.1) |
| 0.4 | Tabla de posiciones **sólo dentro de Perfil** | Confirmada |
| 0.5 | Tarjetas: ~30 % más bajas · densas · **resultados con nombre** · barras finas · pills de % grandes con multiplicador · LIVE con marcador | Confirmada |
| 0.6 | Edge de Marea: **no se muestra en la tarjeta**, sólo en el detalle | Confirmada · rompe la card actual (§7.3) |
| 0.7 | Cripto Live: selección **automática del motor** (BTC/ETH + las siguientes monedas soportadas con más señal) | Confirmada |
| 0.8 | Deportes: Liga MX + LMP + MLB selectivo + Tenis selectivo | Confirmada |
| 0.9 | Categorías nuevas: **Oro y Petróleo** · **Clima y desastres** · **Política MX + Latam** | Confirmada · amplía `MarketCategory` (§7.4) |
| 0.10 | Hot ahora: 5–6 mercados de calidad por defecto | Confirmada |

Regla de conflicto: **la decisión bloqueada gana**; la regla vieja del repo se enmienda por escrito en §7, nunca en silencio.

---

## 1 · Sistema de diseño

### 1.1 Color — sin tokens nuevos

Los catorce tokens de `src/styles/tokens.css` se quedan tal cual (`tokens.lock.json` no se mueve). v6 no inventa color: le da **trabajos nuevos** a los que ya pasaron contraste.

| Token | Trabajo en v6 |
|---|---|
| `--bg` | Fondo de app, header y barra inferior (sólido, nunca translúcido) |
| `--panel` | Superficie de tarjeta |
| `--panel2` | Pill del resultado no líder · avatar · estado presionado |
| `--line` | Borde de la tarjeta abierta con posición propia |
| `--line2` | Borde por defecto, separadores, riel vacío de la barra |
| `--text` | Título de mercado y número de la pill líder |
| `--text2` | Etiqueta del resultado, número del rival |
| `--muted` | Pie de tarjeta, categoría, multiplicadores, barra de los resultados no líderes |
| `--teal` | Marca, pestaña activa, **relleno de la barra del líder**, CTA primario |
| `--teal-soft` | Fondo de la pill líder |
| `--teal-ink` | Texto sobre relleno teal |
| `--up` / `--dn` | Variación de precio en Cripto Live y destello de actualización |
| `--hot` | Badge HOT |
| `--live` | Punto y badge LIVE, minuto de partido |

Contraste: todo par texto/superficie de arriba ya está verificado ≥ 4.5:1 por `tests/contrast.test.ts`. Las barras son gráfico, no texto: `--teal` y `--muted` sobre `--line2` cumplen ≥ 3:1 en ambos temas.

### 1.2 Tipografía

| Rol | Familia | Tamaño / interlínea | Peso |
|---|---|---|---|
| Marca en el header | Fraunces (`--font-display`) | 19 / 22, `tracking-[-0.01em]` | 600 |
| Título de tarjeta | Fraunces | 15 / 19 | 600 |
| Número de la pill (%) | Fraunces, `tabular-nums` | **24 / 26**, `tracking-[-0.02em]` | 600 |
| Signo `%` de la pill | Hanken | 10, alineado arriba | 700 |
| Número del rival | Fraunces, `tabular-nums` | 17 / 20 | 600 |
| Etiqueta de resultado | Hanken | 12 / 14 | 600 |
| Multiplicador | Mono, `tabular-nums` | 12 / 14 | 600 |
| Marcador deportivo | Fraunces, `tabular-nums` | 16 / 20 | 600 |
| Badges (LIVE/HOT/país) | Hanken | 10 / 12, `tracking-[0.04em]`, versalitas | 700 |
| Pie de tarjeta | Hanken | 11 / 12 | 400 |
| Categoría | Hanken | 11 / 12 | 500 |
| Probabilidad en **detalle** | Fraunces | 44 / 44 (`text-prob`) | 600 |

**Enmienda a R-004.** El nodo de 44 px sale de la tarjeta y se queda en el detalle. En la tarjeta el nodo dominante sigue siendo la probabilidad —la pill de 24 px es el único elemento en escala display con `tabular-nums`, el doble que cualquier otro texto de la card—, y esa jerarquía es la que R-004 protege. Los 20 px que devuelve son la mitad del recorte de altura.

Escala nueva de Tailwind (`tailwind.config.ts` → `fontSize`):
```ts
prob:      ["44px", { lineHeight: "1",     letterSpacing: "-0.02em" }], // sólo detalle
"prob-pill": ["24px", { lineHeight: "26px", letterSpacing: "-0.02em" }], // tarjeta, líder
"prob-riv":  ["17px", { lineHeight: "20px", letterSpacing: "-0.01em" }], // tarjeta, rival
```

### 1.3 Espaciado y forma

Escala de 4: `4 · 8 · 12 · 16 · 24`. Nada intermedio.

| Token | Valor | Dónde |
|---|---|---|
| `--card-pad-y` | 9 px | Arriba y abajo de la tarjeta |
| `--card-pad-x` | 14 px | Lados de la tarjeta |
| `--card-row-gap` | 3 px | Entre filas de la tarjeta |
| `--card-stack-gap` | 8 px | Entre tarjetas |
| `--bar-h` | 3 px | Alto de toda barra de probabilidad |
| `--page-pad-x` | 16 px | Márgenes de pantalla |
| `--touch` | 44 px | Mínimo de cualquier target |

Radios: tarjeta **14 px** (baja de 18: con 110 px de alto, 18 px se comía la esquina del contenido), hoja 24 px, pill 999 px, barra 999 px.
Sombra: `shadow-card` sin cambio.
Ancho máximo de contenido: **520 px**, centrado.

### 1.4 Jerarquía visual de la tarjeta (orden de lectura, de mayor a menor)

1. Pill de probabilidad del líder (24 px, fondo `--teal-soft`)
2. Título del mercado (15 px display)
3. Barra de probabilidad (3 px, `--teal`)
4. Etiquetas de resultado + multiplicadores (12 px)
5. Badges LIVE / HOT / país (10 px)
6. Pie: pozo · gente · cierre (11 px `--muted`)

---

## 2 · Shell global

### 2.1 Header — 56 px + `--safe-t`

Contenedor: `sticky top-0 z-30`, fondo `--bg` **sólido**, borde inferior `1px --line2`, `max-w-[520px]`, `px-16`.

**Zona izquierda (idéntica en los dos estados, es la identidad):**
- Espiral de marea (SVG, `stroke: --teal`, `stroke-width 1.6`) a **26 × 26 px** (sube de 24).
- Palabra `Marea`, Fraunces 600, 19 px, `--text`, separación 8 px del símbolo.
- El bloque logo+palabra es el único elemento de 26 px de alto en la barra: domina por tamaño y por ser el único con color de marca a la izquierda.

**Estado A — sin sesión (derecha):**

| Elemento | Especificación |
|---|---|
| `Entrar` | Botón de texto. Hanken 14 px / 600, color `--text2`. Alto táctil 44 px, `px-8`. Sin fondo ni borde. |
| `Crear cuenta` | Pill primaria. Fondo `--teal`, texto `--teal-ink` Hanken 14 px / 700, alto **34 px**, `px-14`, radio 999. Alto táctil real 44 px vía `py` transparente. |
| Separación | 4 px entre ambos |

**Estado B — con sesión (derecha):**

| Elemento | Especificación |
|---|---|
| Bloque de saldo | Alineado a la derecha. Línea 1: `Saldo`, 10 px versalitas `tracking-[0.06em]` `--muted`. Línea 2: valor en mono 15 px / 600 `tabular-nums` `--text`. Es **accionable** (44 px de alto táctil). |
| Avatar | Círculo de 32 px, fondo `--panel2`, `ring-1 --line2`, inicial del usuario en Hanken 13 px / 700 `--text2`. Separación 10 px del saldo. Abre la hoja de cuenta. |

**Regla de saldo cero (conserva V12 sin meter un tercer elemento).** Si el saldo es 0, el bloque de saldo pinta el valor en `--muted`, agrega debajo del avatar un punto de 6 px `--teal`, y **al tocarlo abre la hoja de recarga** en vez de la de cuenta. Nunca hay muro: el camino para tener saldo está a un toque, dentro de los dos elementos permitidos.

El header no lleva ninguna otra acción. Las decisiones viven abajo, en la zona del pulgar (R-010).

### 2.2 Navegación inferior — exactamente 4 destinos

Contenedor: `fixed inset-x-0 bottom-0 z-30`, fondo `--bg` sólido, borde superior `1px --line2`, `padding-bottom: --safe-b`, `max-w-[520px]` centrado. Alto de fila: 56 px (cada target ≥ 44 px).

| Orden | `id` | Etiqueta | Icono (lucide) | Contenido |
|---|---|---|---|---|
| 1 | `markets` | **Mercados** | `LayoutGrid` | Feed: Hot ahora + chips de categoría + todos los mercados. Destino por defecto. |
| 2 | `search` | **Buscar** | `Search` | Búsqueda por texto y por categoría |
| 3 | `portfolio` | **Portafolio** | `PieChart` | Posiciones abiertas, cerradas y — en modo dinero — el acceso a Cartera como acción del encabezado |
| 4 | `profile` | **Perfil** | `User` | Cuenta, **Tabla de posiciones**, ajustes, legal, cerrar sesión |

Estado activo: color `--teal`, etiqueta en 700, `strokeWidth 2.4` (inactivo: `--muted`, 500, `strokeWidth 1.8`). El estado nunca depende sólo del color (R-005).
Semántica: `<nav>` → `<ul role="tablist">` → `<li role="presentation">` → `<button role="tab" aria-selected>`.

**Qué pasa con los dos destinos que se van:**
- **Tabla** deja de ser pestaña y pasa a ser la **primera sección de Perfil**: encabezado `Tabla de posiciones`, tu fila fijada arriba con tu posición, top 10 debajo, enlace `Ver tabla completa` que abre la pantalla `TablaScreen` como hoja. Cero pérdida de función.
- **Cartera** (modo dinero) pasa a ser acción del encabezado de Portafolio (icono `Wallet`, 44 px) **y** fila en Perfil. En modo puntos no existe, como hoy.

---

## 3 · Sistema de tarjetas

### 3.1 Anatomía común

```
┌────────────────────────────────────────────────┐  ← radio 14, borde 1px --line2
│ [LIVE] [HOT] [MX]                  ● Cripto    │  fila 1 · 16 px
│ Bitcoin cierra la semana arriba de 71k         │  fila 2 · 19 px  (1 línea)
│ ┌──────┐                                       │
│ │ 62 % │ Arriba de 71,000  1.61×   38 % Abajo  │  fila 3a · 30 px
│ └──────┘                          2.63×        │
│ ██████████████████████░░░░░░░░░░░░░░░░░        │  fila 3b · 3 px
│ Pozo 2,240 pts · 38 jugando · Cierra dom 23:59 │  fila 4 · 12 px
└────────────────────────────────────────────────┘
```

**Presupuesto de altura (390 × 844, DPR 2):**

| Zona | px |
|---|---|
| Padding vertical (9 + 9) | 18 |
| Fila 1 · badges + categoría | 16 |
| Fila 2 · título (1 línea) | 19 |
| Fila 3 · bloque de opciones (pill 30 + 3 + barra 3) | 36 |
| Fila 4 · pie | 12 |
| Separaciones entre filas (3 × 3) | 9 |
| **Total** | **110** |

**110 px contra los 159 px medidos hoy = −30,8 %.** Se cumple el "~30 % más bajas" con número, no con adjetivo.

Cómo se paga ese recorte, en orden de aporte: el número baja de 44 a 24 px (−20), el título se limita a **una** línea vía `shortTitle` (−19), el padding baja de 12 a 9 y las separaciones de 6 a 3 (−15), el Edge sale de la card (−5, era una badge en la fila de decisión). Suma −59; la barra nueva devuelve +6 y el radio menor +4 de aire visual sin costo de alto.

**`shortTitle` es obligatorio.** Campo nuevo en `Market`: `shortTitle?: string`, ≤ 42 caracteres, sin signo de interrogación, afirmativo. El catálogo propio y las plantillas lo generan siempre; los mercados agregados que no lo traigan caen a `title` con `line-clamp-2` (tarjeta de 129 px, excepción declarada y medida).

- `title`: `¿Bitcoin cierra la semana arriba de 71,000 dólares?` → detalle
- `shortTitle`: `Bitcoin cierra la semana arriba de 71k` → tarjeta

**Densidad resultante.** A 390 × 844: 844 − 56 (header) − 56 (nav) − 40 (chips) = 692 px de contenido; 110 + 8 = 118 px por mercado → **5 tarjetas enteras** (hoy 4), y 5,8 con la altura media del feed. Presupuesto para `npm run densidad`: alto de tarjeta ≤ 116 px en los tres tipos de una pregunta, ≥ 5 tarjetas enteras, 0 nodos de texto envueltos a 320 / 360 / 390 / 430 px.

### 3.2 Barras de probabilidad (nivel Kalshi)

- Alto **3 px**, radio 999, ancho = ancho de contenido de la tarjeta (330 px a 390 de viewport).
- **Binario:** un solo riel `--line2`. Segmento del líder pegado a la izquierda, `--teal`, ancho = P(líder). Segmento del rival pegado a la derecha, `--muted`, ancho = P(rival). Separación de 2 px entre ambos, hecha con `gap`, no con borde.
- **Multi-resultado:** una barra por fila de resultado, alineada bajo su etiqueta, ancho = probabilidad de ese resultado sobre el 100 % de la barra. Fila 1 en `--teal`; filas 2+ en `--muted`.
- **Nunca** se pinta una barra de 0 px: por debajo de 2 % se dibuja un tope de 2 px, para que "casi nada" y "nada" no se vean igual.
- Transición de ancho: 240 ms `cubic-bezier(.22,1,.36,1)`. Cambio de probabilidad en vivo: destello del segmento a `--teal-deep` durante 180 ms y vuelta.
- La barra es decorativa para el lector de pantalla (`aria-hidden`): el porcentaje ya está en texto al lado.

### 3.3 Resultados con nombre — obligatorio

**Ningún resultado se llama `Sí` ni `No` en la tarjeta.** `BINARY_OUTCOMES` deja de ser `[{si,"Sí"},{no,"No"}]` como valor por defecto mostrable: los ids `si`/`no` se conservan (los datos ya persistidos dependen de ellos), pero cada mercado **debe** declarar `outcomes[].label` con nombre propio.

Reglas de nombrado: frase verbal o umbral que se lea solo, ≤ 22 caracteres, mayúscula inicial, sin punto final, sin la palabra "Sí"/"No".

| Familia | `si` | `no` |
|---|---|---|
| Precio (cripto, oro, petróleo) | `Arriba de 71,000` | `Abajo de 71,000` |
| Tasa Banxico / Copom | `Recorta` | `Mantiene` |
| Inflación con umbral | `Abajo de 4.0 %` | `4.0 % o más` |
| Tipo de cambio | `Cierra bajo 19 pesos` | `Cierra arriba` |
| Clima / desastres | `Toca tierra cat. 3+` | `No llega` |
| Política — reforma | `Se aprueba` | `Se cae` |
| Política — elección binaria | `Gana el oficialismo` | `Gana la oposición` |
| Deportes — resultado | `Gana el América` | `Gana Santos` |

La puerta es `assertPublishable()` en `src/domain/resolution.ts`: un mercado con una etiqueta vacía, con más de 22 caracteres o igual a `Sí`/`No` **no se publica**.

### 3.4 Los cuatro tipos de tarjeta

#### 3.4.1 Cripto Live

- **Header row:** badge `LIVE` (punto 6 px `--live` pulsando + palabra) · badge `HOT` si aplica · a la derecha, marca de categoría (círculo 6 px `--teal`) + palabra `Cripto`, 11 px `--muted`. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Bitcoin cierra la semana arriba de 71k`. Fraunces 600, 15 / 19, `--text`, `line-clamp-1`.
- **Options block:** dos grupos en una fila, `justify-between`.
  - Líder: pill de 30 px de alto, fondo `--teal-soft`, radio 999, `px-10`; dentro, `62` en 24 px Fraunces `tabular-nums` `--text` + `%` en 10 px alineado arriba. Fuera de la pill, a 8 px: etiqueta `Arriba de 71,000` (12 px / 600 `--text2`, `truncate`) y multiplicador `1.61×` (mono 12 px `--muted`).
  - Rival, alineado a la derecha: `38 %` en 17 px `--text2` + etiqueta `Abajo de 71,000` + `2.63×`.
  - Debajo, a 3 px: la barra binaria de §3.2.
- **Footer:** una línea, 11 px `--muted`, `truncate`: `BTC 71,204 · +1.4 % hoy · Pozo 2,240 pts · Cierra dom 23:59`. La variación va en `--up` o `--dn` según signo, con el signo siempre escrito.
- **Visual notes:** alto total **110 px**. El precio spot del pie se actualiza cada 10 s y la barra sólo se remueve cuando la probabilidad cambia ≥ 0,5 pp. El badge LIVE pulsa 1,8 s. Si el oráculo se atrasa > 5 min, el badge LIVE se sustituye por `Precio con retraso` en `--muted` y el spot deja de pintarse en color de variación.

#### 3.4.2 Deportes Live

- **Header row:** badge `LIVE` · badge de minuto `72'` (mono 10 px, fondo `--live` al 14 %, texto `--live`) · escudos de los dos equipos (22 px, `rounded-full`, sólo ≥ 360 px de ancho) · a la derecha, marca de categoría + `Deportes`. Alto 16 px.
- **Main content:** el marcador **es** el título — `América 2 – 1 Santos`, Fraunces 600, 16 / 20, `tabular-nums`; los goles en `--text`, el guion y los nombres en `--text2`. Una línea, `truncate` por nombre de equipo, nunca por el marcador.
- **Options block:** tres grupos si el mercado es 1X2, dos si es binario. Cuando son tres, se usa el patrón multi-resultado (§3.4.4) con las filas ordenadas por pozo:
  - `Gana el América` — pill 30 px `61 %` + `1.63×` + barra `--teal`
  - `Empatan` — `24 %` + `4.10×` + barra `--muted`
  - `Gana Santos` — `15 %` + `6.50×` + barra `--muted`
- **Footer:** `Resultado final · Pozo 4,120 pts · 96 jugando`. La pregunta larga (`¿Cómo termina el América ante Santos?`) vive en el detalle.
- **Visual notes:** alto **111 px** en su forma binaria (dos grupos en una fila), **149 px** en 1X2. El marcador destella `--up` 200 ms cuando cambia y el minuto se refresca cada 30 s. Sin oráculo de marcador vivo no hay badge LIVE: un partido "en vivo" sin marcador es una promesa que la tarjeta no puede cumplir.

#### 3.4.3 Binario con nombre (estándar)

- **Header row:** badge `HOT` si aplica · badge de país (`MX`, `BR`, `CO`…, 10 px, fondo `--panel2`) · a la derecha, marca de categoría (cuadro 6 px `--hot`) + `Economía`. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Banxico recorta la tasa en agosto`.
- **Options block:** idéntico al de Cripto Live: pill líder + etiqueta + multiplicador a la izquierda, rival alineado a la derecha, barra binaria de 3 px debajo.
  - `54 %` `Recorta` `1.80×`  ·  `46 %` `Mantiene` `2.12×`
- **Footer:** `Pozo 2,240 pts · 38 jugando · Cierra el 8 ago`.
- **Visual notes:** alto **110 px** con `shortTitle`, 129 px en el caso degradado de dos líneas. Sin `LIVE` y sin borde de color: sólo el mercado con posición propia abierta lleva borde `--line`. **El Edge no aparece aquí** en ninguna forma.

#### 3.4.4 Multi-resultado

- **Header row:** badges igual que el estándar · a la derecha, categoría. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Quién gana la elección en Chile`.
- **Options block:** las **tres** respuestas con más pozo, una por fila, cada fila de 20 px + barra de 3 px, separadas 3 px:
  - fila = pill compacta (alto 24, `px-8`, número 20 px) `41 %` · etiqueta `Gana Jara` (12 px `--text2`, `truncate`) · multiplicador `2.44×` alineado a la derecha (mono 12 px `--muted`) · barra debajo, ancho proporcional.
  - Orden: por probabilidad descendente. Fila 1 con pill `--teal-soft` y barra `--teal`; filas 2 y 3 con pill `--panel2` y barra `--muted`.
- **Footer:** `+4 respuestas · Pozo 9,800 pts · 211 jugando · Cierra el 16 nov`. El `+N respuestas` va primero y en `--text2`: es la señal de que hay más detrás.
- **Visual notes:** alto **149 px**, excepción declarada al presupuesto de 116 px — reemplaza la información de tres tarjetas, así que sigue siendo el formato más denso disponible. Nunca se muestran más de 3 filas en la tarjeta, ni siquiera con hueco: la cuarta respuesta se lee en el detalle. Si hay exactamente 2 respuestas, no es multi-resultado: es binario con nombre.

### 3.5 Regla de variante

```
status === "live" && category === "cripto"    → Cripto Live
status === "live" && category === "deportes"  → Deportes Live
outcomes.length > 2                           → Multi-resultado
resto                                          → Binario con nombre
```
`hasEdge()` deja de participar en la elección de variante y deja de tener borde propio.

---

## 4 · Arquitectura de mercados

### 4.1 Cripto Live — selección automática del motor

La UI **no elige** monedas. Las elige `ownMarketsAdapter` cada 5 minutos y expone un riel ya ordenado.

**Escalón 1 — fijas.** BTC y ETH siempre, si su oráculo de precio está fresco (< 60 s). Si uno se atrasa, no lo sustituye nadie: baja a tarjeta normal sin `LIVE` y conserva su lugar.

**Escalón 2 — las siguientes con más señal.** De las monedas soportadas por el oráculo (hoy Kraken: SOL, XRP, DOGE, ADA, AVAX, LINK), se toman las **2 mejores** por:

```
score = 0.50 · z(volumen 24 h) + 0.35 · z(|Δ % 1 h|) + 0.15 · frescura_oráculo
frescura_oráculo = 1 si < 60 s · 0.5 si < 5 min · 0 si más
```

**Histéresis (anti-parpadeo):** una moneda sólo desplaza a la titular si supera su score en ≥ 15 % durante **2 ciclos seguidos** (10 min). Sin esto el riel cambia cada refresco y el feed se siente inestable.

**Elegibilidad de "Live":** ventana de mercado ≤ 24 h, precio de referencia programático, cierre y resolución leídos de la misma vela. Un mercado semanal de BTC no es Live: es binario con nombre.

**Techo:** máximo **4** tarjetas Cripto Live simultáneas (2 fijas + 2 rotatorias). Degradación: oráculo atrasado > 5 min → se cae el badge; > 15 min → la tarjeta sale del riel Live y el feed lo declara con la franja de datos viejos que ya existe.

### 4.2 Deportes — selectivo por definición

| Liga | Regla de inclusión | Techo por jornada |
|---|---|---|
| **Liga MX** | Todos los partidos de la jornada, apertura de mercado 72 h antes | Sin techo |
| **LMP** (Liga Mexicana del Pacífico) | Toda la temporada de invierno, incluidos playoffs | Sin techo |
| **MLB** | Sólo si abre un lanzador mexicano o latino, **o** es postemporada | 3 por día |
| **Tenis** | Sólo ATP/WTA 500+ con jugador latino, **o** Grand Slam de cuartos en adelante | 2 por día |

Un partido sólo entra en estado `live` si el oráculo de partido (`matchOracle`) entrega marcador y minuto. Sin marcador no hay Deportes Live.
Mercados por partido: `Resultado final` (1X2) siempre; `Total de goles` sólo en Liga MX y sólo si el partido ya tiene ≥ 20 apostadores en el 1X2 — un mercado secundario sin gente es un pozo muerto.

### 4.3 Oro y Petróleo — categoría `materias`

Marca visual: cuadro 6 px en `--hot` (comparte forma con Economía y color de "dato duro"); palabra `Materias`.
Fuente: `priceOracle` con `XAU/USD` y `WTI/USD`, lectura de vela diaria, misma mecánica que las plantillas de cripto.

| Plantilla | Cadencia | Paso del umbral | Ejemplo (`shortTitle`) |
|---|---|---|---|
| Cierre semanal del oro | Semanal, domingo 23:59 UTC | 25 USD | `El oro cierra la semana arriba de 3,400` |
| Cierre mensual del petróleo | Mensual, último día hábil | 1 USD | `El WTI cierra el mes arriba de 68` |
| Toque de nivel | Quincenal | 50 USD (oro) / 2 USD (WTI) | `El oro toca 3,500 antes del 15 de agosto` |

Resultados con nombre: `Arriba de 3,400` / `Abajo de 3,400`; `Toca 3,500` / `No lo toca`.
Ángulo Latam obligatorio en al menos un mercado vivo de la categoría: el petróleo se lee también contra Pemex y la mezcla mexicana, y el oro contra el peso (`El oro arriba de 62,000 pesos la onza`).

### 4.4 Clima y desastres — categoría `clima`

Marca visual: círculo 6 px `--dn`; palabra `Clima`.
**Regla dura:** sólo se publica lo que una fuente pública nombrada resuelve por programa. Fuentes admitidas: SMN/Conagua (México), NHC (ciclones del Atlántico y Pacífico oriental), USGS (sismos), CENAPRED (volcanes), INMET (Brasil).

| Plantilla | Fuente | Ejemplo (`shortTitle`) | Resultados |
|---|---|---|---|
| Ciclón que toca tierra | NHC | `Un huracán cat. 3+ toca costa mexicana en agosto` | `Toca tierra cat. 3+` / `No llega` |
| Nivel de presa | Conagua | `El Cutzamala pasa de 60 % antes de octubre` | `Pasa de 60 %` / `Se queda abajo` |
| Actividad volcánica | CENAPRED | `El Popocatépetl llega a semáforo amarillo fase 3` | `Llega a fase 3` / `Se queda en fase 2` |
| Temporada de lluvias | SMN | `Agosto cierra arriba del promedio de lluvia en CDMX` | `Arriba del promedio` / `Abajo del promedio` |

**Prohibido publicar** mercados sobre número de muertos, heridos, desaparecidos o daño a personas identificables. Se apuesta sobre el fenómeno, nunca sobre la desgracia de nadie. Esta regla entra en `assertPublishable()` como lista de términos vetados y se documenta en `vault/RULINGS.md`.

### 4.5 Política MX + Latam — categoría `politica`

Fuentes admitidas: INE y OPLEs (México), CNE (Colombia), TSE (Brasil), Servel (Chile), Diario Oficial de la Federación y la Gaceta Parlamentaria para reformas, encuestadoras nombradas (El Financiero, Enkoll, Reforma) para aprobación.

| Familia | Ejemplo (`shortTitle`) | Resultados |
|---|---|---|
| Aprobación presidencial | `Sheinbaum arriba de 70 % en El Financiero de agosto` | `Arriba de 70 %` / `70 % o menos` |
| Reformas | `La reforma electoral pasa la Cámara antes de diciembre` | `Se aprueba` / `Se cae` |
| Elecciones Latam | `Quién gana la elección en Chile` (multi) | `Gana Jara` / `Gana Kast` / `Gana Matthei` / `+4` |
| Nombramientos | `La Corte queda con nueva presidencia en enero` | `Cambia` / `Sigue igual` |
| Política económica | `Banxico recorta la tasa en agosto` (cuenta como `economia`) | `Recorta` / `Mantiene` |

Reglas: el mercado nombra a la encuestadora o al órgano que lo resuelve dentro de `resolution_summary` (R-027/R-046); nada de mercados sobre la vida, salud o seguridad de una persona; nada sobre procesos judiciales individuales.

### 4.6 Hot ahora — 5 a 6, sin excepción

**Candidatos:** `status === "live"` ∨ `hot === true` ∨ cierra en < 24 h ∨ pozo en el decil superior.

```
score = 0.40 · vivo + 0.25 · z(pozo) + 0.20 · z(participantes) + 0.15 · urgencia_cierre
vivo = 1 si status === "live", 0.6 si cierra en < 6 h, 0 si no
urgencia_cierre = 1 − min(horas_al_cierre / 72, 1)
```

**Reglas de armado, en este orden:**
1. Ordenar candidatos por score descendente.
2. **Máximo 2 por categoría** — seis mercados de cripto no son un feed, son un ticker.
3. Si hay algún deporte en vivo, el primero entra sí o sí en el top 3.
4. Cortar en 5. Si el sexto tiene score ≥ 0,55, entra: **6**.
5. Si hay menos de 5 candidatos, completar con los mercados abiertos de mayor score hasta 5. El riel **nunca** muestra 4.
6. Ningún mercado con menos de `MIN_APOSTADORES` (2) entra en Hot: un pozo de una persona no está caliente.

El encabezado `Hot ahora` sigue siendo `sr-only`: los badges ya lo dicen y 36 px de cromo son un tercio de tarjeta.

### 4.7 Edge — dónde vive

`computeEdge()` y `EDGE_MIN_PP = 4` no se tocan. El Edge se muestra **sólo en el detalle del mercado**, bajo el bloque de probabilidad: `Aquí 62 % · Polymarket 69 % · Edge +7 %`, con `Base de la lectura` debajo. En el feed no hay Edge en ninguna forma: ni badge, ni borde teal, ni orden. La promesa de marca ("con edge") se cumple donde se decide, no donde se hojea — la tarjeta gana 5 px y pierde su nodo más ruidoso.

---

## 5 · Interacción y pulido

| Estado | Especificación |
|---|---|
| **Pulso LIVE** | Punto de 6 px `--live`, `opacity 1 → 0.35 → 1`, 1,8 s `ease-in-out`, infinito. Un solo punto por tarjeta. Se detiene con `prefers-reduced-motion`. |
| **Actualización de probabilidad** | El número cruza con `fade` de 120 ms; la barra transiciona 240 ms `cubic-bezier(.22,1,.36,1)`. Sube → destello `--up` 200 ms sobre el número; baja → `--dn`. Umbral mínimo para animar: 0,5 pp. |
| **Marcador deportivo** | Al cambiar, el marcador destella `--up` 200 ms y el minuto se refresca sin animación. |
| **Presionado** | Toda la tarjeta es un target. `active:` fondo `--panel2`, `scale(0.985)`, 120 ms `ease-out`. Sin efecto de elevación. |
| **Cargando (feed)** | 5 esqueletos de **exactamente 110 px** con `animate-shimmer`. La altura clavada es lo que mantiene el CLS en 0. |
| **Cargando (acción)** | El botón conserva su ancho y cambia el texto (`Preparando…`), nunca se encoge. |
| **Vacío (filtro)** | `No hay mercados en esta categoría por ahora.` + `Ver todos los mercados`. |
| **Vacío (Hot)** | No existe: la regla 4.6.5 garantiza 5. |
| **Vacío (Portafolio)** | `Todavía no tienes posiciones.` + `Ver mercados`. |
| **Error** | `ErrorState` con mensaje en español y `Reintentar`. Nunca un stack trace (R-008). |
| **Datos viejos** | Franja existente sobre el feed: `Esto es lo último que cargamos` + `Reintentar`. Se sigue mostrando el contenido. |
| **Cerrado** | El pie dice `Cerrado`; las pills bajan a `--muted` y la barra a 40 % de opacidad; la tarjeta sigue abriendo el detalle. |
| **Resuelto** | Badge `Resuelto` en `--up`; el resultado ganador conserva pill `--teal-soft`, los demás caen a `--panel2`. |

**Mobile-first, restricciones no negociables:**
- Anchos de prueba: **320 / 360 / 390 / 430 px**. Cero scroll horizontal (V11), cero nodos de texto envueltos.
- `max-w-[520px]` centrado; por encima de 520 px la app no se estira, se centra.
- Todo target ≥ 44 px. Las acciones que deciden viven en la mitad inferior (R-010).
- `--safe-t` y `--safe-b` respetados en header y nav.
- Texto al 200 %: la fila de opciones puede envolver (`flex-wrap`); el número y su etiqueta nunca se separan.
- Escudos ocultos por debajo de 360 px (`angosto:`).
- `prefers-reduced-motion`: todas las animaciones a 0,01 ms, incluido el pulso LIVE.
- `prefers-color-scheme` + `data-theme`: los dos temas son sets reales de valores (R-012).

---

## 6 · Copy — español Latam, directo

Todo el texto vive en `src/lib/strings.ts` (R-007). Lo que v6 agrega o cambia:

```ts
header: {
  balance: "Saldo",
  entrar: "Entrar",
  crearCuenta: "Crear cuenta",
  recargar: "Recargar",          // saldo 0, dentro del bloque de saldo
},
tabs: { markets: "Mercados", search: "Buscar", portfolio: "Portafolio", profile: "Perfil" },
categories: {
  cripto: "Cripto", economia: "Economía", deportes: "Deportes",
  politica: "Política", materias: "Materias", clima: "Clima",
  cultura: "Cultura", otros: "Otros",
},
market: {
  respuestasMas: (n: number) => `+${n} respuestas`,
  resultadoFinal: "Resultado final",
  precioRetraso: "Precio con retraso",
  hoy: "hoy",
},
perfil: { tabla: "Tabla de posiciones", tablaCompleta: "Ver tabla completa" },
```

Tono: se tutea, se dice lo que pasa y se cierra la frase. `Pozo 2,240 pts`, no `Pool total acumulado`. `38 jugando`, no `38 participantes activos`. `Cierra el 8 ago`, no `Fecha de cierre: 08/08`. Cero anglicismos innecesarios: se conservan sólo `LIVE`, `HOT` y `Edge`, que son las tres palabras que el usuario ya lee así en cualquier casa de mercados.

---

## 7 · Deltas contra el código actual (hand-off)

| # | Cambio | Archivos | Riesgo |
|---|---|---|---|
| 7.1 | Nav de 5 → **4** destinos. `tabla` y `wallet` dejan de ser pestañas | `src/components/BottomTabs.tsx`, `src/state/store.ts` (`TabId`), `tests/navegacion.test.ts` | Medio — hay pruebas que cuentan pestañas |
| 7.2 | Header con dos estados; `Depositar` sale del header y el bloque de saldo se vuelve accionable | `src/components/AppHeader.tsx`, `src/lib/strings.ts` | Bajo — V12 se conserva por la regla de saldo cero |
| 7.3 | **Edge fuera de la tarjeta**: se va la badge, el borde teal y la variante `edge` | `src/components/MarketCard.tsx`, `src/screens/MarketDetailScreen.tsx` | Bajo — el dominio no se toca |
| 7.4 | `MarketCategory` suma `materias` y `clima`; marca visual y chips | `src/domain/types.ts`, `src/lib/categoria.ts`, `src/screens/HomeScreen.tsx`, `src/lib/strings.ts` | Bajo |
| 7.5 | `shortTitle` en `Market`, generado por catálogo y plantillas | `src/domain/types.ts`, `src/adapters/ownMarkets/{catalog,templates}.ts` | Medio — hay que escribir uno por mercado del catálogo |
| 7.6 | Etiquetas con nombre obligatorias; `Sí`/`No` prohibidos como label | `src/domain/parimutuel.ts`, `src/domain/resolution.ts`, catálogo y plantillas | **Alto** — toca los mercados ya sembrados; migración: script que rellena labels por familia antes de desplegar |
| 7.7 | Barras de probabilidad de 3 px, binaria y multi | `src/components/MarketCard.tsx` (componente nuevo `ProbBar`) | Bajo |
| 7.8 | Escala tipográfica: `prob-pill` y `prob-riv`; `prob` sólo en detalle. Radio de card 14 px | `tailwind.config.ts` | Bajo |
| 7.9 | Tabla de posiciones dentro de Perfil | `src/screens/ProfileScreen.tsx`, `src/screens/TablaScreen.tsx` | Bajo |
| 7.10 | Selección automática de Cripto Live con histéresis | `src/adapters/ownMarkets/ownMarketsAdapter.ts`, `src/adapters/oracles/priceOracle.ts` | Medio |
| 7.11 | Armado de Hot ahora por score con techo por categoría | `src/screens/HomeScreen.tsx` → mover a `src/domain/feed.ts` (nuevo) | Medio — la regla debe ser probable sin montar la UI |
| 7.12 | Presupuesto de densidad nuevo: ≤ 116 px por tarjeta, ≥ 5 enteras | `scripts/densidad.mjs`, `vault/CARD_SPEC.md` | Bajo |

**Enmiendas de reglas que quedan escritas:** R-004 (el nodo de 44 px pasa al detalle; la pill de 24 px es el dominante de la tarjeta), R-001 (el Edge sigue teniendo umbral de 4 pp, pero su superficie es sólo el detalle), R-063 (los dos lados siguen a la vista y ahora además tienen nombre propio).

---

## 8 · Apéndice — Verification Swarm

Cinco agentes revisaron el borrador completo. Ronda 1 con dos fallos, corregidos por el protocolo de recuperación; ronda 2 unánime.

| Agente | Ronda 1 | Ronda 2 |
|---|---|---|
| **1 · Design Critic** | PASS — densidad medida (110 px, −30,8 %), logo a 26 px y único elemento de marca a la izquierda, barras especificadas al píxel | PASS |
| **2 · Market Architect** | **FAIL** — el borrador dejaba `BINARY_OUTCOMES` con `Sí`/`No` como valor por defecto mostrable, y las plantillas de cripto seguían sembrando esas etiquetas | PASS — §3.3 prohíbe la etiqueta, `assertPublishable()` es la puerta, §7.6 declara la migración de los mercados ya sembrados |
| **3 · Consistency Guardian** | **FAIL** — el header perdía V12 (con saldo 0 la app no puede quedarse sin camino a recargar) al quitar el botón `Depositar` | PASS — §2.1 hace accionable el bloque de saldo; se conservan exactamente los dos elementos bloqueados |
| **4 · Implementation Readiness** | PASS — los cuatro tipos traen ejemplo estructurado; la aritmética de altura suma; §7 mapea cada cambio a su archivo | PASS |
| **5 · LATAM Voice** | PASS — Liga MX, LMP, Banxico, Cutzamala, Popocatépetl, mezcla mexicana, Servel/CNE/TSE; copy tuteado y sin anglicismos de relleno | PASS |

**Veredicto: 5/5 PASS.** Especificación emitida.
