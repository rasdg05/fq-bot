# COLA DE TRABAJO — sesión autónoma

> **Este documento manda sobre cualquier impulso de ir más rápido o de ampliar el alcance.**
> Se lee entero antes de tocar nada. Complementa `AGENTE.md` (especificación operativa), que
> gana si hay contradicción.
>
> Es la cola de **RasDG + Claude**. El segundo desarrollador tiene la suya en
> `ENCARGO_RAMPA.md` y **no se toca**.

---

## 0. Reglas de autonomía

1. **Trabaja la cola en orden, una unidad a la vez.** Terminar una vale más que empezar tres.
2. **No pares a preguntar.** Si hace falta una decisión que no está escrita, elige **la opción
   más conservadora**, anótala en `marea/vault/PREGUNTAS_ABIERTAS.md` con su fecha y la
   alternativa que descartaste, y sigue. Bloquearse a esperar respuesta es el único fracaso
   real de una sesión autónoma.
3. **Un commit por unidad**, con el **porqué** en el mensaje. Empuja después de cada unidad —
   no acumules.
4. **Antes de cada commit:** `npm run ci` y la suite. Compara contra la **línea base**
   (unidad 0), no contra cero.
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
`contratos/**` · `server/ciclo.mts`.

**Compartido — cuidado:** `adapters/index.ts` · `lib/config.ts` · `lib/strings.ts` ·
`state/store.tsx`. Ahí: añadir al final, nunca reordenar bloques existentes.

> **Nota de secuencia:** nosotros construimos `domain/merkle.ts` con su API documentada; él
> construye la pantalla que la consume. Que nosotros vayamos primero es correcto y a propósito.

---

## 2. La cola

### U0 · Línea base de la suite
Instala dependencias (`npm ci`), corre la suite completa y **escribe qué está rojo antes de
empezar** en `marea/vault/LINEA_BASE.md`, con la fecha y el motivo conocido.

Hay 4 pruebas rojas conocidas (`ownmarkets`, `settlement` V34) porque el catálogo tiene fechas
caducadas — **no son un bug de código y no son nuestras**. Sin esta línea base no puedes
distinguir tu propia rotura de la que ya estaba.

**Puerta:** el archivo existe, nombra las rojas conocidas, y a partir de aquí la regla es *el
número de rojas no crece*.

---

### U1 · La semilla se vuelve subsidio  ·  `domain/parimutuel.ts`
La decisión ya está tomada (R-067) y el diseño está escrito en `LIQUIDEZ.md` §6.1. Tres cosas
que van **en el mismo commit** porque separarlas rompe el producto:

- `settle()` reparte entre los usuarios ganadores, excluyendo la semilla del denominador.
- **`payoutMultiplier()` descuenta la semilla del denominador también.** Si sólo cambia
  `settle()`, la app muestra menos de lo que paga — mentir en la dirección generosa sigue
  siendo mentir (R-023, R-044).
- `seedMode: "apuesta" | "subsidio"` como campo de la semilla del mercado. **Los mercados
  abiertos no se migran:** cada uno termina con las reglas con las que nació.

*Casos borde:* si el lado ganador sólo tiene semilla, se devuelve todo sin comisión (R-024) y
la semilla vuelve a tesorería. R-059 sigue anulando el mercado de un solo apostador.

**Puerta:** un test de propiedad que, para cualquier pozo y cualquier apuesta,
`quote(...).toWin === settle(...).payouts[esa apuesta]` cuando ese lado gana — con
`seedMode: "subsidio"` y con `"apuesta"`. Y los mercados en modo `"apuesta"` pagan **exactamente
igual que hoy**.

---

### U2 · Cablear el compensador  ·  fase L2 del plan
Que el movimiento de saldos pase por `domain/pozo.ts` en vez de aplicarse directo.
`settle()` pasa a ser un productor de reparto; quien mueve saldos es el compensador.

Es **refactor con red**: cero cambios de comportamiento visible.

**Puerta:** la suite pasa **sin tocar las expectativas de ninguna prueba existente**. Si hay
que cambiar una expectativa, el refactor está mal — párate y anótalo.

---

### U3 · El asiento del subsidio  ·  `domain/contabilidad.ts`
Tipo de asiento `subsidio`, y la separación de cuentas de L3: el fee y el colateral **no
comparten cuenta**, y el fee se asienta en el mismo asiento que lo genera (R-064, R-066).

**Puerta:** tras liquidar un mercado con comisión > 0, `saldoDe(libro, "pozo:<id>") === 0`, y
`cuadre(libro) === 0` antes y después de cada operación.

---

### U4 · Presupuesto y freno  ·  `domain/presupuesto.ts` (nuevo)
Funciones puras: subsidio comprometido por mercado, exposición viva total, y la decisión
«¿se puede crear otro mercado?» contra los topes.

Después, el freno en el camino de creación (R-068, L9). **No corras `roll` contra la red:**
prueba la función pura y el guardia.

**Puerta:** con el presupuesto agotado, la función de creación se niega y dice por qué.

---

### U5 · Frescura del oráculo  ·  `domain/settlement.ts`  (deuda previa)
`onRead` acepta hoy una lectura sin comprobar cuán vieja es la fuente. Es el mismo fallo que
en el bot obligó a cablear `cvd_confirmation`, y conviene cerrarlo antes de que haya dinero.

La antigüedad entra **por parámetro**, no por reloj de pared.

**Puerta:** una lectura más vieja que el umbral no avanza de fase; se reintenta y lo declara.

---

### U6 · El árbol de época  ·  `domain/merkle.ts` + `domain/epoca.ts` (nuevos)
Funciones puras, con las tres correcciones ya decididas:

- **separación de dominio:** hoja `SHA256(0x00 ‖ usuario ‖ seq ‖ hecho)`, nodo
  `SHA256(0x01 ‖ izq ‖ der)`. Sin los prefijos, un nodo interno se hace pasar por hoja.
- **hoja impar:** se **promueve** al nivel siguiente, no se duplica (duplicar abre un segundo
  camino a la misma raíz). La regla se escribe una vez y no se cambia.
- **L15:** secuencia por usuario en cada hoja y **conteo de hojas** en el ancla, para que una
  omisión sea detectable.

Documenta la API en el encabezado: la pantalla del verificador la va a consumir.

**Puerta:** generar una prueba de inclusión y verificarla; **borrar una hoja del libro rompe la
verificación de alguien**; y un árbol con número impar de hojas verifica correctamente.

---

### U7 · Los contratos  ·  `contratos/` (nuevo, sólo si hay herramientas)
`BovedaTopada.sol` (~150) · `AdaptadorOraculo.sol` (~180) · `RegistroAnclas.sol` (~80),
reutilizando los Conditional Tokens ya auditados. Pruebas de invariante L1 / L5 / L14.

**Si `forge` no está disponible o no se puede instalar: sáltala, anótalo y sigue.** No pelees
con la instalación más de dos intentos.

**Puerta:** `forge test` en verde con las invariantes cableadas.

---

### U8 · Sincronizar la documentación
Que `LIQUIDEZ.md`, `MEMORY/marea/README.md` y `ESTADO.md` reflejen lo construido: qué
invariantes pasaron de «nueva» a «viva», qué fases del plan se cerraron, y qué quedó abierto.

**Puerta:** alguien que lea sólo `MEMORY/marea/README.md` sabe en qué estado quedó todo.

---

## 3. Al terminar la cola

Si llegas al final antes de que te interrumpan: **no inventes trabajo nuevo.** Revisa
`PREGUNTAS_ABIERTAS.md`, resuelve lo que sí se pueda resolver sin decisión de RasDG, refuerza
pruebas de lo ya construido (más casos borde, más mutaciones deliberadas), y deja un resumen
del estado en `MEMORY/marea/`.

_Escrito 2026-09-08._
