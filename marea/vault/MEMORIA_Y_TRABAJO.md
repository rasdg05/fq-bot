# Cómo trabajamos — la memoria del repo y la ingeniería agéntica

> Documento 2 del manual del co-desarrollador. Complementa `ENCARGO_RAMPA.md`.
> Entregable maquetado: `MEMORY/marea/memoria-y-trabajo.pdf`.
> La especificación operativa que manda sigue siendo `vault/AGENTE.md`.

## 1. La memoria es un grafo, no un manual

`CLAUDE.md` se carga en cada sesión y por eso es corto: **rutea, no repite**. El contexto
largo vive en `MEMORY/` y se lee a demanda.

| Nodo | Contesta |
|---|---|
| `MEMORY/00-INDICE.md` | la puerta, 60 s, orienta desde cero |
| `CONSTITUCION.md` | qué no se rompe nunca |
| `DECISIONES.md` | por qué algo está así, con su evidencia |
| `CEMENTERIO.md` | qué ya se mató y por qué — **se lee antes de proponer**, no después |
| `ESTADO.md` | qué está vivo hoy (el que más caduca: confirmar fecha contra `git log`) |
| `MEMORY/marea/` | todo lo de Marea: estado del producto y obras |

**Las seis reglas del grafo:** un nodo, una responsabilidad · nada se duplica (se enlaza por
nombre de archivo, para que un agente lo pueda abrir) · todo nodo lleva fecha · el cementerio
es de primera clase · se escribe **al cerrar**, no al empezar · documentar no es entregar —
un documento sólo cuenta si cambia una decisión.

**Por qué existe:** en julio el repo ya sabía que una racha del bot era un espejismo, y el
código siguió publicando el número un mes más. El fallo no fue de conocimiento sino de
cableado. De ahí: **un hallazgo sin un test que lo haga cumplir es una nota, no un arreglo.**

## 2. Dueños por zona (para no encimarnos)

| Zona | Dueño |
|---|---|
| `adapters/puente/*`, `domain/solicitudes.ts`, pantallas de depósito | **el segundo dev** |
| `domain/pozo.ts`, `domain/parimutuel.ts`, `contratos/`, merkle y época | **RasDG + Claude** |
| `adapters/index.ts`, `lib/config.ts`, `lib/strings.ts`, `state/store.tsx` | **compartida** |

En zona compartida: commits pequeños (una razón por commit) · traer `main` a tu rama **a
diario** · añadir al final, no reordenar bloques existentes · avisar antes de mover algo
estructural.

**Ramas.** Una por encargo. **Fusiona tus propias ramas como quieras** — merge, rebase,
squash, es tu espacio. Nunca reescribas historia de una rama que otro ya sacó. A `main` sólo
por PR: `main` redespliega producción.

## 3. Lo que de verdad cuesta un turno

La API **no tiene estado**: cada turno reenvía la conversación entera. Contra eso está el
caché de prefijo, y sus reglas mandan:

- leer del caché ≈ **10%** del precio de entrada; escribirlo ≈ **1.25×**
- vida por defecto **5 minutos**, ampliable a **1 hora**
- **cualquier byte que cambie en el prefijo invalida todo lo que sigue**

**La conclusión contradice la intuición:** una sesión larga no es cara por ser larga. Con el
prefijo estable, continuar cuesta una décima parte. Lo caro es **invalidar el caché** y
**arrastrar contexto irrelevante** — que se paga dos veces, en tokens y en que el modelo
trabaja peor rodeado de ruido.

**La regla:** *reinicia cuando el contexto dejó de ser relevante, no cuando es largo.*

Y lo que hace barato reiniciar es la memoria: con el estado en el repo, arrancar en frío
cuesta **tres archivos** (`CLAUDE.md`, el doc del encargo, `ESTADO.md`) en vez de cuarenta
turnos de historia. **Por eso la memoria y la economía de tokens son el mismo tema.**

*Señales de reinicio:* el agente relee lo que ya leyó · repite conclusiones o se contradice ·
cambiaste de tarea (la más común) · volviste después de un rato largo y el caché ya está frío.

*Anti-patrones:* usar el chat como memoria · reiniciar cada quince minutos «por ahorrar»
(cada arranque paga precio completo) · meter la hora o un id aleatorio al principio del
contexto, que mata el caché sin que se note.

## 4. El ciclo de una sesión

**Arranque:** `git fetch --all` · `CLAUDE.md` · el doc del encargo · `ESTADO.md` ·
`CEMENTERIO.md` si vas a proponer algo · elegir **una** unidad de trabajo y su puerta.

**Trabajo:** una sola cosa · el test en el mismo commit que el código · **romperlo a propósito
y verlo rojo** · `npm run ci` antes de commitear.

**Cierre:** commit con el **porqué** · lo aprendido a `MEMORY/marea/` con fecha · cerrar la
sesión sin miedo.

## 5. Caso de estudio: `pozo.ts`

Se escribió el módulo y su prueba de mil secuencias aleatorias. **Verde a la primera** — que
es sospechoso. Se rompió el código a propósito tres veces y las tres se pusieron rojas: la
prueba tenía dientes. Luego se midió el perfil del generador, y ahí saltó: **cero mercados de
tres resultados**. El generador aleatorio, sembrado con valores consecutivos, daba primeras
extracciones correlacionadas — y esa primera extracción decidía cuántos resultados tenía el
mercado. Mil secuencias en verde que nunca probaron un caso entero.

**El bug no estaba en el código probado: estaba en la prueba.** Y no lo encontró escribir más
código — lo encontró **medir si la prueba cubría lo que decía cubrir**.

_Escrito 2026-09-07._
