# LÍNEA BASE — antes de tocar nada

> Unidad 0 de `COLA_TRABAJO.md`. Sin esto no se puede distinguir una rotura
> propia de la que ya estaba. **A partir de aquí la regla es: el número de
> rojas no crece.**

- **Fecha:** 2026-09-08
- **Commit:** `857a125` (Marea: la cámara de compensación — diseño, invariantes,
  compensador puro y manuales, #225)
- **Rama:** `claude/marea-autonomous-work-3sggb9`, partiendo de `origin/main`.
- **Entorno:** Node v22.22.2, npm 10.9.7, `npm ci` → 277 paquetes, sin errores.

---

## Resultado medido

| Comando | Resultado |
|---|---|
| `tsc -b --noEmit` | **verde** |
| `npx vitest run` | **6 rojas / 287 verdes** (293), 2 archivos rojos de 22 |
| `node scripts/validate.mjs` | **FAIL** — 8 fallos (6 son las mismas pruebas rojas) |
| `npm run build` | **no llega a correr**: `npm run ci` aborta en `validate` |

`npm run ci` = `tsc -b --noEmit && node scripts/validate.mjs && npm run build`.
Como `validate` sale con FAIL, la cadena se corta ahí. **La línea base de
`npm run ci` es, por tanto, FAIL**, y comparar contra ella significa: los mismos
8 fallos, ni uno más.

## Las 6 pruebas rojas conocidas

Todas en dos archivos, y **todas con la misma causa raíz**:

`tests/settlement.test.ts`
1. `catálogo que se repone solo > V34 un mercado vencido sale del feed`
   — `expected 4 to be 13`

`tests/ownmarkets.test.tsx`
2. `adapter > expone el pozo, la probabilidad implícita y el criterio citado`
   — `expected 4 to be 13`
3. `adapter > la referencia externa se carga sola y enciende el Edge`
   — `TypeError: Cannot read properties of undefined (reading 'edge')`
4. `adapter > si la referencia se cae, no hay Edge y el feed sigue vivo`
   — `expected 4 to be greater than 8`
5. `interfaz > las cards muestran cuánto paga, no cuánto se ha operado`
   — `expected 4 to be greater than 5`
6. `interfaz > explorar sigue sin costar nada: se ve todo con cero puntos`
   — `expected 4 to be greater than 5`

Más dos verificaciones de `validate.mjs` que no son pruebas de `vitest`:

7. `L1 — todo mercado publicado tiene camino de liquidación`
   — «el liquidador no corre desde hace 1015 h» (presupuesto: ≤ 36 h).
8. `M1 — el feed no se queda sin mercados abiertos`
   — «sólo 4 mercados abiertos (mínimo 6)».

## La causa raíz, verificada

`src/adapters/ownMarkets/catalog.ts` tiene **13 mercados**. `activeSeeds()` filtra
por `closesAt > now`. Al 2026-09-08 sólo **4** siguen abiertos:

| Mercado | `closesAt` |
|---|---|
| `br-ipca-5` | 2026-09-09 |
| `br-selic-corte` | 2026-09-16 |
| `eth-4500` | 2026-09-30 |
| `pe-inflacion-lima` | 2026-09-30 |

Los otros 9 vencieron entre el 2026-07-31 y el 2026-09-01. **El 4 que aparece en
los seis mensajes de error es ese 4.** No es un bug de código: el filtro hace
exactamente lo que debe. Es el catálogo estático que caducó.

El L1 rojo es el mismo hecho por otro lado: el liquidador lleva 1015 h sin correr
(≈42 días), que es justo la ventana en la que el catálogo se fue venciendo.

## Por qué no se arreglan aquí

`COLA_TRABAJO.md` §0 lo prohíbe explícitamente: **el catálogo caducado es del
segundo desarrollador** (su día 1), y correr `npm run roll` / `npm run settle`
sale a APIs reales y reescribe el catálogo de producción. Se dejan rojas a
propósito.

## Discrepancia con la cola

`COLA_TRABAJO.md` dice «4 pruebas rojas conocidas». Son **6** pruebas de `vitest`
(en los dos archivos que la cola nombra) más 2 verificaciones de `validate`. La
causa raíz es la que la cola describe y la frontera no cambia; lo que cambia es
el número contra el que se compara. **Vale el 6 medido, no el 4 escrito** —
anotado en `PREGUNTAS_ABIERTAS.md`.

---

_Medido el 2026-09-08 corriendo los comandos, no de memoria._
