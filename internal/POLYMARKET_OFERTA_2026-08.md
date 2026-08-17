# POLYMARKET — la oferta capturable (agosto 2026)

> Sondeo measure-first del paso 1 de 2. Contesta **cuánta oferta hay**, no si hay
> edge. Reproducible: `tools/polymarket_supply.py`, tests en
> `tests/test_polymarket_supply.py`. Data: `markets.parquet` (281 MB) del dataset
> [SII-WANGZJ/Polymarket_data](https://huggingface.co/datasets/SII-WANGZJ/Polymarket_data),
> 1,841,683 mercados, 2020-10-02 → 2026-07-20.
>
> **Nada de aquí autoriza operar.** El gate (DSR>0.95 / CPCV / PBO) no se ha
> corrido sobre nada de Polymarket porque todavía no hay ninguna señal que
> gatear. Esto mide el TAMAÑO DE LA CANCHA, no si sabemos jugar.

---

## Por qué se midió esto y no otra cosa

Llegó una lista de 10 repos de Polymarket ("hay que hacer feria"). Ocho son
deuda o trampa (ver `MEMORY/CEMENTERIO.md`, entrada *Lista de 10 repos*). De los
dos que sirven, el dataset es el único activo real, y su valor **no** es una
estrategia: es que permite contestar barato la única pregunta que puede matar la
línea entera antes de gastar en ella.

La pregunta se eligió por el mismo criterio que ordena E7/E8 en el
`BRIEF_INSTRUMENTO_2026-08.md`: *los diagnósticos que pueden invalidar el resto
van primero, porque cuestan poco y ahorran meses.*

---

## La aritmética que gobierna el venue

Compras N acciones a precio `p`; cada una paga $1 si resuelve Sí. Con edge `e`
en puntos de probabilidad:

```
capital desplegado          = N·p
ganancia esperada           = N·e
retorno sobre capital       = e/p          <- NO depende del tamaño
retorno ANUALIZADO          = (e/p)·(365/h_pond)
capital pico                = q·Σ(V·h)/365
```

`h_pond = Σ(V·h)/ΣV` es el horizonte **ponderado por volumen**: el capital se
reparte proporcional al tamaño del mercado, así que la mediana mentiría a favor
de los mercados dust (y en este dataset el 50% de los mercados tiene volumen
mediano de **$102.76**).

**La participación `q` se cancela del retorno.** Solo fija la escala — cuánto
capital cabe, no cuánto rinde. Por eso `h_pond` es el número que decide.

Y de ahí sale la diferencia estructural con el motor de perps:

| | perps (fq-bot) | Polymarket |
|---|---|---|
| Cruces de horquilla | 2 (entrada + salida) | **1** (se aguanta a resolución) |
| Fee | maker/taker por lado | 0 |
| Coste dominante | fees + slippage + fill | **horquilla, una sola vez** |
| Coste oculto | — | **capital inmovilizado `h` días** |
| Breakeven | WR de equilibrio 36.9% | **e > spread/2** |

---

## Resultado 1 — la oferta existe, y es grande

Corte de referencia: **volumen ≥ $100k, horizonte ≤ 7d, edge supuesto 2pp,
precio medio 0.5, participación 2%.**

```
   año         n       volumen    h_pond  vueltas/año   capital pico  ret. anual
  2024       851         425M     4.48d          81x          0.1M     325.6%
  2025    11,948       4,753M     4.39d          83x          1.1M     332.4%
  2026    32,085      13,848M     3.24d         113x          4.5M     450.6%
```

(2020-2023 salen con n<30 y quedan marcados como no-concluyentes: el venue casi
no existía.)

**32,085 mercados en 7 meses de 2026, con $13.8 mil millones de volumen.** Mi
estimación previa —"trescientos mercados al año", y capital bloqueado meses— era
**falsa por tres órdenes de magnitud**. La corrige el dato, no una opinión.

---

## Resultado 2 — el mercado se volvió de corto plazo (y eso lo cambia todo)

Volumen en millones de USD, por año de creación × horizonte:

```
 año     <=1d     1-7d   7-30d  30-90d     >90d
2024     59.1    501.0  1085.8  2653.3  14709.8     <- la elección de EE.UU.
2025    740.0   5939.2  6192.6  3022.3  19329.9
2026   4139.3  13603.2  9933.2  5916.7   1562.4     <- se invirtió
```

En 2024 el volumen vivía en `>90d` (mercados electorales). En 2026 vive en
`≤7d`. **El horizonte mediano de todo el dataset es 1.44 días.**

Consecuencia directa: *la objeción del capital inmovilizado, que era mi
argumento más fuerte contra esta línea, se disuelve.* No es un venue de apostar
a la elección y esperar un año; hoy es un venue de horas y días.

**Ojo con este cuadro (sesgo conocido):** `volume` es acumulado-a-la-fecha. Un
mercado largo creado hace poco todavía no acumuló su volumen, así que los cortes
de horizonte largo salen **sub-contados** en el año más reciente. El giro
2024→2026 es real (lo confirman los conteos, no solo el volumen), pero la
magnitud del `>90d` de 2026 está deprimida por censura, no solo por desinterés.

---

## Resultado 3 — capacidad y retorno se pelean entre sí

El eje de horizonte es un trade-off, no un dial que se sube. Año 2026:

| corte | n | h_pond | vueltas/año | **capital pico** | ret. anual (2pp bruto) |
|---|---|---|---|---|---|
| ≤ 1d | 11,513 | 0.74d | 494x | **$0.2M** | 1975% |
| ≤ 7d | 32,085 | 3.24d | 113x | **$4.5M** | 451% |
| ≤ 30d | 46,742 | 7.76d | 47x | **$17.5M** | 188% |
| ≤ 90d | 49,906 | 17.04d | 21x | **$48.2M** | 86% |

Los retornos de tres y cuatro cifras **no son un hallazgo, son la aritmética de
`365/h_pond` con un edge inventado por parámetro.** Lo que sí es hallazgo es la
forma de la curva: donde el retorno es espectacular, el capital que cabe es
ridículo ($200k), y donde cabe capital serio ($48M) el retorno vuelve a ser
terrenal. Esa tensión es la restricción real de diseño de cualquier estrategia
aquí, y no aparece en ninguno de los 10 repos de la lista.

---

## Resultado 4 — la horquilla es el único juez, y NO está medida

Con edge supuesto de 2pp, el breakeven es **spread ≥ 4pp**: cualquier horquilla
media por encima de eso deja el retorno en cero o negativo, en todos los años y
en todos los cortes.

Y la palanca funciona en los dos sentidos: **las mismas ~113 vueltas al año que
hacen atractivo un edge de 2pp convierten un spread de 4pp en ruina.** El
apalancamiento temporal no distingue entre edge y coste.

Esto es exactamente la brecha E8 del brief, en su versión Polymarket: el cube
decía +0.224R bruto y el motor con fees −0.510R neto. Aquí todavía no sabemos
cuál es el número neto porque **`markets.parquet` no trae libro**. El spread
está en `trades.parquet` (32 GB) y `quant.parquet` (21 GB) del mismo dataset.

> **El sondeo de oferta salió a favor. El veredicto sigue abierto, y depende de
> un número que aún no medimos.** Presentar el 451% como resultado sería
> exactamente el pecado de agosto con otro disfraz.

---

## Higiene del dato (lo que está roto, contado)

```
filas                       1,841,683
horizonte <= 0 (EXCLUIDAS)     25,439  (1.38%)  end_date antes de created_at
volumen == 0                  665,635  (36.1%)  más de un tercio son mercados muertos
preguntas duplicadas          341,321  (18.5%)  plantillas que se reponen
COLUMNAS CONSTANTES:
  · active   = 1 en las 1,841,683 filas
  · archived = 0 en las 1,841,683 filas
```

`active` y `archived` **no son features: son columnas.** Es la lección
`vp_basis` repitiéndose en un dataset ajeno. Cualquier filtro que las use cree
estar filtrando y no filtra nada. El detector vive en
`polymarket_supply.constant_columns` y las carga **a propósito** aunque ningún
cálculo las use — un detector de columnas muertas que solo mira las columnas que
ya usas no detecta nada.

Las 25,439 filas de horizonte imposible se **excluyen y se cuentan**; el reporte
las imprime encima de cualquier número, por invariante, no por acordarse.

---

## Lo que este sondeo NO dice

- **No dice que haya edge.** No se midió ninguna señal. `e` entra por parámetro.
- **No dice que el edge de cripto transfiera.** El repo ya vivió que no
  transfiere: POC-distance PBO 0.76 en TradFi, KL solo en NQ y del lado
  contrario. `CEMENTERIO.md` es explícito — *el bot es cripto-específico*. Un
  venue nuevo empieza en cero, no hereda.
- **No dice que la capacidad sea alcanzable.** El capital pico asume 2% de
  participación sin impacto. En mercados con volumen mediano de $102 eso es
  optimista, y `capacity_analysis.py` ya existe para modelar justamente eso.
- **No mide el spread**, que es el único coste que importa aquí.

---

## Paso 2, si se decide seguir

Medir la horquilla sobre el corte que salió vivo (vol ≥ $100k, h ≤ 7d, 2026:
n=32,085) con `quant.parquet`. Tres números y se cierra el veredicto:

1. **Horquilla media ponderada por volumen** en ese corte. Si supera 4pp, la
   línea muere aquí y va al cementerio con su n.
2. **Cuánto del volumen está a menos de X pp de horquilla** — si el edge vive
   solo en el 3% más líquido, ese 3% *es* la estrategia y el resto es ruido caro
   (mismo razonamiento que E8).
3. **Brier advantage contra el precio del venue**, que es la vara correcta para
   mercados de predicción: mide si nuestra probabilidad le gana a la del
   mercado. Es la única idea que vale la pena robar del repo #2 de la lista
   (`evan-kolberg/prediction-market-backtesting`) — la idea, no el código:
   meterse NautilusTrader sería reemplazar `validation_gate.py` + `deflated.py`
   + `bt_walkforward` por un motor ajeno.

Y un prior que ya es nuestro y ahorra trabajo: `marea/vault/MODEL.md` midió un
modelo propio de probabilidad contra preguntas de precio con umbral —
walk-forward de 5 pliegues, **17,430 predicciones fuera de muestra, error 3.29 pp
contra una vara de 2 pp: NO PASA**. O sea: para las preguntas de precio de
cripto, que son justo donde este repo tendría ventaja natural, **ya sabemos que
nuestra probabilidad no le gana al venue con el modelo lognormal**. El paso 2 no
debe empezar por ahí.

---

_Herramienta: `tools/polymarket_supply.py`. Tests: `tests/test_polymarket_supply.py`
(13, fijan las 4 lecciones: desglose obligatorio, n<30 marcada, exclusión contada,
columna constante delatada + el neteo de horquilla). Suite completa verde
(1303 passed / 6 skipped / 36.9s) antes del commit. Medido 2026-08-17._
