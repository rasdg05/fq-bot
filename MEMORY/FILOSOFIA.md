# FILOSOFÍA — una organización de agentes autónomos

> Escrita el 2026-10-01 a pedido de RasDG: *«Los agentes autónomos de decisión son el
> futuro de las organizaciones. Y nosotros somos una organización del futuro.»*
>
> Este documento dice **cómo** se vuelve eso verdad sin dejar de ser lo que ya somos:
> un repo que mide antes de creer. Cada principio lleva dónde está cableado. Un
> principio sin cableado es una aspiración, no una regla (CLAUDE.md, «la lección más
> cara»).

---

## La tesis

Una organización del futuro no es una con más gente revisando más cosas: es una donde
**las decisiones repetibles las toma un agente**, las personas fijan las reglas, los
presupuestos y los límites, y **todo lo que el agente decide queda escrito** de forma
que cualquiera pueda auditarlo después.

Ni «la IA decide todo» ni «una persona aprueba cada mercado». Arriba del bucle, no en
medio.

## Los diez principios

1. **Los agentes deciden; las invariantes mandan.** Un agente opera dentro de reglas
   que compilan o que una prueba hace cumplir. Si una regla sólo vive en un documento,
   el agente puede romperla. → `seResuelveSolo` (R-076), `SPREAD_MAXIMO` (R-077).

2. **Una decisión sin rastro no ocurrió.** Cada decisión autónoma se escribe en una
   bitácora *append-only* y encadenada por hash: qué se decidió, sobre qué, por qué
   regla, con qué evidencia y quién la tomó (las reglas, o el modelo con su versión).
   Borrar o editar una entrada rompe la cadena y se nota. → `domain/bitacora.ts`.

3. **Reglas primero, juicio después.** Lo que se puede escribir como regla
   determinista se escribe así. El modelo de lenguaje juzga **sólo** lo que una regla
   no alcanza —¿la pregunta se entiende?, ¿el criterio dice lo mismo que la regla?,
   ¿la evidencia sostiene el resultado?— y **propone o veta; nunca mueve dinero solo**.
   → `server/juez.mts` (R-081).

4. **La autonomía se gradúa por reversibilidad.** Lo reversible y acotado, el agente
   lo hace solo: no publicar un candidato, retener un pago dudoso, abrir un hallazgo.
   Lo irreversible —pagar distinto de lo que dice la fuente, tocar el presupuesto,
   cambiar una regla, que la casa tome un lado— **nunca** lo hace solo. → acciones del
   revisor (R-082).

5. **Un agente que no se mide es una superstición.** El director publica sus números:
   cuánto resuelve, cuánto tarda, cuánto se atora, qué fuentes fallan, cuántas veces
   lo corrigieron. Se le juzga con la misma vara que al bot: por lo medido. → panel
   `/api/director`.

6. **Decir «no sé» antes que inventar.** Un oráculo sin dato contesta `sin_dato`; un
   libro sin gente no da precio; un juez sin llave se apaga. El sistema prefiere un
   mercado menos a uno inventado.

7. **Falla seguro.** Si el agente, su modelo o una fuente se caen, el resto sigue
   funcionando. Sin `ANTHROPIC_API_KEY` el juez se apaga y las reglas siguen decidiendo
   igual; sin Kalshi no hay espejos nuevos, pero lo abierto se sigue resolviendo.

8. **Hallazgo → prueba → invariante.** Lo que el revisor encuentra dos veces se
   convierte en una regla que impide que vuelva. El revisor no es el arreglo: es el
   sensor que dice dónde falta uno.

9. **Transparencia hacia afuera.** Lo que el director decide se puede ver. Un mercado
   de predicción que pide confianza tiene que enseñar cómo decide.

10. **El agente no es la contraparte.** El director pone la semilla con un prior que
    cita su fuente; **nunca** toma el lado contrario de un usuario ni gana cuando el
    usuario pierde (R-057; «pozo como creador de mercado», muerto en `CEMENTERIO.md`).
    «Market maker», aquí, quiere decir **quien hace que exista el mercado**, no quien
    apuesta contra la gente.

## Los roles

| Rol | Qué decide solo | Qué nunca decide | Dónde |
|---|---|---|---|
| **Director de mercados** | qué candidatos se publican, en qué orden, con cuántas opciones; registra cada no | el presupuesto (L9), las reglas, el tamaño del subsidio (P-002/P-004) | `domain/director.ts`, `server/reposicion.mts` |
| **Revisor** | abrir y cerrar hallazgos; retener una resolución que contradice al mercado | pagar, anular por su cuenta antes del plazo, reescribir un resultado | `domain/revisor.ts`, `server/ciclo.mts` |
| **Juez (Claude)** | vetar un texto ambiguo o sensible antes de publicarse; señalar una evidencia que no sostiene el resultado | nada con dinero; su veto pasa por las reglas del revisor | `server/juez.mts` |
| **Oráculos** | leer la fuente y decir qué dice, o que no dice nada | interpretar | `adapters/oracles/*` |
| **Personas (RasDG, devs)** | reglas, presupuestos, topes, opiniones legales, lo que el agente escala | — | `vault/RULINGS.md`, `vault/PREGUNTAS_ABIERTAS.md` |

## La primera vuelta, en producción (2026-10-01)

El revisor abrió 63 hallazgos en su primera lectura de producción: 13 partidos atorados con
el resultado publicado, 17 pozos con saldo heredado, mercados «TBD vs TBD». Nada de eso se veía
en `/salud`. El revisor no arregló nada solo —no le toca—; dio el contexto para que cada
arreglo se decidiera midiendo, y en el ciclo siguiente **cerró solo** los hallazgos que dejaron
de verse. Así se ve el principio 8 funcionando (DECISIONES §26).

## Lo que todavía no es

Dicho en la misma frase, como todo en este repo:

- El director **no** ajusta el tamaño de la semilla por interés: los topes del subsidio
  esperan cifras de RasDG (P-002, P-004). Hoy siembra con el prior de su fuente y el
  tamaño fijo de cada familia.
- El juez corre desde el 2026-10-01 con `ANTHROPIC_API_KEY` en el servicio; si la llave se
  quita o el modelo se cae, todo lo demás corre igual. Su primera vuelta: 15 resoluciones
  revisadas, ninguna señalada.
- El revisor **retiene**, no resuelve: una resolución retenida espera a una persona o
  al plazo de 30 días que devuelve todo.

_Fuente de verdad: `MEMORY/DECISIONES.md §25`, `marea/vault/RULINGS.md` (R-079…R-083),
el código citado. Si un principio y el código no coinciden, manda el código y este
documento está desactualizado._
