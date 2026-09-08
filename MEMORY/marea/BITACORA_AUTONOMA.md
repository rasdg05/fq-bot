# BITÁCORA — sesión autónoma sobre Marea

> Registro por unidad de `marea/vault/COLA_TRABAJO.md`. Regla §0.6: al cerrar cada
> unidad se escribe **qué se hizo y qué costó descubrir**. Lo segundo es lo que
> vale: el código está en el diff, el descubrimiento no.
>
> Iniciada el 2026-09-08 sobre `857a125`, rama
> `claude/marea-autonomous-work-3sggb9`.

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
