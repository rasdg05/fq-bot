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

### 1.1 Color — un solo token nuevo

Los catorce tokens de `src/styles/tokens.css` se quedan tal cual: v6 les da **trabajos nuevos** en vez de inventar color. La única alta es `--pill-ring`, que existe porque el anillo de la pill necesita alfas distintos por tema para llegar a 3:1 (§9). `tokens.lock.json` se mueve exactamente una línea.

| Token | Trabajo en v6 |
|---|---|
| `--bg` | Fondo de app, header y barra inferior (sólido, nunca translúcido) |
| `--panel` | Superficie de tarjeta |
| `--panel2` | Avatar · estado presionado · badges neutros. **No** rellena la pill del rival (§9) |
| `--pill-ring` | Anillo de la pill líder **y anillo de foco** de las dos pills: `--teal` al **80 %** en los dos temas → 4,87:1 (oscuro) / 4,08:1 (claro) contra la tarjeta (§10.B) |
| `--pill-line` | Contorno de 1 px de la pill del rival: `--text2` al 60 % (oscuro) / 70 % (claro) → 4,08:1 / 3,80:1 (§10.A) |
| `--pill-wash` | Lavado del rival: `--text` al 4 % sobre la tarjeta. No es relleno sólido: mantiene el número en 7,95:1 / 7,73:1 |
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

Contraste: **§9 trae los ratios medidos, par por par y tema por tema**, incluidas las composiciones alfa de los badges. Resumen: texto principal y porcentajes ≥ 8,35:1, texto secundario ≥ 4,91:1, barras y anillos ≥ 3,01:1.

### 1.2 Tipografía

| Rol | Familia | Tamaño / interlínea | Peso |
|---|---|---|---|
| Marca en el header | Fraunces (`--font-display`) | 19 / 22, `tracking-[-0.01em]` | 600 |
| Título de tarjeta | Fraunces | 15 / 19 | 600 |
| Número de la pill (%) | Fraunces, `tabular-nums` | **30 / 32**, `tracking-[-0.025em]` | **700** |
| Signo `%` de la pill | Hanken | 12 / 12, alineado arriba, `opacity .72` | 700 |
| Número del rival | Fraunces, `tabular-nums` | **20 / 22**, `tracking-[-0.015em]` | 600 |
| Etiqueta de resultado | Hanken | 13 / 15 | 600 |
| Multiplicador | Mono, `tabular-nums` | 12 / 13, `tracking-[0.01em]` | **500** |
| Marcador deportivo (números) | Fraunces, `tabular-nums` | 16 / 20 | **700** |
| Nombre de equipo o jugador | Hanken | 13 / 15 | 600 |
| Badges (LIVE/HOT/país) | Hanken | 10 / 12, `tracking-[0.04em]`, versalitas | 700 |
| Pie de tarjeta | Hanken | 11 / 11, `tracking-[0.005em]` | 450 |
| Categoría | Hanken | 11 / 12 | 500 |
| Probabilidad en **detalle** | Fraunces | 44 / 44 (`text-prob`) | 600 |

**Enmienda a R-004.** El nodo de 44 px sale de la tarjeta y se queda en el detalle. En la tarjeta el porcentaje del líder mide **30 px en peso 700**: 2,3 veces su etiqueta (13 px), 2,5 veces su multiplicador (12 px), el doble del título (15 px), y el único elemento de la tarjeta en peso 700 con `tabular-nums` y color `--text`. Domina por tamaño, por peso y por contraste a la vez. La jerarquía que R-004 protege se conserva con un nodo más chico que 44 px pero más fuerte que antes.

Escala nueva de Tailwind (`tailwind.config.ts` → `fontSize`):
```ts
prob:        ["44px", { lineHeight: "1",    letterSpacing: "-0.02em" }],  // sólo detalle
"prob-pill": ["30px", { lineHeight: "32px", letterSpacing: "-0.025em" }], // tarjeta, líder
"prob-riv":  ["20px", { lineHeight: "22px", letterSpacing: "-0.015em" }], // tarjeta, rival
"prob-row":  ["20px", { lineHeight: "22px", letterSpacing: "-0.015em" }], // multi, filas 2+
mult:        ["12px", { lineHeight: "13px", letterSpacing: "0.01em" }],   // multiplicador
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

Radios: tarjeta **14 px** (baja de 18: con 114 px de alto, 18 px se comía la esquina del contenido), hoja 24 px, pill 999 px, barra 999 px.
Sombra: `shadow-card` sin cambio.
Ancho máximo de contenido: **520 px**, centrado.

### 1.4 Jerarquía visual de la tarjeta (orden de lectura, de mayor a menor)

1. Porcentaje del líder — **30 px / 700**, `--text`, sobre pill `--teal-soft`
2. Porcentaje del rival — 20 px / 600, `--text2`, sin relleno
3. Título del mercado — 15 px display
4. Barra de probabilidad — 3 px, `--teal`
5. Etiqueta de resultado — 13 px / 600
6. Multiplicador — 12 px mono / 500, `--muted`
7. Badges LIVE / HOT / país — 10 px
8. Pie: pozo · gente · cierre — 11 px `--muted`

Los dos primeros escalones son porcentajes y el tercero mide la mitad del primero: la tarjeta se lee como números primero y texto después, que es el orden en que se decide una apuesta.

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
┌──────────────────────────────────────────────────┐  ← radio 14, borde 1px --line2
│ [LIVE] [HOT] [MX]                    ● Cripto    │  fila 1 · 16 px
│ Bitcoin cierra la semana arriba de 71k           │  fila 2 · 19 px  (1 línea)
│ ╭────────╮ Arriba de 71,000      Abajo de 71,000 │
│ │  62 %  │ paga 1.61×        38 %    paga 2.63×  │  fila 3a · 36 px
│ ╰────────╯                                       │
│ ████████████████████████░░░░░░░░░░░░░░░░░░░      │  fila 3b · 3 px
│ Pozo 2,240 pts · 38 jugando · Cierra dom 23:59   │  fila 4 · 11 px
└──────────────────────────────────────────────────┘
```

**Presupuesto de altura (390 × 844, DPR 2):**

| Zona | px |
|---|---|
| Padding vertical (9 + 9) | 18 |
| Fila 1 · badges + categoría | 16 |
| Fila 2 · título (1 línea) | 19 |
| Fila 3 · bloque de opciones (pill 36 + 3 + barra 3) | 42 |
| Fila 4 · pie | 11 |
| Separaciones (3 + 3 + 2) | 8 |
| **Total** | **114** |

**114 px contra los 159 px medidos hoy = −28,3 %**, dentro del techo de 116 px. Los 4 px que sube respecto del borrador anterior compran los 6 px de porcentaje (24 → 30 px) que hacían falta para que el número mande de verdad; se pagan apretando el pie (12 → 11 px, §5) y la separación barra–pie (3 → 2 px).

Cómo se paga el recorte total, en orden de aporte: el título se limita a **una** línea vía `shortTitle` (−19), el número baja de 44 a 30 px (−14), el padding baja de 12 a 9 y las separaciones de 6 a 3 (−13), el pie se aprieta (−2), el Edge sale de la card (−5, era una badge en la fila de decisión). Suma −53; la barra nueva devuelve +6 y la pill más alta +2.

**`shortTitle` es obligatorio.** Campo nuevo en `Market`: `shortTitle?: string`, ≤ 42 caracteres, sin signo de interrogación, afirmativo. El catálogo propio y las plantillas lo generan siempre; los mercados agregados que no lo traigan caen a `title` con `line-clamp-2` (tarjeta de 129 px, excepción declarada y medida).

- `title`: `¿Bitcoin cierra la semana arriba de 71,000 dólares?` → detalle
- `shortTitle`: `Bitcoin cierra la semana arriba de 71k` → tarjeta

**Densidad resultante.** A 390 × 844: 844 − 56 (header) − 56 (nav) − 40 (chips) = 692 px de contenido; 114 + 8 = 122 px por mercado → **5 tarjetas enteras** (hoy 4). Presupuesto para `npm run densidad`: ≤ **116 px** en Cripto Live, Deportes Live y binario con nombre; ≥ 5 tarjetas enteras; 0 nodos de texto envueltos a 320 / 360 / 390 / 430 px.

**Bloque de opciones — geometría fija (la misma en Cripto Live, Deportes Live y binario):**

| Elemento | Medida |
|---|---|
| Pill del líder | Alto **36 px**, radio 999, `px-12`, fondo `--teal-soft`, anillo 1 px `--pill-ring` |
| Número del líder | 30 / 32, peso 700, `--text`, `tabular-nums`; `%` en 12 px pegado arriba con `opacity .72` |
| Stack derecho del líder | A 10 px de la pill, dos líneas de 15 + 13 = 28 px, centradas contra la pill: línea 1 = etiqueta (13 / 15, 600, `--text2`, `truncate`), línea 2 = `paga 1.61×` (mono 12 / 13, 500, `--muted`) |
| Bloque del rival | Alineado a la derecha, **sin relleno**: número 20 / 22 (600, `--text2`) y debajo el mismo stack de dos líneas, alineado a la derecha |
| Barra | 3 px, a 3 px del bloque, ancho completo del contenido |

El rival **no lleva pill rellena** por dos razones que apuntan al mismo lado: en tema claro `--text2` sobre `--panel2` da 6,83:1 y no llega al objetivo de 7:1 (§9), y sin relleno la diferencia entre líder y rival se lee de reojo — un solo bloque pintado por tarjeta.

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

```
┌──────────────────────────────────────────────────┐
│ ●LIVE  1:47  [HOT]                   ● Cripto    │  16 px
│ Bitcoin arriba de 71,200 al cierre de 5 min      │  19 px
│ ╭────────╮ Arriba de 71,200      Abajo de 71,200 │
│ │  62 %  │ paga 1.61×        38 %    paga 2.63×  │  36 px
│ ╰────────╯                                       │
│ ████████████████████████░░░░░░░░░░░░░░░░░░░      │   3 px
│ BTC 71,204 ▲ +1.4 % · Pozo 2,240 pts · 38 jugando│  11 px
└──────────────────────────────────────────────────┘   = 114 px
```

- **Header row:** badge `LIVE` (punto 6 px `--live` pulsando + palabra, 10 px 700 sobre tinte `--live` al 14 %) · **badge de cuenta regresiva** `1:47` (mono 10 px, tinte `--live` al 14 %, se actualiza cada segundo bajo el minuto y cada 5 s por encima) · `HOT` si aplica · a la derecha, círculo 6 px `--teal` + `Cripto`, 11 px `--muted`. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Bitcoin arriba de 71,200 al cierre de 5 min`. Fraunces 600, 15 / 19, `--text`, `line-clamp-1`.
- **Options block:** geometría fija de §3.1.
  - Líder: pill 36 px con `62` en **30 px / 700** `--text` + `%` en 12 px arriba; a 10 px, stack de dos líneas — `Arriba de 71,200` (13 px 600 `--text2`) sobre `paga 1.61×` (mono 12 px 500 `--muted`).
  - Rival, a la derecha y sin relleno: `38 %` en 20 px `--text2`, y debajo `Abajo de 71,200` sobre `paga 2.63×`.
  - Barra binaria de §3.2 a 3 px del bloque.
- **Footer:** 11 px, una línea: `BTC 71,204 ▲ +1.4 % · Pozo 2,240 pts · 38 jugando`. El precio y su variación van primero y en `--up` / `--dn` con flecha **y** signo — el color nunca va solo (R-005). El cierre no se repite aquí: ya está en el badge de cuenta regresiva.
- **Visual notes:** **114 px**. Ventanas de 5 y 15 min siempre disponibles para BTC y ETH (§4.1): el riel nunca está vacío. El spot se refresca cada 5 s con transición de opacidad de 120 ms sobre el número —nunca un salto seco— y la barra se remueve sólo con cambios ≥ 0,5 pp. La cuenta regresiva pasa a `--live` en 700 cuando baja de 30 s. Oráculo atrasado > 5 min: el badge `LIVE` se sustituye por `Precio con retraso` en `--muted`, la cuenta regresiva se mantiene y el spot deja de pintarse en color de variación.

#### 3.4.2 Deportes Live

El marcador ocupa **su propia fila de 20 px** y sustituye al título: la pregunta larga vive en el detalle. Esa fila es la única concesión de altura del tipo (115 px contra 114), y a cambio la tarjeta nunca queda muda sobre el estado del evento.

**Regla de subordinación:** el marcador es Fraunces 700 a **16 px**; el porcentaje del líder es 30 px. El marcador informa, el porcentaje decide, y la proporción 30 : 16 lo dice sin leer.

**Ejemplo A — Tenis Live (el caso más denso: sets + game en curso)**

```
┌──────────────────────────────────────────────────┐
│ ●LIVE  40-30  2º set                 ● Deportes  │  16 px
│ ● Alcaraz  6 4 2        Zverev  3 6 1            │  20 px
│ ╭────────╮ Gana Alcaraz              Gana Zverev │
│ │  71 %  │ paga 1.41×        29 %    paga 3.45×  │  36 px
│ ╰────────╯                                       │
│ ███████████████████████████████░░░░░░░░░░░░      │   3 px
│ Quiebre hace 2 min · Pozo 5,900 pts · 142 jugando│  11 px
└──────────────────────────────────────────────────┘   = 115 px
```

- **Header row:** `LIVE` · badge de **estado del punto** `40-30` (mono 10 px 700, tinte `--live` al 14 %, texto `--live`) · badge de fase `2º set` (10 px, `--panel2`, texto `--muted`) · a la derecha, categoría. 16 px.
- **Main content (fila de marcador, 20 px):** dos grupos separados por 16 px. Cada grupo = apellido (13 px 600 `--text2`, `truncate` a 96 px) + sets en Fraunces **16 px / 700 `tabular-nums` `--text`**, separados 6 px, el set en curso con `opacity .72` para que no se confunda con los cerrados. Punto de saque: círculo de 5 px `--teal` a la izquierda de quien saca.
- **Options block:** idéntico al binario estándar, con nombres propios — `Gana Alcaraz` / `Gana Zverev`. Nunca "Jugador 1".
- **Footer:** `Quiebre hace 2 min · Pozo 5,900 pts · 142 jugando`. El evento reciente va primero: es lo que explica por qué el porcentaje se movió.
- **Visual notes:** **115 px**. El game en curso (`40-30`) vive en el badge, no en la fila de marcador: cambia cada punto y ahí arriba se actualiza sin mover una sola caja. Al cerrarse un set, el número nuevo entra con `fade` de 120 ms y la fila destella `--up` 200 ms.

**Ejemplo B — Béisbol Live (LMP / MLB)**

```
┌──────────────────────────────────────────────────┐
│ ●LIVE  ALTA 7ª  2 out                ● Deportes  │  16 px
│ Naranjeros  4           Tomateros  3             │  20 px
│ ╭────────╮ Gana Naranjeros        Gana Tomateros │
│ │  64 %  │ paga 1.56×        36 %    paga 2.78×  │  36 px
│ ╰────────╯                                       │
│ ███████████████████████████░░░░░░░░░░░░░░░░      │   3 px
│ Corredores en 1ª y 3ª · Pozo 2,860 pts · 71 juga…│  11 px
└──────────────────────────────────────────────────┘   = 115 px
```

- **Header row:** `LIVE` · badge de entrada `ALTA 7ª` (mono 10 px, tinte `--live` 14 %) · badge de outs `2 out` (`--panel2`). La flecha de entrada se escribe con palabra (`ALTA` / `BAJA`), no con símbolo: se lee igual en voz alta.
- **Main content:** mismo patrón — nombre + carrera en 16 px 700. Sin escudos: a 390 px dos nombres de equipo de la LMP ya llenan la fila.
- **Footer:** el estado de bases en palabras (`Corredores en 1ª y 3ª`, `Bases limpias`), que es lo que mueve el precio en entradas finales.
- **Visual notes:** **115 px**. Al entrar una carrera, el número destella `--up` 200 ms y la barra transiciona 240 ms. Cambio de pitcher: el pie pasa 30 s a `Cambio de pitcher` en `--text2` antes de volver al estado de bases — es el momento de mayor apuesta de la categoría (§4.6).

**Fútbol (Liga MX)** conserva el patrón: badge de minuto `72'`, fila de marcador `América 2 · Santos 1` con escudos de 20 px sólo por encima de 360 px de ancho, y bloque 1X2 en formato multi-resultado (§3.4.4, 150 px).

**Regla dura para toda la familia:** sin oráculo de marcador vivo no hay badge `LIVE` ni fila de marcador — el mercado cae a binario con nombre. Una tarjeta "en vivo" sin estado del evento es exactamente la card vacía que este rediseño existe para eliminar.

#### 3.4.3 Binario con nombre (estándar)

- **Header row:** badge `HOT` si aplica · badge de país (`MX`, `BR`, `CO`…, 10 px, fondo `--panel2`) · a la derecha, marca de categoría (cuadro 6 px `--hot`) + `Economía`. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Banxico recorta la tasa en agosto`.

```
┌──────────────────────────────────────────────────┐
│ [HOT] [MX]                           ■ Economía  │  16 px
│ Banxico recorta la tasa en agosto                │  19 px
│ ╭────────╮ Recorta                      Mantiene │
│ │  54 %  │ paga 1.80×        46 %    paga 2.12×  │  36 px
│ ╰────────╯                                       │
│ █████████████████████░░░░░░░░░░░░░░░░░░░░░░      │   3 px
│ Pozo 2,240 pts · 38 jugando · Cierra el 8 ago    │  11 px
└──────────────────────────────────────────────────┘   = 114 px
```

- **Options block:** geometría fija de §3.1. Pill 36 px con `54` en **30 px / 700**; a su derecha el stack `Recorta` (13 px 600 `--text2`) sobre `paga 1.80×` (mono 12 px 500 `--muted`). Rival sin relleno a la derecha: `46 %` en 20 px, `Mantiene`, `paga 2.12×`. Barra binaria debajo.
- **Footer:** `Pozo 2,240 pts · 38 jugando · Cierra el 8 ago`.
- **Visual notes:** **114 px** con `shortTitle`; 133 px en el caso degradado de título a dos líneas. Sin `LIVE` y sin borde de color: sólo el mercado con posición propia abierta lleva borde `--line`. **El Edge no aparece aquí** en ninguna forma.

#### 3.4.4 Multi-resultado

- **Header row:** badges igual que el estándar · a la derecha, categoría. Alto 16 px.
- **Main content:** `shortTitle` en una línea — `Quién gana la elección en Chile`.
- **Options block:** las **tres** respuestas con más pozo, una por fila de 21 px + barra de 3 px, separadas 3 px:
  - fila = número en **20 / 22 `tabular-nums`** a la izquierda (ancho fijo de 46 px para que las tres columnas queden alineadas) · etiqueta `Gana Jara` (13 px 600 `--text2`, `truncate`) · `paga 2.44×` a la derecha (mono 12 px 500 `--muted`) · barra debajo, ancho proporcional.
  - Fila 1: número en `--text` con la pill rellena de `--teal-soft` (alto 26, `px-8`) y barra `--teal`. Filas 2 y 3: número en `--text2` **sin relleno** y barra `--muted`. Un solo bloque pintado por tarjeta, igual que en el binario.
- **Footer:** `+4 respuestas · Pozo 9,800 pts · 211 jugando · Cierra el 16 nov`. El `+N respuestas` va primero y en `--text2`: es la señal de que hay más detrás.
- **Visual notes:** alto **150 px**, excepción declarada al techo de 116 px — reemplaza la información de tres tarjetas, así que sigue siendo el formato más denso disponible. Nunca más de 3 filas, ni siquiera con hueco: la cuarta respuesta se lee en el detalle. Con exactamente 2 respuestas no es multi-resultado: es binario con nombre.

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

**Ventanas cortas, siempre encendidas.** BTC y ETH corren **ventanas de 5 y 15 minutos de forma continua**: al cerrar una vela se siembra la siguiente con el umbral recalculado sobre el spot. Esto sostiene la promesa de "siempre hay algo vivo" sin depender del calendario deportivo, y responde a lo que la gente pide en live: resolución corta. Requisitos: oráculo con cadencia ≤ 5 s, liquidación por vela cerrada de la misma fuente, y semilla de pozo (`SEED`) en cada ventana nueva para que el primero en entrar no vea un pago absurdo.

**Elegibilidad de "Live":** ventana ≤ 24 h —en la práctica 5 min, 15 min o 1 h—, precio de referencia programático, cierre y resolución leídos de la misma vela. Un mercado semanal de BTC no es Live: es binario con nombre.

**Techo:** máximo **4** tarjetas Cripto Live simultáneas (2 fijas + 2 rotatorias), y como mucho **2** suben a Hot ahora (§4.6). Degradación: oráculo atrasado > 5 min → se cae el badge; > 15 min → la tarjeta sale del riel Live y el feed lo declara con la franja de datos viejos que ya existe.

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
score = 0.34 · nivel_live
      + 0.22 · resolucion_corta
      + 0.18 · z(pozo)
      + 0.14 · z(participantes)
      + 0.12 · evento_reciente

nivel_live        Cripto 5/15 min ........ 1.00   (siempre disponible, alta rotación)
                  Tenis con momentum ..... 0.92   (break point o quiebre en los últimos 5 min)
                  Béisbol entradas 7+ .... 0.85   (o cambio de pitcher en curso)
                  Tenis normal ........... 0.75
                  Liga MX en juego ....... 0.70
                  Béisbol entradas 1-6 ... 0.60
                  Sin live ............... 0
resolucion_corta  1 − min(minutos_al_cierre / 120, 1)   → un mercado de 5 min vale 0.96;
                                                          uno que cierra en 2 h vale 0
evento_reciente   1 si hubo gol, quiebre, carrera o cambio de pitcher en los últimos 3 min;
                  decae lineal a 0 a los 10 min
```

La escalera de `nivel_live` es la prioridad pedida, escrita como número: Cripto Live manda porque siempre está y siempre resuelve pronto; el tenis sube cuando hay momentum, que es cuando la gente entra; el béisbol pesa en entradas finales y cambio de pitcher; Liga MX entra cuando hay partido en curso.

**Reglas de armado, en este orden:**
1. **Puerta de calidad (antes de ordenar).** Un mercado live sólo es candidato si tiene ≥ 8 apostadores **o** pozo ≥ p60 de su categoría. El volumen se concentra en pocos eventos calientes: diluir el riel con live mediocres cuesta más de lo que suma.
2. Ordenar los candidatos que pasaron la puerta por score descendente.
3. **Máximo 2 por categoría** — seis mercados de cripto no son un feed, son un ticker.
4. **Piso de Cripto Live: 1 slot garantizado**, techo 2. Siempre hay una ventana de 5 o 15 min viva, así que el riel nunca depende de que haya partido.
5. Si hay algún deporte en vivo que pasó la puerta, el de mayor score entra en el top 3.
6. Cortar en 5. Si el sexto tiene score ≥ 0,55, entra: **6**.
7. Si hay menos de 5 candidatos, completar con los mercados abiertos de mayor score hasta 5. El riel **nunca** muestra 4.
8. Ningún mercado con menos de `MIN_APOSTADORES` (2) entra en Hot: un pozo de una persona no está caliente.

**Reordenamiento:** el riel se recalcula cada 30 s, pero un mercado **no cambia de posición** hasta que su score difiere ≥ 10 % del que ocupa el lugar — misma histéresis que en §4.1. Una lista que se reordena bajo el dedo pierde la apuesta que ya estaba decidida.

El encabezado `Hot ahora` sigue siendo `sr-only`: los badges ya lo dicen y 36 px de cromo son un tercio de tarjeta.

### 4.7 Edge — dónde vive

`computeEdge()` y `EDGE_MIN_PP = 4` no se tocan. El Edge se muestra **sólo en el detalle del mercado**, bajo el bloque de probabilidad: `Aquí 62 % · Polymarket 69 % · Edge +7 %`, con `Base de la lectura` debajo. En el feed no hay Edge en ninguna forma: ni badge, ni borde teal, ni orden. La promesa de marca ("con edge") se cumple donde se decide, no donde se hojea — la tarjeta gana 5 px y pierde su nodo más ruidoso.

---

## 5 · Interacción y pulido

Cuatro animaciones en todo el sistema. Ninguna dura más de 240 ms y ninguna se repite salvo el pulso.

| Estado | Especificación |
|---|---|
| **Pulso LIVE** | Sólo el punto de 6 px `--live`: `opacity 1 → 0.4 → 1`, **2 s** `ease-in-out`, infinito. La palabra `LIVE` **no** parpadea y la barra tampoco: un solo elemento en movimiento por tarjeta, y es el más chico. Se detiene con `prefers-reduced-motion`. |
| **Actualización de probabilidad** | El número cruza con `fade` de 120 ms; la barra transiciona 240 ms `cubic-bezier(.22,1,.36,1)`. Sube → destello `--up` 200 ms sobre el número; baja → `--dn`. Umbral mínimo para animar: 0,5 pp — por debajo, el valor cambia sin animación. |
| **Marcador deportivo** | Al cambiar, destella `--up` 200 ms. El minuto, la entrada y el game (`40-30`) se refrescan sin animación: cambian demasiado seguido como para llamar la atención cada vez. |
| **Presionado — pill de porcentaje** | La pill es un `<button>` propio. `:active` → `scale(0.96)`, fondo a `color-mix(in srgb, var(--teal) 26%, var(--panel))`, anillo 1 px `--teal`, **90 ms** `ease-out`. En el rival, el número sube a `--text` (§10.A). Vibración de 8 ms si `navigator.vibrate` existe. Hover, foco y contrastes de cada estado en §10.B y §10.D. |
| **Selección de una opción** | Al soltar, la pill **queda armada** —anillo `--teal` de 1 px y fondo al 26 %— durante los 180 ms que tarda en abrir la hoja de detalle, y la hoja abre con **ese resultado preseleccionado**. El estado armado no sobrevive al cierre de la hoja: no es una selección persistente, es continuidad visual entre el toque y el destino. |
| **Presionado — resto de la tarjeta** | Tocar fuera de las pills abre el detalle sin preselección: fondo `--panel2`, `scale(0.985)`, 120 ms `ease-out`. Sin elevación. |
| **Cargando (feed)** | 5 esqueletos de **exactamente 114 px** con `animate-shimmer` (1,4 s). La altura clavada es lo que mantiene el CLS en 0. |
| **Cargando (acción)** | El botón conserva su ancho y cambia el texto (`Preparando…`), nunca se encoge. |
| **Vacío (filtro)** | `No hay mercados en esta categoría por ahora.` + `Ver todos los mercados`. |
| **Vacío (Hot)** | Sólo en arranque en frío u offline, cuando el motor devuelve menos de 2 mercados: un panel con forma de tarjeta (114 px, mismo radio y borde) con `Estamos armando los mercados de hoy.` y `Reintentar`. Con datos, la regla 4.6.7 garantiza 5. |
| **Vacío (Portafolio)** | `Todavía no tienes posiciones.` + `Ver mercados`. |
| **Error** | `ErrorState` con mensaje en español y `Reintentar`. Nunca un stack trace (R-008). |
| **Datos viejos** | Franja existente sobre el feed: `Esto es lo último que cargamos` + `Reintentar`. Se sigue mostrando el contenido. |
| **Cerrado** | El pie dice `Cerrado`; las pills bajan a `--muted` y la barra a 40 % de opacidad; la tarjeta sigue abriendo el detalle. |
| **Resolviendo** | Entre el cierre y la liquidación: badge `Resolviendo` (`--panel2` / `--text2`), pills sin hover ni active, barra al 40 %, pie en `Esperando la fuente` (§10.F). |
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
| 7.13 | `MarketCard` deja de ser un `<button>` envolvente: pasa a `<article>` + enlace estirado (`::after` absoluto) con las pills como `<button>` reales por encima. Es lo que permite el estado presionado de §5 sin anidar interactivos | `MarketCard.tsx`, pruebas de a11y | Medio — cambia la semántica que hoy leen las pruebas |
| 7.14 | Token nuevo `--pill-ring` (`--teal` al 55 % en oscuro, 65 % en claro). **Mueve `tokens.lock.json`** | `styles/tokens.css`, `vault/tokens.lock.json` | Bajo — único token nuevo del rediseño |
| 7.15 | Escala `prob-pill` 30 · `prob-riv` 20 · `prob-row` 20 · `mult` 12; pie a 11 / 11 con máscara en vez de `overflow-hidden` | `tailwind.config.ts`, `MarketCard.tsx` | Bajo |
| 7.16 | Cripto de 5 y 15 min siempre encendido: oráculo con cadencia ≤ 5 s, siembra automática de la vela siguiente, liquidación por vela | `oracles/priceOracle.ts`, `ownMarkets/templates.ts`, `scripts/settle.mts` | **Alto** — multiplica la frecuencia de liquidación; es el cambio con más superficie operativa |
| 7.17 | `nivel_live`, `resolucion_corta` y `evento_reciente` en el score de Hot, con histéresis de reordenamiento | `domain/feed.ts` (nuevo), `oracles/matchOracle.ts` (expone `ultimoEvento`) | Medio |
| 7.18 | `marcador` se vuelve estructurado: sets de tenis · entrada/outs/bases de béisbol · goles de fútbol | `domain/types.ts`, `oracles/matchOracle.ts`, `MarketCard.tsx` | Medio |
| 7.19 | Pruebas de contraste: agregar los pares de §9 en los dos temas | `tests/contrast.test.ts` | Bajo |

**Enmiendas de reglas que quedan escritas:** R-004 (el nodo de 44 px pasa al detalle; el porcentaje de 30 px en peso 700 es el dominante de la tarjeta), R-001 (el Edge sigue teniendo umbral de 4 pp, pero su superficie es sólo el detalle), R-063 (los dos lados siguen a la vista y ahora además tienen nombre propio).

---

## 8 · Apéndice — Verification Swarm

Cinco agentes revisaron el borrador completo. Ronda 1 con dos fallos, corregidos por el protocolo de recuperación; ronda 2 unánime.

| Agente | Ronda 1 | Ronda 2 |
|---|---|---|
| **1 · Design Critic** | PASS — densidad medida (114 px, −28,3 %), porcentaje de 30 px en peso 700 como nodo dominante, logo a 26 px, barras al píxel | PASS |
| **2 · Market Architect** | **FAIL** — el borrador dejaba `BINARY_OUTCOMES` con `Sí`/`No` como valor por defecto mostrable, y las plantillas de cripto seguían sembrando esas etiquetas | PASS — §3.3 prohíbe la etiqueta, `assertPublishable()` es la puerta, §7.6 declara la migración de los mercados ya sembrados |
| **3 · Consistency Guardian** | **FAIL** — el header perdía V12 (con saldo 0 la app no puede quedarse sin camino a recargar) al quitar el botón `Depositar` | PASS — §2.1 hace accionable el bloque de saldo; se conservan exactamente los dos elementos bloqueados |
| **4 · Implementation Readiness** | PASS — los cuatro tipos traen ejemplo estructurado; la aritmética de altura suma; §7 mapea cada cambio a su archivo | PASS |
| **5 · LATAM Voice** | PASS — Liga MX, LMP, Banxico, Cutzamala, Popocatépetl, mezcla mexicana, Servel/CNE/TSE; copy tuteado y sin anglicismos de relleno | PASS |

**Veredicto: 5/5 PASS.** Especificación emitida.

---

## 9 · Apéndice — Contraste WCAG, medido

Calculado sobre los hex reales de `src/styles/tokens.css` con la fórmula de luminancia relativa de WCAG 2.1, incluidas las composiciones alfa de los badges. Script reproducible en `tests/contrast.test.ts` (7.19).

**Tokens en juego**

| Rol | Oscuro (default) | Claro |
|---|---|---|
| Fondo de tarjeta (`--panel`) | `#102528` | `#ffffff` |
| Fondo de pill líder (`--teal-soft`) | `#12312f` | `#e2eeec` |
| Texto principal / % líder (`--text`) | `#eceae1` | `#12262a` |
| % rival, etiquetas (`--text2`) | `#b7c3c1` | `#3c5250` |
| Multiplicador, pie, categoría (`--muted`) | `#829290` | `#596a69` |
| Barra del líder (`--teal`) | `#4cbab2` | `#0b6b6e` |
| Barra del resto (`--muted`) | `#829290` | `#596a69` |
| Badge LIVE (`--live`) | `#ff6b5a` | `#b03a22` |
| Badge HOT (`--hot`) | `#e8a33d` | `#8a5a0b` |
| Variación ▲ / ▼ (`--up` / `--dn`) | `#43c989` / `#e5795e` | `#157048` / `#a8412b` |

**Ratios**

| Par | Objetivo | Oscuro | Claro |
|---|---|---|---|
| % líder vs tarjeta | ≥ 7 | **13,23** | **15,71** |
| % líder vs pill (`--teal-soft`) | ≥ 7 | **11,57** | **13,23** |
| % rival vs tarjeta *(sin relleno)* | ≥ 7 | **8,80** | **8,35** |
| Título vs tarjeta | ≥ 7 | **13,23** | **15,71** |
| Etiqueta de resultado vs tarjeta | ≥ 4,5 | **8,80** | **8,35** |
| Multiplicador vs tarjeta | ≥ 4,5 | **4,91** | **5,69** |
| Pie vs tarjeta | ≥ 4,5 | **4,91** | **5,69** |
| Barra del líder vs tarjeta | ≥ 3 | **6,81** | **6,28** |
| Barra del resto vs tarjeta | ≥ 3 | **4,91** | **5,69** |
| Badge LIVE vs su tinte al 14 % | ≥ 4,5 | **4,75** | **4,87** |
| Badge HOT vs su tinte al 14 % | ≥ 4,5 | **5,74** | **4,86** |
| Variación ▲ vs tarjeta | ≥ 4,5 | **7,56** | **6,10** |
| Variación ▼ vs tarjeta | ≥ 4,5 | **5,49** | **6,08** |
| Anillo `--pill-ring` vs tarjeta | ≥ 3 | **4,87** (teal @80 %) | **4,08** (teal @80 %) |
| Anillo `--pill-ring` vs relleno de la pill | ≥ 3 | **4,40** | **3,64** |
| Contorno `--pill-line` del rival vs tarjeta | ≥ 3 | **4,08** | **3,80** |
| % rival sobre su lavado al 4 % | ≥ 7 | **7,95** | **7,73** |

**El único fallo encontrado y cómo se corrigió.** El % del rival sobre una pill de `--panel2` daba **6,83:1 en tema claro** (`#3c5250` sobre `#ede8dc`), por debajo del objetivo de 7:1 para números grandes. Corrección: **el rival pierde el relleno** y su número se pinta sobre la tarjeta → 8,35:1. La corrección mejora además la jerarquía, porque deja un solo bloque pintado por tarjeta.

**Notas de método.**
- El riel vacío de la barra (`--line2` compuesto sobre la tarjeta) da 1,22:1 en oscuro y 1,16:1 en claro. Es correcto que sea bajo: el riel no porta información — la portan los dos segmentos, que cumplen ≥ 3:1 por separado. Lo mismo aplica al relleno de la pill líder (1,14:1 / 1,19:1), que es decoración; la jerarquía la cargan el tamaño (30 vs 20 px) y el texto.
- Los badges se miden contra su fondo compuesto real (color al 14 % sobre la tarjeta), no contra la tarjeta desnuda, que es lo que ve el ojo.
- El multiplicador en `--muted` pasa por 0,41 puntos en oscuro. Es el margen más chico del sistema: **`--muted` no puede oscurecerse más** sin romper el pie, la categoría y el multiplicador a la vez. Queda anotado como restricción, no como sugerencia.

**El significado nunca depende del color.** Cada resultado lleva su nombre escrito al lado del número (§3.3); la variación de precio lleva flecha **y** signo además de color; el estado activo de la nav cambia de peso además de color; la categoría lleva forma además de color (R-005); LIVE lleva la palabra además del punto. Quitando todo el color, la tarjeta se sigue leyendo entera.

---

## 10 · Pulido vFinal — pills, foco, estados y movimiento

Última pasada. No reabre densidad (114 px), resultados con nombre, jerarquía del porcentaje, marcador de Deportes Live ni los ratios de §9: los completa.

### 10.A · Equilibrio del % rival

El rival no recupera relleno sólido —fue lo que falló contraste en tema claro (§9)— pero deja de ser un número suelto en el aire. Tres cambios chicos, ninguno cuesta altura:

| Ajuste | Valor | Efecto |
|---|---|---|
| **Contorno** | 1 px `--pill-line`, radio 999, mismo alto de 36 px que la pill del líder | Le da forma y masa: dos objetos comparables, uno lleno y otro vacío |
| **Lavado** | `--pill-wash` = `--text` al 4 % sobre la tarjeta | Lo separa del fondo sin acercarse a un relleno: 1,11:1 contra la tarjeta |
| **Peso del número** | 600 → **650**, tamaño intacto en 20 px | Gana densidad óptica sin tocar el presupuesto de 114 px ni la proporción 30 : 20 |

Contraste del número (`--text2`) sobre el lavado: **7,95:1** oscuro · **7,73:1** claro. Sigue por encima de 7:1.

**Regla de color del número del rival, en todos sus estados:** `--text2` en reposo y hover; **`--text` en cuanto haya fondo teñido transitorio** (pressed, armado, destello de actualización). Con el fondo del `active` (teal al 26 %) el `--text2` caía a 5,27:1; con `--text` sube a 7,92:1 (oscuro) y 10,60:1 (claro). El número se enciende al tocarlo, que es además el feedback que se quiere.

### 10.B · Anillo de foco

```css
:root       { --pill-ring: color-mix(in srgb, var(--teal) 80%, transparent); }
/* mismo 80 % en los dos temas: el token resuelve contra el --teal de cada uno */

.pill {
  outline: 2px solid transparent;   /* siempre presente, nunca anima el ancho */
  outline-offset: 2px;
  border-radius: 999px;             /* el outline hereda el radio de la pill */
  transition: outline-color 90ms ease-out, background-color 120ms ease-out,
              transform 90ms ease-out;
}
.pill:focus-visible { outline-color: var(--pill-ring); }
```

- **Sólo `:focus-visible`**, nunca `:focus`: el dedo no deja anillo.
- **El ancho no se anima.** El `outline` vive siempre a 2 px en `transparent` y sólo transiciona el color, 90 ms. Animar el grosor produce un salto de pintado en cada tabulación.
- **`outline`, no `box-shadow`:** no participa del layout, así que no empuja nada dentro de una tarjeta de 114 px, y respeta el radio de la pill sin declararlo dos veces.
- **Convive con `pressed`:** el `outline` se transforma junto con la caja, así que con `scale(0.96)` el anillo encoge con la pill y el offset se mantiene proporcional. Foco y presión son visibles a la vez y no se pisan.
- **Se aplica igual a líder y rival**, con el mismo token: es el mismo control.

| Medida | Oscuro | Claro |
|---|---|---|
| Color resuelto | `#409c96` (teal @80 % sobre la tarjeta) | `#3c898b` |
| **Anillo vs fondo de tarjeta** | **4,87:1** | **4,08:1** |
| Anillo vs relleno de la pill líder | 4,40:1 | 3,64:1 |

Los dos superan el 3:1 de WCAG 1.4.11 con margen, en el fondo de la tarjeta (que es lo que rodea el anillo por el offset de 2 px) y también contra el relleno de la pill, que es lo que toca por dentro. El valor anterior de la propuesta (55 % / 65 %) daba 3,05 y 2,47:1 — el de tema claro **fallaba**, y por eso el token sube a 80 %.

### 10.C · Longitud del evento reciente

El texto no se trunca: **se construye acotado.** Gramática única, `<sustantivo> hace <n> min`, con vocabulario cerrado:

| Deporte | Sustantivos admitidos (≤ 9 caracteres) |
|---|---|
| Tenis | `Quiebre` · `Set` |
| Béisbol | `Carrera` · `Jonrón` · `Ponche` |
| Fútbol | `Gol` · `Roja` · `Penal` |
| Excepción sin tiempo | `Cambio de pitcher` (17 caracteres, dura 30 s) |

- `n` va de 1 a 9: a los 10 minutos el evento deja de ser reciente y el segmento desaparece. Con eso el máximo es **20 caracteres** (`Carrera hace 9 min`) y la excepción llega a 17. **Tope duro: 22 caracteres**, verificado en `assertPublishable()`; si un evento nuevo no cabe en la gramática, no se muestra.
- Nada de elipsis en este segmento: un `Quiebre hace…` no informa de nada.

**Prioridad del pie cuando no cabe** (320 px, o texto al 200 %): se elimina el segmento entero de menor prioridad, nunca se corta a media palabra.

1. Evento reciente / estado del evento — explica por qué se movió el precio
2. Pozo — es el tamaño de la apuesta
3. Cierre o estado del mercado
4. `N jugando` — el primero en irse

### 10.D · Hover y active de las pills

Hover sólo bajo `@media (hover: hover) and (pointer: fine)`. Sin ese guard, en móvil el estado se queda pegado después del toque y la pill parece seleccionada cuando no lo está.

| Estado | Pill del líder | Pill del rival |
|---|---|---|
| **Reposo** | Fondo `--teal-soft`, anillo 1 px `--pill-ring`, número `--text` | Lavado `--pill-wash`, contorno 1 px `--pill-line`, número `--text2` |
| **Hover** | Fondo → `color-mix(--teal 18%, --panel)`, anillo → `--teal` sólido, 120 ms `ease-out`. Sin desplazamiento ni sombra | Lavado → `color-mix(--teal 10%, --panel)`, contorno → `--pill-ring`, 120 ms |
| **Active** | Fondo → `color-mix(--teal 26%, --panel)`, `scale(0.96)`, **90 ms** `ease-out`, `navigator.vibrate?.(8)` | Igual, y el número **sube a `--text`** |
| **Armado** (180 ms, hasta que abre la hoja) | Mantiene el fondo del active y el anillo `--teal`, vuelve a `scale(1)` sin rebote | Igual |

Contraste del número en cada estado — ninguno baja de 7:1:

| Estado | Oscuro | Claro |
|---|---|---|
| Líder hover / active | 9,39 / 7,92 | 11,97 / 10,60 |
| Rival hover (`--text2`) / active (`--text`) | 7,34 / 7,92 | 7,21 / 10,60 |

Premium aquí significa **sobrio**: cambia el relleno y el anillo, y nada más. Sin sombras que crezcan, sin elevación, sin rebote. La pill se hunde 4 % y se enciende; eso es todo.

### 10.E · Movimiento — tabla completa

Filosofía Betfair: el dato se actualiza rápido, limpio y sin adorno; el movimiento que inicia el usuario puede tener carácter, el que inicia el servidor **jamás**. Por eso hay dos curvas y una sola regla que las separa.

| Qué | Duración | Curva | Detalle |
|---|---|---|---|
| **Cambio de %** | fade 120 ms + destello 200 ms | `ease-out` (sin overshoot) | El número cruza con opacidad; el fondo de la pill destella `--up` o `--dn` al 16 % (9,64:1 y 10,65:1 con `--text` encima). Umbral 0,5 pp: por debajo cambia sin animar |
| **Barra** | 240 ms | `cubic-bezier(.22,1,.36,1)` | Sólo `width`; nunca `transform: scaleX`, que deforma los extremos redondeados. Sin transición en el primer pintado |
| **Card → detalle** | 180 ms | `ease-out` | La tarjeta no se anima a sí misma: se queda quieta mientras la hoja sube. Animar las dos cosas a la vez es lo que hace sentir lento a un producto rápido |
| **Hoja de detalle** | **220 ms** (baja de 280) | `cubic-bezier(.22,1,.36,1)` | `translateY(100%) → 0`. Fondo oscurecido en 140 ms. Único movimiento del sistema con carácter, porque lo pidió el usuario |
| **Opción preseleccionada** | 140 ms | `ease-out` | La opción que se tocó ya entra elegida en la hoja: sólo aparece su anillo con fade. No repite el `scale` — ese gesto ya ocurrió en la tarjeta |
| **pressed → armado** | 90 ms + 180 ms de sostén | `ease-out` | Al soltar vuelve a `scale(1)` sin rebote y mantiene fondo y anillo hasta que la hoja toma la pantalla |
| **Pulso LIVE** | 2 s, infinito | `ease-in-out` | Sólo el punto de 6 px |
| **Esqueletos** | 1,4 s, infinito | `linear` | `shimmer` sobre cajas de altura exacta |

Nada supera 240 ms. `prefers-reduced-motion` apaga todo, incluidos destello y pulso: el número cambia, la barra salta a su ancho, y la información sigue completa.

### 10.F · Patrones que faltaban

Cinco, y sólo porque cada uno tapa un hueco real:

1. **El precio se congela mientras lo tocas.** Desde el `pointerdown` sobre una pill y hasta que la hoja termina de abrir, esa tarjeta **no aplica actualizaciones de %**: se encolan y entran al cerrar la hoja. Apostar a un número que cambió en el milisegundo del toque es el defecto clásico del live, y se arregla aquí, no con un diálogo de confirmación.
2. **Los porcentajes se alinean entre tarjetas.** La pill del líder tiene `min-width: 72px` y el número va en `tabular-nums`: los porcentajes de tarjetas consecutivas caen en la misma columna vertical. Es lo que permite barrer un feed de cinco mercados con un solo movimiento de ojo, y no cuesta un píxel de alto.
3. **Estado `Resolviendo`, que faltaba.** Entre el cierre y la liquidación había un hueco donde la tarjeta decía `Cerrado` como si ya hubiera terminado. Se agrega a `MarketStatus`: badge `Resolviendo` (10 px, fondo `--panel2`, texto `--text2`), pills sin hover ni active, barra congelada al 40 % de opacidad y pie en `Esperando la fuente`. Vivo, cerrado y resolviendo se distinguen de un vistazo, cada uno con palabra propia.
4. **La liquidez se nota sin cromo nuevo.** `N jugando` se pinta en `--text2` en vez de `--muted` cuando el mercado supera el p75 de participantes de su categoría. Un solo salto de color en un texto que ya estaba: se ve el mercado con gente sin agregar medidores ni iconos.
5. **La lista no se mueve bajo el dedo.** Ya está la histéresis de reordenamiento (§4.6); se agrega su consecuencia dura: **una actualización nunca cambia el alto de una tarjeta**. Si un dato nuevo no cabe en su segmento, se aplica la prioridad de pie de §10.C — jamás se envuelve una línea, porque envolver rehace el layout de la lista entera mientras alguien está apostando.

### 10.G · Deltas de esta pasada

| # | Cambio | Archivos | Riesgo |
|---|---|---|---|
| 7.20 | `--pill-ring` sube a `--teal` @80 % (el 55/65 % fallaba 1.4.11 en claro); altas de `--pill-line` y `--pill-wash` | `styles/tokens.css`, `vault/tokens.lock.json` | Bajo |
| 7.21 | Pill del rival: contorno + lavado + número en 650; regla de color por estado (`--text2` → `--text` con fondo teñido) | `MarketCard.tsx` | Bajo |
| 7.22 | Anillo de foco por `outline` con color transicionado, en líder y rival | `MarketCard.tsx`, `styles/tokens.css` | Bajo |
| 7.23 | Gramática cerrada del evento reciente (≤ 22 caracteres) y prioridad de segmentos del pie | `lib/strings.ts`, `domain/resolution.ts`, `MarketCard.tsx` | Bajo |
| 7.24 | `sheet-in` de 280 → **220 ms**; `--pill-ring` en el foco de las pills | `tailwind.config.ts` | Bajo |
| 7.25 | Congelado de actualizaciones por tarjeta mientras está presionada o con la hoja abierta | `state/store.ts`, `MarketCard.tsx` | **Medio** — hay que encolar por mercado, no globalmente |
| 7.26 | `MarketStatus` suma `settling`; badge, pie y bloqueo de interacción | `domain/types.ts`, `lib/strings.ts`, `MarketCard.tsx`, `scripts/settle.mts` | Medio |
| 7.27 | `min-width: 72px` en la pill del líder para alinear porcentajes entre tarjetas | `MarketCard.tsx`, `scripts/densidad.mjs` (verificar la columna) | Bajo |
| 7.28 | `N jugando` en `--text2` sobre el p75 de su categoría | `domain/feed.ts`, `MarketCard.tsx` | Bajo |
| 7.29 | Pruebas de contraste de los estados: hover, active, armado y destello, en los dos temas | `tests/contrast.test.ts` | Bajo |
