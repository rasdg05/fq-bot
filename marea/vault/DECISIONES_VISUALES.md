# DECISIONES VISUALES — por qué Marea se ve como se ve

Documento corto y con criterio. No es un moodboard: cada entrada existe porque
cambió una decisión, y dice qué se descartó.

---

## Por qué no puede parecer Kalshi traducido

El objetivo declarado es dejar huella cultural. Una app que se ve como la
versión en español de algo gringo no deja huella: recuerda al original. Ellos
son azul institucional y una gruesa neutra —Inter—, el lenguaje visual del
fintech estadounidense. Copiar eso nos deja compitiendo en su terreno con menos
presupuesto.

| | Kalshi | Marea |
|---|---|---|
| Color base | azul institucional | azul marino profundo (`#0d1627`) con azul eléctrico de acento y color pleno por categoría |
| Tipografía de titular | grotesca neutra | serif de display |
| Número dominante | grande, neutro | grande, **serif**, con el `%` en superíndice |
| Tono | mercado financiero | quiniela |

### El verde azulado, no el azul

El azul es el color por defecto de todo producto financiero, y por eso no dice
nada. El verde azulado profundo es agua: Marea se llama Marea. Además se
distingue en una captura de pantalla compartida en un grupo de WhatsApp, que es
donde de verdad nos van a ver por primera vez.

### La serif en el número

La probabilidad es el nodo dominante (R-004) y va en serif de display. Es la
decisión que más nos separa: nadie en mercados de predicción pone el número
principal en serif porque "los números van en grotesca". Un `54%` en serif se
lee como una cifra de periódico, no como un ticker — y la referencia cultural
del producto es la quiniela, no el terminal de Bloomberg.

### La quiniela, no el terminal

Todo el vocabulario sale de ahí: **pozo**, no "liquidez". **Paga 1.8×**, no
"odds". **Le atinaste**, no "posición ganadora". Es lo que ya sabe decir la
gente a la que le hablamos, y no hay que enseñárselo.

---

## Cambios de token, con su razón

`vault/tokens.lock.json` congela los valores. Un cambio sin justificación
escrita es una regresión silenciosa, así que aquí queda cada uno.

### 2026-09-25 · Rediseño vibrante: color, fichas y feed por secciones

Encargo de RasDG, un día después del rediseño limpio: «está muy aburrido…
colores más vibrantes como Polymarket… más mercados y más diseños». Sustituye
la paleta del 24; lo demás de ese rediseño (controles de 12 px, etiquetas en
tipo oración, cifras tabulares, esmerilado) se queda.

**Qué cambió.**

| | 24-sep (limpio) | 25-sep (vibrante) |
|---|---|---|
| Fondo noche / día | carbón `#1b1a18` / marfil `#faf9f5` | marino `#0d1627` / blanco azulado `#f4f6fb` |
| Acento (`--teal`) | teal `#5db8ad` / `#0c6b66` | azul eléctrico `#4d9bff` / `#1d5fe0` (el nombre del token no cambia: son 200 clases) |
| Sí / No (`--up`, `--dn`) | apagados | verde `#22c983` y rojo `#ff5c70` |
| Categorías | las de v6 | color pleno (cripto naranja, economía índigo, deportes verde…) |
| Botón principal | teal plano | degradado acento → cian con halo |
| Tokens nuevos | — | `--coin-btc/eth/sol/xrp/doge`: color de marca de cada moneda |

**Diseños nuevos.**

- **Ficha del mercado** (`AvatarMercado`, 38 px en la card, 52 en el detalle):
  los dos escudos de ESPN en un partido, la moneda en su color en cripto, el
  glifo de la categoría sobre degradado en lo demás. Abarca la fila de categoría
  y el título, así que **no suma alto**: la card sigue en 116 / 121 px. Sustituye
  al azulejo de 16 px y hereda su `data-testid="categoria-marca"`.
- **Pestañas en pastilla** con el glifo de la categoría y relleno de su color
  cuando mandan (antes texto con raya). Separación de 20 → 8 px: la forma
  separa (`tests/mobile.test.tsx` actualizado).
- **Feed por secciones**: Cripto, Liga MX, MLS, NFL, MLB… con encabezado, conteo
  y «Ver N más» a partir de la quinta card. Con 70 mercados, una lista plana
  obligaba a leer cada título.
- **Carrusel destacado** con filo en degradado (categoría → acento → cian).
- **Barras de lado**: verde para sí/arriba, rojo para no/abajo, en la card y
  como relleno proporcional de cada respuesta en el detalle. **En partidos no**:
  pintar a un equipo de rojo lo haría «el malo»; ahí va el acento.
- El badge «LATAM» ya no sale en cada card: sólo cuando nombra un país.

**Sobre «no puede parecer Kalshi traducido».** La tabla de arriba se escribió
para diferenciarnos del azul institucional. Esta paleta también es azul, pero
eléctrico sobre marino y con color por categoría; y lo que de verdad nos separa
se queda: el número en serif, el `%` en superíndice y el vocabulario de quiniela.
La decisión de ir hacia el lenguaje de Polymarket es de RasDG.

**Medido.** Contraste verde en ambos temas (texto dominante ≥ 8:1, categorías
≥ 3:1). `npm run densidad` contra el servidor propio **pasa entero por primera
vez**: 5 cards enteras a 390 px (antes 3, por falta de mercados), card 116 / 121
px sin cambio, cromo 121 px, 0 envolturas, 49 imágenes con medidas y `lazy`.

### 2026-09-24 · Rediseño «limpio»: neutros cálidos, teal de acento

Encargo de RasDG: más moderna y más limpia, «desde los moldes hasta los botones».

**Qué cambió.**

| | antes | ahora |
|---|---|---|
| Superficies | verde azulado (`#0c1a1c` / `#102528` / `#15292b`) | carbón cálido (`#1b1a18` / `#232220` / `#2b2a27`); de día marfil (`#faf9f5` / `#ffffff` / `#f1efe8`) |
| Filetes (`--line`, `--line2`) | teñidos de teal | el color del texto al 12 % y al 7 %: separan sin colorear |
| Teal | fondo de marca + bordes + tab activa | **sólo acento**: CTA, selección, raya de pestaña, barra del líder |
| Cifras (`--font-mono`) | monospace del sistema | la misma grotesca con dígitos tabulares (`.font-mono`) |
| Botones y controles | cápsula (`rounded-pill`) | rectángulo de 12 px (`rounded-ctl`); cápsula sólo en badges |
| Etiquetas | MAYÚSCULAS espaciadas en negrita | tipo oración, 13 px, peso medio |
| Badges | contorno de color | lavado del color al 14 %, sin contorno |
| Header y barra | fondo sólido | esmerilado: `color-mix` sobre `--bg` + `backdrop-blur` (R-017 intacta) |
| `--pill-line` | `--text2` al 60 % / 70 % | 38 % / 42 %: el rival se lee sin pelear con el líder |

**Por qué.** El teal en todo (fondos, bordes, pestaña activa) hacía que nada
destacara. Con las superficies neutras, el acento vuelve a significar «aquí se
actúa». La serif en el número y el vocabulario de quiniela no se tocan: siguen
siendo lo que nos separa de Kalshi.

**Medido.** `tests/contrast.test.ts` en verde en los dos temas (texto dominante
≥ 8:1, `--muted` sobre `--panel2` ≥ 4.5:1, categorías ≥ 3:1). Densidad (`npm run
densidad` contra el servidor propio): card 116 / 121 px, sin cambio; cromo
previo 123 → **119 px**. Los colores de categoría no cambian.

**Qué se descartó.** Llevar el acento al terracota de otras apps: Marea es agua y
su acento es el teal. Tampoco se apagó el tema oscuro por defecto: se entra de
noche y desde WhatsApp.

**Fuera del alcance.** `DepositSheet.tsx` y `WalletScreen.tsx` son zona del
segundo dev (`COLA_TRABAJO.md` §1): heredan los tokens nuevos, pero conservan
sus etiquetas en mayúsculas hasta que él las toque.

### 2026-07-28 · `--muted` sube de contraste

| | antes | ahora | contraste sobre `--panel2` |
|---|---|---|---|
| oscuro | `#7e8e8c` | `#829290` | 4.43:1 → **4.67:1** |
| claro | `#5d6e6d` | `#596a69` | 4.39:1 → **4.65:1** |

**Por qué.** `--muted` sobre `--panel2` no llegaba a AA (4.5:1) en **ninguno**
de los dos temas. `--panel2` es la superficie más clara del sistema y es donde
vive la zona de decisión del detalle y el bloque de error, así que el texto que
menos contrastaba estaba justo donde más importa entender.

**Por qué no se había visto.** `tests/contrast.test.ts` no probaba **ningún**
par sobre `panel2`. La prueba daba verde sin llegar a mirar el caso peor. Se
agregaron los pares que faltaban —`panel2` entero y el bloque `teal-soft`— y
fallaron antes de tocar el token, que es como se supo que el defecto era real.

**Qué se descartó.** Oscurecer `--panel2` habría aplanado la jerarquía de
superficies (`bg` → `panel` → `panel2` dejaba de leerse). Subir `--muted` sólo
en el tema oscuro habría dejado el claro roto. El ajuste es el mínimo que pasa
con margen: al filo, un redondeo futuro lo devuelve abajo.

**Efecto colateral medido.** Ningún otro par bajó: `--muted` sobre `--panel`
pasa de 4.66 a 4.91 (oscuro) y de 5.36 a 5.69 (claro); sobre `--bg`, de 5.20 a
5.48 y de 4.83 a 5.13.

---

## Lo que no se toca

- La probabilidad es el único nodo en escala `text-prob` (R-004).
- Todo color con significado lleva además texto o forma: el color nunca es el
  único portador (R-005). Un Edge negativo no apunta hacia arriba.
- Ningún color de token lleva modificador de opacidad de Tailwind: un color
  declarado como `var(--x)` no admite alfa y la declaración se descarta,
  dejando la superficie transparente (R-017).
- Los dos temas declaran exactamente los mismos tokens: cero drift (R-012).
