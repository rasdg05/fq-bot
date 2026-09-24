# COLA DE TRABAJO — sesión autónoma

> **Este documento manda sobre cualquier impulso de ir más rápido o de ampliar el alcance.**
> Se lee entero antes de tocar nada. Complementa `AGENTE.md` (especificación operativa), que
> gana si hay contradicción.
>
> Es la cola de **RasDG + Claude**. El segundo desarrollador tiene la suya en
> `ENCARGO_RAMPA.md` y **no se toca**.
>
> **Arranque en frío:** un turno nuevo lee, en orden, `CLAUDE.md` → `MEMORY/00-INDICE.md` →
> `MEMORY/marea/README.md` → `MEMORY/ESTADO.md` → `vault/RULINGS.md` → este archivo. Con eso
> sabe qué es Marea, qué está vivo, qué reglas no se rompen y qué toca hoy.

---

## 0. Reglas de autonomía

1. **Trabaja la cola en orden, una unidad a la vez.** Terminar una vale más que empezar tres.
2. **No pares a preguntar.** Si hace falta una decisión que no está escrita, elige **la opción
   más conservadora**, anótala en `marea/vault/PREGUNTAS_ABIERTAS.md` con su fecha y la
   alternativa que descartaste, y sigue. Bloquearse a esperar respuesta es el único fracaso
   real de una sesión autónoma.
3. **Un commit por unidad**, con el **porqué** en el mensaje. Empuja después de cada unidad —
   no acumules.
4. **Antes de cada commit:** `npm run ci` y la suite (`npx vitest run`). Compara contra la
   **línea base** (U-V0), no contra cero.
5. **Rompe cada test nuevo a propósito una vez** y confirma que se pone rojo. Escribe en el
   commit que lo hiciste y qué rompiste. Un test que nunca viste en rojo no sabes si prueba algo.
6. **Al cerrar cada unidad**, escribe a `MEMORY/marea/` qué se hizo y qué costó descubrir.
7. **Si una unidad se atasca tras dos intentos serios:** anótala en `PREGUNTAS_ABIERTAS.md`,
   déjala como estaba y **pasa a la siguiente**. No quemes la sesión en una piedra.
8. **Sigue hasta que te interrumpan.** No hay «terminé por hoy».

### Lo que no se hace, nunca

- **Tocar la zona del segundo desarrollador** (§1).
- **Abrir la puerta de elegibilidad**, ni «para probar». Todos los países siguen en `pendiente`.
- **Empujar a `main`** ni abrir PR sin que RasDG lo pida.
- **Correr `npm run roll` / `settle` / `deploy` contra la red.** Reescriben catálogo de
  producción y salen a APIs reales. El catálogo caducado es del segundo dev (su día 1).
- Tocar llaves, secretos, o cualquier cosa que mueva dinero.
- Cambiar una regla de `RULINGS.md` o una invariante sin que lo pida RasDG.
- **Inventar números de ley.** Los topes de nivel, la ventana de anti-structuring y los
  umbrales fiscales los fija el abogado (P11, P15–P18). El código deja el hueco parametrizado
  y conservador; nunca hardcodea una cifra como si fuera la norma.

---

## 1. La frontera con el segundo desarrollador

**Suyo — no se toca ni para «mejorarlo»:**

```
src/adapters/puente/**          la rampa entera
src/domain/solicitudes.ts       la máquina de estados de depósito
src/screens/  (depósito)        pantallas del flujo de entrada de dinero
src/screens/VerificarPrueba.tsx la pantalla del verificador (consume nuestro módulo)
server/vigilante.mts            el vigilante de L14
```

**Nuestro:** `domain/pozo.ts` · `domain/parimutuel.ts` · `domain/contabilidad.ts` ·
`domain/settlement.ts` · `domain/merkle.ts` · `domain/epoca.ts` · `domain/presupuesto.ts` ·
`domain/niveles.ts` (nuevo) · `contratos/**` · `server/ciclo.mts`.

**Compartido — cuidado:** `adapters/index.ts` · `lib/config.ts` · `lib/strings.ts` ·
`state/store.tsx` · `domain/eligibility.ts`. Ahí: añadir al final, nunca reordenar bloques
existentes, y en `eligibility.ts` **nunca cambiar el estado de un país** — sólo componer,
apagado por defecto.

> **Nota de secuencia:** el dominio puro (`domain/niveles.ts`) se construye con su API
> documentada; la pantalla que la consume (suya, `VerificarPrueba.tsx` y el flujo de depósito)
> viene después. Que nosotros vayamos primero es correcto y a propósito.

---

## 2. La cola — Sprint actual: verificación por niveles

Cierra el lazo de las reglas R-069…R-072 recién escritas: pasarlas de regla a **dominio puro
con prueba**, que es lo que la casa entiende por «cableado» (CLAUDE.md: *un hallazgo sin
invariante que lo haga cumplir es una nota*). Todo esto es construible **hoy**, en dominio puro,
**sin abrir la puerta de elegibilidad** y **sin tocar la zona del segundo dev**. Los números de
topes y la ventana exacta se dejan parametrizados: la estructura no depende de ellos.

Contexto de diseño: `vault/NIVELES_VERIFICACION.md` (§3 escalera, §5 preguntas) y el Plano 07 de
`vault/planos-construccion.html`.

### U-V0 · Línea base de la suite
Corre `npx vitest run` y **anota qué está rojo antes de empezar** en `marea/vault/LINEA_BASE.md`,
con fecha y motivo conocido.

Rojas conocidas (2026-09-24): **6**, todas en `ownmarkets.test.tsx` (5) y `settlement.test.ts`
(1), por fechas de catálogo caducadas (R-041) — **no son bug de código y no son nuestras**; se
arreglan con `npm run roll`, que no se corre aquí. Regla desde aquí: **el número de rojas no
crece**.

**Puerta:** el archivo existe, nombra las 6 rojas conocidas.

---

### U-V1 · La escalera y el tope efectivo · `domain/niveles.ts` (nuevo) — R-069/L16
Módulo de funciones puras. Sin estado, sin red, sin importar `eligibility.ts` (recibe el tope de
país por parámetro; así no hay riesgo de rozar la puerta).

- `Nivel = "N0" | "N1" | "N2" | "N3"` y la metadata de la escalera (qué se le pide, qué puede)
  como estructura de datos, no como lógica dispersa.
- `effectiveCapUsd(countryCapUsd, nivelCapUsd)` donde `nivelCapUsd: number | null` (null = el
  nivel no impone tope; sólo manda el país, caso N3). Resultado = `min` tratando null como +∞.
- `NIVEL_CAP_USD`: N0/N1 = 0 (sin dinero), **N2 = provisional, marcado pendiente P11** (constante
  nombrada, no una cifra disfrazada de ley), N3 = null.

**Puerta:** property test — para cualquier par `(country, nivel)`, `effectiveCap ≤ ambos` y
`= min(country, nivel)`; N3 nunca añade tope propio; N0 y N1 nunca habilitan dinero. Rompe el
`min` a propósito (cámbialo por `max`) y confirma rojo.

---

### U-V2 · Anti-structuring por ventana móvil · `domain/niveles.ts` — R-070
Función pura sobre una lista de retiros; **sin relojes de pared** (el `now` entra por parámetro,
como en el resto del repo).

- `detectStructuring(retiros, { windowDays = 30, thresholdUsd }, now)` →
  `{ triggered, acumuladoUsd, destinosDistintos, motivo }`.
- Suma los retiros dentro de la ventana móvil que termina en `now`; dispara si el acumulado cruza
  el umbral aunque cada retiro individual quede debajo. El cambio recurrente de dirección destino
  en ventana corta también dispara.

**Puerta:** varios retiros bajo umbral que suman > umbral dentro de la ventana → `triggered`; los
mismos, fuera de la ventana → no; monotonía (más retiros no baja el acumulado). Rompe un test
(ventana que ignora el tiempo) y confirma rojo. La ventana de 30 días es valor de trabajo (P15);
va como default parametrizable, no como constante mágica.

---

### U-V3 · Lista cerrada de KYC y screening · `domain/niveles.ts` — R-072/R-071
- `kycTrigger(ctx): "tope" | "structuring" | "voluntario" | null`. La **lista cerrada** la
  garantiza el tipo de retorno: fuera de esas tres condiciones, `null` (no se piden papeles, R-002).
- `screenDestino(direccion, isSanctioned): { firmar: boolean, motivo }`. Rechaza en **ambos
  sentidos** (depósito y retiro), sin excepción por nivel. Rechazar es **no firmar**, nunca
  retener: la función no toca saldo, sólo decide si se firma esa transferencia.

**Puerta:** sin ninguna de las 3 condiciones → `kycTrigger` = null; una dirección sancionada →
`firmar: false` tanto en retiro como en depósito; una limpia → `firmar: true`. Rompe un test
(que una condición falsa dispare KYC) y confirma rojo.

---

### U-V4 · Sincronizar la documentación del sprint
Que `MEMORY/marea/README.md` y `MEMORY/ESTADO.md` reflejen que `domain/niveles.ts` pasó de plan a
**vivo**, y qué invariantes (R-069…R-072) quedaron con prueba. Actualiza la tabla «qué se puede
construir ya» del `NIVELES_VERIFICACION.md` si algún YA cambió de estado.

**Puerta:** alguien que lea sólo `MEMORY/ESTADO.md` sabe que el dominio de niveles está cableado
y qué falta (los números, que esperan al abogado; y la pantalla, que es del 2º dev).

---

## 3. Backlog previo (liquidez y cadena) — después del sprint

Unidades del plan de compensación/cadena que siguen **pendientes** y son la siguiente cola cuando
el sprint de verificación cierre. No se borran: son trabajo válido, sólo des-priorizado frente a
cerrar el lazo de las reglas nuevas.

- **Subsidio de la semilla** (`domain/parimutuel.ts`): `settle()` y `payoutMultiplier()` descuentan
  la semilla del denominador en el **mismo commit**; `seedMode` por mercado; no migrar mercados
  abiertos (R-023, R-024, R-044, R-067). *Puerta:* `quote().toWin == settle().payouts[esa apuesta]`
  para cualquier pozo, en ambos modos.
- **Presupuesto y freno** (`domain/presupuesto.ts`, nuevo): subsidio comprometido, exposición viva,
  y el guardia de creación contra los topes (R-068, L9). *Puerta:* sin presupuesto no se crea mercado.
- **Frescura del oráculo** (`domain/settlement.ts`, deuda L8): la antigüedad entra por parámetro, no
  por reloj. *Puerta:* una lectura más vieja que el umbral no avanza de fase; se reintenta y lo declara.
- **El árbol de época** (`domain/merkle.ts` + `domain/epoca.ts`, nuevos): hoja `0x00`, nodo `0x01`,
  hoja impar se promueve, secuencia por usuario + conteo en el ancla (L15). *Puerta:* borrar una hoja
  rompe la verificación de alguien; árbol impar verifica.
- **Los contratos** (`contratos/`, sólo si hay Foundry): `BovedaTopada.sol` (con el tope por nivel de
  L16/R-069), `AdaptadorOraculo.sol`, `RegistroAnclas.sol`, reutilizando los Conditional Tokens.
  *Puerta:* `forge test` verde con invariantes L1/L5/L14/L16. Si no hay `forge`, se salta y se anota.

Detalle de cada una en el histórico de este archivo y en `LIQUIDEZ.md`.

---

## 4. Al terminar la cola

Si llegas al final antes de que te interrumpan: **no inventes trabajo nuevo.** Revisa
`PREGUNTAS_ABIERTAS.md`, resuelve lo que sí se pueda sin decisión de RasDG, refuerza pruebas de lo
ya construido (más casos borde, más mutaciones deliberadas), y deja un resumen del estado en
`MEMORY/marea/`.

_Escrito 2026-09-08. Reescrito 2026-09-24: sprint de verificación por niveles al frente; el
backlog de liquidez/cadena pasa a §3._
