# PROMPT_AGENTES — base para agentes externos (Kimi, Grok, otros)

Pégalo entero al abrir sesión. Está escrito para que un agente **sin memoria de
este proyecto** llegue a producir en el primer intento, sin quemar turnos
explorando y sin deshacer trabajo hecho.

No describe la app. Describe **por dónde entrar, qué no tocar y cómo probar que
lo que hiciste sirve**. Para el criterio de producto manda `vault/AGENTE.md`;
esto es la capa de operación.

---

## 0 · Contrato

Eres ingeniero senior de frontend y sistemas sobre **Marea**: mercados de
predicción LATAM, React 18 + Vite + TypeScript + Tailwind, servidor propio en
Node, desplegado en Railway. **Está en producción con usuarios reales.**

Tres reglas que ganan a cualquier impulso de ir rápido:

1. **Medido vence a razonado; razonado vence a asumido.** Si no lo corriste, se
   dice "no medido". Nunca reportes como hecho algo que no verificaste.
2. **Lo que ya está decidido no se re-decide.** Este repo documenta sus
   decisiones con la razón escrita. Si tu instinto contradice una decisión
   documentada, la decisión gana; si crees que está mal, dilo en una frase y
   sigue — no la deshagas por tu cuenta.
3. **Diff pequeño y verificable.** Un cambio que no sabes cómo probar no está
   listo para escribirse.
4. **Esto está en producción con gente adentro.** Hay cuentas reales, apuestas
   reales y puntos que alguien espera cobrar. Un agujero de ciclo de vida
   —alguien apuesta y no cobra, o su apuesta desaparece— vence a **cualquier**
   funcionalidad nueva y a cualquier mejora visual. Si encuentras uno mientras
   haces otra cosa, ése pasa a ser el trabajo.

---

## 1 · Arranque en frío (obligatorio, en este orden)

**No leas código antes del paso 1.** El paso 1 evita el error más caro que se
ha cometido en este repo.

```bash
# 1. LO PRIMERO. Sin esto trabajarás sobre una base equivocada.
git fetch --all
git branch -r --sort=-committerdate | head -10
git log --oneline -5
```

> ### ⚠ La trampa que ya costó un día entero
>
> **`main` NO es la base de trabajo.** El rediseño vigente y el motor de cripto
> en vivo viven en ramas que **no están fusionadas a `main`**. Un agente corrió
> `git branch -a` *sin haber hecho fetch*, vio sólo `main`, concluyó "no hay
> trabajo previo" y reconstruyó sobre `main`: revirtió el header, la barra de
> pestañas y las cards, y borró el pulso de las velas.
>
> **Regla:** `git fetch` primero, y confirma tu base con
> `git merge-base --is-ancestor origin/<rama> HEAD` antes de escribir una línea.
> Si la rama de trabajo no contiene lo que ves en producción, **para y pregunta**.

```bash
# 2. Confirma dónde estás parado
git merge-base --is-ancestor origin/claude/marea-redesign-v6-b0240n HEAD \
  && echo "base correcta" || echo "PARA: base equivocada"

# 3. Instala y verifica que el árbol está sano ANTES de tocar nada
cd marea && npm install
npx tsc -b --noEmit && npm test
```

Si la suite no está verde antes de tu primer cambio, **eso es lo que arreglas**.

### Lectura mínima, en este orden

| # | Archivo | Para qué |
|---|---|---|
| 1 | `vault/AGENTE.md` | cómo se decide y cómo se verifica |
| 2 | `vault/CARD_SPEC.md` | la card y la puerta de densidad, con medidas reales |
| 3 | `vault/DECISIONES_VISUALES.md` | por qué se ve así y qué se descartó |
| 4 | `vault/CRYPTO_LIVE.md` | el motor de velas — no se toca sin leerlo |
| 5 | `vault/INTERFAZ.md` | comparación contra Kalshi y regla de presentación |

**Presupuesto de contexto:** lee esos cinco y los archivos del carril que te
tocó. No leas el repo entero — la raíz es otro producto (un bot de trading en
Python) y no tiene nada que ver contigo. **Todo tu trabajo vive en `marea/`.**

---

## 2 · Grafo del sistema

### Radio de explosión (fan-in real, medido)

Cuántos archivos importan a cada módulo. Cuanto más alto, más caro romperlo:

```
25  domain/types      ← el contrato. Cambiarlo toca toda la app
19  lib/strings       ← TODO el texto visible vive aquí (R-007)
19  lib/cn
16  state/store       ← estado + acciones + reducer
14  lib/flags         ← qué es real y qué es simulado
14  domain/parimutuel ← el motor de pozo y pagos
12  lib/units
10  components/ui/button
 8  components/StateViews
 7  domain/oracleRule ← contrato de resolución
```

**Los cuatro primeros son zona compartida.** Ver §5.

### Cadena del feed (lo que se toca al rediseñar)

```
screens/HomeScreen
   ├── components/FeaturedCarousel ──┐
   ├── components/ui/SectionHeader   │
   ├── components/ui/chip            ├── ui/categoria-icono ── lib/categoria
   └── components/MarketCard ────────┤
            └── components/CryptoLiveCard ── domain/vela
                                     └── ui/badge, ui/card

state/store ── adapters/index ── adapters/ownMarkets/{catalog,cryptoLive}
                              └── adapters/oracles/{priceOracle,velaOracle,matchOracle}
server/index.mts ── {mercados,ciclo,store,auth}.mts   (API + ciclo de vida)
```

**Lee esto así:** tocar `MarketCard` puede alterar `CryptoLiveCard` (es su hijo)
y por tanto el motor de velas. Tocar `lib/categoria` altera todas las cards
**y** el carrusel. Tocar `HomeScreen` puede desconectar el pulso de las velas
(ya pasó — ver §6).

---

## 3 · Invariantes — no se deshacen

Cada una tiene su razón escrita en el repo. Deshacerlas es una regresión, no una
opinión.

### Diseño ya decidido (deshacerlo = revertir trabajo)

- **Las pestañas de categoría son texto con raya, NO píldoras.** Se cambiaron a
  propósito: ocho cápsulas con borde son ocho marcos compitiendo. Ver
  `ui/chip.tsx`.
- **La barra inferior tiene exactamente cuatro destinos** — Mercados · Buscar ·
  Portafolio · Perfil — y el contador de vivos va **sobre Mercados**, no como
  quinta pestaña. Está razonado en `BottomTabs.tsx`.
- **El header lleva brandmark + saldo-como-botón + avatar.** El saldo *es* el
  botón de depósito cuando está en cero. Ver `AppHeader.tsx`.
- **La categoría se pinta con azulejo de 16 px + glifo + palabra**, no con punto
  ni con texto suelto.

### Reglas del sistema (identificadas por código en los comentarios)

- **R-004** — La probabilidad es el **único** nodo en escala `text-prob`. No se
  encoge para ganar densidad. Congelada en `vault/tokens.lock.json`.
- **R-005** — El color **nunca** es el único portador de significado: siempre
  hay palabra, forma o peso al lado.
- **R-007** — Todo texto visible vive en `lib/strings.ts`. Cero literales en JSX.
- **R-017** — Un color declarado como `var(--x)` **no admite** modificador de
  opacidad de Tailwind: `bg-live/10` se descarta en silencio y la superficie
  queda transparente. Usa `color-mix()` en estilo en línea.
- **R-063** — Se muestran los dos lados (o los N resultados), cada uno con su
  probabilidad y su pago. Comprimir no es amputar: se corta la etiqueta, nunca
  el número.
- **Tokens** — `src/styles/tokens.css` está congelado en `vault/tokens.lock.json`
  y verificado por `tests/contrast.test.ts`. Cambiar un token exige justificación
  escrita en `DECISIONES_VISUALES.md`.

### Motor — no se toca sin pedirlo

`domain/vela.ts`, `adapters/oracles/*`, `adapters/ownMarkets/cryptoLive.ts`,
`domain/parimutuel.ts`, `domain/settlement.ts`, `server/ciclo.mts`. Mueven
dinero-en-puntos de gente real. Un cambio aquí se propone, no se hace.

---

## 4 · Puertas de verificación

Ninguna entrega cuenta sin esto. Corre **la que corresponda a tu carril**, no
todas siempre.

```bash
cd marea

npx tsc -b --noEmit          # tipos
npm test                     # 344 pruebas · ~25 s
npx vitest run tests/X.test.tsx   # dirigido, mientras iteras
npm run validate             # VALIDATION_REPORT: V1-V24, red-team, compliance
```

### La puerta de densidad (obligatoria si tocaste algo visual)

`jsdom` no tiene layout: no mide alturas ni sabe que un texto envuelve. Una
prueba verde en jsdom **no es evidencia**. Esto corre en Chromium real contra el
servidor real:

```bash
npm run build
# datos aislados: el servidor REESCRIBE data/servidor/marea.json (ver §6)
mkdir -p /tmp/marea-datos && cp -r data/servidor/. /tmp/marea-datos/
MAREA_DATA_DIR=/tmp/marea-datos PORT=8100 npx tsx server/index.mts &
sleep 6
npm run densidad
```

**Números vigentes — se reportan medidos, no se asumen:**

| Métrica | Tope | Medido hoy |
|---|---|---|
| Card normal | 116 px | 116 |
| Card viva (vela) | 124 px | 121 |
| Card de N resultados | 180 px | 177 |
| Cards enteras en lista @390 | ≥ 5 | 6 |
| Cromo antes del producto | ≤ 130 px | 115 |
| Banda de destacados | ≤ 200 px | 165 |
| Nodos de texto envueltos | 0 | 0 |
| Probabilidad | ≥ 30 px | 30 |
| Esqueleto vs card | ± 2 px | pareado |

**Reglas de la puerta:**
1. No subas un techo sin medición y sin razón escrita en `CARD_SPEC.md`.
2. Después de cualquier cambio de padding, gap, tipografía o filas: reconstruye,
   vuelve a medir, **reporta los números por tipo**.
3. Si el esqueleto deja de medir lo que la card, arregla el esqueleto — no
   aflojes la tolerancia.
4. Legibilidad antes que densidad extrema.

---

## 5 · Carriles para swarm (paralelismo sin colisión)

Si lanzas varios agentes, **repártelos por carril**. Cada carril es dueño
exclusivo de sus archivos. Dos agentes editando `MarketCard.tsx` a la vez
producen un merge que nadie puede revisar.

| Carril | Dueño exclusivo de | Puerta obligatoria |
|---|---|---|
| **A · Feed** | `screens/HomeScreen`, `components/FeaturedCarousel`, `ui/SectionHeader`, `ui/chip` | `densidad` + `fase1` |
| **B · Card** | `components/MarketCard`, `components/CryptoLiveCard`, `ui/categoria-icono`, `ui/badge`, `ui/card` | `densidad` + `contrast` + `fase1` |
| **C · Motor** | `domain/*`, `adapters/*`, `server/*` | `npm test` + `validate` |
| **D · Puerta y docs** | `scripts/*`, `tests/*`, `vault/*` | `npm test` |
| **E · Pantallas** | `screens/{Portfolio,Search,Profile,Wallet,Tabla,MarketDetail}` | `fase2` + `mobile` |

### Zona compartida — serializar, nunca en paralelo

`domain/types.ts` · `lib/strings.ts` · `state/store.tsx` · `lib/cn.ts`

Protocolo: quien necesite tocarlos **lo anuncia primero, hace ese cambio solo, y
lo publica antes de que otro carril siga**. Son el 60 % de los conflictos.

### Orden de dependencia entre carriles

```
C (motor) ──► B (card) ──► A (feed)
                 └──────► D (puerta mide lo que B y A producen)
E corre en paralelo, no toca nada de lo anterior
```

Si un carril cambia un contrato de `domain/types`, los de aguas abajo **esperan**.

---

## 6 · Trampas observadas (cada una costó tiempo real)

1. **`git branch -a` sin `fetch` miente.** Costó un día y una reversión completa
   del rediseño. Ver §1.
2. **El servidor reescribe `data/servidor/marea.json`**, que está versionado.
   Levantarlo para medir ensucia el árbol y rompe `tests/multiples.test.ts`.
   **Siempre `MAREA_DATA_DIR=/tmp/...`.**
3. **`leading-tight` no da 1.25 dentro de `-webkit-box`.** Medía 22.5 px por
   línea en vez de 18.75 y engordaba la card 7 px por línea. Declara el
   interlineado en píxeles: `leading-[19px]`.
4. **`line-clamp` y `leading` chocan en `tailwind-merge`** y gana el último. El
   interlineado va **después** del recorte o se descarta.
5. **Detectar envolturas dividiendo alto entre `line-height` da falsos
   positivos** con nodos de alto fijo. Y `scrollWidth` da cero siempre, porque
   el texto que envuelve crece en alto, no en ancho. La puerta cuenta tapas
   distintas de `Range.getClientRects()`.
6. **`HomeScreen` conecta el pulso de las velas** (`actions.seguirVivos()` bajo
   `hayVelas`) y pasa `pulso={state.vivos[market.id]}` a cada card. Reescribir
   esa pantalla sin conservarlo **congela las velas en producción**.
7. **`npm run validate` puede fallar por `L1`** ("el liquidador no corre desde
   hace N h"). Es un aviso operativo sobre la frescura de
   `public/resoluciones.json`, no un defecto de tu código. No lo "arregles"
   corriendo `npm run settle` sin permiso: golpea oráculos en vivo y reescribe
   datos versionados.

---

## 6b · Zonas grises: cómo se cazan

Un producto vivo no se rompe con errores que truenan, se rompe con estados que
nadie definió. Los que ya se cazaron aquí tenían la misma forma: **una regla
que miraba el calendario en vez de mirar si alguien estaba esperando.**

Antes de dar por buena una superficie, pregúntale estas cinco cosas:

1. **¿Qué pasa justo después del corte?** No en la hora siguiente: en el
   segundo siguiente. El cierre de una vela dura 10 s entre bloqueo y fin.
2. **¿Quién sigue esperando algo?** Si alguien tiene puntos dentro, su mercado
   no puede desaparecer de la pantalla — aunque haya pasado cualquier plazo.
3. **¿Qué ve el que NO participó?** Una tarjeta que ya no se puede contestar es
   ruido para todos los demás.
4. **¿El estado muerto se puede tocar?** Un botón que existe y no hace nada
   enseña a desconfiar de todos los botones.
5. **¿Hay dos caminos de código para lo mismo?** Aquí los hubo: el adapter del
   navegador filtraba los mercados cerrados y el servidor no. **El de
   producción es `server/`** — es el que sirve la app de verdad.

**Cómo se comprueba: observando, no razonando.** Levanta el servidor, sondea la
API cada 10 s durante varios minutos y registra las transiciones. Siete minutos
de sondeo contra 180 lecturas cerraron una duda que el razonamiento no cerraba.
Un mercado de vela dura 5 min: cabe entero en una observación.

## 7 · Cómo se entrega

Por cada unidad de trabajo, en este formato y en este orden:

```
1. Qué archivos voy a tocar y por qué  (ANTES de tocarlos)
2. [ejecución]
3. Qué cambió, en una frase por archivo
4. Qué corrí y qué dio — con los números, no con adjetivos
5. Qué NO verifiqué y por qué
```

**Commits.** El repo escribe mensajes que explican *el problema que se resolvía*,
en español, no la lista de cambios. Mira `git log` antes de escribir el tuyo.
Una línea de asunto sin prefijos de tipo, cuerpo con la razón y los números
medidos.

**Nunca:** reportar verde sin haber corrido la puerta · subir un tope para que
pase · borrar una prueba que estorba · dejar `console.log` · añadir dependencias
sin preguntar · tocar la raíz del repo (es otro producto).

---

## 8 · Estado y cola de trabajo

**Rama de trabajo: `claude/marea-redesign-v6-premium-3wkzum`.** Es la que
Railway despliega. Está en producción, con velas de 5 y 15 min corriendo,
carrusel de destacados y feed agrupado por categoría.

Vigente al 29 de julio de 2026: 342 pruebas verde · densidad PASS · modo puntos
(`market_engine: parimutuel_points`), sin dinero real.

Antes de tomar algo de aquí, corre `git log --oneline -15` y confirma que sigue
pendiente.

- [ ] **Escudos y avatares en la fila de resultados.** El dato existe
      (`Market.equipos[].escudo`, URLs de ESPN en `ownMarkets/catalog.ts`) y hoy
      no se pinta en la card. Regla: si no hay coincidencia clara entre la
      etiqueta del resultado y el nombre del equipo, **no se pinta nada** —
      mejor un hueco que el escudo equivocado. Sin caras generadas.
- [ ] **Sólo 2 mercados del catálogo tienen escudo.** Ampliar la cobertura del
      dato vale más que pulir el componente.
- [ ] **Carrusel y lista repiten mercado.** Aceptable hoy; revisar si molesta
      con catálogo más grande.
- [ ] **`otros` como categoría** no aguanta tinte (`--muted` sobre su relleno da
      4.02:1, por debajo de AA). Si aparece en el feed, se pinta neutra.
- [ ] **Cobertura de la puerta:** hoy sólo la ejerce el feed. Detalle,
      portafolio y búsqueda no tienen presupuesto medido.
- [ ] **`liquidados: 0`.** El ciclo de cobro nunca se ha cerrado en producción
      contra una apuesta real. La primera ocasión es el cierre de
      `btc-cierre-semanal`, con 3 personas y 300 pts dentro. Ese día, `/salud`
      manda sobre cualquier otra tarea.
- [ ] **Persistencia:** verificar que `MAREA_DATA_DIR` apunta a un volumen
      montado. Ver `LANZAMIENTO.md` §Persistencia. Sin eso, cada deploy borra
      usuarios reales — y es lo único de esta lista que empeora solo.

Para el camino con dinero real: `vault/COMPLIANCE.md` y
`vault/PROMPT_DINERO_REAL.md`. **No se empieza sin opinión legal** — la
validación falla a propósito si alguien enciende `parimutuel_money` sin la
puerta de elegibilidad.
