# POLYMARKET — la horquilla (paso 2, agosto 2026)

> Cierra la pregunta que `POLYMARKET_OFERTA_2026-08.md` dejó abierta: **el coste
> de ejecución, ¿se come el edge como en los perps?**
>
> Respuesta: **no.** Y esa es toda la noticia — no hay ningún edge medido todavía.
>
> Reproducible: `tools/polymarket_spread.py`, 19 tests en
> `tests/test_polymarket_spread.py`. Muestra: 14.68 M trades de `trades.parquet`
> (1,028 M filas / 37.5 GB), leídos **por rangos HTTP sin bajar el archivo**,
> en 14 row groups estratificados por mes de 2026.

---

## El problema de método: no hay libro

Ni `trades.parquet` ni `quant.parquet` traen bid/ask. Son ejecuciones, no
cotizaciones. **La horquilla cotizada no se puede medir con este dataset** y
decir lo contrario sería inventar.

Lo que sí se mide es la horquilla **efectiva**: la que pagó quien cruzó. Para un
taker es la magnitud relevante — es su coste real, no una cotización que quizá
nunca tocó. Dos estimadores independientes, a propósito:

| | usa dirección | supuesto | resultado (vol≥100k, h≤7d) |
|---|---|---|---|
| **Rebote comprador-vendedor** | sí | deriva media-cero | **1.13 pp** |
| **Roll (1984) crudo** | no | signo del taker **iid** | 1.57 pp |
| **Roll corregido por ρ** | no | ρ medida | **1.90 pp** |

El veredicto usa **1.90 pp**, el más adverso. Tomar el más favorable sería elegir
el estimador por su resultado — la selección por resultado que este repo tiene
prohibida, cableada en `verdict()` y fijada por test.

---

## El sesgo de Roll, medido en vez de supuesto

Roll asume que el signo del taker es iid. **En Polymarket no lo es: ρ₁ = +0.295,
ρ₂ = +0.270** (estable entre +0.246 y +0.310 en todos los cortes). Con
`p_t = m_t + (s/2)·q_t` y `q` autocorrelado:

```
−cov = (s²/4)·(1 + ρ₂ − 2ρ₁)   ⇒   s = roll_crudo / √(1 + ρ₂ − 2ρ₁)
```

Factor medido: **0.825**. Roll crudo se queda ~18% corto, y por eso 1.57 → 1.90.

Nota importante para no ilusionarse: **ρ₁>0 es order-splitting — la misma firma
que este repo validó como F2** (`CEMENTERIO.md`: autocorrelación positiva del
signo por ejecución fraccionada, Bouchaud-Farmer-Lillo 2008). Aquí aparece como
**sesgo de un estimador, y solo se corrige.** No se toca como señal: F2 es
símbolo-específico incluso dentro de cripto (paga en 4/6, negativo en ETH), y un
venue nuevo no hereda nada. Anotarlo es honestidad, no un lead.

---

## Resultado 1 — la horquilla no mata el edge supuesto

Corte de referencia (vol ≥$100k, h ≤7d, 2026), edge supuesto de 2 pp:

```
horquilla adversa      1.90 pp
breakeven (edge 2pp)   4.00 pp
edge neto             +1.05 pp    (se cruza UNA vez: se aguanta a resolución)
→ SOBREVIVE, margen 2.1x
```

**El contraste con el motor de perps es el punto entero.** Allí el cube dice
+0.224R bruto y el motor con fees −0.510R neto: el coste no muerde el edge, se lo
come entero y sigue con hambre (brecha E8). Aquí el coste se lleva **la mitad**
de un edge de 2 pp y deja la otra mitad. Es una estructura de coste distinta, y
esa diferencia es la única razón por la que esta línea merecía medirse.

---

## Resultado 2 — la horquilla ataca justo donde el paso 1 veía el mejor retorno

El paso 1, mirando solo la oferta, señalaba el corte de ≤1d: 494 vueltas al año,
el retorno anualizado más alto de la tabla. **La horquilla ahí es el doble.**

| corte 2026 | n | vueltas | horquilla adversa | breakeven edge | edge neto @2pp | **margen** | ret. anual NETO | capital pico |
|---|---|---|---|---|---|---|---|---|
| ≤ 1d | 11,513 | 494x | **3.29 pp** | 1.65 pp | +0.35 pp | **1.2x** | 350% | $0.2M |
| ≤ 7d | 32,085 | 113x | 1.90 pp | 0.95 pp | +1.05 pp | **2.1x** | 237% | $4.5M |
| ≤ 30d | 46,742 | 47x | 1.74 pp | 0.87 pp | +1.13 pp | **2.3x** | 106% | $17.5M |

El corte de ≤1d tiene **el retorno más alto y el margen más frágil**: 1.2x sobre
breakeven. Un error modesto en la estimación del edge lo borra. Y además es donde
menos capital cabe ($0.2M).

> **La optimización ingenua —maximizar vueltas— elige la esquina frágil.** El
> corte de ≤7d y ≤30d es donde esto vive: menos retorno de titular, el doble de
> margen y dos órdenes de magnitud más de capacidad.

---

## Resultado 3 — la horquilla es estable donde importa

Gradiente por tamaño de mercado (rebote / Roll corregido, h≤7d):

```
vol >=  10k    1.20pp / 2.14pp     n=2,932
vol >= 100k    1.13pp / 1.90pp     n=1,037
vol >=   1M    0.99pp / 1.42pp     n=  124
```

Y por nivel de precio (vol≥100k, h≤7d, rebote):

```
p<=0.05      0.55pp      p 0.35-0.65   1.02pp
p 0.05-0.15  1.03pp      p 0.65-0.85   1.08pp
p 0.15-0.35  1.13pp      p 0.85-0.95   1.02pp
                         p>0.95        0.57pp
```

Plano entre 0.05 y 0.95 (~1.0-1.13 pp) y **más barato en las colas** (~0.55 pp),
donde el tick es más fino. No hay una zona de precio que haya que evitar por
coste. Que sea plano importa: significa que el veredicto no depende de haber
elegido bien el bucket.

---

## Lo que este número NO es (leer antes de citarlo)

1. **Es cota INFERIOR.** La horquilla efectiva está condicionada a que hubo
   trade. Los momentos en que el libro se abre y nadie cruza no entran en la
   muestra. Sirve para MATAR la tesis (si ya fuera alta, muerta) y no para
   bendecirla.
2. **No hay impacto de mercado.** Al tomar tamaño, la horquilla efectiva sube.
   `capacity_analysis.py` es el marco para eso y no se ha corrido aquí.
3. **El edge sigue siendo un supuesto.** Esto mide el COSTE. No se midió ninguna
   señal, no se corrió el gate, y no hay nada que gatear todavía.
4. **La corrección de Roll es un modelo.** Si el modelo `p = m + (s/2)q` no
   describe bien estas series, el 1.90 se mueve. El rebote (1.13), que no depende
   de ese modelo, es la referencia baja del rango.

---

## Corrección honesta de la versión anterior

El encabezado inicial de `polymarket_spread.py` afirmaba que sin colapsar los
fills por `transaction_hash` el rebote se sesgaba hacia cero, "casi la mitad de
los pares no son pares". **Es falso y está medido: el efecto del colapso sobre el
rebote es −0.0%.** Los fills consecutivos de una misma orden comparten lado, y el
estimador solo usa pares donde el lado cambia — ya quedaban fuera solos.

El colapso se mantiene porque el precio que pagó el taker es el VWAP de su orden,
no el de su último fill. Pero es una decisión de definición, no un arreglo de
sesgo. El test `test_el_colapso_NO_cambia_el_rebote_y_asi_debe_ser` fija la
verdad medida, no la cómoda.

---

## Veredicto y qué sigue

**El venue es viable. La señal no existe.**

El coste de ejecución de Polymarket deja vivo un edge de 2 pp con margen 2.1x en
el corte de ≤7d. Eso es lo contrario de lo que pasa en el motor de perps, y
responde la pregunta que abrió esta línea.

Pero todo cuelga de un edge supuesto que **nadie ha medido**, y el único intento
propio que sí está medido salió mal: `marea/vault/MODEL.md` reporta 17,430
predicciones fuera de muestra con **error 3.29 pp contra una vara de 2 pp**. Para
tener 1 pp de ventaja sobre el precio del venue habría que estar
sustancialmente mejor calibrado que él, y la única vez que lo medimos, no lo
estábamos. (Comparación direccional, no aritmética: ese 3.29 pp es error de
calibración, no ventaja sobre el mercado.)

Eso cambia la naturaleza del problema, no lo resuelve. En perps el problema es
*el coste se come el edge*; aquí es *falta el edge*. El siguiente paso honesto no
es operar: es **medir Brier advantage contra el precio del venue** sobre alguna
familia de preguntas concreta, y pasarlo por el gate (DSR/CPCV/PBO) como
cualquier otra cosa. Si no hay ventaja de calibración demostrada, no hay negocio,
por barata que sea la horquilla.

---

_Herramientas: `tools/polymarket_spread.py` (paso 2), `tools/polymarket_supply.py`
(paso 1). Tests: 19 + 13. Suite completa verde (1322 passed / 6 skipped / 60s).
Medido 2026-08-17. Cero capital, cero código en el path del motor._
