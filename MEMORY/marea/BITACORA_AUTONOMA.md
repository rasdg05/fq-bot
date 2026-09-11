# BITÁCORA — sesión autónoma sobre Marea

> Registro por unidad de `marea/vault/COLA_TRABAJO.md`. Regla §0.6: al cerrar cada
> unidad se escribe **qué se hizo y qué costó descubrir**. Lo segundo es lo que
> vale: el código está en el diff, el descubrimiento no.
>
> Iniciada el 2026-09-08 sobre `857a125`, rama
> `claude/marea-autonomous-work-3sggb9`.

---

## Resumen: en qué quedó todo

**Lo construido.** Ocho unidades de la cola, una por commit. De las invariantes
de liquidez, **L1, L2, L3, L5, L6, L8, L9 y L15 pasaron de escritas a vivas**.
U7 (contratos) se saltó: `forge` no es alcanzable en este entorno.

**Lo que NO cambió, y hay que decirlo en la misma frase.** Nadie nace en modo
subsidio, los topes no tienen cifras, los contratos no existen, las hojas de la
época no se publican y nada está desplegado. El dominio está; el producto en
cadena no.

**Los dos defectos de producto que aparecieron midiendo**, y que valen más que
todo lo demás porque eran agujeros de ciclo de vida:

1. **Cinco mercados no podían resolverse nunca por programa** — `mx-inpc-anual`,
   `mx-banxico-tasa`, `br-ipca-5`, `br-selic-corte`, `pe-inflacion-lima`.
   Descartaban su propio dato correcto por viejo: el margen por defecto era de
   1.5 días y una serie mensual llega fechada ~35 días antes de resolver, porque
   va fechada al periodo y no a la publicación. **Dos de los cinco estaban
   tapados por la falta de token**: sin llave el oráculo contesta
   `requiere_humano` antes de llegar a la comprobación, así que el defecto sólo
   habría aparecido el día en que el mercado por fin iba a funcionar solo.
2. **La ventana entre pagar y marcar.** `ciclo.mts` paga primero y marca después,
   a propósito. Si el proceso muere ahí, al arrancar la fase sigue en
   `en_disputa` y el ciclo vuelve a liquidar. Medido con la guarda desactivada:
   la casa cobra la comisión **dos veces**, y eso **no descuadra el libro** — lo
   deja cuadrado con el saldo del pozo en negativo. En Railway, que redeploya en
   cada push, la ventana es real.

**La lección que se repitió cuatro veces.** Escribí **diez tests que pasaban en
verde sin probar lo que decía su nombre**, y no estaban repartidos al azar: se
concentran en guardas que nunca se disparan en el camino feliz y en propiedades
adversarias — separación de dominio del árbol, codificación de las hojas,
idempotencia del cierre, la guarda del store tras un redeploy. El camino feliz se
prueba solo. Lo que un atacante rompería, o lo que sólo pasa con datos corruptos,
hay que romperlo a propósito para saber que el test lo mira.

Por eso `npm run mutaciones` está versionado: **55 mutaciones, 53 detectadas, 2
equivalentes documentadas, 0 huecos**, y sale con código distinto de cero si
aparece uno. El arnés falló él mismo de las dos formas posibles antes de ser
fiable —falso positivo por una lista de archivos mal puesta, falso negativo por
comparar contra cero en vez de contra la línea base— y las dos están escritas
abajo.

**Suite:** 8 rojas (todas de línea base, catálogo caducado, no son nuestras) ·
**287 → 375 verdes**.

**Lo que espera a RasDG** (`marea/vault/PREGUNTAS_ABIERTAS.md`): las tres cifras
de los topes (P-004), encender el modo subsidio (P-002) y qué hacer con los
contratos ahora que `forge` no llega pero npm sí trae Solidity (P-006). Ninguna
bloquea lo construido.

---

## U0 · Línea base de la suite ✔

**Qué se hizo.** `npm ci` (277 paquetes, limpio) y se corrió todo: `tsc`, `vitest`,
`validate`, y el intento de `npm run ci`. El resultado quedó fijado en
`marea/vault/LINEA_BASE.md` con fecha, commit y comandos.

**Lo medido.** `tsc -b --noEmit` verde. `vitest`: **6 rojas / 287 verdes**, en dos
archivos. `validate.mjs`: **FAIL con 8 fallos** (las 6 pruebas + L1 + M1).
`npm run ci` **no llega a `build`**: la cadena es
`tsc && validate && build` y `validate` la corta. Es decir: **la línea base de
`npm run ci` es FAIL**, y «no empeorar» significa *esos mismos 8*, no «verde».

**Lo que costó descubrir.**

1. **La cola decía 4 rojas; son 6.** Y las dos que la cola no cuenta (L1, M1) no
   son pruebas de `vitest` sino verificaciones de `validate.mjs`, así que no
   aparecen si sólo corres la suite. Un agente que hubiera corrido `vitest` y
   comparado contra el 4 escrito habría concluido que rompió dos cosas antes de
   escribir una línea. **Ese es exactamente el fallo que U0 existe para evitar**,
   y estuvo a un paso de ocurrir en la propia unidad que lo previene.

2. **Las 6 son una sola causa, y se puede nombrar con un número.** El catálogo
   estático (`src/adapters/ownMarkets/catalog.ts`) tiene 13 mercados;
   `activeSeeds()` filtra por `closesAt > now`; al 2026-09-08 sobreviven 4
   (`br-ipca-5`, `br-selic-corte`, `eth-4500`, `pe-inflacion-lima`). **El «4» que
   aparece en los seis mensajes de error es ese 4.** Verlo convierte seis fallos
   con seis mensajes distintos en un hecho: nueve mercados vencieron entre el
   31-jul y el 1-sep.

3. **L1 es el mismo hecho por otro lado.** «El liquidador no corre desde hace
   1015 h» ≈ 42 días, que es justo la ventana en la que se fueron venciendo. Dos
   síntomas, un reloj parado. Vale la pena anotarlo porque el instinto es tratar
   L1 como un problema de infraestructura y el catálogo como uno de datos; son el
   mismo.

**Lo que no se tocó, a propósito.** Arreglar esto es correr `npm run roll` /
`settle`, que sale a APIs reales y reescribe el catálogo de producción. Es del
segundo desarrollador (su día 1) y la cola lo prohíbe. Las rojas se quedan rojas.

**Puerta:** ✔ el archivo existe, nombra las rojas conocidas con su causa, y fija
el número contra el que se compara de aquí en adelante.

---

## U1 · La semilla se vuelve subsidio ✔

**Qué se hizo.** El mecanismo completo de R-067, con el interruptor **apagado**.
`Pool` gana dos campos (`seed`, `seedMode`), aparece `bettorStake()` como único
lugar donde se decide quién cobra, y `payoutMultiplier()` y `settle()` pasan los
dos por ahí. El catálogo declara su semilla y se queda en modo `"apuesta"`.

**La pieza que hace que no se puedan separar.** La cola pedía mover `settle()` y
`payoutMultiplier()` en el mismo commit, porque mover uno solo hace que la app
muestre un número y pague otro. Se cumplió, pero **la disciplina no es acordarse
de mover los dos**: es que los dos llamen a la misma función.

```
bettorStake(pool, id) = max(0, outcomeStake(id) − subsidyStake(id))
```

`payoutMultiplier` divide por `bettorStake(id) + stake`; `settle` divide por
`bettorStake(ganador)`. No son dos fórmulas que hay que mantener iguales: son la
misma. Ésa es la versión cableada de R-044, y es el motivo de que el test de
propiedad pase por construcción y no por suerte.

**Lo que costó descubrir.**

1. **Había cuatro sitios que reconstruían el pozo a mano.** `server/ciclo.mts`
   llamaba `settle({ outcomes: pozo.outcomes, feeBps: pozo.feeBps }, ...)`,
   `server/mercados.mts` hacía lo mismo dos veces (`sembrarPozos` y `poolDe`), y
   `migrar()` en `server/store.mts` reescribía `{ marketId, outcomes, feeBps }`.
   Cada uno de los cuatro **tira los campos nuevos en silencio**. Con el campo
   añadido y nada más, un mercado con subsidio habría liquidado como los de antes
   —cobrando la casa— sin un solo error en la consola. Los cuatro pasan ahora por
   `normalizePool`, que es el único que sabe qué campos tiene un pozo.

   Esto es lo que el CLAUDE.md del repo llama fallo de cableado, y es la clase de
   cosa que un test de dominio puro **no** ve: las cuatro funciones de
   `parimutuel.ts` estaban bien desde el primer minuto.

2. **`nadieAcerto` estaba escrito dos veces, y las dos con la definición vieja.**
   `domain/settlement.ts` y `server/ciclo.mts` preguntaban
   `outcomeStake(ganador) <= 0`. Con subsidio eso es la pregunta equivocada: un
   lado ganador que sólo tiene semilla **no tiene ganadores**, aunque el pozo no
   esté vacío. Sin corregirlo, ese mercado se habría marcado como `pagado` con
   `payouts` vacíos: nadie cobra, la fase dice que sí, y el descuadre aparece
   semanas después. Las dos usan ahora `bettorStake`.

3. **La verificación en proceso real encontró lo que la suite no.** Arrancando el
   servidor contra un directorio limpio: 28 pozos en disco, **13 con semilla
   declarada y 15 sin ella**. Los 15 son mercados que un `roll` anterior ya
   publicó con el pozo en formato viejo, donde la semilla y las apuestas están
   sumadas en el mismo número y ya **no se pueden separar**. `normalizePool` hace
   lo correcto y no les inventa una. La consecuencia es de U4: el presupuesto de
   subsidio vivo los va a contar como cero, o sea que el freno se dispararía
   tarde. Anotado en `PREGUNTAS_ABIERTAS.md` P-003. Matar el proceso y levantarlo
   otra vez confirmó que los 13 conservan su modo: `identicos: True`.

4. **La probabilidad no lleva la resta, y eso es a propósito.** El primer impulso
   fue descontar el subsidio también de `impliedProbability`. Es incorrecto: el
   subsidio es colateral de verdad y mueve el precio como cualquier otro. Lo que
   el subsidio cambia es **quién cobra**, no cuánto se apostó. La consecuencia es
   que con subsidio `multiplier > 1 / probability`, y esa diferencia **es** el
   premio. Si las dos llevaran la resta, el subsidio no se vería por ningún lado.

**Las mutaciones (§0.5).** Los cuatro tests nuevos se rompieron a propósito:

| Se rompió | Se puso rojo |
|---|---|
| `payoutMultiplier` vuelve a no descontar el subsidio | 2 pruebas |
| `settle` vuelve a no descontar el subsidio | 3 pruebas |
| `normalizePool` tira `seedMode` al releer | 2 pruebas |
| `declareSeed` no registra la semilla | 4 pruebas |

Las dos primeras importan por separado: son exactamente los dos medios arreglos
que la cola advertía, y **cada uno pone rojo el test de propiedad**. Ninguna
mutación pasó desapercibida.

**Lo que se decidió sin preguntar.** Nadie nace en `"subsidio"` todavía, ni
siquiera los mercados nuevos de `templates.ts`: R-067 pide subsidio **con tope**,
y el tope es U4. Encenderlo antes que el freno es comprometer un coste por
mercado sin nada que lo apague. `PREGUNTAS_ABIERTAS.md` P-002.

**Puerta:** ✔ propiedad `quote(...).toWin === settle(...).payouts[esa apuesta]`
sobre 400 escenarios aleatorios reproducibles × los dos modos; y los mercados en
`"apuesta"` dan `toEqual` exacto contra un pozo escrito como se escribía antes.
Línea base intacta: mismas 8 rojas, +7 verdes (287 → 294).

---

## U2 · Cablear el compensador ✔

**Qué se hizo.** `settle()` deja de ser el que mueve dinero y pasa a ser lo que
su nombre promete: **un productor de reparto**. Quien mueve saldos es el
compensador. Entre la capa de precio y la cámara aparece un puente puro,
`domain/compensacion.ts`, y `server/ciclo.mts` liquida a través de él.

**La traducción, que resultó más literal de lo esperado.** El primer plan era
inventar una correspondencia entre el parimutuel y los conjuntos completos de
`pozo.ts`. No hizo falta inventar nada:

```
contratos del resultado o  =  quién cobraría si ganara o
Σ contratos de o           =  T  (el pozo entero)          ∀ o
```

Si gana `o`, el pozo entero se va a alguien —quienes acertaron, la tesorería por
la comisión, y lo que sobre— y eso suma `T`. Repetido para cada `o`, **eso es**
la definición de conjunto completo. De ahí sale gratis lo que R-065 promete: la
exposición neta es cero en todos los resultados, y es aritmética, no una
comprobación al final.

**Lo que costó descubrir.**

1. **La versión útil de esto no es traducir: es pedir el reparto de TODOS los
   resultados.** La tentación era compensar sólo el ganador —es el único que
   paga— y habría sido decoración: un pozo que cuadra con el ganador que salió
   no dice nada sobre neutralidad. Pidiendo los N repartos, el resto
   (`T − Σ pagos − comisión`) se calcula N veces, y **si sale negativo en
   cualquiera**, `acunar()` lo rechaza al escribir. Eso es L5 con dientes: no un
   informe a fin de mes, sino una liquidación que no ocurre. La mutación
   «sólo se comprueba el resultado que ganó» pone rojo exactamente ese test y
   ningún otro, que es la prueba de que el test paga su sitio.

2. **El resto tiene que tener dueño o el colateral se pierde de vista.** El
   primer borrador mandaba a tesorería sólo el fee. Con eso, la asignación de
   cada resultado sumaba menos que `T` y `acunar()` la rechazaba — el compensador
   se negó antes de que yo entendiera por qué. Tenía razón: en modo `"apuesta"`
   la parte de la semilla ganadora es colateral real y **alguien** lo tiene. Un
   colateral sin dueño es colateral que se pierde de vista.

3. **Lo que la suite no habría visto: que el cable fuera decorativo.** Se puede
   llamar al compensador, ignorar su respuesta y pagar como antes; los 45 tests
   del ciclo seguirían verdes. La verificación en proceso real fue hacerlo
   **negarse** a propósito y mirar qué pasa con el dinero de verdad:

   | | compensador normal | compensador que se niega |
   |---|---|---|
   | acreditado | 465.6 | **0** |
   | comisión | 24 | **0** |
   | cuadre del libro | 0 | 0 |
   | fase | `pagado` | **`en_disputa`** |

   Nadie cobra, la casa no cobra, el libro sigue cuadrado y el mercado **no
   avanza de fase**: queda pendiente y reintentable, no medio pagado. El modo de
   falla es seguro, y eso no se puede afirmar desde jsdom.

4. **La medida que le deja el trabajo hecho a U3.** Tras liquidar el mercado de
   prueba, la cuenta contable del pozo se queda con **310.4** — la parte de la
   semilla ganadora, que hoy nadie mueve. Es exactamente la puerta de U3
   (`saldoDe(libro, "pozo:<id>") === 0`). No se toca aquí a propósito: U2 es
   refactor con red y mover ese saldo **sería** un cambio de comportamiento.

**Las mutaciones (§0.5).**

| Se rompió | Se puso rojo |
|---|---|
| el sobrepago ya no se rechaza | 1 prueba |
| un pago negativo pasa | 1 prueba |
| el resto no llega a tesorería | 4 pruebas |
| sólo se comprueba el resultado que ganó | 1 prueba |

**Puerta:** ✔ la suite pasa **sin tocar una sola expectativa existente** —
`git diff` sobre `tests/` no devuelve nada; el único cambio es un archivo nuevo.
Los 45 tests que ya ejercitaban `correrCiclo` (servidor, contabilidad,
liquidación) pasan igual. Línea base intacta: mismas 8 rojas, +9 verdes
(294 → 303).

---

## U3 · El asiento del subsidio ✔

**Qué se hizo.** Tipo de asiento `subsidio`, cuenta `capital` separada de
`tesoreria`, y el cierre de un mercado en **un solo asiento** que deja
`pozo:<id>` en cero exacto.

**Lo que costó descubrir.**

1. **`cuadre()` no ve el fallo que L3 previene.** Es lo primero que hay que
   entender y no es obvio: el libro puede sumar cero con dinero atrapado en la
   cuenta equivocada. Antes, pagar y cobrar comisión eran **dos asientos**, y
   entre los dos existía un instante en que el libro decía que el pozo todavía
   tenía la comisión dentro. Si el proceso moría ahí, esa comisión se quedaba en
   `pozo:<id>` para siempre: nadie la reclamaba, nadie la echaba de menos, y
   `cuadre()` seguía dando cero. Con un asiento, ese instante no existe — y para
   lo que ya se escribió así está `pozosSinVaciar()`, que es lo que `cuadre` no
   puede ver.

2. **La separación que pide R-066 tiene un número que enseñar.** Medido en
   proceso real tras liquidar el mercado de prueba:

   ```
   tesoreria (ingreso)      +24.0
   capital   (principal)    −89.6
   pozo:prueba-u2             0.0
   ```

   Son dos hechos distintos: *ganamos 24 de comisión* y *tenemos 89.6 de nuestro
   propio principal fuera*. Netearlos en una caja daría −65.6 y no significaría
   nada — la casa se sentiría solvente con el principal que puso ella misma, que
   es cómo quiebra un intermediario. Y la semilla dejó de pasar por `entrada`:
   no llegó del mundo exterior, es capital propio puesto a trabajar.

3. **El tipo `subsidio` no es una etiqueta: es lo que hace posible L9.**
   `subsidioComprometido(libro)` suma el compromiso **leyendo el libro
   auditable**, no un contador aparte. Un contador aparte es una segunda fuente
   de verdad, y el día que se separen no se sabe cuál miente. U4 lee de aquí.

4. **Una mutación no se puso roja, y tenía razón.** «Liquidar dos veces paga dos
   veces» dejó los 29 tests en verde. El test miraba el saldo del usuario — que
   ya está protegido por la guarda de «esta apuesta ya cobró», nivel apuesta. Lo
   que sólo protege la guarda del libro es el **segundo asiento**: uno más
   sacaría otra vez la comisión y el resto, y el saldo del mercado se iría a
   **negativo** con el libro cuadrado. Reforzado el test para contar asientos y
   mirar el pozo *después* de la segunda llamada; ahora sí se pone rojo. Un test
   que nunca se vio en rojo no prueba lo que uno cree que prueba, y éste probaba
   una cosa distinta de la que decía su nombre.

5. **Un pago a un usuario que ya no existe.** Al escribir el cierre en un solo
   asiento apareció el caso: si una apuesta apunta a un usuario borrado, su pago
   no se acredita a nadie y —con la fórmula ingenua— se quedaría en el pozo,
   abriendo justo el hueco que L3 cierra. Lo prometido que no llegó a un usuario
   vivo se suma a lo que vuelve al capital, y hay un test que lo fija.

**Renombre en el camino.** `Compensacion.aTesoreria` pasó a `aLaCasa`. El nombre
ya mentía: incluye el colateral que nadie reclamó, que **no** va a tesorería. La
cámara sólo cuenta contratos y no debe saber la diferencia (R-066); quien la sabe
es el libro, que los parte en ingreso y principal. Un nombre engañoso en el
camino del dinero es exactamente lo que este repo castiga.

**Las mutaciones (§0.5).**

| Se rompió | Se puso rojo |
|---|---|
| la semilla vuelve a salir de `entrada` | 4 pruebas |
| el subsidio no se distingue de la semilla | 1 prueba |
| lo que nadie reclamó no vuelve al capital | 3 pruebas |
| el auditor deja de ver el pozo con saldo | 1 prueba |
| liquidar dos veces paga dos veces | **0 → 1** (tras reforzar el test) |

**Puerta:** ✔ medido en proceso real, no en jsdom: el saldo de `pozo:prueba-u2`
tras liquidar con comisión 24 pasó de **310.4 (U2) a 0**, `cuadre()` en cero
antes y después, y `pozosConSaldoTrasLiquidar()` vacío. Línea base intacta:
mismas 8 rojas, +7 verdes (303 → 310).

---

## U4 · Presupuesto y freno ✔

**Qué se hizo.** `domain/presupuesto.ts` (nuevo, puro) y el freno en el camino de
creación de `scripts/roll.mts`. El subsidio comprometido, la exposición viva y la
decisión «¿se puede crear otro mercado?» con su motivo.

**Lo que costó descubrir.**

1. **P-003 tenía dos mitades y sólo una era un problema.** En U1 anoté que los 15
   mercados sin semilla declarada harían que el presupuesto los contara como cero
   y el freno se disparara tarde. Al escribirlo se ve que depende de contra qué:

   | | ¿contar cero es correcto? |
   |---|---|
   | Presupuesto de **subsidio** | **Sí, exacto.** Un pozo sin `seed` tampoco tiene `seedMode`, luego es `"apuesta"` por definición y su subsidio es cero **de verdad** |
   | Tope de **exposición** | **No.** Ahí sí es una cota inferior |

   Así que se hace lo conservador sólo donde hace falta: con tope de exposición
   configurado y mercados opacos, `puedeCrear` **se niega y los nombra**; sin
   tope configurado no hay nada que hacer cumplir y no se estorba. La versión
   ingenua —negarse siempre— habría roto `roll` para el segundo desarrollador
   sin que nadie lo pidiera.

2. **El error de lote, que es el que se cuela.** `puedeCrear` sobre una tanda
   entera contra el estado inicial deja pasar N mercados que **juntos** cruzan el
   tope aunque ninguno lo cruce solo. Por eso existe `filtrarPorPresupuesto`, que
   va en orden y **cuenta los aceptados como vivos** para el siguiente. La
   mutación «la tanda no se cuenta entre sí» pone rojo exactamente ese test.
   Medido: tres candidatos de 400 contra un tope de 1000 ⇒ pasan dos, se rechaza
   el tercero, subsidio vivo 800.

3. **Un tope mal escrito es peor que no tener tope.** `MAREA_EXPOSICION_MAX="mucho"`
   leído como `Number` da `NaN`, y **cualquier** comparación con `NaN` es falsa:
   `1e9 > NaN` es `false`. Un freno que siempre dice que sí es el mismo que no
   existe, y encima parece configurado. Se ignora, se avisa y se cae al default.

4. **El freno nace armado y aun así no estorba.** Los dos topes de subsidio
   nacen en cero autorizado. Hoy nada nace en modo subsidio (P-002), así que un
   tope de cero no impide nada de lo que se hace — y el día que alguien encienda
   el subsidio sin presupuesto, `roll` no crea **ninguno** y dice por qué. Ése es
   el orden que R-067 exige: primero el tope, después el gasto. Verificado con
   los candidatos reales de `rollingSeeds`: con el catálogo de hoy pasan todos;
   con las mismas semillas en modo subsidio, cero aceptados.

5. **El guardia se probó sin tocar la red, que es lo que la cola pide.** `roll`
   sale a Kraken y a ESPN y reescribe producción. Lo que se corre en la suite es
   exactamente lo que `roll` decide —los mismos candidatos de `rollingSeeds`, el
   mismo `filtrarPorPresupuesto`, los mismos topes—; lo que queda en el script es
   una llamada y un `console.warn`.

**Las mutaciones (§0.5).** Seis, todas rojas:

| Se rompió | Se puso rojo |
|---|---|
| el tope abierto deja de frenar | 2 pruebas |
| el tope por mercado deja de frenar | 1 prueba |
| la tanda no se cuenta entre sí | 1 prueba |
| el freno nace desarmado | 3 pruebas |
| los opacos se suman como cero contra el tope | 1 prueba |
| un tope mal escrito se lee como `NaN` | 1 prueba |

**Puerta:** ✔ con el presupuesto agotado, la creación se niega y dice por qué —
con el número que lo causó, no con una opinión. Línea base intacta: mismas 8
rojas, +18 verdes (310 → 328).

**Queda pendiente de RasDG:** las tres cifras (`PREGUNTAS_ABIERTAS.md` P-004).
Con puntos da igual; con dinero es el número.

---

## U5 · Frescura del oráculo ✔ (deuda previa, L8)

**Qué se hizo.** `onRead` deja de aceptar una lectura sin mirar de cuándo es el
dato. La antigüedad entra **por parámetro** (`now − observedAt`, los dos desde
fuera): ni un reloj de pared dentro, o el replay heredaría la hora del click.
Los tres oráculos de producción reportan ya `observedAt`.

**El fallo que previene no se parece a una caída.** Una fuente parada contesta al
instante y con un 200; lo que la delata no es la latencia, es que el dato que
devuelve sigue siendo el de anteayer. Es el mismo fallo que en el bot obligó a
cablear `cvd_confirmation`.

**Lo que costó descubrir, y que cambió el diseño a mitad.**

1. **El default obvio habría atascado el catálogo entero.** El primer diseño era
   un umbral global de 48 h. Al ir a ponerlo, medí el catálogo: **9 de 13
   mercados son series mensuales** (INPC, IPCA, IMACEC, Selic, TRM, Badlar). Su
   `observedAt` es la fecha del **periodo observado**, que por construcción tiene
   semanas cuando el dato se publica. Un umbral de 48 h no los protegería: los
   atascaría a los nueve, y para siempre.

   Convertir una puerta de seguridad en un atasco de producto es peor que el
   fallo que previene. De ahí la forma final: **la antigüedad se mide siempre; se
   hace cumplir donde el reloj es la herramienta correcta**, y eso lo declara
   cada mercado. Hoy lo declaran los 4 de precio y de partido.

2. **Para las series, el reloj era la herramienta equivocada desde el principio.**
   Que la serie esté al día ya lo comprueba la propia regla: `seriesOracle`
   devuelve `sin_dato` cuando la última observación es anterior al periodo que el
   mercado pide. La puerta de reloj habría sido una segunda comprobación peor de
   lo mismo. (`PREGUNTAS_ABIERTAS.md` P-005 deja escrito qué faltaría para
   cerrarlo bien: medir la cadencia real de las seis fuentes institucionales.)

3. **Tres estados distintos, no dos.** «Fresca», «vieja» y **«no sé»** no son lo
   mismo, y colapsarlos es cómo una fuente parada pasa por una viva:
   - vieja **con umbral** → no avanza, lo declara, se reintenta;
   - sin fecha → **no se bloquea** (bloquear por no saber atascaría todo), pero
     el estado queda marcado `frescuraVerificada: false` y `resueltosSinFrescura()`
     lo lista;
   - fresca → resuelve, y guarda de cuándo era el dato.

4. **No se atora: se reintenta.** Una fuente retrasada suele ponerse al día sola,
   y marcar `atorado` llamaría a una persona sin necesidad (R-062 limita a tres
   los mercados que dependen de alguien). La evidencia dice la antigüedad, el
   umbral y que se reintenta.

5. **`tsc` atrapó lo que `vitest` no.** La suite pasaba en verde con un error de
   tipos en el test: `vitest` no typechequea. Lo cazó `npm run ci`, que corre
   `tsc` primero — razón por la que la puerta de cada unidad es `ci` y no sólo la
   suite.

**Verificado en proceso real** con un colector detenido que responde 200 y un
resultado plausible en cada ciclo:

```
t+  2h (dato de hace 122h) → fase cerrado · pagados 0 · acreditado 0
t+ 30h (dato de hace 150h) → fase cerrado · pagados 0 · acreditado 0
t+ 60h (dato de hace 180h) → fase cerrado · pagados 0 · acreditado 0
t+200h (dato de hace 320h) → fase cerrado · pagados 0 · acreditado 0

evidencia: «… — NO se usa: el dato es de hace 320.0 h y el máximo de esta
fuente son 48 h. Se reintenta.»
saldo de ana: 700 — no cobró nada
```

El mercado no avanza nunca de `cerrado`, nadie cobra, y la razón está escrita.

**Las mutaciones (§0.5).** Cinco, todas rojas:

| Se rompió | Se puso rojo |
|---|---|
| la puerta de frescura deja de existir | 2 pruebas |
| el umbral se vuelve estricto en el límite | 1 prueba |
| sin fecha se declara frescura verificada | 3 pruebas |
| una fecha futura da antigüedad negativa | 1 prueba |
| el auditor mira al revés | 1 prueba |

**Puerta:** ✔ una lectura más vieja que el umbral no avanza de fase, se reintenta
y lo declara — medido en proceso real. Línea base intacta: mismas 8 rojas,
+12 verdes (328 → 340).


---

## U6 · El árbol de época ✔

**Qué se hizo.** `domain/merkle.ts` y `domain/epoca.ts`, puros, con las tres
correcciones ya decididas y L15 encima. Y `domain/sha256.ts`, que no estaba en el
plan.

**Lo que costó descubrir.**

1. **Hizo falta escribir SHA-256 a mano, y por una razón de diseño.**
   `node:crypto` no existe en el navegador, y la pantalla del verificador —de
   quien comprueba **su propia** prueba— corre ahí. `crypto.subtle` existe en los
   dos pero es **asíncrono**, y una API asíncrona se contagia hacia arriba: el
   árbol entero, las pruebas y quien las verifique acabarían devolviendo promesas
   por una decisión de plataforma, no de dominio. Sesenta líneas de aritmética
   cuestan menos que eso. Contrastado contra `node:crypto` sobre 300 entradas
   aleatorias en las longitudes que cruzan el borde de bloque (55, 56, 64, 119,
   120): que una implementación sea consistente **consigo misma** no prueba nada.

2. **Dos de mis tests pasaban en verde sin probar nada, y las mutaciones lo
   destaparon.** Es el hallazgo de la unidad y merece el detalle:

   - **Separación de dominio.** Mi test afirmaba `hashNodo(a,b) !== a`. Eso es
     cierto por casualidad **aunque los dos prefijos sean idénticos**. Puse
     `PREFIJO_NODO = 0x00` y los 20 tests siguieron verdes. La afirmación útil no
     es «el nodo no es igual a la hoja», sino que **los dos prefijos existen y son
     distintos**, y eso se comprueba contra los bytes: se reconstruye a mano lo
     que debería hashearse y se exige que el nodo sea `SHA256(0x01 concat ...)` y
     **no** `SHA256(0x00 concat ...)`.

   - **Campos con longitud.** Mi test usaba `{usuario:"ab", hecho:"c"}` contra
     `{usuario:"a", hecho:"bc"}`. **No colisionan** ni sin longitudes, porque el
     `seq` de ancho fijo va **en medio** y separa los dos campos de texto. Otra
     mutación en verde. Busqué la colisión de verdad y existe: con la
     codificación sin longitudes, `{usuario:"ab", seq:1, hecho:""}` y
     `{usuario:"a", seq:0x62000000, hecho:<byte 0x01>}` dan los mismos bytes
     (`61 62 00 00 00 01`). Dos hechos de **usuarios distintos** con la misma
     hoja. Ahora el test usa ése.

   La lección no es «me equivoqué dos veces»: es que **los dos tests que
   fallaron eran justo los de las propiedades adversarias**. El camino feliz se
   prueba solo; lo que un atacante rompería hay que romperlo a propósito para
   saber que el test lo mira. Sin §0.5, U6 se habría cerrado con dos invariantes
   de seguridad sin verificación y nadie lo habría notado.

3. **La hoja impar sí estaba bien probada, y se nota en qué falla.** Duplicar en
   vez de promover puso rojas 4 pruebas, incluida la de propiedad. Es el fallo de
   maleabilidad de Bitcoin (CVE-2012-2459): `[a,b,c]` y `[a,b,c,c]` darían la
   misma raíz y la raíz dejaría de identificar el libro.

4. **L15 necesita las tres comprobaciones porque ninguna implica a las otras.**
   Se puede enseñar con dos ataques distintos:
   - **borrar una hoja** produce que falle el **conteo** del ancla y que las
     pruebas ya entregadas dejen de verificar;
   - **borrar una hoja y reanclar** deja raíz y conteo cuadrando entre sí
     perfectamente, y lo único que delata el robo es que a beto le falta su
     hecho n.º 2 — que **él ve solo, mirando únicamente sus hojas**, sin ver el
     resto del libro ni tener que creernos.

   El segundo es el caso que importa, porque es el que haría alguien de dentro.

**Lo que queda dicho y no hecho.** La tercera pata de L15 —**publicar las hojas**
de la época— no es código de dominio: sin ella, «auditable» sigue dependiendo de
que nosotros contestemos. Está anotado en el encabezado de `epoca.ts` para que
nadie confunda «mi prueba verifica» con «el libro está entero».

**Las mutaciones (§0.5).**

| Se rompió | Se puso rojo |
|---|---|
| se quita la separación de dominio | **0 → 1** (tras reescribir el test) |
| los campos se concatenan sin longitud | **0 → 2** (tras encontrar la colisión real) |
| la hoja impar se duplica en vez de promoverse | 4 pruebas |
| el ancla deja de anclar el conteo | 2 pruebas |
| la secuencia por usuario deja de comprobarse | 2 pruebas |
| una época vacía devuelve un hash en vez de lanzar | 1 prueba |

**Puerta:** ✔ se genera una prueba de inclusión y se verifica; borrar una hoja
del libro rompe la verificación de alguien (por dos caminos distintos); y un
árbol con número impar de hojas verifica correctamente (probado con 1, 3, 5, 7,
9, 11, 13, 21 y 33). La API está documentada en el encabezado de `merkle.ts` para
la pantalla del verificador. Línea base intacta: mismas 8 rojas, +20 verdes
(340 a 360).


---

## U7 · Los contratos — SALTADA (sin herramientas)

**Qué pasó, medido en dos intentos.** `forge` no está instalado. `foundryup` se
descarga y arranca bien, pero falla al buscar la release: los binarios de Foundry
vienen de **GitHub releases**, y en este entorno `api.github.com` responde
**403**. La política de red deja pasar directo sólo unos pocos registros (npm,
PyPI, crates.io, proxy.golang.org). No es un problema de instalación — es la red,
y no se arregla desde aquí.

**Lo que costó descubrir, y que cambia la nota.** El reflejo era escribir «no hay
herramientas» y seguir. Pero `registry.npmjs.org` **sí** es alcanzable, y desde
ahí hay cadena de Solidity completa: `solc` 0.8.36 y `hardhat` 3.16.0, los dos
comprobados. Decir «no se puede» sin haber mirado el registro habría sido pereza
disfrazada de prudencia, que es literalmente lo que AGENTE §2 nombra.

**Y aun así se salta, que es distinto de no poder.** La puerta escrita es
`forge test` en verde. Meter Hardhat no es sustituir una herramienta: es añadir
una **segunda cadena de construcción** al repo, que heredan RasDG y el segundo
desarrollador con su config, su lenguaje de pruebas y su mantenimiento. Esa
elección no es de una sesión autónoma. Y escribir los tres contratos sin poder
probarlos sería peor que no tenerlos: Solidity sin pruebas de invariante en el
camino del dinero es exactamente lo que este repo llama una nota, no un arreglo.

**Lo que U7 ya no tendrá que inventar cuando se haga.** U6 deja la regla del
ancla escrita y probada —prefijos de dominio, hoja impar promovida, conteo y
secuencia—, así que `RegistroAnclas.sol` sólo tiene que emitir eso. La aritmética
ya no está en discusión.

`PREGUNTAS_ABIERTAS.md` P-006 deja las tres salidas posibles para RasDG.


---

## U8 · Sincronizar la documentación ✔

**Qué se hizo.** `LIQUIDEZ.md`, `MEMORY/marea/README.md` y `MEMORY/ESTADO.md`
dicen ahora lo que hay, no lo que se planeó.

- **`LIQUIDEZ.md`** — la tabla de invariantes pasa de «hay que cablear» a una
  tabla de **estado con el archivo donde quedó cada una**: L1, L2, L3, L5, L6,
  L8, L9 y L15 vivas; L14 pendiente de los contratos; la tercera pata de L15
  (publicar las hojas) dicha como lo que es, que no es código. Las fases L1, L2 y
  L3 quedan marcadas cerradas con **cómo cerraron**, no con un tic.
- **`MEMORY/marea/README.md`** — sección 9 nueva: las ocho unidades con su puerta
  **medida**, y las tres cosas que costó descubrir y no están en el diff.
- **`MEMORY/ESTADO.md`** — la foto de Marea, con la deuda L8 marcada saldada y la
  cifra de rojas corregida de 4 a 6.

**Lo que costó decidir: qué NO decir.** La tentación de una unidad de
documentación es contar lo hecho. Lo que hace útil la página es lo que sigue sin
estar, y por eso va en la **misma frase** que el estado, no en un apéndice:

> «Nadie nace en modo subsidio todavía, los topes no tienen cifras, los
> contratos no existen y las hojas de la época no se publican. El dominio está;
> el producto en cadena no.»

Un lector que sólo abra `MEMORY/marea/README.md` tiene que salir sabiendo las dos
mitades. Si sale creyendo que Marea tiene subsidio funcionando, la página hizo
daño en vez de servir — y ésa es exactamente la forma de fallo que el `CLAUDE.md`
del repo documenta como la lección más cara del proyecto: el repo sabía, y el
código siguió publicando otra cosa.

**Una corrección de dato, no de estilo.** `ESTADO.md` decía «4 rojas
preexistentes». Son **6** de `vitest` más 2 de `validate`, con la misma causa
raíz. Corregido, con la referencia a `LINEA_BASE.md` para que la próxima sesión
no vuelva a heredar el número equivocado.

**Puerta:** ✔ alguien que lea sólo `MEMORY/marea/README.md` sabe en qué estado
quedó todo — lo construido, lo que espera cifras de RasDG y lo que no existe.
Línea base intacta: 8 rojas, 360 verdes.


---

## §3 · Reforzar lo construido: el barrido de mutaciones

La cola dice que, al llegar al final, no se invente trabajo nuevo: se refuerzan
las pruebas de lo ya construido con más casos borde y **más mutaciones
deliberadas**. Eso es lo que se hizo, y automatizado.

**Por qué automatizarlo.** §0.5 —«rompe cada test nuevo a propósito una vez»— es
la regla más valiosa del repo y la más fácil de saltarse: hacerlo a mano son
cinco minutos por test y nadie los echa de menos. Un proceso que depende de que
alguien se acuerde no existe (AGENTE §2). Ahora es `npm run mutaciones`, con las
**50 mutaciones versionadas** en `marea/scripts/mutaciones.mjs`, y sale con
código 1 si alguna sobrevive sin estar marcada como equivalente.

**Lo que encontró la primera pasada: 7 de 24 mutaciones SOBREVIVÍAN.** Es decir,
siete formas de romper el código que la suite no veía, en código escrito **esta
misma sesión** y con sus tests puestos a mano. Los siete huecos:

| Hueco | Qué pasaba de verdad |
|---|---|
| `bettorStake` permite negativo | Un pozo corrupto (semilla > pozo) daría un multiplicador negativo: pagos negativos a quien acertó |
| `normalizePool` comparte el mapa de semilla | Alias: mutar el pozo releído cambiaría el que ya estaba en memoria. `outcomes` se copiaba por esta razón; la semilla no |
| El polvo de coma flotante crea una pata | `1000 − 999.9999999999999 = 1.1e-13` acreditaría a la casa una fracción de nada, en **cada** liquidación que no divide exacta |
| Un pago de cero crea una pata | Un asiento con tantas líneas como apostadores y una sola con dinero. Cuadra igual, y es ilegible |
| `verificar` no comprueba el rango del índice | El índice **no entra en el hash**: el camino solo ya prueba la inclusión, así que un índice absurdo no rompe la aritmética y hay que comprobarlo aparte |
| `pruebaDeInclusion` acepta índice fuera del árbol | Devolvería en silencio la prueba de la hoja 0: quien la pide se llevaría una prueba **válida de un hecho que no es el suyo** |
| Falta el reparto de un resultado | *(resultó equivalente, ver abajo)* |

**Y un mutante equivalente, que es un resultado distinto de un hueco.** «Falta el
reparto de un resultado» sobrevive porque `acunar()` lo rechaza igual, con un
mensaje que también nombra el resultado — medido, no supuesto. Pero **borrar la
guarda del todo no es equivalente**: `asignacionDe` recibiría `undefined` y
saldría un `TypeError: Cannot read properties of undefined`, un error de
plataforma en el camino del dinero que no dice qué arreglar. El test se cambió
para fijar **eso** —error de dominio, no `TypeError`— en vez de forzar una
comprobación sobre el texto de un mensaje. Una mutación que sobrevive no siempre
es un test que falta, y decir cuál es cuál es parte del trabajo.

**Resultado final: 49/50 detectadas, 1 equivalente documentada, 0 huecos.**

**La lección, que ya van tres veces esta sesión.** Los huecos no estaban
repartidos al azar: se concentran en **guardas que nunca se disparan en el camino
feliz** y en **propiedades adversarias**. El camino feliz se prueba solo. Lo que
un atacante rompería, o lo que sólo pasa con datos corruptos, hay que romperlo a
propósito para saber que el test lo mira — y contando U3 y U6, esta sesión
escribió **diez** tests que pasaban en verde sin probar lo que decía su nombre.


---

## §3 · La afirmación de U5 que no era del todo cierta

En U5 escribí que «para las series, que estén al día ya lo comprueba la propia
regla». Lo **leí** en el código; no lo medí. §3 pedía resolver lo que se pudiera
sin RasDG, y verificar una afirmación propia entra ahí de lleno.

**La regla existe, pero el margen estaba mal puesto en casi todas.**
`seriesOracle` compara `ultima.fecha >= settlesAt − frescuraDias`, y **sólo
`cl-imacec` declaraba `frescuraDias`**. Las otras ocho caían al defecto de **1.5
días** — mientras que el dato de una serie mensual llega fechado ~35 días antes
de resolver, porque va fechado al **periodo**, no a la publicación.

**Medido, inyectando las observaciones y sin tocar la red: cinco mercados no
podían resolverse nunca por programa.** `mx-inpc-anual`, `mx-banxico-tasa`,
`br-ipca-5`, `br-selic-corte` y `pe-inflacion-lima` descartaban su propio dato
correcto por viejo y se quedaban en `sin_dato` para siempre. Es un agujero de
ciclo de vida —se apuesta y no se cobra— y por AGENTE §0.1 vence a cualquier
otra cosa que hubiera podido hacer en ese rato.

**El detalle que más me interesa de todo esto:** dos de los cinco estaban
**tapados por la falta de token**. Sin `INEGI_TOKEN` / `BANXICO_TOKEN` el oráculo
contesta `requiere_humano` **antes** de llegar a la comprobación del margen. El
defecto sólo aparecía cuando alguien configurase las llaves — es decir, el día en
que el mercado por fin iba a funcionar solo. Lo encontré porque el test pone
tokens de mentira, no porque lo buscara. **Una configuración que falta puede
esconder un bug detrás, y el bug espera justo al momento en que dejas de mirar.**

**Arreglado y cerrado el lazo.** Los cinco declaran `frescuraDias: 100`, con su
porqué al lado. El 100 no es medido: es el valor que el repo ya había elegido
para `cl-imacec`, otra serie mensual, aplicado con consistencia — cubre el
desfase mensual (~35 d) y dos reuniones de COPOM/Banxico (~90 d), y **sigue
rechazando** una serie parada 200 días, con test de las dos cosas. Y
`tests/frescura.test.ts` comprueba que **toda** serie del catálogo acepta un dato
fechado a su cadencia real: escribir un mercado de serie sin margen adecuado
pone la suite en rojo, en vez de publicar un mercado que nadie podrá cobrar.

**La simetría que esta unidad enseña.** U5 evitó el umbral demasiado **holgado**
—una fuente parada resolviendo— y estuvo a punto de crear el demasiado
**apretado**. Resulta que el apretado ya existía, en cinco mercados, desde antes.
Las dos mitades de L8 son el mismo trabajo y ninguna se ve sin medir: leer el
código me dio la mitad correcta y la mitad falsa, con la misma confianza.


---

## §3 · El arnés de mutaciones tuvo que aprender a no mentir

Al ampliar el barrido al catálogo y a los oráculos, el propio arnés falló dos
veces — y las dos son instructivas, porque son los dos modos de falla de
cualquier detector.

**Falso positivo.** Declaré un hueco que no existía: «un partido a medias cuenta
como resultado» salía SOBREVIVE. Lo que estaba mal no era el código ni el test,
sino **la lista de archivos de la entrada** — apunté a `fuentes.test.ts` y la
cobertura estaba en `settlement.test.ts` y `multiples.test.ts`. Un arnés que da
falsas alarmas se acaba ignorando, y entonces deja de servir justo cuando
encuentre algo de verdad. Arreglado: si los tests declarados no ven la mutación,
se reintenta con **la suite entera** antes de cantar un hueco, y el informe
distingue «no lo ve nadie» de «corrige la lista».

**Falso negativo, y peor.** El arreglo anterior, tal como lo escribí primero,
daba por detectada **cualquier** mutación — porque la suite arrastra 6 rojas
conocidas del catálogo caducado, y yo comparaba contra cero. Un arnés que siempre
dice que sí es el mismo que no existe, sólo que además esconde los huecos de
verdad. Se vio al instante: el mutante que sabía equivalente salió «6 rojas ·
detectada».

Arreglado midiendo **la línea base al arrancar** y contando detectada sólo si
sube de ahí. Es la misma lección de U0 —comparar contra la línea base, no contra
cero— aplicada al detector en vez de al trabajo. Que haya vuelto a aparecer en la
misma sesión, en una herramienta que escribí precisamente para tener disciplina,
dice bastante de lo fácil que es.

**Estado final del barrido: 53 mutaciones, 52 detectadas, 1 equivalente
documentada, 0 huecos.** `npm run mutaciones` sale con código distinto de cero si
aparece un hueco.

**Y una comprobación de ciclo de vida que ahora es permanente:** todo mercado del
catálogo —serie, precio y partido— tiene que resolverse por programa cuando su
fuente contesta lo que la regla pide. Es la forma general del agujero que atascó
las cinco series, y estaba a un test de distancia de no encontrarse nunca.


---

## §3 · La ventana entre pagar y marcar

Verificado el ciclo entero en proceso real —crear, apostar, cerrar, resolver,
esperar la disputa, pagar, reiniciar— no apareció ningún defecto. Pero al
convertirlo en test permanente apareció otra cosa, y es la cuarta vez esta
sesión.

**El test que escribí para el redeploy no probaba lo que decía su nombre.**
Corría el ciclo dos veces con un reinicio en medio y daba verde **aunque se
desactivara la idempotencia del store**. La razón: `ciclo.mts` ve la fase
`pagado` y se salta el bloque de liquidación entero, así que la guarda del store
ni se llama. El test probaba la guarda de fuera y no la de dentro. Lo encontró
el arnés de mutaciones, no yo.

**Y la guarda de dentro protege un caso real que ningún test tocaba.**
`ciclo.mts` **paga primero y marca después**, a propósito: si el proceso muere en
medio, el dinero ya está acreditado y el estado se recalcula solo. Pero si muere
justo ahí, al arrancar la fase sigue siendo `en_disputa`, `isPayable` sigue dando
true, y el ciclo **vuelve a liquidar un mercado que ya se pagó**. En Railway, que
redeploya en cada push, esa ventana es real.

Medido con la idempotencia desactivada, el fallo es exactamente el que se teme:
la casa cobra la comisión de 24 **dos veces**. Y pagar dos veces no descuadra el
libro — lo deja cuadrado con el saldo del pozo en **negativo**, que es mucho peor
de encontrar. Hay test, y se ve en rojo.

**Un tercer hallazgo, más pequeño:** la condición `estado.phase === "en_disputa"`
de `ciclo.mts` es **redundante** — `isPayable` ya la comprueba por dentro. La
protección real contra un mercado ya pagado viene de ahí. Queda anotado como
mutante equivalente en el arnés en vez de borrarse: dos guardas para lo mismo son
baratas, y saber cuál es la que sostiene el peso vale más que quitar una línea.

**Barrido final: 55 mutaciones, 53 detectadas, 2 equivalentes documentadas, 0
huecos.**


---

## §3 · El barrido sobre lo que ya existía: la puerta de elegibilidad

Ampliar el arnés al código anterior a esta sesión encontró **dos guardas viejas
sin verificación**, y una de ellas es la que la cola nombra explícitamente como
intocable.

### 1. La puerta de elegibilidad aguantaba por casualidad

Poner `allowed = true` en `eligibilityFor` —abrir la puerta para **todos** los
países de golpe— dejaba **la suite entera y `npm run validate` en verde**.

Por qué se escapó de las tres capas:

| Capa | Qué comprueba | Por qué no lo vio |
|---|---|---|
| `validate.mjs` | que el archivo no contenga `status: "permitido"` | es una comprobación sobre el **texto de los datos**; la función que los lee puede cambiar sin tocarlos |
| `eligibility.test.ts` | `canDeposit === false` en todos los países | sigue en `false` **por el tope**: `canDeposit = allowed && cap > 0`, y todos los topes valen 0 |
| nadie | `canTrade` | no tiene consumidor todavía, así que podía volverse `true` para todo el mundo sin que nada fallara |

**La puerta aguantaba por una coincidencia —el tope en cero— y no por el
estado.** Con un tope distinto de cero en un país `pendiente`, se abría. Y
`canTrade` era una bandera que decía «esta persona puede operar» esperando a su
primer consumidor.

Es exactamente la forma de fallo que el `CLAUDE.md` del repo llama la lección más
cara: *el fallo no fue de conocimiento sino de cableado*. La política decía lo
correcto; lo que la lee podía dejar de obedecerla en silencio.

Arreglado atando el comportamiento al **estado**: para todo país cuyo `status` no
sea `permitido`, `canDeposit` y `canTrade` son `false`. Y se mantiene la otra
mitad —explorar nunca pide nada (R-002, I1)— que también estaba sin comprobar en
todos los países.

### 2. La recarga diaria se podía pedir dos veces

El test que existía —«no se recarga dos veces el mismo día»— pedía la recarga con
el saldo **intacto**, y ahí el tope de saldo ya devuelve 0 por su cuenta: la
comprobación de «ya la pidió hoy» quedaba enmascarada. Medido: quitarla dejaba la
suite en verde.

El caso que la necesita es el que un usuario encuentra solo: recarga, apuesta los
100, y vuelve a pedir. Sin la guarda, eso son **puntos infinitos**. Con test, y
con el del día siguiente para que el arreglo no se pase de frenada.

### Lo que enseña el patrón

Las dos guardas llevaban meses puestas y las dos estaban sin verificar. **Una
guarda vieja sin verificación es igual de frágil que una nueva; sólo lleva más
tiempo siéndolo.** Y las dos fallaron por la misma razón: el test miraba un
efecto que estaba tapado por **otra** condición —el tope en un caso, el saldo en
el otro—, así que pasaba en verde por el motivo equivocado.

**Barrido final: 67 mutaciones, 65 detectadas, 2 equivalentes documentadas, 0
huecos.**


---

## §3 · El arnés rompía el repo y se le podía morir a medias

Al retomar la sesión, `git status` mostraba `settlement.ts` modificado — y yo no
lo había tocado. Era un **resto de mutación**: el barrido se interrumpió a mitad
y el archivo se quedó roto en el árbol de trabajo, con un `Math.max(0, ...)`
menos. El `finally` que restaura cada mutación **no corre si el proceso muere
por señal**.

Es el peor fallo posible en esta herramienta: rompe el repo a propósito, y si la
matan deja el daño puesto y en silencio. Alguien podría commitear una mutación.

Blindado con tres cosas:

1. **Restaura ante señal.** `SIGINT`, `SIGTERM`, `SIGHUP` y `uncaughtException`
   devuelven a su sitio todos los archivos en vuelo antes de salir.
2. **No arranca con el árbol sucio** en un archivo que vaya a mutar. Podría ser
   trabajo legítimo sin guardar —que se perdería al restaurar— o el resto de un
   barrido anterior. Las dos cosas se arreglan mirando, no siguiendo.
3. **Respaldos con nombre único** por posición, para que dos mutaciones sobre el
   mismo archivo no se pisen el respaldo.

**Y el guardia funcionó a la primera:** al probarlo encontró un **segundo** resto
que yo no sabía que estaba ahí — un `if (false)` en la comprobación de frescura
de `seriesOracle.ts`, de la misma interrupción. Dos archivos rotos en el árbol,
uno de ellos sin que nadie lo hubiera notado.

La lección se parece a la de siempre en esta sesión: la herramienta que existe
para tener disciplina también necesita que alguien la mire.


---

## El arreglo de producción (2026-09-10/11)

Fuera de la cola. RasDG mandó capturas de la app: la pantalla casi vacía, su
portafolio lleno de apuestas que no concluían, la tabla diciendo «precisión 10 %
· 1/10», y un mercado cerrado de Brasil saliendo entre los abiertos.

**El hallazgo que cambia cómo se trabaja este repo.** `/api/mercados` de
producción sirve campos —`shortTitle`, y los mercados `live` de velas de 5 y 15
min— que **no existen en `main` ni en nada que `main` contenga**. Producción no
corre `main`: corre `claude/marea-redesign-v6-b0240n`, una rama sin fusionar, 15
commits por delante, del 7 de agosto. Mis 19 commits de la cola estaban sobre
`main`, así que no habrían llegado a la app; peor, fusionarlos a `main` y
desplegar habría podido pisar el rediseño y la cripto en vivo.

Se portaron con un merge (4 conflictos, resueltos conservando los dos lados) y
**se fusionaron a la rama de producción** con permiso explícito de RasDG.

### Lo que estaba roto, medido contra producción y no razonado

| Síntoma | Causa, con su evidencia |
|---|---|
| Mercados congelados sin resultado | `/salud`: **1008 corridas, 0 errores, 0 atorados** mientras había apuestas de agosto sin concluir. El oráculo contesta `sin_dato`, `onRead` hace lo correcto y reintenta — y mil veces seguidas eso es un mercado congelado. `sin_dato` no es `atorado`, así que era invisible por construcción. El propio mercado `br-ipca-5` guardaba la evidencia: «No se pudo leer Banco Central do Brasil: Unexpected token '<', "<?xml vers"… is not valid JSON» |
| Precisión 1/10 en la tabla | Consecuencia: nueve apuestas nunca concluyeron |
| `latam-libertadores-br` con el id crudo por título | El ciclo itera sobre **semillas**; si el mercado sale del catálogo, nadie vuelve a mirarlo jamás y el dinero se queda quieto |
| Abrir una apuesta vieja daba «ese mercado ya no existe» | La ruta de detalle filtraba por `activeSeeds`, que es el filtro del **feed** |
| Brasil cerrado entre los abiertos | `hot` se calculaba por pozo sin mirar si aceptaba apuestas — y los pozos viejos, que son los más grandes, **subían el listón** a los mercados nuevos |
| La plataforma vacía | `roll` lo dispara un cron instalado **en la máquina de alguien**. Nadie lo corrió desde principios de agosto |

### Lo que se cableó

- **Dos plazos** desde `settlesAt`: a los 7 días el mercado se marca `atorado` y
  **aparece**; a los 30 se da por incobrable, se anula y **se devuelve todo sin
  comisión**. `atorado` deja de ser un callejón sin salida: si la fuente vuelve,
  el mercado se resuelve solo y el motivo se borra con él.
- **`congelados()` y `apuestasHuerfanas()`**, los dos auditores que faltaban, y
  los dos expuestos en `/salud`. `cuadre()` no puede ver esto: no hay dinero
  descuadrado, hay dinero **quieto**.
- **Las huérfanas se devuelven** íntegras y sin comisión. Si el mercado
  desapareció nadie puede acertar, y quedarnos con esos puntos porque el mercado
  se perdió por el camino sería cobrar por nuestro propio error (R-024).
- **El feed** no enseña puertas con candado: un cerrado nunca es `hot`, va al
  final, y el umbral se mide sólo entre los que aceptan apuestas.
- **`server/reposicion.mts`**: el catálogo se repone **dentro del servidor**, por
  el mismo reloj que el liquidador y al mismo volumen persistente, pasando por el
  freno de presupuesto de L9.

### Las dos cosas que encontró el proceso real y no la suite

1. **Conté las velas de 5 min como feed sano.** Arrancando contra un disco limpio
   no repuso **nada** —cuatro velas más tres duraderos daban siete, por encima
   del mínimo de seis— con la pantalla igual de vacía. Ahora sólo cuentan los
   duraderos, y hay test con ese caso exacto.
2. **La reposición se callaba cuando no podía.** El mismo fallo de invisibilidad
   que llevo toda la sesión cerrando, cometido por mí. Ahora registra también el
   intento fallido.

Medido en proceso real, disco limpio: primer ciclo «el feed está corto (3 de 6) y
no se creó nada» —el ticker aún no tenía precios—; segundo ciclo, «4 mercados
nuevos». El feed pasó de **4 a 8 mercados duraderos, solo**.

### El arnés, por tercera vez

Volvió a dar una falsa alarma, y la causa es la misma que las dos anteriores: **no
distinguía las maneras de no detectar algo**. Tres patrones quedaron obsoletos
tras el merge y el resumen los contó como huecos. «El patrón ya no existe» es una
mutación caduca —deuda—, no un test que falta. Ahora se reportan aparte.

**Barrido final sobre la rama de producción: 92 mutaciones, 89 detectadas, 3
equivalentes documentadas, 0 huecos.**
