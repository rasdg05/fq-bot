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
