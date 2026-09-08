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
