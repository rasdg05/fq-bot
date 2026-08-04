# BRIEF — Cerrar el instrumento (agosto 2026)

> Encargo para una sesión nueva. `CLAUDE.md` ya carga el estado, los números
> vigentes y las invariantes: **no los repitas ni los re-derives**. Esto es solo
> el trabajo pendiente, en orden.

## Regla que gobierna este encargo

Un hallazgo sin invariante que lo haga cumplir es una nota, no un arreglo. Cada
entrega de abajo termina en un test que falla si la regresión vuelve. Si no
puedes escribir ese test, la entrega no está lista.

Nada aquí requiere decidir si el sistema tiene edge. **No lo tiene demostrado**
(IC95% cruza cero en toda configuración medida). Esto construye el instrumento
que permitirá decidirlo con datos en vez de con ganas.

---

## E1 · Snapshot completo de features en el OPEN

**Problema.** `MOTOR_OPEN_META` sella ~10 campos elegidos a mano en 2026-07. En
tres meses, cualquier pregunta que nadie anticipó entonces será incontestable
sobre los trades de hoy. Es la diferencia entre un log y un dataset.

**Entrega.** Vector completo de features en el `OPEN`, con `schema_version`.
Diseña para que añadir un campo en el futuro **no invalide** las filas viejas:
el consumidor debe poder distinguir "esta feature no existía" de "valía null".
Esa distinción es la que hoy no se puede hacer con `cvd_confirmed`.

**Ojo.** No sobre-selles: si una feature es constante (como fue `vp_basis`), el
snapshot debe delatarlo, no enterrarlo. Considera un chequeo de varianza que
avise cuando una feature lleve N aperturas sin cambiar.

---

## E2 · Registrar los fires VETADOS

**Problema.** Se mide lo que se abrió. No se sabe si los vetos
(`london_open_kz`, `segment_veto`, gate KL) están salvando o costando, porque el
contrafactual no existe. `MOTOR_VETOED` ya se sella pero **sin el snapshot**, así
que no se puede repreciar lo que habría pasado.

**Entrega.** Que cada veto lleve el mismo vector de E1 + el motivo. Con eso, en
un mes, `tools/` puede responder "¿cuánto R dejó sobre la mesa cada veto?" sin
arriesgar un centavo.

**Prior relevante.** `GHOST_MAP` H2 dice que el filtro KL *cuesta cadencia sin
salvar de pérdidas*, y H7 que el silencio del VIP es el stack de gates, no falta
de setups. E2 es lo que convierte esas dos sospechas en medición.

---

## E3 · Comando `/salud` — el instrumento visible

**Problema.** `_ledger_health`, `n_excluded`, `MOTOR_FILL_REJECTED`,
`cvd_staleness_min`, `bars_held` — todo escrito, nada visible. Cinco arreglos
invisibles no son producto.

**Entrega.** Comando admin que responda de un vistazo: ¿el track record es
fiable? ¿cuántas filas se excluyen y por qué? ¿el CVD está fresco? ¿cuántos
fills se rechazaron? ¿cuándo corrió el último audit y con qué veredicto?

Esto es producto, no ingeniería. Escríbelo para que se entienda a las 3am.

---

## E4 · Grafo de procedencia de métricas

**Problema.** Hoy la auditabilidad es binaria: una fila cuenta o no cuenta. Pero
un número publicado depende de mediciones que dependen de colectores. Cuando uno
se rompe, hay que *acordarse* de qué afirmaciones caen — y acordarse es
exactamente lo que falló en julio.

**Entrega.** Que cada número publicado pueda nombrar las filas y los filtros de
los que salió, y que romper un nodo invalide automáticamente lo que cuelga de él.
`ledger_stats` ya es el cuello de botella por donde sale todo: constrúyelo ahí.

**Alcance.** Empieza pequeño y útil: procedencia para el track record público y
para el veredicto del audit. No construyas un motor de grafos genérico.

---

## E5 · Batches API para el research

**Problema.** Los barridos del CI (`cross_asset_sweep`, ablaciones, walkforward)
corren en línea pagando tarifa completa por trabajo que tolera latencia.

**Entrega.** Migrar los jobs no interactivos a la Batches API (50% de coste,
ventana de 24h). Consulta la skill `claude-api` para la forma exacta; no la
escribas de memoria.

---

## E6 · Mapeado, NO implementar

Estas cuatro están **prohibidas** en este encargo. Se documentan para que nadie
las proponga como si fueran nuevas, y se listan con la condición exacta que las
desbloquea.

| Idea | Condición para desbloquear |
|---|---|
| Ir a real | IC95% de la expectancy por encima de cero, con fees, n≥100, forward |
| Tocar TP/SL | ≥30 cierres con recorrido sellado + veredicto de `geometry_report` |
| Añadir features nuevas | Arreglar antes las muertas (`vp_basis` constante, CVD congelado) |
| Book imbalance (ver abajo) | Que el CVD firmado pase el gate primero |

### Sobre el book imbalance — contexto para no reinventarlo

Circula la idea de `I = (V_bid − V_ask)/(V_bid + V_ask)` sobre el libro. **No es
lo que ya mides.** Tu `cvd_imbalance` es imbalance de volumen **ejecutado**
(taker buy vs sell); esa ratio es de órdenes **en reposo**. Son cosas distintas:
una dice qué se cruzó, la otra qué está esperando.

Lo interesante es que conecta con el hallazgo de agosto. El motor pierde el 80%
de su R en límites que se llenan en 1 barra — selección adversa: tu orden se
llena porque el precio la está atravesando. **Eso es exactamente un evento de
libro.** Hoy se filtra a ciegas por `bars_waited`; un `I` del lado propio podría
predecirlo *antes* de colocar la orden en vez de descartarla después.

Y ya está mapeado en el repo: `internal/EXPERIMENT_ORDER_FLOW.md` dice que
`trades` basta para el CVD y que **MBP-10 es la escalada** — MBP-10 es
precisamente la profundidad de libro que esa ratio necesita. O sea: no es una
idea nueva, es el paso 2 de un plan ya escrito, y su prerrequisito (que el CVD
firmado pase el gate) no se ha cumplido.

Coste real a considerar antes de ilusionarse: la data de libro es órdenes de
magnitud más cara y pesada que la de trades, y el imbalance de libro es
notoriamente frágil (spoofing, órdenes que se cancelan, latencia). No lo trates
como señal hasta que sobreviva el mismo gate que todo lo demás.

---

## Cómo entregar

Rama `claude/instrumento-2026-08`. Un commit por entrega, cada uno con su test.
Suite completa (~40 s) verde antes de cada commit. No mergees a `main` sin
decirlo — `main` despliega a producción con suscriptores de pago.
