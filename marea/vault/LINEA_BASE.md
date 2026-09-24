# LÍNEA BASE de la suite — antes de tocar nada

> Se escribe al arrancar una sesión autónoma (U-V0). Sirve para distinguir una rotura
> propia de la que ya estaba. **Regla desde aquí: el número de rojas no crece.**

## Corte 2026-09-24 · `npx vitest run` en `marea/`

- **287 verdes · 6 rojas.**
- Las 6 rojas son **preexistentes y no son de código**: el catálogo estático de mercados
  tiene fechas ya vencidas (R-041). Se arreglan con `npm run roll` (que reescribe catálogo de
  producción y **no se corre en la sesión autónoma**), no con un cambio de código.

### Las 6 rojas conocidas

```
tests/ownmarkets.test.tsx  > adapter  > expone el pozo, la probabilidad implícita y el criterio citado
tests/ownmarkets.test.tsx  > adapter  > la referencia externa se carga sola y enciende el Edge
tests/ownmarkets.test.tsx  > adapter  > si la referencia se cae, no hay Edge y el feed sigue vivo
tests/ownmarkets.test.tsx  > interfaz > explorar sigue sin costar nada: se ve todo con cero puntos
tests/ownmarkets.test.tsx  > interfaz > las cards muestran cuánto paga, no cuánto se ha operado
tests/settlement.test.ts   > catálogo que se repone solo > V34 un mercado vencido sale del feed
```

Todas fallan porque `activeSeeds(hoy)` encuentra menos mercados vigentes de los esperados: las
semillas del catálogo caducaron. Es el mismo síntoma que documentó `MEMORY/ESTADO.md` (eran 4
en septiembre; el paso del tiempo las subió a 6).

_Si en un arranque futuro hay **más** de estas 6, o alguna **fuera** de `ownmarkets`/`settlement`,
es una rotura nueva: párate y encuéntrala antes de seguir._
