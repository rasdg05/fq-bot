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
| Color base | azul institucional | verde azulado profundo (`#0c1a1c`) |
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
