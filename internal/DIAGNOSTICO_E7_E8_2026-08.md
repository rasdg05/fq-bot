# Diagnóstico E7/E8 (agosto 2026) — la geometría y el coste sobre 13.429 señales

> Los dos diagnósticos del `BRIEF_INSTRUMENTO_2026-08`. Corren sobre data que ya
> existe (`cosecha_cubes/*.parquet`), no sobre los 90 cierres del motor paper.
> **Bruto y sobre etiquetas triple-barrera:** cota de lo capturable, no simulación.
>
> Reproducir:
> ```
> python tools/geometry_report.py --cube cosecha_cubes/ --tp tp4 --horizon 288
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
