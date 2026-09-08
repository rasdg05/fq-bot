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

---

_Se abre esta bitácora el 2026-09-08. Formato: qué faltaba, qué se eligió, qué se
descartó, qué costaría revertirlo._
