# EXPERIMENT — KLD grado-grado vs grado simple (la mejora que sugirió Lacasa)

> Origen: una IA externa citó a Lacasa et al. (visibility-graph irreversibility) y Lacasa mismo
> advierte que la KLD sobre la *distribución de grado* (la que usa FQ) es la versión "benchmark,
> simple e intuitiva", y que "para un proceso irreversible con corriente neta nula hay que usar
> la distribución grado-grado". Probamos si esa mejora separa más en nuestro cube. Measure-first:
> si separa mejor → avanzamos el método; si no → cementerio.

## Qué se probó
- **irrev (actual)**: `KL(P_in ‖ P_out)` de las distribuciones marginales de grado del DHVG.
- **irrev_dd (candidato)**: `KL(P(k_out,k_in) ‖ P(k_in,k_out))` — histograma 2D conjunto de pares
  (out,in) vs su reverso temporal. Capta la irreversibilidad de corriente-neta-nula que la
  marginal pierde.
- Ventana causal 64×5m, majors BTC/ETH/SOL, n=3,137 señales (celda tp1/h96), join a pnl_r.

## Resultado: la grado-grado NO separa mejor — separa PEOR

| Medida | Spearman vs pnl_r | avgR reversible | avgR irreversible | **spread** | gap del gate @p60 |
|---|---|---|---|---|---|
| **irrev (grado, actual)** | −0.037 | +0.282 | +0.166 | **+0.116** | **+0.103** |
| irrev_dd (grado-grado) | +0.002 | +0.200 | +0.216 | −0.016 | +0.001 |

- Las dos medidas correlacionan solo 0.319 → sí miden cosas distintas. Pero lo que mide la
  grado-grado **no predice el outcome**: spread ~0, gap del gate ~0 (muerto).
- En la "zona ciega" de la grado (irrev alto, donde suprimimos), ordenar por grado-grado da
  spread −0.167 **con el signo AL REVÉS** de la tesis de régimen (dd-alto rinde más) → no
  rescata nada usable, apunta en dirección contraria.

## Por qué falla (el mecanismo, no solo el número)
La distribución **grado-grado es un histograma 2D** — sobre una ventana de **64 puntos** los
bins conjuntos quedan casi vacíos (estimación dispersa). Se ve en la dispersión: irrev_dd tiene
**std 0.92 y rango hasta 8.8** vs irrev std 0.36, rango 2.8 — mucho más ruidosa. La marginal 1D
se estima bien con 64 muestras; la conjunta 2D **necesita miles de puntos** (que es donde Lacasa/
Fan la usan: series históricas largas, no ventanas causales live).

## Veredicto: **CEMENTERIO. La grado simple es la correcta para gating en ventana corta.**
La mejora académica **no transfiere** a nuestro caso de uso (5m, 64 barras, gate por barra en
vivo). No es que Lacasa esté mal — es que su caveat aplica a series largas; en ventana causal
corta la versión simple no es solo suficiente, es **estrictamente mejor** (separa +0.103 gap vs
+0.001). El sesgo de muestra chica mata la conjunta antes de que su ventaja teórica aparezca.

**Valor del experimento (aunque falle):** ahora sabemos, medido, que la operacionalización 1D de
FQ es la elección correcta para el régimen live — no un atajo, una decisión validada. Y queda el
recibo por si alguien vuelve a sugerir "usa la grado-grado, es más completa": lo es, sobre 10k
puntos; sobre 64, es ruido.

## Reproducibilidad
Script `/tmp/dd_experiment.py` (autocontenido; reusa `_hvg_degrees` del repo). Datos:
`data/kl_hist_{BTC,ETH,SOL}USDT.parquet` (5m) + `cosecha_cubes/tp_cube_{...}_USDT.parquet`.
Medidas por señal en `/tmp/dd_measures.parquet`. n_trials=6 declarado; DSR de ambos gates =1.000
(confirma que el edge base existe bajo cualquiera de los dos cortes — no que dd mejore).
