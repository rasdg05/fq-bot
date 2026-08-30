# BRIEF — Cerrar el instrumento (agosto 2026)

> Encargo para una sesión nueva. `CLAUDE.md` ya carga el estado, los números
> vigentes y las invariantes: **no los repitas ni los re-derives**. Esto es solo
> el trabajo pendiente, en orden.

## ESTADO DEL ENCARGO — leer antes que nada (act. 2026-08-30)

**E7 y E8 están HECHOS y CONTESTADOS.** Lo demás (E1–E5, E9) sigue pendiente y sigue
siendo el trabajo que toca. E6 sigue prohibido.

> **E7 — `internal/EXCURSION_2026-08.md`.** La ENTRADA sí distingue: +3.6 pp de WR sobre
> un placebo emparejado, IC95% [+2.5, +4.7], n=13.429. La TRAYECTORIA no: 8 de 8 celdas
> indistinguibles del placebo.
>
> **E8 — `internal/E8_BRUTO_NETO_2026-08.md`.** Del bruto no sobrevive nada. Neto −0.023R
> suponiendo fill exacto en `stop_price` (imposible), −0.170R con medio sobrepaso medido.
> Ningún símbolo aguanta. Pregunta abierta 6 del GHOST_MAP: contestada.
>
> **En una frase: hay señal y no alcanza.** No se sigue que el sistema no pueda funcionar;
> se sigue que *esta* configuración no, y por cuánto.

### Dos cosas que este brief decía y estaban mal

1. **E7 proponía la lectura de separación de `geometry_report` como veredicto.** Es
   circular: ganar ES tocar el TP, luego MFE ≥ rr por construcción (96.5% vs 0.0%). El
   veredicto "separan" salía siempre. Sustituida por `tools/cube_fixed_window.py`
   (ventana fija + solo vivas en k + placebo obligatorio).
2. **E7 citaba "MFE +6.66R / MAE −5.65R" del GHOST_MAP H5 como recorrido por señal.** Era
   la excursión de la ventana del horizonte. En vida el MAE de los ganadores es −0.364R.
   Ver `CEMENTERIO.md` §Instrumento.

Y una tercera, que no estaba en el brief pero afectaba a su condición de desbloqueo de E6:
el contrafactual de `geometry_report` **sesgaba a "aprieta el stop"** (+0.083R al
estrechar). E8 midió después que apretar el stop **encarece** el trade en R.

---

Lo que cambió antes, en agosto:

- **La línea de Polymarket está CERRADA.** Se midieron cuatro pasos (oferta ✓,
  horquilla ✓, Brier ✗, neg_risk ✗) y no hay edge. El venue es bueno y no
  tenemos qué venderle. Detalle y condición de desbloqueo en `CEMENTERIO.md`
  §Polymarket + `internal/POLYMARKET_*_2026-08.md`. **No re-proponerla**, ni
  entera ni por partes (recalibración y arb de conjunto completo están muertos
  con su n). El triaje de los 10 repos que la originaron también está ahí.
- **Se añaden a E6 (prohibidas) las dos vías muertas de Polymarket**, ver tabla.
- **El instrumento demostró que sirve.** En esa sesión cazó dos artefactos que se
  habrían publicado como hallazgos: un sesgo de calibración de −4/−5 pp que era
  ponderación por trade, y un "arbitraje del 35%" que eran patas faltantes. Las
  dos reglas que los cazaron ya estaban escritas en `CLAUDE.md`. Eso es
  exactamente lo que E1–E9 quiere multiplicar.

**Orden recomendado (histórico): E7 y E8 primero.** Ya están hechos; se deja el
razonamiento porque se cumplió: cuatro preguntas caras se contestaron con datos en disco. Son los diagnósticos que
pueden invalidar el resto, leen datos que ya existen y cuestan poco. La sesión de
Polymarket es evidencia a favor de ese orden: cuatro preguntas caras se
contestaron con datos ya en disco, en horas de cómputo, sin arriesgar un peso.

---

## QUÉ TOCA AHORA (act. 2026-08-30) — arranque en frío

```bash
git fetch origin claude/instrumento-2026-08
git checkout -b <tu-rama> origin/claude/instrumento-2026-08
git log origin/main --oneline | grep -i excursion   # ¿vacío? NO está mergeada
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/python -m pytest tests/ -q                # ~45 s, debe dar 1372 passed
```

**Ojo con los datos.** `data/` está en `.gitignore` y el contenedor es efímero: las velas
de OKX y los cubos re-etiquetados **no viajan con la rama**. Regenerarlos cuesta ~25 min:

```bash
.venv/bin/python tools/fetch_okx_life_windows.py --workers 5   # ~20 min, 9.127 peticiones
.venv/bin/python tools/cube_regrade_excursion.py               # debe dar 13/13 a 1.0000
```
Si el regrade NO reproduce 1.0000, **para**: significa que las velas no son las del venue
con el que se cosechó el cube (OKX **spot**), y nada medido encima vale.

### El orden, con lo que ya se sabe

1. **E9 primero** (antes era el último de su grupo). Métrica particionada por régimen con
   su n, y agregado con asterisco. Sube de prioridad porque E7/E8 acaban de demostrar que
   un número agregado sobre una sola configuración esconde el problema: el bruto +0.231R
   y el neto −0.023R son el MISMO set, y solo uno de los dos se citaba.
2. **E1 y E2** (snapshot de features en el OPEN, y los fires VETADOS). Miden hacia
   adelante y son lo que permitirá contestar la pregunta que E7/E8 dejan abierta: si la
   entrada distingue (+3.6 pp) pero no alcanza, ¿hay un subconjunto de entradas con más
   edge por trade? Eso no se contesta con el cube, se contesta registrando mejor.
3. **E3 y E4** (el `/salud` y la procedencia). Hacen visible el instrumento.
4. **E5** (Batches API) abarata el research.

### Deuda que estaba abierta y quedó cerrada (2026-08-30)

- ~~**Franja muerta en los tests.**~~ **ARREGLADO.** Los 6 tests de
  `test_tactical_alert.py` que se saltaban una hora al día ya no dependen del reloj: la
  fixture `reloj_fijo` fija el instante (martes 10:00 CDMX) y la lógica real de
  `is_dead_window` corre entera. No se mockea el veredicto, se fija el instante.
  **Invariante:** `test_no_wallclock.py::test_ningun_test_se_salta_segun_la_hora` barre
  `tests/` por AST y falla si alguien vuelve a saltar según la hora. Verificado plantando
  el patrón: lo detecta.
- ~~**`fetch_binance_vision_klines` escribe en `data/okx/`.**~~ **ARREGLADO, y era peor
  de lo que parecía: escribían ahí TRES fetchers de Binance**, no uno. Dos cambios:
  1. El defecto local pasa a `data/mercado` (neutral), con `data/okx` como fallback si
     existe — nada se rompe. Producción usa `/data`, no le afecta.
  2. **El arreglo de verdad: el venue va SELLADO en el dato** (`bt_data.stamp_venue`), no
     en el nombre del directorio. Los fetchers de velas sellan, el cubo re-etiquetado
     hereda el sello de sus velas, y `sl_noise_screen` exige que cubo y klines vengan del
     mismo tape antes de dividir uno por otro. Un fichero sin sello no se inventa: la
     guarda calla.
  **Invariante:** `tests/test_venue_procedencia.py`.
- ~~**Cruce de venue spot/perp.**~~ **NOMBRADO, no silenciado.** `cube_net_expectancy` lee
  el venue del cube y, si sale de un tape spot mientras el `CostModel` cobra funding (que
  es de perp), **lo dice en su propia salida**. El funding pesa +0.001R y no cambia ningún
  signo, por eso avisa en vez de bloquear. **El arreglo de verdad sigue pendiente y es
  re-cosechar sobre el tape que se opera** — no editar el informe. El aviso lo exige un
  test, para que el cruce no vuelva a ser silencioso.

### Deuda que sigue abierta

- **Re-cosechar el cube sobre el tape que se opera.** Hoy se etiqueta sobre OKX spot y se
  ejecuta en perp. Medido, el funding pesa +0.001R — pero la mezcla es real y el día que
  algo dependa del tape (basis, funding, profundidad) va a morder.

### Lo que NO se hace

- Tocar TP/SL. Sigue prohibido por E6, y ahora además se sabe que el contrafactual que
  desbloqueaba ese candado estaba sesgado hacia el lado equivocado.
- Citar `−0.170R` sin decir que viene de suponer que el stop se come medio sobrepaso.
- Citar cualquier celda de la rejilla tp×horizonte elegida por ser la mejor: son doce
  sobre el mismo set, y eso es selección.

---

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

## Las tres brechas reales (E7–E9)

E1–E5 construyen el instrumento. E7–E9 lo apuntan a las tres cosas que
realmente separan a este sistema de uno que funcione. **No son tareas de
ajuste: son diagnósticos.** Un desenlace legítimo de cualquiera de las tres es
"la estrategia no es viable como está", y decirlo vale más que maquillarlo.

---

## E7 · La brecha de win rate — contestable HOY con 13k, no en 30 trades

**El problema.** 21.1% de aciertos contra un 36.9% de equilibrio. Faltan 16
puntos, y no se cierran con ejecución: o la geometría TP/SL está mal, o la señal
no separa. Son dos enfermedades con el mismo síntoma.

**El atajo.** `tools/geometry_report.py` lee el ledger vivo, donde hay que
esperar cierres. Pero el cube **ya tiene MFE/MAE por señal**: `GHOST_MAP` H5
reporta MFE medio +6.66R, MAE medio −5.65R sobre las 13.429 señales canónicas.
La pregunta se puede contestar ahora con tres órdenes de magnitud más muestra.

**Entrega.** Que la lógica de lectura de `geometry_report` (distribución,
TP-demasiado-lejos, SL-demasiado-cerca, separación, contrafactual) corra sobre
`cosecha_cubes/*.parquet`. Reutiliza las funciones; no las dupliques.

**Antes de creerte el número, verifica dos cosas y di lo que encuentres:**
1. **¿Coincide la definición?** El MFE/MAE del cube se mide sobre el horizonte de
   la etiqueta triple-barrera; el del ledger, sobre la vida real con TTL. Si no
   son lo mismo, los números no son comparables y hay que decirlo, no promediarlos.
2. **¿Hay orden de barra?** El contrafactual necesita saber si el MFE llegó antes
   que el MAE. Si el cube no lo trae, aplica la regla pesimista y **declara
   explícitamente que la tabla es una cota inferior**.

**La lectura que más importa** es la de separación: si el recorrido de ganadores
y perdedores se solapa sobre 13k señales, ninguna geometría lo arregla y el
trabajo se mueve a la entrada. `GHOST_MAP` H4 ya apunta ahí (`p_master` no
separó); esto lo confirmaría o lo mataría con muestra seria.

---

## E8 · La brecha bruto/neto — la pregunta abierta 6 del GHOST_MAP

**El problema.** El cube dice **+0.224R**. El motor con fees dice **−0.510R**. El
coste de ejecución no muerde el edge: se lo come entero y sigue con hambre. La
pregunta abierta 6 del `GHOST_MAP` se preguntaba cuánto sobrevive; la respuesta
medida es "nada", y eso cambia qué estrategias son siquiera viables.

**Entrega.** Aplicar `bt_engine.CostModel` a las etiquetas del cube para que
backtest y forward hablen en las mismas unidades. Después responder:
¿cuántas de las 13k sobreviven costes? ¿el edge neto se concentra en algún
subconjunto (símbolo, régimen, horizonte, distancia de TP) que sí aguante?

**Cuidado con el alcance.** El cube etiqueta con triple barrera y **sin modelo de
fill**. Aplicarle fees da una cota superior de lo capturable, no una simulación:
ya sabemos que el fill importa muchísimo (los maker rápidos pierden el 80% del R).
No presentes el resultado como "lo que se habría ganado".

**Por qué esto va antes que cualquier idea nueva.** Mientras el edge bruto no
sobreviva a los costes, añadir features es decorar. Si algún subconjunto sí
sobrevive, ese subconjunto **es** la estrategia y todo lo demás es ruido caro.

---

## E9 · La brecha de régimen — nunca más un número agregado

**El problema.** 90 trades de un mes. `GHOST_MAP` H1 ya muestra que el lado
ganador se voltea por época: 2020-22 pagó LONG (+0.36–0.46), 2023-25 pagó SHORT
(+0.21–0.32). **Un número agrupado esconde exactamente eso** — y el fantasma fue
precisamente un agregado sobre un solo régimen presentado como ley.

**Entrega.** Que toda métrica del repo se reporte **particionada por régimen (o
año) con su n**, y que el agregado sea el que lleve el asterisco, no al revés.
Empieza por `ledger_stats` (el cuello de botella de lo publicado) y por los
reportes de `tools/`.

**Criterio de aceptación.** Que sea *imposible* imprimir un E[R] agregado sin que
salga al lado su desglose. Si un régimen tiene n<30, que aparezca marcado en vez
de diluido en el promedio. Esta es la vacuna estructural: el espejismo de mayo no
habría sobrevivido a un desglose obligatorio.

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
| Reabrir Polymarket (cualquier variante) | Nada la desbloquea salvo la condición E6 escrita en `CEMENTERIO.md` §Polymarket |
| Recalibrar el precio de un venue de predicción | Muerta y medida (Brier advantage −0.0043 OOS). No se re-prueba |
| Arb de conjunto completo / `neg_risk` | Muerta y medida (1.00pp de incoherencia vs 3.80pp de coste) |

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

## Orden y por qué

**E7 y E8 primero.** Son diagnósticos que pueden invalidar el resto: si la señal
no separa sobre 13k, o si ningún subconjunto sobrevive a los costes, entonces
E1–E5 están instrumentando algo que no debería operar. Cuestan poco (leen data
que ya existe) y pueden ahorrar meses.

Luego E1, E2, E9 (miden hacia adelante), E3 y E4 (hacen visible el instrumento),
E5 (abarata el research). E6 no se toca.

## Cómo entregar

Rama `claude/instrumento-2026-08`, **sacada de
`claude/polymarket-trading-tools-grx05x`, NO de `main`**:

```bash
git fetch origin claude/polymarket-trading-tools-grx05x
git checkout -b claude/instrumento-2026-08 origin/claude/polymarket-trading-tools-grx05x
```

Mientras esa rama no esté mergeada, es la única que tiene el cementerio de agosto
(línea de Polymarket cerrada + triaje de los 10 repos) y las reglas E6 de abajo.
Ramificar desde `main` las pierde y te haría re-proponer lo ya muerto. **Si para
cuando leas esto ya está en `main`, sal de `main` y ya.** Compruébalo con:

```bash
git log origin/main --oneline | grep -i polymarket   # ¿vacío? entonces NO está mergeada
```

Un commit por entrega, cada uno con el test que hace fallar la regresión. Suite
completa (~60 s) verde antes de cada commit. No mergees a `main` sin decirlo —
`main` despliega a producción con suscriptores de pago.

**Si E7 o E8 salen en contra**, para y dilo antes de seguir con el resto. Un
diagnóstico que mata una línea de trabajo es un buen resultado, no un fracaso; el
repo tiene `MEMORY/CEMENTERIO.md` justo para eso.
