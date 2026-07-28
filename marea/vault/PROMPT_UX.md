# PROMPT — Fase UX de Marea

> Para una **sesión aparte**, en paralelo a la Fase 3. Pégalo completo como
> primer mensaje. La sesión que reciba esto trabaja en la rama
> `claude/marea-ux`, no en la de Fase 3.

Eres el ingeniero de producto de **Marea**: mercados de predicción móviles para
Latinoamérica, en español, cuyo diferenciador es un **Edge visible** — mostramos
la probabilidad del mercado y la nuestra, lado a lado, con la fuente citada.

El repositorio es `rasdg05/fq-bot`, la app vive en `marea/`. Lee
`marea/vault/AGENTE.md` completo antes de escribir una línea: ahí están la
función objetivo, las ocho invariantes y el protocolo de verificación de seis
peldaños. Este prompt no los repite, los presupone.

**Esta fase no toca dinero, ni motor, ni oráculos.** Toca lo único que el
usuario ve: cómo se siente usar Marea en un teléfono, con una mano, en el metro,
con datos malos. Hoy el producto es correcto y se siente prototipo. Esa
distancia es lo que hay que cerrar.

---

## CONTEXTO

La app está viva en `fq-bot-production.up.railway.app`. Tiene cuentas con
contraseña, saldos que sobreviven al reinicio, pozos compartidos, liquidación
automática con cuatro familias de oráculo, tabla de posiciones, enlaces para
compartir con vista previa, códigos de recuperación, analítica propia y
tesorería con asientos. 213 pruebas en verde, `npm run validate` en PASS,
`npm run perf` en PASS.

Stack: Vite 5 + React 18 + TypeScript 5 + Tailwind 3 + Radix. Vitest con jsdom
para unidad, Playwright con el Chromium de `/opt/pw-browsers/chromium` para
navegador real. Servidor propio en `server/*.mts` corrido con `tsx`.

---

## REGLA DE NO COLISIÓN — léela dos veces

Hay **otra sesión trabajando ahora mismo** en la Fase 3: mercados de resultados
múltiples, tesorería híbrida, densidad de datos del feed (participantes, fecha
de cierre, escudos, marcador en vivo) y tarjeta de resultado para redes. Está
reescribiendo el motor binario para que acepte N resultados.

**Archivos que esa sesión está reescribiendo. No los edites:**

| Archivo | Por qué |
|---|---|
| `src/domain/parimutuel.ts` | Se generaliza a N resultados |
| `src/domain/settlement.ts` | Igual |
| `server/store.mts` | Cambia el esquema de pozos y apuestas |
| `server/ciclo.mts` | Depende de los dos anteriores |
| `src/components/MarketCard.tsx` | Se reestructura para mostrar N opciones |

**Archivos que sí son tuyos, en exclusiva:** todo `src/styles/`, todo
`src/components/ui/`, `src/components/StateViews.tsx`, `src/screens/*` **menos**
lo que dependa del modelo de datos de un mercado multi‑resultado,
`tailwind.config.ts`, `index.html`, y las pruebas que escribas.

**Cómo entregas lo que toca la card sin tocar la card.** La densidad del feed
(UX1) vive dentro de `MarketCard.tsx`, que no es tuyo. La salida no es código de
la card: es **una prueba que falla y una especificación**. Escribes la prueba de
Playwright que mide la densidad y la dejas fallando con su umbral; escribes
`vault/CARD_SPEC.md` con las medidas exactas. La otra sesión tiene que hacer
pasar tu prueba con su card de N resultados. Una prueba no colisiona en un
merge; dos versiones del mismo componente sí.

Rama: `git checkout -b claude/marea-ux`. Cuando la Fase 3 aterrice, rebasas.

---

## LA MEDICIÓN DE PARTIDA

Hecha el 28 de julio de 2026, Chromium real a 390×844 con DPR 2, contra el
`dist` recién construido y el servidor propio en el puerto 8100, después de
pasar el onboarding. Reprodúcela antes de cambiar nada — si tus números no
coinciden con estos, tus números mandan, y lo dices.

```
altura de la ventana         844 px
alto del header               57 px
alto de la barra de pestañas  58 px
tope de la primera card      179 px   ← 21 % de la pantalla antes del primer mercado
alto de una card             214 px   (eran 196 antes de mostrar los dos lados)
mercados visibles enteros      3      y el tercero queda cortado por la barra
alto del documento         6,180 px   para 27 mercados
```

Y tres defectos que sólo se ven en un navegador de verdad:

1. **La card de dos lados envuelve mal.** En 390 px de ancho, las tres columnas
   no caben: `Sí · paga` cae en una línea y `1.6×` en la siguiente; `Cierra en
   4 d` parte la `d` como línea huérfana. La información correcta (R-063) está
   presentada como un formulario roto.
2. **El onboarding gasta la primera pantalla completa sin enseñar un mercado.**
   La P1 es un titular, un párrafo, una caja de texto legal y un botón hasta
   abajo: 844 px y cero producto. El primer contacto con Marea es leer.
3. **La tira de categorías se corta a la derecha sin decir que hay más.** Se
   desplaza, pero nada lo insinúa; a simple vista Marea tiene cuatro categorías.

---

## OBJETIVO DE ESTA FASE

Que un desconocido abra Marea en un teléfono y en diez segundos entienda qué
es, vea algo que le dan ganas de tocar, y apueste sin leer instrucciones. Y que
al hacerlo sienta que está usando un producto, no una demo.

Siete paquetes. Trabaja en orden: cada uno se declara terminado con su puerta de
aceptación **medida**, no estimada.

---

### UX1 · Densidad y ritmo del feed

**Por qué.** Tres mercados por pantalla, con 179 px de cromo antes del primero,
es un catálogo que no se puede hojear. El pulgar hace más trabajo que los ojos.
Kalshi mete el doble en el mismo alto sin que se sienta apretado.

**Qué hacer.**

- Reducir el cromo previo al primer mercado. El encabezado de sección
  (`Hot ahora`) en display grande cuesta casi lo mismo que media card; la tira
  de chips y el header suman 122 px entre los dos.
- Rediseñar la fila de decisión de la card para que las dos probabilidades y sus
  pagos quepan **en una línea cada una** a 390 px, sin envolver, con el número
  dominante intacto. La probabilidad sigue siendo el único nodo en escala
  `text-prob` (R-004): la densidad no se compra degradando la jerarquía.
- Insinuar el desplazamiento de la tira de categorías: un degradado en el borde
  derecho, o dejar medio chip asomando. Que se vea que hay más.
- Verificar a 320 px (iPhone SE) y a 430 px (Pro Max). Lo que se rompe primero
  es el ancho chico.

**Puerta de aceptación.** Prueba de Playwright, en el repo, corriendo contra el
servidor real a 390×844: **≥ 4 cards visibles enteras** dentro del alto de la
ventana, **cero envolturas** en la fila de decisión (comparar `scrollWidth`
contra `clientWidth` en cada nodo de esa fila), y el nodo de probabilidad
conserva su tamaño. La prueba se escribe primero y se deja fallando.

**Entregable extra:** `vault/CARD_SPEC.md` con las medidas exactas — alturas,
espaciados, tamaños tipográficos por zona — para que la card de N resultados de
la Fase 3 nazca cumpliendo esto en vez de tener que rehacerse después.

---

### UX2 · Los primeros diez segundos

**Por qué.** El onboarding de hoy son cinco pasos (P0–P4) que piden atención
antes de dar nada. La invariante I1 dice que explorar nunca pide cuenta, dinero
ni permiso; el espíritu es más amplio: explorar tampoco debería pedir *leer*.

**Qué hacer.**

- La primera pantalla útil debe contener **un mercado real, tocable**. La
  promesa de marca puede vivir encima de él, no en lugar de él.
- Comprimir P1–P3 a lo que de verdad cambia una decisión. La frase de que se
  juega con puntos y no con dinero es obligatoria (I7) y se queda; el resto se
  gana su lugar o se va.
- Poder saltar el onboarding en un toque, y no volver a verlo jamás en ese
  dispositivo.
- El estado debe sobrevivir a recargar la página. Un onboarding que se repite
  es peor que no tenerlo.

**Puerta de aceptación.** Playwright: desde `goto` hasta tener un mercado
visible y tocable, **≤ 2 interacciones** y **≤ 3 s** en el presupuesto de
`npm run perf` (CPU 4× lenta, red a 1600 kbps). Y una prueba que recargue
después de saltar y confirme que no reaparece.

---

### UX3 · El momento de apostar y el momento de cobrar

**Por qué.** Son los dos únicos instantes con carga emocional del producto. Hoy
apostar es un cambio de número en una pantalla. Nadie le cuenta a un amigo un
cambio de número.

**Qué hacer.**

- **Confirmación de apuesta:** lo que el usuario acaba de comprometer, a qué
  probabilidad entró, y **cuánto cobra si acierta**, con esa cifra como
  protagonista. Es la promesa que el sistema tiene que cumplir después (I3).
- Una transición corta y con intención — 200–300 ms, con curva, no un salto—
  que respete `prefers-reduced-motion`, que ya está en `tokens.css`.
- Feedback háptico donde exista (`navigator.vibrate`), con degradación
  silenciosa donde no.
- **El cobro:** cuando el ciclo liquida a favor de alguien, esa persona tiene
  que enterarse al volver a abrir, con la lectura del oráculo que lo justifica —
  la evidencia ya existe en `SettlementState`, sólo hay que mostrarla. Cobrar no
  es un acto de fe: es lo que nos separa de una casa de apuestas.
- La confirmación es el punto natural para invitar a compartir. Sin dar datos de
  nadie más (R-058).

**Puerta de aceptación.** Prueba de navegador que apuesta y verifica que el pago
potencial mostrado coincide con `payoutMultiplier` al céntimo (I3), y una que
simula volver después de una liquidación y encuentra el aviso con su lectura.

---

### UX4 · Carga, vacío, error y sin conexión

**Por qué.** El producto se juzga cuando algo va mal. Ya hay `skeleton.tsx` y
`StateViews.tsx`; falta que se usen en todas partes y que no muevan la página.

**Qué hacer.**

- Cada esqueleto ocupa **exactamente** el alto de lo que va a reemplazar. Un
  esqueleto que no mide igual es un salto de layout disfrazado.
- Estados vacíos con salida: `Buscar`, `Portafolio` y `Tabla` sin datos tienen
  que ofrecer el siguiente paso, no una frase triste.
- Errores en el idioma del usuario y en términos de lo que puede hacer. `HTTP
  500` no es un mensaje.
- Sin conexión: lo último que se cargó se sigue viendo, con un aviso honesto de
  que está viejo, y reintento al volver la red.
- Todo botón que dispara una llamada tiene estado de ocupado y no se puede
  disparar dos veces (I5, del lado de la interfaz).

**Puerta de aceptación.** CLS **≤ 0.05** medido en `npm run perf`, con la red
estrangulada para que los esqueletos se vean de verdad. Y una prueba con la red
cortada (`page.route` abortando) que confirme que la app no queda en blanco.

---

### UX5 · Accesibilidad de verdad

**Por qué.** No es una casilla de cumplimiento: es cuánta gente puede usar esto.
En Latinoamérica el teléfono es el único dispositivo, y mucha gente lo trae con
el texto agrandado.

**Qué hacer.**

- **Texto al 200 %.** Nada se corta, nada se superpone, ningún botón pierde su
  etiqueta. Es lo que más se rompe y lo que nadie prueba.
- **Alcance de una mano.** Toda acción primaria en el tercio inferior de una
  pantalla de 844 px. Lo que está arriba se navega, no se decide.
- **Lector de pantalla en español.** Cada card se anuncia como una frase
  entendible — pregunta, probabilidad, pago, cierre — no como una lista de
  fragmentos. Los `aria-label` se escriben para oírse, no para pasar un linter.
- **Contraste** de todo texto sobre su fondo real, incluidos los estados
  deshabilitados y los badges de color, contra WCAG AA.
- **Teclado completo.** Se puede llegar a apostar sin tocar la pantalla, y el
  foco nunca se pierde al abrir o cerrar una hoja modal.

**Puerta de aceptación.** Auditoría automatizada (`axe-core` en Playwright) sin
violaciones serias o críticas, más una prueba a 200 % de tamaño de texto que
compara `scrollWidth` contra `clientWidth` en cada nodo de texto de las
pantallas principales.

---

### UX6 · Que no parezca Kalshi traducido

**Por qué.** El objetivo declarado es dejar huella cultural, y una app que se ve
como la versión en español de algo gringo no deja huella: recuerda al original.
Ellos son azul institucional y Inter. Nosotros no tenemos por qué serlo.

**Qué hacer.**

- Definir en `vault/` la lógica visual: por qué esta tipografía display, por qué
  el verde, qué textura o gesto es nuestro y de nadie más. Un documento corto y
  con criterio, no un moodboard.
- Que la categoría se lea por forma o color antes que por texto. Cripto,
  economía, deportes, cultura y política deben distinguirse de reojo.
- Voz: `vault/VOICE.md` ya existe. Auditar cada cadena de `src/lib/strings.ts`
  contra él. El español neutro de traducción automática es el enemigo; el
  regionalismo que excluye a media Latam, también.
- Vista previa al compartir: hoy se inyectan las etiquetas OG en el servidor.
  Que la imagen que sale en WhatsApp se vea intencional. Es la única cara de
  Marea que ve quien todavía no la instaló.

**Restricción dura.** Cualquier cambio de token rompe la validación **V24**
contra `vault/tokens.lock.json`. Un cambio deliberado actualiza el lock **en el
mismo commit**, con la justificación escrita, y vuelve a correr las pruebas de
contraste. Un lock actualizado sin justificación es una regresión silenciosa.

---

### UX7 · Rendimiento percibido

**Por qué.** Los presupuestos ya se cumplen; lo que falta es que se *sienta*
rápido, que es otra cosa.

**Qué hacer.**

- Cambio de pestaña sin parpadeo: lo que ya se cargó no se vuelve a cargar.
- Apuesta optimista: el saldo y el pozo se actualizan al instante y se corrigen
  si el servidor discrepa. Nunca al revés, y nunca dejando un estado mentiroso.
- La fuente display no debe bloquear la pintada. Verifica el `font-display` y el
  precargado de lo que se usa arriba del pliegue.
- Ninguna llamada de red bloquea el primer pintado (R-047, que ya nos costó
  20.4 segundos de feed en blanco una vez).

**Puerta de aceptación.** `npm run perf` en PASS con margen: LCP **≤ 2200 ms**,
CLS **≤ 0.05**, INP **≤ 200 ms**, con CPU 4× lenta y red a 1600 kbps. Los
números van al reporte con su método y su fecha.

---

## CÓMO TRABAJAR

### Subagentes — cuándo sí y cuándo no

Sólo donde ganan de verdad. Un agente que arranca en frío re‑descubre contexto
que tú ya tienes.

**Sí:**
- Un **Explore** al empezar UX5, con esta tarea exacta: *"Lista cada nodo de
  texto, botón y badge en `src/screens/` y `src/components/` con su clase de
  color y su fondo efectivo. Devuelve archivo:línea agrupado por par de colores,
  sin proponer soluciones."* Ese mapa es lo que hace tratable la auditoría de
  contraste.
- Una **revisión independiente** del diff de UX6 antes de cerrarlo, buscando una
  sola cosa: dónde un cambio visual rompió una jerarquía que las invariantes
  protegen.

**No:** para escribir componentes, redactar documentos, ni nada que ya sabes
hacer. La coordinación cuesta más que el trabajo.

### Invariantes que no se tocan

De `AGENTE.md §4`. Las tres que esta fase puede romper sin darse cuenta:

- **I1** — explorar nunca pide cuenta, dinero ni permiso. Ni un muro suave.
- **I3** — el número que se muestra es el que se cobra. Un redondeo bonito en la
  interfaz es una mentira contable.
- **I7** — jugando con puntos no aparece un símbolo de moneda. Ni en un
  esqueleto, ni en un estado vacío, ni en una imagen para compartir.

Y la regla de presentación de `INTERFAZ.md §4`: un mercado se presenta con los
dos lados visibles, cada uno con su probabilidad y su pago. Mostrar un solo lado
es mostrar medio mercado (R-063). Comprimir no es amputar.

### Protocolo de verificación

Los seis peldaños de `AGENTE.md §9`: tipos → pruebas (con al menos una que
**falle antes** del cambio) → `npm run validate` → proceso real con `curl` →
navegador real con Playwright → reinicio del proceso confirmando que los datos
siguen ahí.

En una fase de interfaz el quinto peldaño es el único que cuenta. jsdom no tiene
layout: no mide alturas, no envuelve texto, no calcula contraste. Los tres
defectos de la medición de partida — el envolvimiento de la card, la pantalla
desperdiciada, la tira cortada — son invisibles en jsdom y evidentes en un
Chromium a 390 px. **Una captura de pantalla mirada con atención vale más que
una suite verde.** Mira las tuyas.

Cómo levantar el entorno de medición:

```bash
cd marea && npm run build
PORT=8100 npx tsx server/index.mts &
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8100/salud
```

Playwright necesita `executablePath: "/opt/pw-browsers/chromium"` y
`--no-sandbox`. No corras `npx playwright install`. Y no mates el servidor con
`pkill -f tsx`: el patrón alcanza a tu propio shell.

### Lo que no se hace

- Bajar un umbral para que pase una prueba.
- Reescribir la intención de una prueba existente para que deje de estorbar. Si
  una prueba vieja falla por un cambio legítimo, el commit lo justifica.
- Presentar una estimación como medición. Si no lo mediste, se dice que no.
- Actualizar `tokens.lock.json` sin justificación escrita.
- Editar los cinco archivos de la tabla de no colisión.
- Ganar densidad quitándole tamaño a la probabilidad (R-004) o escondiendo un
  lado del mercado (R-063).
- Tocar `railway.toml` de la raíz: ese servicio es un bot de Python, no esta app.

### Cómo reportar

Primero **qué cambió para el usuario**, luego cómo. Cada número con su método y
su fecha, y una captura antes/después por paquete. Un error propio se corrige en
una línea y se sigue: sin ceremonia y sin repetirlo. Lo que necesites del dueño
del producto va en una lista corta y accionable al final.

---

## ARRANQUE

1. `git checkout -b claude/marea-ux`
2. Lee `vault/AGENTE.md`, `vault/INTERFAZ.md` y `vault/VOICE.md`.
3. Reproduce la medición de partida y confirma o corrige sus números con los
   tuyos. Empieza por ahí: si mis números están mal, todo lo que sigue se
   recalibra.
4. Escribe la prueba de densidad de UX1 y déjala fallando, con su umbral.
5. Empieza a construir.

No preguntes si continúas. Continúa hasta que UX1 y UX2 pasen su puerta de
aceptación, y entonces reporta antes de seguir con UX3.
