# BRIEF — El VIP: de "no demostrado" a decidible (agosto 2026)

> Encargo para una sesión nueva. `CLAUDE.md` y `MEMORY/ESTADO.md` cargan el estado
> y los números vigentes: **no los repitas ni los re-derives.** Esto es solo el
> trabajo pendiente, en orden, y por qué es ESE y no otro.
>
> Rama de trabajo: la que indique el encargo. **No se mergea a `main` sin
> decírselo a RasDG** — `main` despliega a producción con suscriptores de pago.

## La regla que gobierna este encargo

La misma de siempre: *un hallazgo sin invariante que lo haga cumplir es una nota,
no un arreglo.* Cada entrega termina en un test que falla si la regresión vuelve.

**Y aplica a lo primero que vas a leer:** la medición del VIP de abajo se corrió
**ad-hoc**, en un script de sesión que ya no existe. Es una **NOTA**, no un
arreglo. Cementarla es parte de V1.

---

## De dónde sale este encargo (2026-08-05)

Pregunta de RasDG: **"¿Y el VIP? ¿Funciona?"**

Se midió el universo exacto del producto (`FQ_VIP_PAIRS = BTC,ETH,SOL`) sobre el
cube completo, neto de costes, n=3.774 señales canónicas, 2019-2026:

| celda | bruto | **neto** | IC95% | WR |
|---|---|---|---|---|
| tp4/h288 (celda de research) | +0.271 | **+0.010** | [−0.060, +0.080] | 29.5% |
| tp4/h576 | +0.278 | **+0.017** | [−0.054, +0.086] | 29.2% |
| **tp1/h288 — la geometría que opera el motor vivo** | +0.192 | **−0.069** | **[−0.112, −0.028]** | 51.0% |

Resto del pool (10 símbolos, n=9.655), misma celda tp4/h288: **−0.040** neto.

Por símbolo VIP en tp4/h288, ~16 señales/mes cada uno:
**ETH +0.059** · **BTC +0.003** · **SOL −0.054**.

**Las dos lecturas, y las dos importan:**

1. **La selección SOL/BTC/ETH de junio se sostiene.** El universo VIP bate al
   resto del pool por ~+0.05R neto sobre 7 años. Esa decisión fue buena y ahora
   tiene 13.429 señales detrás en vez de una ventana.
2. **La geometría tp1 reparte mal, y esta vez el signo está determinado.** En tp4
   el IC95% cruza cero (no concluye). En **tp1 el IC95% está entero por debajo de
   cero**. No es "no sabemos": en la configuración que se publica, sabemos.

El track record publicado (`n=12 · WR 41.7% · E[R] +0.208 · PF 1.76`) **no
contradice** esto: n=12 está por debajo del `MIN_N=30` del propio repo y no
concluye ni a favor ni en contra. La muestra de n=3.774 sí concluye.

**Lo que cambia el foco:** el problema del VIP no es el símbolo ni la señal. Es
**dónde se ponen las barreras y cuánto capital se compromete a la vez.**

---

## V1 · El barrido acotado por lo que el producto tolera

**Problema.** El barrido de geometría de agosto (`tools/geometry_sweep.py`) buscó
el **máximo de R por trade** y encontró una celda que la señal respalda con seis
controles — y que es inoperable: 13.7 posiciones simultáneas, 71% de drawdown,
tirando el 66% de las señales. Se buscó la respuesta a la pregunta equivocada.

**La pregunta correcta:** de las geometrías que un producto con suscriptores
puede sostener, ¿alguna tiene el neto por encima de cero?

**Entrega.**

- Barrido **tp1 → tp2 → tp3** sobre el **mismo horizonte** que opera hoy,
  restringido al **universo VIP** (BTC/ETH/SOL).
- `tools/portfolio_risk.py` encima **desde el primer minuto**, no como
  post-mortem: una celda que no pasa el filtro de cartera **no se reporta como
  candidata**. La cota es `DD < 35%` y concurrencia baja sin cap ciego.
- Cementa la medición de arriba (`tools/vip_report.py` o dentro de `cube_report`,
  **prefiere editar a crear**) con su test. "¿Funciona el VIP?" tiene que
  contestarse con un comando, no con una sesión.

**Ojo con lo que ya se sabe.** Ensanchar el stop está **medido y agotado**
(`CEMENTERIO.md`, 2026-08-04): confirma la señal y mata el producto por
concurrencia. Esto NO es repetir aquel barrido — es el mismo eje con la
restricción de cartera puesta **antes** de elegir, y acotado al universo que se
publica. Si el resultado es "ninguna celda operable clarea cero", **eso es un
desenlace legítimo y vale más que maquillarlo**: al cementerio, con su n.

**Es local y gratis.** El cube ya está en `cosecha_cubes/`. Cero runners de CI —
RasDG no puede lanzarlos ahora mismo.

---

## V2 · La brecha técnica real: posición en cola

**Problema.** El simulador contesta *"¿el precio tocó el nivel?"*. Los que juegan
en serio contestan *"¿dónde estaba mi orden en la cola cuando el precio llegó?"*.
No es lo mismo, y este repo ya pagó la diferencia sin saber que la pagaba.

**La evidencia de que aplica aquí, ya medida:** `tools/fill_quality.py` encontró
**selección adversa −1.039R** — las órdenes que llenan (+0.114R) llenan **porque
el precio va a atravesarte**, y las que escapan (+1.153R) eran las buenas. El
80% de la pérdida se concentra en los fills de 1 barra. **Eso es exactamente lo
que un simulador de cola te dice ANTES de perderlo**, no después.

**Entrega.** Modelar dónde queda la orden en el libro y qué se ejecuta delante de
ella, en vez del proxy actual (penetración más allá de eps). Empieza pequeño y
útil: el objetivo no es un simulador de microestructura completo, es que
`maker_entry_fill_mask` deje de ser binario y devuelva **probabilidad de fill
condicionada al flujo que pasó por ese nivel**.

**La invariante que tiene que salir de aquí:** que ninguna cifra maker se pueda
publicar con fill asumido al 100%. Ese supuesto ya voló un resultado en agosto
(el "+0.060R con entrada maker" que el fill real dejó en −0.0350R).

---

## V3 · Capacidad — un edge no se defiende con secreto, se defiende con capacidad

**Problema.** Nadie ha preguntado a qué tamaño se muere esto. Es lo primero que
pregunta cualquiera que sepa, y separa una estrategia de una anécdota.

**Entrega.** `tools/capacity_analysis.py` **ya existe** — úsalo, no lo reescribas.
Sobre el universo VIP y la geometría que sobreviva a V1: ¿a qué notional el
impacto se come el neto? Reporta la curva, no un número suelto.

**Por qué importa ahora y no después:** si la capacidad resulta ser de \$5k, el
producto es un servicio de señales y punto. Si es de \$500k, la conversación de
capital real que RasDG quiere tener tiene una cifra detrás. Hoy no la tiene.

---

## Dónde estamos de verdad (calibración, 2026-08-05)

Para que la sesión nueva no confunda "resultados malos" con "proyecto malo":

1. **El método está arriba del percentil 95 del retail.** DSR deflactado, CPCV con
   purga y embargo, PBO, cementerio de ideas muertas, medición forward con fees,
   ledger encadenado. Eso es metodología de fondo pequeño. La mayoría de proyectos
   que presumen no tienen ni uno de los cinco. **No degrades esto para que salgan
   números bonitos** — es literalmente el activo del repo.

2. **Lo que falta no es tecnología, es serie temporal larga y honesta.** El edge no
   se demuestra con mejor stack: se demuestra con n grande, fuera de muestra, con
   costes, en varios regímenes. El cube de 7 años vale más que cualquier feature
   nueva. E7/E8 lo empezaron a explotar; V1 sigue por ahí.

3. **La brecha técnica concreta es V2** (cola / selección adversa). No es teoría
   de vanguardia por gusto: es directamente el problema que ya costó dinero medido.

4. **La brecha de negocio concreta es V3** (capacidad).

**Y el estado honesto del producto:** no hay edge demostrado. Ninguna configuración
medida tiene el IC95% de la expectancy por encima de cero **neto**. El VIP no está
en desastre — en su mejor celda medida está en **cero neto con IC que cruza** —
pero tampoco está demostrado que gane. Decir eso no es pesimismo: es el estado del
arte del repo, y es la razón de que exista el cementerio.

---

## Prohibido y no negociable

- **E6 sigue prohibido.** Solo confirma que sigue mapeado.
- **El gate ORO (DSR > 0.95), CPCV y PBO no se degradan jamás** por conveniencia
  de ingeniería. Si el brief choca con `MEMORY/CONSTITUCION.md`, **gana la
  constitución** y se le dice a RasDG.
- **Nada a `main` sin avisar.** Producción con suscriptores de pago.
- **n < 30 no concluye.** Ni a favor ni en contra. Cita la n en cada afirmación.
- Un commit por entrega, cada uno con el test que hace fallar la regresión.
  Suite completa verde antes de cada commit (~40 s, `pytest tests/`).

## Rutas que vas a necesitar

```
cosecha_cubes/*.parquet        13.429 señales canónicas, 13 símbolos, 2019-2026
tools/cube_report.py           celdas del cube CON costes (el bruto no sale solo)
tools/geometry_sweep.py        re-etiquetado triple-barrera sobre rejilla
tools/portfolio_risk.py        lo que el R por trade NO dice de la cuenta
tools/fill_quality.py          fill maker real + gate de venue
tools/capacity_analysis.py     ya existe — V3
tools/validation_gate.py       DSR / CPCV / PBO — la vara
internal/DIAGNOSTICO_E7_E8_2026-08.md   el detalle de agosto, con reproducibles
```
