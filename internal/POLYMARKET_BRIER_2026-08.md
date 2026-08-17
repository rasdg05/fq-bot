# POLYMARKET — Brier advantage (paso 3, agosto 2026)

> **Veredicto: NO le ganamos al precio de Polymarket. La recalibración muere.**
>
> Los pasos 1 y 2 midieron el coste y salieron a favor: hay oferta (32,085
> mercados) y la horquilla no la mata (1.90pp adversos vs 4pp de breakeven).
> Todo colgaba de un edge de 2pp **supuesto**. Esto lo atacó de frente y no está.
>
> Reproducible: `tools/polymarket_brier.py`, 14 tests. Muestra: 56 row groups
> estratificados de 2026, **6,561 MERCADOS** con resolución limpia y vol ≥$100k.

---

## El resultado

```
-- EL MERCADO CONTRA SÍ MISMO (una observación por MERCADO) --
      lead   n mkts    Brier    skill     sesgo
       ~1h    3,565   0.1769   +0.287    +0.35pp
       ~6h    4,008   0.1994   +0.196    +0.69pp
      ~24h    6,561   0.1843   +0.243    +0.62pp

-- ¿UNA RECALIBRACIÓN LE GANA? (walk-forward, n_oos=5,249 mercados) --
  Brier del MERCADO      0.1777
  Brier del MODELO       0.1820
  Brier advantage        -0.0043   → el MERCADO gana

  edge realizado         +0.29 pp  ± 0.58 (1 EE)
  breakeven (paso 2)      0.95 pp
  IC95% del edge         [-0.85, +1.44] pp
  → NO supera el breakeven
```

Tres lecturas, en orden de importancia:

1. **El modelo pierde fuera de muestra.** Brier advantage **negativo**: la
   recalibración es *peor* que el precio crudo. No es que gane poco — pierde.
2. **El edge realizado no llega al breakeven.** +0.29 pp contra 0.95 pp que hay
   que pagar de horquilla. Y su IC95% cruza el cero: ni siquiera es distinto de
   nada, con n=5,249 mercados.
3. **El mercado tiene skill real.** +0.24 a +0.29 sobre la tasa base. No es una
   multitud desinformada esperando que la desplumen.

---

## La calibración: un patrón que NO sobrevive

Con una observación por mercado a ~24h (n=6,561):

| precio | n mkts | frecuencia real | sesgo |
|---|---|---|---|
| 0.00–0.02 | 666 | 0.0150 | **+0.99 pp** |
| 0.02–0.05 | 242 | 0.0413 | +0.74 pp |
| 0.05–0.10 | 320 | 0.0906 | +1.57 pp |
| 0.10–0.20 | 427 | 0.1827 | +3.10 pp |
| 0.20–0.35 | 689 | 0.3149 | +3.27 pp |
| 0.35–0.50 | 1,837 | 0.4774 | +1.19 pp |
| 0.50–0.65 | 1,470 | 0.5415 | −0.47 pp |
| 0.65–0.80 | 446 | 0.6973 | −2.52 pp |
| 0.80–0.90 | 147 | 0.8163 | −3.87 pp |
| 0.90–0.95 | 83 | 0.9398 | +0.94 pp |
| 0.95–0.98 | **60** | 0.8667 | **−10.21 pp** |
| 0.98–1.00 | 174 | 0.9885 | −0.65 pp |

Se ve un patrón: los precios bajos salen **infra**valorados y los altos
**sobre**valorados. Es el *inverso* del clásico favorite-longshot bias de las
casas de apuestas, lo cual ya debería dar desconfianza.

**Y el walk-forward dice que no se puede cobrar.** Un mapa ajustado sobre ese
patrón con datos anteriores **pierde** aplicado a datos posteriores. Es
estructura en muestra que no se replica.

El bucket 0.95–0.98 con **−10.21 pp sobre n=60** es el ejemplo perfecto de lo que
este repo tiene prohibido leer como hallazgo: el número más grande de la tabla
vive en la celda con menos muestra. Es el +1.47R de n=17 otra vez.

---

## El artefacto que casi me como

La **primera** medición ponderó por TRADE y encontró esto:

```
(0.35, 0.5]     973,273 trades   sesgo -4.11 pp
(0.5, 0.65]     870,272 trades   sesgo -4.11 pp
(0.65, 0.8]     569,144 trades   sesgo -5.12 pp
```

Un sesgo de 4-5 pp, monótono, en el tramo más líquido, sobre millones de trades.
Contra un breakeven de 0.95 pp habría sido el hallazgo del año.

**Era un artefacto de la unidad de observación.** Un mercado que va de 0.60 a 0
genera enorme volumen *en la caída*, así que ponderar por trade sobre-muestrea el
camino "estaba caro y resolvió NO". Con una observación por mercado:

| medición | sesgo global |
|---|---|
| ponderado por **trade** | **−2.25 pp** (y −4/−5 pp en el medio) |
| por **mercado**, a 24h | −1.35 pp (buckets con signos alternos) |
| por **mercado**, a 1h | **+0.22 pp** — cero |

Lo cazó la regla de la casa: *una métrica demasiado limpia es un bug antes que un
hallazgo*. Un sesgo de 4 pp en la parte más líquida de un mercado de $13.8 mil
millones sería dinero gratis, y alguien ya lo habría tomado.

La lección queda cableada, no anotada: la unidad de observación es el **mercado**,
y `test_ponderar_por_trade_fabrica_un_sesgo_que_por_mercado_NO_existe` reconstruye
el artefacto en sintético y exige que los dos sesgos salgan de **signo contrario**.
Si alguien revierte a "usa todos los trades", falla en rojo.

---

## La otra trampa: el 0.50 no es un desenlace

De **1,777,818** mercados "cerrados", **327,496 tienen precio final exactamente
0.50** — no es una resolución, es el valor por defecto de "sin información"
(anulado, sin liquidar, o metadata vieja). Solo el **72.4%** resuelve limpio.
Usar el resto como outcome envenena el Brier entero.

Descartados y contados: 490,692.

---

## Qué mata esto exactamente, y qué NO

**MUERE: la recalibración como edge.** La idea de que Polymarket tiene un sesgo
de calibración sistemático y explotable, que se cobra mecánicamente sin
información externa, **está medida y no existe**. No se re-propone.

**NO muere: un edge de información externa.** Esto probó *una familia* de modelo
— mapas `p_modelo = f(p_mercado)`, que por construcción no usan nada de fuera del
propio precio. Un edge que venga de leer una fuente pública antes de que el
mercado repreecie, o de coherencia entre mercados de un mismo evento, no pasa por
esta prueba y sigue sin medir.

Honestidad sobre el alcance: se probó un mapa de 8 bins ajustado walk-forward. La
apuesta implícita es que si 8 parámetros no le ganan al mercado fuera de muestra,
800 tampoco lo harán por buenas razones. Es defendible y es una apuesta, no un
teorema.

---

## Lo que queda vivo, en orden

1. **Coherencia de conjunto completo (`neg_risk`).** Los resultados mutuamente
   excluyentes de un evento deben sumar 1. Cuando suman 1.05 hay un arb mecánico
   **sin modelo**. El 17.8% de los mercados lleva el flag y ya está en los datos
   bajados. Advertencia previa: dinero tan obvio suele estar comido por latencia
   y gas — la medición dirá si queda residuo.
2. **Latencia de la fuente de resolución.** Un feed público se actualiza antes de
   que el mercado repreecie. No hace falta mejor modelo, hace falta leer más
   rápido. Es la forma que este repo ya tiene (colectores no-críticos, invariante
   de frescura).
3. **NO hacer:** un mejor modelo de probabilidad para preguntas macro o
   políticas. Es competirle al mercado en su cancha, y ya hay dos mediciones en
   contra: ésta (Brier advantage negativo) y `marea/vault/MODEL.md` (3.29 pp
   contra una vara de 2 pp).

---

_Herramienta: `tools/polymarket_brier.py`. Tests: 14, incluidos el que reconstruye
el artefacto de ponderación y la guarda anti-fuga (sobre ruido puro la
recalibración no puede ganar OOS). Suite completa verde (1336 passed / 6 skipped).
Medido 2026-08-17. Cero capital, cero código en el path del motor._
