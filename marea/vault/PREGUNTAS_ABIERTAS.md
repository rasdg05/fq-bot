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

_Se abre esta bitácora el 2026-09-08. Formato: qué faltaba, qué se eligió, qué se
descartó, qué costaría revertirlo._
