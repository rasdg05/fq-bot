# PREGUNTAS ABIERTAS — sesión autónoma

> Regla de `COLA_TRABAJO.md` §0.2: si falta una decisión que no está escrita, se
> toma **la más conservadora**, se anota aquí con su fecha y la alternativa que
> se descartó, y se sigue. **Nada de esto bloquea la cola.**
>
> Cada entrada es para RasDG: si contesta distinto, se cambia y se dice qué costó.

---

## P-001 · La cola dice 4 rojas; hay 6 (+2 de `validate`)

- **Fecha:** 2026-09-08 · **Unidad:** U0 · **Estado:** decidido, sin coste
- **El hueco:** `COLA_TRABAJO.md` U0 dice «Hay 4 pruebas rojas conocidas
  (`ownmarkets`, `settlement` V34)». Medido: **6 pruebas rojas** de `vitest`, en
  esos mismos dos archivos, más **2 verificaciones de `validate.mjs`** (L1 y M1)
  que no son pruebas de `vitest` y que la cola no menciona.
- **Lo que se hizo (conservador):** vale el número medido. La línea base queda en
  **6 rojas de vitest + 8 fallos de `validate`**, y la regla «el número de rojas
  no crece» se aplica contra ese número, no contra el 4 escrito.
- **Lo que se descartó:** tratar la diferencia como una rotura propia y ponerse a
  arreglarla. Habría sido tocar el catálogo, que es del segundo desarrollador y
  que la cola prohíbe explícitamente.
- **Por qué no importa mucho:** las 6 comparten causa raíz (catálogo caducado, 9
  de 13 mercados vencidos) y ninguna es de código nuestro. La frontera no cambia.
- **Lo que necesitaría RasDG decidir:** nada, salvo que quiera que la cola se
  corrija. Detalle completo en `LINEA_BASE.md`.

---

## P-002 · ¿Quién nace en modo `"subsidio"`? Hoy: nadie

- **Fecha:** 2026-09-08 · **Unidad:** U1 · **Estado:** decidido, se revisa en U4
- **El hueco:** R-067 dice que **toda** liquidez de la casa es subsidio declarado
  **con tope**. U1 construye el mecanismo; la cola dice explícitamente que los
  mercados abiertos no se migran, así que los 13 del catálogo estático se quedan
  en `"apuesta"`. Lo que nadie escribió es qué modo llevan los **mercados nuevos**
  que genera `templates.ts` cuando corre `roll`.
- **Lo que se hizo (conservador):** también `"apuesta"`, por ahora. El tope de
  R-067 es `domain/presupuesto.ts` (U4) y todavía no existe. Encender el subsidio
  antes que el freno sería comprometer un coste por mercado sin nada que lo
  apague — la mitad de la regla, y justo la mitad cara. `LIQUIDEZ.md` §6.1 lo dice
  con otras palabras: «un tope que no apaga nada es un comentario».
- **Lo que se descartó:** que `templates.ts` nazca en `"subsidio"` desde U1. Es lo
  que R-067 pide en la frase, pero incumple la misma regla en la palabra «tope».
- **Lo que sí cambió hoy:** la semilla queda **registrada** (`pool.seed`) en todos
  los mercados nuevos, aunque el modo sea `"apuesta"`. Sin ese registro, media
  hora después de abrir un mercado ya no se puede saber cuánto del pozo es de la
  casa — y eso es exactamente lo que el presupuesto de L9 va a tener que sumar.
- **Cuándo se resuelve:** en U4, junto con el freno. Cambiar un `"apuesta"` por un
  `"subsidio"` en `templates.ts` es una línea; lo que no es de una línea es el
  tope que la hace legítima.
- **Lo que necesitaría RasDG decidir:** el valor de los topes
  (`MAREA_SUBSIDIO_MAX_MERCADO`, `MAREA_SUBSIDIO_MAX_ABIERTO`,
  `MAREA_EXPOSICION_MAX`). Con puntos da igual; con dinero es el número.

---

## P-003 · Los 15 mercados ya publicados no declaran su semilla

- **Fecha:** 2026-09-08 · **Unidad:** U1 · **Estado:** conocido, sin arreglar
- **El hueco:** `public/mercados.json` tiene 15 mercados generados por un `roll`
  anterior, con el pozo en el formato viejo (`{si, no, feeBps}`). Al releerlos,
  `normalizePool` no les inventa semilla — y hace bien: **no se sabe** cuánto de
  ese pozo es de la casa, porque las apuestas y la semilla ya están sumadas en el
  mismo número. Verificado arrancando el servidor: de 28 pozos en disco, 13
  traen `seed` (el catálogo estático) y 15 no.
- **La consecuencia real:** cuando U4 sume el subsidio vivo, esos 15 van a contar
  **cero**. Es una subestimación del compromiso, no una sobreestimación, así que
  el freno se dispararía tarde. Con puntos no cuesta nada; con dinero sí.
- **Lo que se hizo (conservador):** nada. Estampar una semilla inventada sobre un
  pozo que ya recibió apuestas sería peor que no tenerla: convertiría dinero de
  usuarios en dinero de la casa, y con subsidio eso es dinero que deja de cobrar
  alguien que apostó.
- **Cómo se cierra solo:** el próximo `roll` los reescribe con la semilla
  declarada, porque `templates.ts` ya la estampa. `roll` es del segundo
  desarrollador y esta sesión tiene prohibido correrlo.
- **Lo que necesitaría RasDG decidir:** si U4 debe **negarse a arrancar** mientras
  haya mercados vivos sin semilla declarada, o sólo avisar. Lo conservador es
  negarse; lo que no se puede es sumar cero y llamarlo presupuesto.
- **RESUELTO en U4 (2026-09-08), y el susto era menor de lo que parecía.** La
  pregunta tenía dos mitades y sólo una era un problema:
  - Contra el **presupuesto de subsidio**, contar cero es **correcto**, no una
    subestimación: un pozo sin `seed` tampoco tiene `seedMode`, así que es
    `"apuesta"` por definición y su subsidio es cero de verdad. La suma es
    exacta.
  - Contra el **tope de exposición** —todo el dinero de la casa, vuelva o no—
    sí es una cota inferior. Ahí se hace lo conservador: si hay un tope
    configurado y hay mercados opacos, `puedeCrear` **se niega** y los nombra.
    Si no hay tope configurado, no hay nada que hacer cumplir y no se estorba.
  El tope de exposición nace sin configurar, así que hoy esto no frena nada y
  el segundo desarrollador puede correr `roll` igual que siempre.

---

## P-004 · Los tres topes necesitan números, y no los pongo yo

- **Fecha:** 2026-09-08 · **Unidad:** U4 · **Estado:** decidido, pendiente de RasDG
- **El hueco:** `LIQUIDEZ.md` §6.1 nombra `MAREA_SUBSIDIO_MAX_MERCADO`,
  `MAREA_SUBSIDIO_MAX_ABIERTO` y `MAREA_EXPOSICION_MAX`, pero ningún documento
  dice **cuánto** vale cada uno. Es una decisión de producto con dinero detrás.
- **Lo que se hizo (conservador), y por qué no es lo mismo para los tres:**
  - Los dos de subsidio nacen en **cero autorizado**. Un tope de cero no impide
    nada de lo que se hace hoy —nada nace en modo subsidio (P-002)— y en el
    momento en que alguien lo encienda sin presupuesto, la creación se detiene.
    El freno nace **armado**, que es el único orden que respeta R-067: primero
    el tope, después el gasto.
  - El de exposición nace **sin tope**. Acotar las semillas recuperables que ya
    existen es una decisión con un número que sólo puede poner RasDG, y elegirlo
    aquí sería inventar un límite que parece una decisión. Se dice en el
    veredicto (`sinDeclarar`, `exposicionViva` se miden siempre) para que
    «no hay tope» nunca pase por «pasó el tope».
- **Lo que se descartó:** poner cifras plausibles. Un límite inventado es peor
  que no tenerlo, porque el siguiente que lo lea creerá que alguien lo pensó.
- **Un valor mal escrito no se lee como `NaN`.** `MAREA_EXPOSICION_MAX="mucho"`
  se ignora, avisa y cae al default. Un `NaN` haría pasar cualquier comparación,
  y un freno que siempre dice que sí es el mismo que no existe.
- **Lo que necesitaría RasDG decidir:** las tres cifras, en puntos hoy y en
  dinero cuando abra la puerta. Con puntos da igual; con dinero es el número.

---

## P-005 · La frescura de las series mensuales necesita una medición que nadie ha hecho

- **Fecha:** 2026-09-08 · **Unidad:** U5 · **Estado:** decidido, medible después
- **El hueco:** L8 pide que una lectura vieja no resuelva. Al implementarlo salió
  un hecho que cambia el diseño: **9 de los 13 mercados del catálogo se resuelven
  con series mensuales** (INPC, IPCA, IMACEC, Selic, TRM, Badlar). Su `observedAt`
  es la fecha del **periodo observado**, que por construcción tiene semanas
  cuando el dato se publica. Un umbral de reloj de 48 h no los protegería: los
  **atascaría a los nueve**.
- **Lo que se hizo (conservador):** la antigüedad se **mide siempre** y se guarda
  en el estado; se **hace cumplir** sólo donde el mercado declara `maxAgeHours`,
  y hoy lo declaran los 4 mercados de precio y de partido — las fuentes que laten
  a diario, donde el reloj sí dice si el colector sigue vivo. Para las series, que
  el dato esté al día ya lo comprueba la propia regla, que devuelve `sin_dato`
  cuando la última observación es anterior al periodo que el mercado pide.
- **Lo que se descartó:** un umbral global. Habría convertido una puerta de
  seguridad en un atasco de producto, que es peor que el fallo que previene.
- **Por qué no está cerrado del todo:** una serie mensual **parada** (el instituto
  dejó de publicar) hoy se detecta sólo por la vía de la regla. Cerrarlo bien pide
  saber la cadencia real de cada fuente —cuántos días tarda el INEGI, el IBGE, el
  BCRP— y eso es una **medición** sobre el histórico de cada endpoint, no una
  cifra que se pueda razonar desde aquí. Un umbral inventado por fuente sería
  exactamente lo que P-004 dice que no se hace.
- **Mientras tanto no es invisible:** `resueltosSinFrescura()` lista los mercados
  que se resolvieron sin poder comprobar la antigüedad, y los tres oráculos de
  producción ya reportan `observedAt`. La cifra existe aunque todavía no bloquee.
- **Lo que necesitaría RasDG decidir:** si vale la pena medir la cadencia de las
  seis fuentes institucionales para poner umbrales por serie, o si la puerta de
  la regla basta hasta que haya dinero real.

### Actualización (2026-09-08, §3): la afirmación era medio falsa, y costaba caro

Al verificar la frase «para las series, que estén al día ya lo comprueba la
propia regla» —que en U5 se dio por buena **leyendo el código**— salió que la
regla existe pero **el margen estaba mal puesto en casi todas**. `seriesOracle`
compara `ultima.fecha >= settlesAt − frescuraDias`, y **sólo `cl-imacec`
declaraba `frescuraDias`**. Las otras ocho caían al defecto de **1.5 días**,
mientras que el dato de una serie mensual llega fechado ~35 días antes de
resolver, porque va fechado al **periodo**, no a la publicación.

Medido inyectando las observaciones, sin red: **cinco mercados no podían
resolverse nunca por programa** — `mx-inpc-anual`, `mx-banxico-tasa`,
`br-ipca-5`, `br-selic-corte`, `pe-inflacion-lima`. Descartaban su propio dato
correcto por viejo y se quedaban en `sin_dato` para siempre. Es un agujero de
ciclo de vida: se apuesta y no se cobra.

**Un detalle que importa para el futuro:** dos de los cinco estaban **tapados por
la falta de token**. Sin `INEGI_TOKEN` / `BANXICO_TOKEN` el oráculo contesta
`requiere_humano` **antes** de llegar a la comprobación del margen, así que el
defecto sólo aparece cuando alguien configura las llaves — es decir, el día que
el mercado por fin iba a funcionar solo. Una configuración que falta puede
esconder un bug detrás.

**Arreglado:** los cinco declaran `frescuraDias: 100`, con el porqué de cada uno
escrito al lado. El 100 **no es medido**: es el valor que este repo ya había
elegido para `cl-imacec`, otra serie mensual, aplicado con consistencia. Cubre el
desfase de una serie mensual (~35 d) y de dos reuniones de COPOM / Banxico
(~90 d) con holgura, y sigue rechazando una serie parada 200 días — hay test de
las dos cosas.

**Cerrado el lazo:** `tests/frescura.test.ts` comprueba ahora que **toda** serie
del catálogo acepta un dato fechado a su cadencia real. Escribir un mercado de
serie nuevo sin margen adecuado pone la suite en rojo, en vez de publicar un
mercado que nadie podrá cobrar.

**Lo que sigue pendiente de RasDG (más pequeño que antes):** si se mide la
cadencia real de cada fuente, el 100 se puede afinar por serie. Hoy es holgado a
propósito: prefiere no atascar antes que apurar el umbral, y la puerta contra la
fuente parada de verdad sigue puesta.

---

## P-006 · U7 (contratos) saltada: `forge` no es alcanzable, pero Hardhat sí

- **Fecha:** 2026-09-08 · **Unidad:** U7 · **Estado:** saltada, decisión de RasDG
- **Lo que pasó, medido:** `forge` no está instalado. `foundryup` se descarga y
  arranca, pero falla al buscar la release: los binarios de Foundry vienen de
  **GitHub releases**, y en este entorno `api.github.com` responde **403**. La
  política de red del entorno sólo deja pasar directo unos pocos registros
  (npm, PyPI, crates.io, proxy.golang.org). No es un problema de instalación:
  es la red, y no se arregla desde aquí. Dos intentos, como manda la cola.
- **Pero la nota honesta no es «no hay herramientas».** `registry.npmjs.org` sí
  es alcanzable, y desde ahí hay cadena de Solidity completa: `solc` 0.8.36 y
  `hardhat` 3.16.0, los dos comprobados con `npm view`. Decir «no se puede»
  sin mirar el registro habría sido pereza disfrazada de prudencia (AGENTE §2).
- **Lo que se hizo (conservador): saltarla igual.** La puerta escrita es
  `forge test` en verde, y meter Hardhat en el repo no es sustituir una
  herramienta: es **añadir una segunda cadena de construcción** que heredan
  RasDG y el segundo desarrollador, con su config, su lenguaje de pruebas y su
  mantenimiento. Esa elección no es de una sesión autónoma.
- **Lo que se descartó:** (a) escribir los tres contratos sin poder probarlos —
  Solidity sin pruebas de invariante en el camino del dinero es peor que no
  tenerlo, y la cola pide invariantes cableadas, no ficheros; (b) pelear más con
  la instalación, que la cola limita a dos intentos.
- **Lo que necesitaría RasDG decidir:** o (1) Hardhat como cadena de contratos
  del repo, o (2) dejar U7 para una máquina con Foundry, o (3) permitir GitHub
  releases en la política de red del entorno. Con cualquiera de las tres, U7 se
  hace tal cual está escrita: `BovedaTopada.sol` (~150) · `AdaptadorOraculo.sol`
  (~180) · `RegistroAnclas.sol` (~80) sobre los Conditional Tokens ya auditados,
  con las invariantes L1 / L5 / L14.
- **Lo que U7 ya no necesita inventar:** `domain/merkle.ts` y `domain/epoca.ts`
  (U6) dejan la regla del ancla escrita y probada — prefijos de dominio, hoja
  impar promovida, conteo y secuencia. `RegistroAnclas.sol` tiene que emitir
  exactamente eso; la aritmética ya no está en discusión.

---

_Se abre esta bitácora el 2026-09-08. Formato: qué faltaba, qué se eligió, qué se
descartó, qué costaría revertirlo._
