# Diagnóstico E7/E8 (agosto 2026) — la geometría y el coste sobre 13.429 señales

> Los dos diagnósticos del `BRIEF_INSTRUMENTO_2026-08`. Corren sobre data que ya
> existe (`cosecha_cubes/*.parquet`), no sobre los 90 cierres del motor paper.
> **Bruto y sobre etiquetas triple-barrera:** cota de lo capturable, no simulación.
>
> Reproducir:
> ```
> python tools/geometry_report.py --cube cosecha_cubes/ --tp tp4 --horizon 288
> python tools/cube_report.py cosecha_cubes/
> ```

---

## E7 · La brecha de win rate

### Lo primero: las dos verificaciones que pedía el brief

**1. ¿Coincide la definición de MFE/MAE? NO.** Y la diferencia importa.

`bt_labeler.label_event_grid` acumula `mfe_cum`/`mae_cum` hasta el final del
horizonte de la etiqueta (`h` velas), **no hasta `bars_held`**. El recorrido del
cube sigue contando después de que la barrera resolvió el trade. El del ledger
(`execution.Position.excursion_r`) para cuando la posición cierra.

Es la forma exacta del fantasma de julio: crédito por un recorrido posterior a la
muerte de la señal. Un ejemplo del propio cube (SOL, `entry_index` 383): stop
tocado en la barra 10, `pnl_r = −1.0`, y sin embargo `mfe_r = 5.65` (h96) y
`9.97` (h288) — un movimiento que la señal, ya muerta, no podía cobrar.

Consecuencia cableada: los dos recorridos **no se promedian**. `excursion_scope()`
levanta `MixedScopeError` si un informe recibe cierres de las dos fuentes, y las
lecturas 1 (TP demasiado lejos) y 2 (SL demasiado cerca) se degradan
explícitamente a **cota superior** cuando el scope es `horizon`. El "82% de los
perdedores llegó a +1R" que sale del cube **no** dice que se salga tarde.

**2. ¿Hay orden de barra? NO.** El cube guarda el máximo y el mínimo del tramo,
no cuándo ocurrió cada uno. Se aplica la regla pesimista, y con horizontes largos
eso vacía la tabla: en la celda tp4/h288, **el 86% de las señales cruza los dos
umbrales** sin orden conocido, así que casi toda celda del contrafactual colapsa
a −SL. La tabla es una cota inferior **vacía**: no puede juzgar geometrías, y el
informe lo imprime en vez de dejar leer "−0.4R" como veredicto.

Para juzgar geometrías sobre el cube haría falta re-etiquetar sellando
`mfe_bar`/`mae_bar`. Hoy solo el ledger vivo trae ese orden.

### La lectura que más importa: ¿separa la entrada?

La comparación clásica del informe (MFE de ganadores vs. perdedores) **no vale**:
"ganador" significa que el precio tocó el TP, luego su MFE es ≥ la distancia al
TP por construcción. Esa lectura separa siempre, mida lo que mida. Métrica
demasiado limpia → bug de medición, no hallazgo.

El contraste honesto es contra la **señal invertida**: tomar el lado contrario en
la misma vela con la misma distancia de riesgo intercambia el recorrido
(`mfe' = −mae`), así que el estadístico por señal se reduce a `mfe_r + mae_r`.
Positivo = el tape se movió más a favor que en contra. Cero = volado. No depende
del TP ni del SL: separa "¿la entrada vale algo?" de "¿la geometría lo cobra?".

**Celda tp4/h288, n=13.429, bootstrap 2.000 reps:**

| grupo | n | asimetría MFE+MAE | IC95% | P(>0) |
|---|---|---|---|---|
| todos | 13.429 | **+1.011R** | [+0.825, +1.199] | 1.000 |
| long | 5.726 | +0.668R | [+0.382, +0.947] | 1.000 |
| short | 7.703 | +1.267R | [+1.022, +1.527] | 1.000 |

Por horizonte: +0.671R (h96) · +1.011R (h288) · +1.275R (h576) — el IC95% queda
por encima de cero en los tres. Por año, positivo en los ocho (2019 +0.47 …
2020 +1.79 … 2026 +0.73).

**Veredicto E7: la entrada SÍ separa.** Los 16 puntos de WR que faltan **no** se
explican por "la señal no distingue". Que sea positivo en **ambos lados** descarta
que sea deriva del mercado: un long y un short no se benefician los dos de la
misma tendencia. Es el primer contraste de este repo que aísla la entrada del
desenlace sin ser tautológico.

**Lo que NO dice.** Es bruto y sobre el recorrido: dice que el movimiento
*existe*, no que una orden real lo capture. La asimetría es de ~1R sobre un MFE
medio de +6.66R y un MAE medio de −5.65R — el margen es fino comparado con la
amplitud del ruido, y el coste de ejecución muerde ahí. Eso lo contesta E8.

**Lo que queda abierto.** Con la señal exonerada, la duda se mueve a la geometría
— y la geometría **no es contestable con este dato** (ver verificación 2). El
desbloqueo no es opinar sobre TP/SL, es sellar `mfe_bar`/`mae_bar`.

---

## E8 · La brecha bruto/neto — respuesta a la pregunta abierta 6 del GHOST_MAP

`bt_engine.CostModel` (taker ambos lados: 5 bps de fee + 1 bp de slippage por
pierna, funding 1 bp/8h) aplicado a las etiquetas del cube, celda tp4/h288,
n=13.429 señales canónicas:

| | valor |
|---|---|
| bruto | **+0.2305R** |
| **neto** | **−0.0258R** |
| coste | **−0.2563R por trade** |
| IC95% del neto | **[−0.0589, +0.0131]** |
| P(E[R]>0) | 0.110 |
| señales con neto>0 | 3.716 / 13.429 = 27.7% |

**El +0.224R bruto no sobrevive.** El coste no muerde el edge: se lo come entero.

### Por qué se lo come: el mecanismo, no la mala suerte

El fee se paga sobre el **notional**; la R es la **distancia al stop**. Entonces

```
coste_R ≈ (2·fee + 2·slip) / (stop_dist / precio)
```

Con el stop mediano de esta cosecha — **0.525% del precio** — eso son 0.0012 /
0.00525 ≈ **0.23R por trade**, más funding. No es un parámetro desafortunado: es
aritmética de un motor de 5m con stops estrechos. El mismo edge bruto con stops
de swing (5% del precio) pagaría 0.02R y sobreviviría entero.

Se ve directo en el quintil de distancia de stop (bruto → neto):

| quintil | stop (% precio) | n | bruto | neto | coste |
|---|---|---|---|---|---|
| Q1 (más estrecho) | 0.27% | 2.686 | +0.305 | −0.156 | −0.461 |
| Q2 | 0.40% | 2.686 | +0.315 | +0.014 | −0.301 |
| Q3 | 0.52% | 2.686 | +0.212 | −0.016 | −0.228 |
| Q4 | 0.68% | 2.685 | +0.161 | −0.014 | −0.175 |
| Q5 (más ancho) | 0.99% | 2.686 | +0.160 | +0.043 | −0.117 |

El coste cae 4× de Q1 a Q5 — pero el bruto cae con él, así que el neto se queda
plano alrededor de cero. **No hay ningún sitio donde el edge bruto sea grande y
el coste chico a la vez.**

### ¿Se concentra el neto en algún subconjunto que sí aguante? No

Se inspeccionaron **28 cortes** (13 símbolos × 8 años × 2 lados × 5 quintiles de
stop) y cada candidato pasó por el gate con `n_trials = 28`:

| corte | n | bruto | neto | IC95% neto | DSR |
|---|---|---|---|---|---|
| año 2020 | 965 | +0.460 | +0.188 | [+0.038, +0.336] | 0.359 |
| AVAX | 830 | +0.382 | +0.150 | [−0.008, +0.311] | 0.210 |
| BCH | 1.627 | +0.324 | +0.073 | [−0.036, +0.187] | 0.008 |
| ETH | 1.482 | +0.332 | +0.069 | [−0.049, +0.185] | 0.009 |
| stop Q5 | 2.686 | +0.164 | +0.048 | [−0.022, +0.120] | 0.000 |
| pool completo | 13.429 | +0.230 | −0.026 | [−0.059, +0.013] | 0.000 |

**Ninguno clarea DSR > 0.95.** El mejor (2020, DSR 0.356) es el ganador de un
concurso de 28 juzgado después de ver los resultados. Y los dos candidatos que
más tientan ya estaban desmentidos por el propio repo: `GATE-D` midió que el
liderazgo por símbolo **no persiste** (rank-corr mitad-a-mitad −0.19), y `H1` que
el régimen del año se voltea. Elegir AVAX o 2020 es exactamente el error de mayo.

Por celda tp × horizonte, las **12 son negativas netas** (de −0.022 en tp4/h576 a
−0.118 en tp1/h96). Estirar el objetivo ayuda — diluye el coste fijo sobre más R —
pero no alcanza para cruzar cero.

### El alcance (leer antes de citar cualquier número de arriba)

Es una **cota superior**, no una simulación. La etiqueta triple-barrera asume
fill perfecto en el precio de la barrera: sin modelo de cola, sin rechazos, sin
fills parciales. Ya está medido que el fill importa muchísimo (los maker rápidos
pierden el 80% del R). **Lo realizable está por debajo de esta tabla, nunca por
encima.** El −0.510R del motor paper vivo es la misma cosecha con fill real: la
distancia entre −0.026 y −0.510 es lo que cuesta ejecutar de verdad.

### Veredicto E8: en contra

La pregunta abierta 6 del `GHOST_MAP` preguntaba cuánto del +0.224R sobrevive al
coste. **La respuesta medida es: nada, ni siquiera en el mejor caso teórico.**

---

## Qué significan los dos juntos

E7 y E8 no se contradicen, se completan:

- **La entrada sí separa** (+1.011R de asimetría de recorrido, IC95% por encima
  de cero, ambos lados, ocho años). El movimiento existe.
- **El coste se lo come entero** (−0.256R/trade sobre un bruto de +0.230R), y no
  hay subconjunto donde eso deje de pasar.

O sea: el problema **no** es que la señal no vea nada. Es que ve ~1R de asimetría
y cobra 0.23R de peaje por mirar, sobre una geometría que hoy captura +0.23R
brutos de ese 1R. **La palanca no está en la entrada ni en más features: está en
la relación entre el recorrido disponible y el coste fijo** — o sea en R por
trade (stops/objetivos más anchos, menos trades) y en fill (maker que llene de
verdad). Ambas cosas **son E6-prohibidas hoy** y sus condiciones de desbloqueo ya
están escritas en el brief.

Consecuencia para el encargo: E1–E5 siguen valiendo la pena — el instrumento es
justo lo que hace falta para decidir esto con datos — pero **instrumentan un
sistema que hoy no debe operar con capital**. Eso ya era el estado del arte
(`CLAUDE.md`: "no hay edge demostrado"); ahora está medido sobre 13.429 señales
en vez de sobre 90.

---

## LA MEDICIÓN DEL FILL (2026-08-04) — la pregunta que decidía, contestada

E8 dejó una sola puerta abierta: con **entrada maker** el signo se voltea
(+0.0601R, IC95% [+0.0235, +0.0958], P(>0)=0.998). Pero ese escenario asume
**fill del 100%**, y el repo ya sabía que la suposición es falsa en la dirección
optimista. El error de la suposición era más grande que todo el margen — así que
toda la diferencia entre rentable y no rentable estaba ahí.

Ya no está abierta.

> Reproducir (local, sin runners):
> ```
> for S in SOLUSDT BTCUSDT ETHUSDT BCHUSDT LTCUSDT XRPUSDT ADAUSDT AVAXUSDT \
>          BNBUSDT DOGEUSDT DOTUSDT LINKUSDT TRXUSDT; do
>   FQ_CVD_DIR=data/binance python tools/fetch_binance_vision_klines.py "$S" \
>     --start 2019-06-01 --end 2026-06-30
> done
> python tools/fill_quality.py
> ```
> ~139 MB, unos minutos, coste cero (archivo público S3, sin API key).

### Antes del número: el gate de venue

Los cubos se cosecharon de **OKX**, que bloquea desde datacenter (403). Las velas
vienen de **Binance Vision**, y un desajuste entre venues cae justo en la escala
que esto mide (eps = 1 bp). Por eso `validate_venue()` corre primero y es un
**gate, no una nota**: recomputa MFE/MAE desde las velas locales y las compara
con las que el cube trae de OKX. Si no concuerdan, no se imprime ningún fill rate.

Los 13 símbolos pasaron: **corr MFE 0.995–1.000, corr MAE 0.953–0.999**,
92–100% de las señales alineadas por timestamp. Las dos series describen el
mismo mercado, así que la medición es legible.

### El resultado — n=12.941

| | valor |
|---|---|
| fill rate (eps 1 bp, TTL 6 barras) | **88.4%** |
| bruto de las **llenadas** | **+0.114R** (WR 25.4%) |
| bruto de las **escapadas** | **+1.153R** (WR 47.3%) |
| **selección adversa** | **−1.039R** |
| **neto maker sobre lo que se llena** | **−0.0350R**, IC95% [−0.074, +0.004] |
| (recordatorio: E8 con fill 100% asumido) | +0.0601R, IC95% [+0.024, +0.096] |

**La selección adversa está confirmada y es enorme.** No es que se llene poco —
se llena el 88%. Es que **el 12% que se escapa son los ganadores**: +1.153R con
WR 47.3%, contra +0.114R y WR 25.4% de las que sí se llenan. La límite no se
llena precisamente cuando el precio se va a tu favor, que es cuando la querías.

**Veredicto: el margen teórico de E8 no sobrevive al fill real.** +0.0601R
teórico → **−0.0350R** medido. Y sigue siendo cota superior: el fill se juzga con
la vela, y dentro de la vela no se conoce la cola de la orden.

### V2 (2026-08-05) — POSICIÓN EN COLA: la frase de arriba, medida

La sección anterior se cierra diciendo *"sigue siendo cota superior: el fill se
juzga con la vela, y dentro de la vela no se conoce la cola de la orden"*. Eso
era la última cota abierta y ahora tiene número.

**Qué cambia en el modelo.** `maker_entry_fill_mask` contesta *"¿el precio
llegó?"*. Una límite no se llena porque el precio la toque: se llena cuando el
volumen operado en su nivel **consume la cola que tenía por delante**.
`bt_engine.maker_fill_probability` sustituye el booleano por

    p = clip(flujo_consumido / cola_por_delante, 0, 1)

donde el flujo es el **firmado** — a una BID la consume el taker SELL que imprime
en su nivel o por debajo, no el volumen total, del que la mitad son compras que
se cruzan contra el ask (`taker_buy_base` de Binance Vision lo da por barra). La
cola se declara en `queue_frac` = múltiplos del volumen **mediano** de barra del
propio símbolo, que es lo que hace comparables BTC y SOL.

**`queue_frac = 0` ES la binaria de siempre.** Con cola cero cualquier
penetración llena con p=1. O sea que la regla que este repo usó hasta hoy no es
otro modelo: es **la esquina más optimista de éste** — la de estar siempre el
primero de la cola. El test `test_la_cola_cero_reproduce_la_binaria` lo comprueba
en cada corrida, y el informe lo imprime como primera fila para que la tabla se
lea desde ahí.

**La curva — pool completo, n=12.941, celda tp4/h288, neto maker:**

| queue_frac | fill | n esperada | **E[R] neto** | IC95% |
|---|---|---|---|---|
| **0.00** (= la binaria) | 88.4% | 11.438 | **−0.0350** | [−0.076, **+0.004**] |
| 0.05 | 85.5% | 11.071 | **−0.0635** | [−0.104, −0.025] |
| 0.10 | 83.2% | 10.764 | **−0.0908** | [−0.131, −0.053] |
| 0.25 | 77.7% | 10.055 | **−0.1549** | [−0.195, −0.116] |
| 0.50 | 71.1% | 9.206 | **−0.2311** | [−0.271, −0.193] |
| 1.00 | 61.9% | 8.006 | **−0.3294** | [−0.370, −0.290] |
| 2.00 | 49.5% | 6.403 | **−0.4453** | [−0.491, −0.403] |

La fila 0.00 reproduce al cuarto decimal la medición del 2026-08-04 (−0.0350R,
IC [−0.074, +0.004]): la misma medición, ahora como caso límite de un modelo.

**Lo que la tabla dice, y es lo más caro de la sección:** el −0.0350R de agosto
era el único número maker cuyo IC95% aún **rozaba** el cero por arriba (+0.004).
**Con una cola de 0.05 barras medianas por delante — la suposición más pequeña
que se puede hacer que no sea "soy el primero" — el IC ya está entero por debajo
de cero.** No hace falta un modelo de microestructura fino para matar la vía
maker: basta con no ser el primero de la cola.

**El mecanismo, que es mejor evidencia que la curva.** Una curva que baja al
meter cola podría ser puro encogimiento de muestra. Esto no lo es, y se ve
ordenando las señales por su propia probabilidad de llenarse (queue_frac 0.50,
sobre las 11.438 que la binaria da por llenas):

| P(fill) | n | **NETO** |
|---|---|---|
| 0.00–0.25 | 1.468 | **+0.8548** |
| 0.25–0.50 | 925 | +0.7976 |
| 0.50–0.75 | 701 | +0.4710 |
| 0.75–1.00 | 587 | +0.3613 |
| **= 1.00** | **7.757** | **−0.3784** |

**corr(P(fill), R neto) = −0.2267.** La orden que más seguro se llena es la que
peor sale, y el gradiente es monótono en los cinco tramos. Esto es la selección
adversa de agosto (−1.039R) **explicada por su mecanismo**: la cola no te quita
señales al azar, te deja exactamente aquellas en las que el precio te atravesó.
Estar atrás en la cola es un filtro, y filtra al revés.

**El universo VIP (BTC/ETH/SOL), n=3.565 alineadas**, cuenta lo mismo un peldaño
más arriba: cola 0.00 **+0.0282** [−0.047, +0.106] → cola 0.25 **−0.0845**
[−0.161, −0.007] → cola 2.00 **−0.3884**. Ni siquiera la esquina optimista tiene
el IC entero sobre cero.

**Lo que NO dice.** `queue_frac` es un supuesto declarado, no una medición: este
repo no tiene libro L2 y no sabe cuánta cola había de verdad. Por eso el informe
imprime la **curva** y no un punto, y el resultado que se cita es el **umbral**:
*a partir de 0.05 barras de cola, el signo está determinado*. Sigue habiendo una
cota por arriba — dentro de la vela no se conoce el orden de los ticks — pero
ahora la cota está por debajo de cero en todo el rango razonable.

**La invariante que sale de aquí** (`bt_engine`): toda fila que sale de
`simulate` lleva pegada la procedencia de su fill (`taker` / `modelado` /
`asumido_100`), y `maker_expectancy` **levanta `MakerFillAssumedError`** ante
`asumido_100`. El +0.060R de E8 no puede volver a publicarse como resultado: se
puede imprimir, pero solo por la puerta que lo etiqueta TECHO. Es la misma
enfermedad del fantasma de julio — un supuesto viajando sin etiqueta — y esta vez
el cableado la para.

> Reproducir: `python tools/fill_quality.py --klines data/binance`
> (universo VIP: `--symbols SOL_USDT,BTC_USDT,ETH_USDT`; `--queue-grid` cambia la
> rejilla). Las velas se bajan con el bucle de arriba: `data/` está en
> `.gitignore`, así que un clon nuevo no las trae.

### Hallazgo colateral: el gate de producción está al revés en esta muestra

`FQ_MOTOR_MIN_FILL_BARS=2` está **ON por defecto** y descarta los fills de 1
barra, por el hallazgo de agosto sobre n=53 (fills ≤2 barras: WR 11%, 80% de la
pérdida). Sobre n=11.438 el orden se invierte:

| barras de espera | n | NETO | IC95% |
|---|---|---|---|
| **1 barra** | 9.735 | **+0.0010R** | [−0.042, +0.043] |
| 2 barras | 723 | −0.2447R | [−0.376, −0.110] |
| 3–4 barras | 650 | −0.2349R | [−0.374, −0.091] |
| 5+ barras | 330 | −0.2444R | [−0.448, −0.036] |

| | n | NETO | IC95% |
|---|---|---|---|
| sin gate | 11.438 | −0.0350R | [−0.074, +0.004] |
| **con gate ≥2 barras** | 1.703 | **−0.2409R** | [−0.329, −0.152] |

El gate **descarta el único bucket que no es negativo y se queda con los peores**,
y de paso tira el 85% del flujo.

**Esto NO es orden de apagarlo.** La geometría no es la misma (el cube es
tp4/h288; el motor vivo, tp1 con TTL), así que no es una refutación estricta. Es
orden de **remedirlo antes de seguir confiando en él**: el hallazgo que lo
justifica tiene n=53 y el que lo contradice n=11.438, y la regla de este repo
sobre cuál pesa más ya está escrita.

### Qué queda

La palanca no es la entrada (E7: separa) ni el modelo (GATE-H: el ML empeora).
Es la relación entre el recorrido disponible y el coste fijo, y ahora se sabe que
**el fill maker no la arregla**. Lo que queda sin medir:

1. **R por trade más grande.** Stops/objetivos más anchos y menos trades diluyen
   el coste fijo — pero E7 midió que la asimetría escala igual, así que hace
   falta comprobarlo, no suponerlo. Requiere re-etiquetar el cube.
2. **Otro terreno.** Un TF más alto cambia la razón coste/recorrido de verdad.
   Es una cosecha nueva, no un ajuste.

Las dos son E6-adyacentes (tocan TP/SL). Ninguna se toca sin decidirlo antes.

---

## EL BARRIDO DE GEOMETRÍA (2026-08-04) — el primer candidato real

De las dos palancas anteriores se midió la primera: **¿un stop más ancho diluye
el coste fijo lo bastante?** Descartado el cambio de TF por decisión de RasDG.

> `python tools/geometry_sweep.py --klines data/binance`

### El contra-argumento, primero

Ensanchar stop **y** objetivo a la vez es **invariante**: el coste en R se divide
por k, pero la asimetría de recorrido de E7 (+1.011R) también. El ratio
asimetría/coste queda en **4.42× para cualquier k**. Un reescalado puro no
regala nada.

Lo único que puede romper esa invarianza es que la **resolución por barreras no
es lineal**: un trade que hoy muere en el stop y luego se recupera pasa a ganador
con un stop más ancho. Eso cambia la *forma* de la distribución, no su escala.

### Lo medido — rejilla de 84 celdas sobre 12.941 señales

Re-etiquetado con `bt_labeler.label_event_grid` (misma convención de empate
pesimista que la cosecha) sobre las velas locales, con costes **taker**:

| kSL \ tpR (h=1152) | 1.0 | 3.0 | 6.0 | 10.0 |
|---|---|---|---|---|
| **1.0** (actual) | −0.111 | −0.046 | −0.007 | +0.005 |
| 3.0 | +0.002 | +0.029 | +0.060 | +0.076 |
| **5.0** | +0.026 | +0.027 | +0.061 | **+0.085** |
| 8.0 | +0.016 | +0.035 | +0.057 | +0.068 |
| 12.0 | +0.006 | +0.037 | +0.053 | +0.051 |

**El gradiente existe y GIRA** (kSL 5 → 8 → 12 empeora): hay óptimo interior, no
una deriva hacia comprar-y-esperar en la dimensión del stop.

### Los tres controles

**1. ¿Es deriva de mercado?** No. Misma geometría con la señal **invertida**:

| kSL=5, tpR=6, h=1152 | neto |
|---|---|
| señal real | **+0.0608R** |
| señal invertida | **−0.1013R** |

Si fuera beta, la invertida saldría *mejor* (el set es 57% short). Sale peor por
**0.162R**. La dirección que elige la señal vale, consistente con E7.

**2. ¿Sobrevive fuera de muestra?** CPCV con folds temporales, 15 caminos:

| geometría | OOS medio | caminos > 0 | peor camino |
|---|---|---|---|
| kSL=1.0 tpR=6 (**la actual**) | −0.0137 | 5/15 | −0.0710 |
| kSL=5.0 tpR=10 | **+0.0797** | 13/15 | −0.0154 |
| kSL=8.0 tpR=10 | +0.0633 | **15/15** | +0.0002 |
| kSL=12 tpR=6 | +0.0510 | 14/15 | −0.0022 |

**kSL=5/tpR=10 le gana a la geometría actual en 15/15 caminos, +0.0934R de media.**

**3. ¿Es sobreajuste de selección?** **PBO = 0.198.** Bajo. (Referencia del propio
repo: el umbral KL dio 0.897 — alerta; el barbell de convicción dio 0.008 — limpio.)

### Y sin embargo: NO pasa el gate

**DSR = 0.000** en todas las celdas, con `n_trials=84`.

Las tres patas del gate **se contradicen**, y eso es en sí el hallazgo. CPCV dice
que sobrevive OOS; PBO dice que elegirlo no es sobreajuste; DSR dice que el
Sharpe **por trade** no se distingue del máximo de 84 intentos. Las tres pueden
ser ciertas a la vez: el Sharpe por trade es diminuto porque el perfil es de
lotería (**1–6% de aciertos**, colas gordas), y la corrección por skew/kurtosis
del DSR castiga exactamente ese perfil.

**La constitución no admite lectura:** *"nada entra a vivo sin DSR > 0.95"*. Esto
**no va a vivo**, y no se degrada la vara para que quepa.

### Lo que además hay que decir antes de ilusionarse

- **Es OTRO producto.** La celda de mejor Sharpe (kSL=12, tpR=6) resuelve **63%
  por timeout, 35% en stop, 1% en objetivo**, con el stop al **6.3% del precio**.
  Eso no es afinar la geometría del bot: es mantener la dirección 4 días. La
  cadencia, el drawdown y el compromiso de capital son otros.
- **Reparte desigual por año** (2025 negativo; 2021 y 2023 con el IC cruzando
  cero). El agregado no basta — por eso el informe lo desglosa siempre.
- **Sigue siendo pre-fill.** Con una diferencia estructural a favor: a stops del
  5–6% del precio el coste fijo son ~0.02R en vez de 0.23R, así que la
  sensibilidad al fill —lo que mató la entrada maker— es un orden de magnitud
  menor. Pero *menor* no es *medida*.
- **La concurrencia no está medida.** Con holds de 4 días sobre 13 símbolos, las
  posiciones se solapan. El riesgo de cartera NO es el R por trade.

### Veredicto

**El primer candidato real del proyecto.** Todo lo anterior (E7, E8, fill maker)
terminó en "no". Esto termina en "**todavía no, y aquí está exactamente qué
falta**": CPCV ✓, PBO ✓, control de inversión ✓, DSR ✗.

No entra al cementerio. Queda como candidato con tres deberes concretos:
1. **Fill medido a la nueva geometría** (`tools/fill_quality.py` ya lo hace; hay
   que re-correrlo con los stops anchos).
2. **Riesgo de cartera con solapamiento** — el R por trade no lo describe.
3. **Entender el desacuerdo DSR/CPCV** — si el Sharpe por trade es la métrica
   equivocada para un perfil de lotería, hay que decirlo con argumento, no
   saltarse la vara.

---

## LOS TRES DEBERES, HECHOS (2026-08-04)

### 1. Fill a la nueva geometría — **resuelto a favor**

A stops 5× el coste taker son **0.0469R** (contra 0.256R de la geometría vieja).
Eso cambia la respuesta correcta: ya no hay motivo para usar una límite pasiva.

| entrada | n | neto |
|---|---|---|
| **TAKER, todas** (siempre se llena) | 12.941 | **+0.0852R** |
| maker, solo lo que llena | 11.438 | +0.0709R |

Ir maker **resta −0.0143R**: ahorras fee pero pierdes el 11.6% del flujo, que
sigue siendo el mejor (escapadas +0.3658R brutas vs +0.1014R de las llenadas).
La selección adversa sigue existiendo (−0.2644R) pero ya no muerde, porque con
entrada taker no hay orden que se escape. **Veredicto: entrada taker, y el
problema que mató la geometría vieja no aplica aquí.**

### 2. Riesgo de cartera — **el que decide, y decide en contra**

Hold medio **2.0 días** → **13.7 posiciones simultáneas de media, p95 29, máx 54**.
Con el capital comprometido en la apertura y realizado en el cierre
(`tools/portfolio_risk.py`):

| config | ×7 años | DD máx | señales tiradas |
|---|---|---|---|
| risk 1.00% sin límite | **0.00** | **100%** | 0 |
| risk 0.50% sin límite | 0.80 | 97.6% | 0 |
| risk 0.25% sin límite | 2.99 | 69.3% | 0 |
| risk 0.10% sin límite | 2.23 | 33.6% | 0 |
| risk 1% · máx 5 abiertas | 12.86 | **71.1%** | 8.494 (66%) |
| risk 1% · máx 3 abiertas | 9.29 | 57.9% | 10.162 (79%) |

Peores días: **−26.0R en 24 cierres** el mismo día (2026-03-18), −24.2R en 23,
−23.1R en 31. Las pérdidas llegan juntas — medido, no supuesto.

**El edge por trade es real y el producto sigue siendo inviable.** La mejor
configuración por Calmar (×12.86) paga un **71% de drawdown** y descarta **2 de
cada 3 señales**. Un 71% de drawdown no es operable con suscriptores: el cliente
se va mucho antes del suelo. Y es **cota inferior** — no se modela correlación
explícita entre posiciones abiertas.

### 3. El desacuerdo DSR/CPCV — **diagnosticado; el veredicto no cambia**

El DSR falla por **el tamaño de mi rejilla**, no por la estrategia:

| n_trials | sr_trials_std | vara sr0 | Sharpe/trade 0.0377 |
|---|---|---|---|
| 84 | 0.020 | 0.0494 | no la supera |
| 9 | 0.020 | 0.0304 | la supera |
| 1 | 0.020 | 0.0104 | la supera |

Perfil: skew **+2.68**, kurtosis **10.6** — lotería. La corrección por
no-normalidad del DSR castiga exactamente eso, y hace bien.

Como eso es una crítica a mi búsqueda y no a la señal, lo probé fuera de muestra
**por símbolo**, que es lo que el DSR está señalando:

- Partición alfabética 7/6: FIT +0.1233R → **TEST −0.0049R**. Parecía muerte.
- **Repetido sobre 8 particiones aleatorias: 8/8 con TEST positivo**, media
  **+0.0494R**. La partición alfabética era la desafortunada — casi lo mato con
  n=1, que es justo el error contra el que este repo entero está construido.
- Por símbolo: **3/13 con IC95% > 0, 0/13 por debajo**, 10/13 con signo positivo.

**El efecto transfiere.** Pero incluso dándole el máximo beneficio (celda ya
fijada, `n_trials=1` sobre el holdout), **DSR = 0.432 < 0.95**. No pasa.

### Veredicto final del candidato

| prueba | resultado |
|---|---|
| gradiente con óptimo interior | ✅ |
| control de inversión (¿es beta?) | ✅ no lo es (−0.101R invertida) |
| CPCV OOS temporal | ✅ 13–15/15 caminos |
| PBO | ✅ 0.198 |
| holdout por símbolo (×8) | ✅ 8/8 positivos |
| fill a la nueva geometría | ✅ taker, sin problema |
| **DSR > 0.95** | ❌ 0.432 en el mejor caso |
| **riesgo de cartera** | ❌ **71% DD tirando 2/3 del flujo** |

**Se cierra.** No por falta de señal — la señal está confirmada por seis pruebas
independientes. Se cierra porque **el perfil de riesgo que exige es incompatible
con el producto**: 14 posiciones correlacionadas abiertas a la vez, holds de 2
días, 1–6% de aciertos y drawdowns del 60–70% en la contabilidad optimista.

Lo que queda escrito para el futuro: **la palanca de la geometría está medida y
agotada.** Quien vuelva a proponer "stops más anchos" tiene aquí los 84 números,
los seis controles y la razón exacta por la que no basta.

---

## V3 · CAPACIDAD (2026-08-05) — a qué tamaño se muere, con liquidez MEDIDA

> Reproducir: `python tools/capacity_analysis.py --vip`
> (necesita `data/binance/kl_hist_{BTC,ETH,SOL}USDT.parquet`; se bajan con
> `tools/fetch_binance_vision_klines.py <SYM> --start 2019-06-01 --end 2026-06-30`)

### Lo primero: el tool contestaba con parámetros inventados

`tools/capacity_analysis.py` existía desde N8.4 y su propio docstring pedía
"CALIBRARLOS con volumen real". Nadie lo hizo. Medido ahora contra las velas
locales, el default `avg_bar_notional=3e6` estaba **8x por debajo de BTC**:

| símbolo | barras 5m | USD/barra (mediana) | σ/barra | stop mediano (del cube) |
|---|---|---|---|---|
| BTC | 677.766 | **2.563e7** | 20,3 bps | 0,45% |
| ETH | 681.605 | **1.428e7** | 26,5 bps | 0,50% |
| SOL | 523.732 | **4.278e6** | 34,9 bps | 0,63% |

Mediana y no media: media/mediana ≈ 2 en los tres (cola derecha gordísima), y la
media describe el día del crash, no la barra en la que se opera.

El `stop_frac` también estaba inventado (0,012 por defecto). El real es
**0,45–0,63%**, o sea la mitad — y como el impacto entra en R **dividido** por la
distancia al stop, ese solo parámetro desplazaba la curva entera.

### El bug que nadie podía ver: `fill_bars` elegía la respuesta

La ley raíz es `impacto = Y · σ_ventana · sqrt(participación)`. El tool usaba σ
**por barra** contra liquidez **por ventana** (`avg_bar_notional × fill_bars`), y
esa mezcla de escalas hacía que la capacidad creciera con `sqrt(fill_bars)`:

```
sin escalar σ (lo que hacía el tool)      con σ escalada a la ventana
fill_bars=  1 -> C0 $12k                  fill_bars=  1 -> C0 $12k
fill_bars=  6 -> C0 $70k                  fill_bars=  6 -> C0 $12k
fill_bars= 24 -> C0 $282k                 fill_bars= 24 -> C0 $12k
fill_bars= 96 -> C0 $1.126M               fill_bars= 96 -> C0 $12k
```

`fill_bars` es **cómo troceas tu orden**, no una propiedad del mercado: no puede
mover dónde muere el edge. Con σ escalada a la misma ventana que el volumen la
ley raíz es exactamente invariante, y `test_capacity_is_invariant_to_fill_bars`
lo fija. El default de 24 estaba multiplicando la capacidad por 24.

### La curva (celda tp4/h288, universo VIP, risk 1%/trade)

Y es lo único declarado — adimensional, ~0,5–1,5 en la literatura de impacto. Por
eso va la curva entera y lo que se cita es el umbral, no el punto. (Mismo trato
que `queue_frac` en V2.)

| símbolo | Y | bruto | C½ | C0 | **neto** | **C½** | **C0** |
|---|---|---|---|---|---|---|---|
| BTC | 0,5 | +0,2912 | $1,2M | $4,9M | +0,0027 | <$1k | <$1k |
| BTC | 1,0 | +0,2912 | $308k | $1,2M | +0,0027 | <$1k | <$1k |
| BTC | 1,5 | +0,2912 | $137k | $547k | +0,0027 | <$1k | <$1k |
| ETH | 0,5 | +0,3220 | $650k | $2,6M | +0,0586 | $22k | $86k |
| **ETH** | **1,0** | +0,3220 | $162k | $650k | **+0,0586** | **$5k** | **$22k** |
| ETH | 1,5 | +0,3220 | $72k | $288k | +0,0586 | $2k | $10k |
| SOL | 0,5 | +0,1656 | $60k | $242k | −0,0539 | — | — |
| SOL | 1,0 | +0,1656 | $15k | $60k | −0,0539 | — | — |
| SOL | 1,5 | +0,1656 | $7k | $27k | −0,0539 | — | — |

### A los tamaños de la conversación real (Y=1)

| capital | BTC (q · edge) | ETH (q · edge) | SOL (q · edge) |
|---|---|---|---|
| $10k | 0,09% · −0,024 | 0,14% · **+0,019** | 0,37% · −0,121 |
| $50k | 0,43% · −0,056 | 0,70% · −0,031 | 1,85% · −0,205 |
| $100k | 0,86% · −0,081 | 1,41% · −0,068 | 3,71% · −0,267 |
| $500k | 4,31% · −0,183 | 7,04% · −0,224 | 18,54% · −0,530 |
| $1M | 8,61% · −0,260 | 14,09% · −0,341 | 37,08% · −0,728 |

**Todo el edge medido del producto cabe en una celda: ETH por debajo de ~$22k.**
Es literalmente el escenario que el brief planteaba como "si la capacidad resulta
ser de $5k, el producto es un servicio de señales y punto".

### La frontera entre dos regímenes, que es lo accionable

Capital al que el impacto (**escala** con el tamaño) iguala al coste fijo por
trade (fees + slippage de catálogo, **no escala**):

| símbolo | coste fijo | el impacto lo iguala en |
|---|---|---|
| BTC | 0,289R | **$1,2M** |
| ETH | 0,263R | **$434k** |
| SOL | 0,219R | **$106k** |

Por debajo manda el coste fijo: **encoger la cuenta no arregla nada**. Por encima
manda el impacto y la capacidad es el límite real. El rango de la conversación
($10k–$500k) **cruza esa frontera en SOL y roza la de ETH** — no es un tramo
donde el tamaño salga gratis, y hasta hoy nadie sabía de qué lado estaba.

### Por qué sale tan baja, que no es lo que parece

No es falta de libro: BTC mueve 2,6e7 USD por barra de 5m y a $1M la orden es el
8,6% de una barra. Es que **el stop del motor es apretado** (0,45–0,63%) y el
impacto entra en R dividido por esa distancia: los mismos 7 bps valen 0,03R con
un stop del 5% y 0,22R con uno del 0,63%.

Y aquí se cruzan dos medidas viejas del repo que nadie había puesto juntas: el
2026-06-30 se midió que **el stop apretado ES el edge** (Q1-apretado +0,316R vs
Q4-ancho +0,147R, pooled n=13.429) y que ensancharlo bajaría la expectativa.
**Lo que hace rentable a la señal es exactamente lo que la hace frágil al
tamaño.** No son dos problemas: es un compromiso, y ahora tiene números por los
dos lados. (La geometría ancha, que sería la salida natural, está cerrada por
cartera desde el 2026-08-04.)

### Desglose por año — la capacidad de hace cinco años no es la de hoy

El notional por barra de SOL creció **~100x** dentro del cube (4e4 en 2020 →
9,2e6 en 2025). Citar una capacidad de siete años promediados es el mismo error
que citar una expectancy agregada, así que el informe la desglosa (E9):

| año | SOL USD/barra | bruto | C0 bruto |
|---|---|---|---|
| 2021 | 1,349e6 | −0,2507 | — (bruto ≤ 0) |
| 2022 | 2,151e6 | +0,4763 | $156k |
| 2023 | 1,895e6 | +0,0877 | $8k |
| 2024 | 6,862e6 | +0,1060 | $62k |
| 2025 | 9,215e6 | +0,2133 | $248k |
| 2026 | 4,578e6 | +0,4274 | $867k |

La capacidad **sube con el mercado**, y la de 2026 es 100x la de 2023. Lo que no
sube es el edge neto.

### Veredicto

**La pregunta de negocio de V3 tiene respuesta, y es de cinco dígitos.** Esto es
un **servicio de señales, no un vehículo de capital**: la escala a la que el
impacto empieza a doler está en las decenas de miles, y llega **antes** de que el
edge neto esté demostrado.

Con el matiz que manda decir en voz alta: la capacidad del edge **neto** es
prácticamente cero porque **no hay edge neto que escalar**, no porque falte
libro. El techo de ejecución perfecta (serie bruta, sin coste alguno) está en
$60k–$1,2M según símbolo — y esa distancia entre $60k y "<$1k" **es** el coste de
ejecución, otra vez, medido por tercera vía independiente.

### La invariante

`require_measured()` levanta `CapacityAssumedError` ante (a) una capacidad
calculada con liquidez supuesta y (b) una capacidad sobre serie BRUTA sin pedir
explícitamente `allow_ceiling=True`. Espejo de `MakerFillAssumedError` (V2) y de
`GrossWithoutNetError` (E8). Y sin velas locales el informe **se para en seco**
diciendo cómo bajarlas, en vez de contestar con el default de catálogo — que es
lo que llevaba haciendo desde N8.4.
