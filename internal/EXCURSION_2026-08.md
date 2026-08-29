# La excursión del cubo no era la del trade (agosto 2026)

> Estado: **E7 en curso.** Los números de abajo son de 7 de 13 símbolos
> (30.682 celdas ganadoras, 49.808 perdedoras); la cosecha de los 6 restantes
> corre. Ninguna conclusión de aquí depende de los que faltan — son de tipo
> "esto es imposible por construcción", no de tipo "el promedio dice".

## Qué se estaba midiendo mal

`bt_labeler` tiene dos rutas de etiquetado. `label_event` (una señal) acumula la
excursión dentro del bucle y **retorna al tocar la barrera**. `label_event_grid`
(el cubo) indexa por horizonte:

```python
mfe_by_h[h] = float(mfe_cum[min(hc, max_h)])   # hc = min(h, n), no bars_held
```

Las dos exportaban la columna `mfe_r`. Mismo nombre, dos definiciones. La del
cubo recorre la ventana entera del horizonte, muera la señal cuando muera.

Con `bars_held` mediano de 10 velas y horizontes de 96/288/576, eso es
casi todo post-mortem. La firma es que el número **crece con la ventana sobre
las mismas 13.429 señales**:

| horizonte | MFE medio | perdedoras "que estuvieron a +1R" | % ya muertas |
|---|---|---|---|
| 96 | +3,88R | 58,5 % | 98,6 % |
| 288 | +6,66R | 75,6 % | 99,9 % |
| 576 | +9,64R | 83,4 % | 100 % |

GHOST_MAP H5 publicó **+6,66R / −5,65R**: es exactamente el corte h288.

## La prueba que no necesita muestra

H5 lee el MAE así: *"−5,65 dice que muchos ganadores pasan MUY en contra
primero"*. Eso es **aritméticamente imposible**. Un trade con el stop en −1R que
llega a −5,65R no es un ganador que sufrió: es un trade cerrado.

Medido en vida sobre 30.682 celdas ganadoras (7 símbolos):

| | MAE de los ganadores |
|---|---|
| medio | **−0,364R** |
| peor de todos | **−1,000R** |
| que llegan a −1R | **0,0 %** |

El peor caso toca exactamente la cota y no la cruza. Los ganadores **apenas
sufren**: −0,36R de media, no −5,65R. La lectura publicada estaba invertida.

(Que el peor sea −1,000R clavado es también la verificación del re-etiquetado:
si el código estuviera mal, esa cota no aparecería sola.)

## Lo que sí se llevó por delante: la separación es circular

El brief pedía usar la lectura de separación de `geometry_report` como veredicto
de E7 — *"si el recorrido de ganadores y perdedores se solapa, ninguna geometría
lo arregla"*. No puede solaparse:

| | MFE ≥ rr del TP |
|---|---|
| ganadores | **96,5 %** |
| perdedores | **0,0 %** |

Un ganador **es** el que tocó el TP, luego su MFE ≥ rr por definición. Un
perdedor no lo tocó, luego MFE < rr por definición. La separación de 1,16R a
3,18R que `geometry_report` imprimiría —y su veredicto *"Separan. Hay margen
para que la geometría capture más"*— es una tautología. El único margen no
definicional es el exceso sobre el rr: **+0,08R a +0,41R**.

Esto **no es un defecto de aplicar la herramienta al cubo**: está en
`geometry_report`, que corre sobre el ledger vivo. La condición
`abs(mw - ml) < 0.25` no puede dispararse en un sistema con TP fijo.

La única comparación no circular es sobre una **ventana fija** que no dependa
del desenlace: el recorrido de las primeras k velas de toda señal, viva o
muerta. Por eso la cosecha baja 96 velas por señal (`MIN_FWD`), cueste lo que
viva.

## El puente con E8: el stop no se llena donde se cree

Con la excursión en vida aparece un dato que la de ventana escondía. El labeler
asume fill **exacto** en `stop_price`. La vela que dispara el stop se pasa de
largo (n = 49.808 perdedoras):

| | sobrepaso de la vela respecto al stop |
|---|---|
| p50 | +0,211R |
| p90 | +0,902R |
| medio | **+0,388R** |

**Cuidado con leer esto como slippage.** Es una **cota**, no una estimación: una
orden stop se llena en algún punto entre `stop_price` y el extremo de la vela, y
el recorrido solo dice hasta dónde llegó la vela. Pero la cota importa, porque
el sobrepaso medio (0,388R) es **del mismo orden que la expectancy bruta del
cube (+0,224R)**. La brecha bruto/neto de E8 (+0,224R en cube vs −0,510R vivo)
tiene aquí un sospechoso con tamaño medido, no supuesto.

## El venue: OKX spot, no Binance

Re-etiquetar exige las velas del **mismo** venue: si se mueve el bar en que
salta la barrera, se mueve la vida del trade, que es justo lo que se recorta.
Verificado contra el `entry_price` de las señales:

| feed | coincidencia exacta |
|---|---|
| OKX spot | **5/5** |
| OKX swap | 0/5 |
| Binance futuros | 0/5 — y el 22 % de los entries cae FUERA del [low,high] |

Los cubos se cosecharon con `cosecha_shard --exchange okx` (el default). Con
Binance el re-etiquetado reproducía `outcome` 0,977 pero `bars_held` 0,766; con
OKX spot reproduce **1,0000 / 1,0000 / 1,0000** y sesgo +0,0000.

> **Trampa activa en el repo:** `fetch_binance_vision_klines` escribe por defecto
> en `data/okx/` — un directorio con nombre de OKX que guarda velas de BINANCE.
> `sl_noise_screen` lee de ahí para compararlo contra cubos de OKX. Este camino
> usa `data/okx_real`.

## Qué quedó cableado

| Invariante | Dónde | Qué impide |
|---|---|---|
| Una sola definición de excursión | `tests/test_cube_excursion_scope.py` | Que las dos rutas de etiquetado vuelvan a divergir bajo el mismo nombre |
| Esquema del cubo | `bt_labeler.CUBE_SCHEMA` + `require_life_scoped` | Que un cubo viejo (mismas columnas, otro significado) entre como si fuera nuevo |
| Barrido de consumidores | mismo test | Que un tool nuevo lea la excursión del cubo sin declarar el alcance |
| Contigüidad de la ventana | `cube_regrade_excursion` | Que un hueco de velas adelante el toque de barrera en silencio |
| Reproducir antes de creer | `cube_regrade_excursion.validate` | Escribir un cubo que no reproduce lo que él mismo ya afirmaba |

El barrido de consumidores es el que encontró `sl_noise_screen.right_but_stopped_pct`
leyendo la columna contaminada. No lo encontró nadie leyendo código.

## Publicaciones a corregir

- `internal/GHOST_MAP_2026-07.md` H5 — "+6,66R / −5,65R" es del **tape**, no del
  trade. Correcto como "hasta dónde llegó el precio en 288 velas"; falso como
  recorrido de la señal. La lectura derivada ("los ganadores pasan muy en
  contra") está invertida: −0,364R.
- `internal/GHOST_MAP_2026-07.md` pregunta abierta 4 — está construida sobre el
  −5,65R. Se reformula o cae.
- `internal/BRIEF_INSTRUMENTO_2026-08.md` E7 — cita el número y propone la
  lectura de separación como veredicto. Ambas cosas hay que corregirlas.

Ninguna de estas toca el **track record publicado** (n=12 · WR 41,7 % · E[R]
+0,208 · PF 1,76): ese sale de `ledger_stats` sobre el ledger vivo, que sella la
excursión en vida desde siempre. La contaminación vivía en el research, no en el
producto.

## `geometry_report` arreglado (ago-2026)

### La separación, retirada

El veredicto circular ya no se dicta. En su lugar el informe explica por qué no
puede dictarse y a dónde va la pregunta. Las otras tres lecturas **se quedan**,
porque no son circulares: un perdedor se define por tocar el STOP, así que
cuánto llegó a ganar antes de morir es legítimo; un ganador se define por tocar
el TP, así que su MAE es libre en (−1R, 0].

Que `report_sl_too_tight` sigue discriminando lo confirma el dato: su umbral
(>30 % de ganadores por debajo de −0,7R) da **16,4 %** real — ni se dispara
siempre ni es inalcanzable.

> Había un **test fijando la lectura circular**
> (`test_el_informe_detecta_que_la_senal_no_separa`). Su fixture era imposible:
> un perdedor con MFE 1,15 sobre un TP de +1,0R habría tocado el TP y sería
> ganador. La rama "NO separa" solo se alcanzaba con datos que no pueden
> existir — por eso en producción salía siempre la otra. El test está reescrito
> para decir eso.

### El contrafactual: sesgo medido en el eje del SL

Comparado contra el **camino real** sobre 4.668 señales (ventana de 96 velas):

| error (sellado − real) | SL 0,50 | SL 0,75 | **SL 1,00** | SL 1,50 |
|---|---|---|---|---|
| TP 1,00 | +0,079 | +0,036 | **−0,004** | −0,032 |
| TP 2,00 | +0,076 | +0,042 | **+0,000** | −0,052 |
| TP 3,00 | +0,061 | +0,048 | **+0,022** | −0,049 |

Como R = |entry − stop|, **SL = 1,00 ES el stop original**, y ahí el cálculo es
exacto. El eje del TP también es fiable. Mover el stop no lo es:

- **estrechar sobreestima** hasta +0,083R — `mfe_bar`/`mae_bar` marcan el
  *extremo*, no el primer cruce del umbral nuevo;
- **ensanchar subestima** hasta −0,052R — tras el stop original el camino no
  existe en el dato.

Sobre una expectancy de ~0,2R eso es un **40 %**, y el sesgo apunta justo a
"aprieta el stop". El informe ahora lo declara en la propia tabla.

### El sobrepaso también ocurre en el TP, y no se compensa

| barrera | sobrepaso medio de la vela |
|---|---|
| stop | +0,388R |
| TP | +0,485R |

Parecen cancelarse, y no lo hacen: un TP suele ser orden **límite** (te llenas a
tu precio; el exceso es dinero que no ves pero tampoco pierdes) y un stop suele
ser **market** (te comes el exceso). La asimetría es de un solo lado, en contra.

## E7, contestado (parcial: 5 símbolos, 4.321 señales)

La lectura no circular: ventana **fija** de k velas, solo señales **vivas en k**,
y **contra placebo** (misma cinta, mismo día, misma dirección, misma geometría
relativa, entrada arbitraria 48 velas después).

El placebo no es opcional. Sin él, el recorrido temprano da **AUC 0,69** y parece
separación. Con él se ve lo que era: una entrada arbitraria sobre la misma cinta
da lo mismo. Lo que medía no es la señal — es que el precio que ya se movió hacia
el TP lo tiene más cerca. Cualquier entrada lo cumple.

### Resultado 1 — la trayectoria NO anticipa nada

Diferencia de AUC contra el placebo, bootstrap pareado (2.000 resamples):

| k | mfe_k | net_k |
|---|---|---|
| 3 | +0,025 [−0,002, +0,051] ~ | +0,010 [−0,015, +0,034] ~ |
| 6 | +0,029 [+0,002, +0,056] | +0,009 [−0,016, +0,033] ~ |
| 12 | +0,016 [−0,013, +0,045] ~ | +0,000 [−0,028, +0,028] ~ |
| 24 | +0,006 [−0,029, +0,042] ~ | −0,012 [−0,047, +0,021] ~ |

Siete de ocho celdas cruzan cero. La única que no (mfe_k a k=6) es **1 de 8 a
95 %**, justo lo que se espera por azar: no es un hallazgo. **El recorrido de las
primeras velas no dice nada del desenlace que no diga ya la cinta.** Ninguna
gestión basada en la trayectoria temprana va a añadir nada.

### Resultado 2 — pero la ENTRADA sí bate al azar

| | WR (vida 48 velas, TP=rr_tp4, SL=1R) |
|---|---|
| motor | **37,4 %** |
| placebo | 32,7 % |
| diferencia | **+4,7 pp**, IC95 % [+2,8, +6,7], P(diff≤0) = 0,000 |

Es la primera vez en este repo que la entrada se mide contra un placebo
emparejado, y **gana**. El emparejamiento sesga en contra (el placebo hereda el
régimen que disparó la señal), así que +4,7 pp es un suelo.

**Cuidado con lo que NO dice.** Esa geometría (vida 48 velas, TP a rr_tp4) no es
la de producción, así que 37,4 % no es el WR publicable. Y +4,7 pp sobre un
placebo no es rentabilidad: el WR de equilibrio con fees es 36,9 %, y el motor
vivo mide 21,1 %. Que la entrada distinga es necesario y no es suficiente.

### Cómo se lee junto

E7 preguntaba: faltan 16 puntos de WR, ¿es la geometría o es que la señal no
separa? Respuesta parcial: **la señal separa un poco en la entrada y nada en la
trayectoria.** Así que ni el problema es "no hay señal" ni se arregla gestionando
mejor el trade una vez abierto. Lo que queda en pie como sospechoso del hueco es
el **coste de ejecución** — que es E8, y que ya tiene magnitud medida en la
sección del sobrepaso.

## Lo que falta para cerrar E7

1. Terminar la cosecha (BCH, DOT y los 6 que faltan) y repetir sobre los 13.
   Nada de lo de arriba depende de ellos para el signo, sí para la precisión.
2. ~~La lectura no circular~~ — hecha, con placebo obligatorio dentro del tool.
3. ~~Arreglar la separación de `geometry_report`~~ — hecho, con su test.
