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
