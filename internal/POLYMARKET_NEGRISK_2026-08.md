# POLYMARKET — coherencia de conjunto completo (paso 4, y el cierre)

> **Veredicto: NO SOBREVIVE.** La incoherencia es real (~1.0 pp) y es MENOR que
> el coste de cobrarla (3.80 pp mediano) — que es exactamente por qué sigue ahí.
>
> Con esto se cierran los cuatro pasos. Radiografía completa del arco al final.
>
> Reproducible: `tools/polymarket_negrisk.py`, 12 tests. Muestra: 42 row groups
> de 2026, **472 observaciones sobre 395 eventos** con simultaneidad ≤15 min.

---

## El mecanismo, y por qué merecía medirse

En un evento `neg_risk` los resultados son mutuamente excluyentes y exhaustivos:
exactamente uno ocurre. Por lo tanto **ΣP(YES) = 1**. Si suma 1.05, comprar NO en
todas las patas paga 5 pp. **No hace falta modelo de nada** — es aritmética, no
pronóstico. Era el mejor candidato que quedaba tras la muerte de la
recalibración (paso 3).

**El supuesto se verificó antes de medir:** de 38,502 eventos cerrados con ≥2
patas resueltas, el **97.9% tiene exactamente un SÍ**. La mecánica es real.

---

## El resultado

```
-- CON FRESCURA <= 15 min, POR NÚMERO DE PATAS --
    patas   n obs  n evts  |dev| med    coste   net med   % net>0
        2      88      76      1.00pp    1.90pp    -0.90pp    28.4%
        3     144     121      1.00pp    2.85pp    -1.85pp    10.4%
      4-5      36      29      1.15pp    4.28pp    -3.37pp    16.7%
     6-11     179     147      2.20pp    8.95pp    -6.35pp     5.6%
      12+      25      22      1.60pp   15.69pp   -13.35pp     0.0%  << n<30

-- VEREDICTO --
  n = 472 observaciones sobre 395 eventos
  incoherencia mediana   1.00 pp
  coste mediano          3.80 pp
  NETO mediano          -2.55 pp
  rentable en           11.9% de las observaciones
  → NO SOBREVIVE
```

**El coste escala con N patas; la incoherencia no.** Ésa es toda la aritmética.
La incoherencia se queda en ~1.0-2.2 pp sin importar cuántas patas tenga el
evento, mientras el coste de tocarlas todas crece linealmente: 1.90 pp con 2
patas, 15.69 pp con 12+.

Ni siquiera el caso más barato posible sobrevive: **con 2 patas, 1.00 pp de
incoherencia contra 1.90 pp de coste.**

---

## El sobre-redondeo existe, y no se puede cobrar

Σp > 1 en el **64.8%** de los casos, con mediana **+0.90 pp**. Eso es margen de
casa real y sistemático — el equivalente al *overround* de una casa de apuestas.

**Y es menor que el coste de arbitrarlo.** Un margen persistente de +0.90 pp
frente a un coste mínimo de 1.90 pp no es una ineficiencia que nadie vio: es una
ineficiencia calibrada justo por debajo del umbral que la haría desaparecer. Esa
es la explicación económica de por qué sigue ahí después de $13.8 mil millones de
volumen, y es la respuesta a la pregunta obvia de "¿por qué nadie lo ha tomado?".

---

## Las dos trampas, cuantificadas (valen más que el veredicto)

### (a) Las patas faltantes fabrican el arbitraje

```
observaciones incompletas   28,732
desviación mediana FINGIDA  -35.00 pp   (se vieron 2 de 8 patas)
```

Si sólo ves 2 de 8 patas, Σp sale bajísimo y parece **un arbitraje del 35%**. Con
28,732 observaciones así en la muestra, cualquiera que no exija completitud
publica un hallazgo espectacular y falso.

Aquí sólo cuentan los eventos donde **todas** las patas vivas en ese instante
tienen precio. Una pata que falta **nunca se rellena**: se descarta la
observación entera, y el número fingido se imprime en el reporte para que viva
ahí y no en la memoria de nadie.

Sutileza que también es trampa: el denominador son las patas **vivas en ese
momento**, no las de hoy. Usar el conteo actual sobre un instante pasado contaría
como "faltante" una pata que todavía no existía.

### (b) La asincronía infla la desviación al doble

Un row group de `trades.parquet` abarca **~8 días**. Tomar "el último precio de
cada pata en el row group" suma la pata A del lunes con la B del jueves: eso no
es incoherencia, es desfase.

```
cap 1440 min → |dev| mediana 1.90pp   (n=11,520)
cap  240 min → 1.50pp                 (n= 3,734)
cap   60 min → 1.20pp                 (n= 1,445)
cap   15 min → 1.00pp                 (n=   472)
cap    5 min → 1.00pp                 (n=   214)
```

Converge a 1.00 pp al apretar. **Cerca de la mitad de la desviación aparente era
desfase.** Y nótese el sentido del sesgo: la medición floja es la que *favorece*
la tesis. Aun así no la salva — con cap de 24h, 1.90 pp de desviación contra
2.85 pp de coste a 3 patas sigue siendo negativo. **El veredicto aguanta incluso
con la medición sesgada a su favor**, que es la forma más robusta de matarlo.

---

## Alcance honesto

- **n=472 observaciones / 395 eventos** con simultaneidad estricta. No es enorme.
  Lo que sostiene el veredicto no es sólo la n: es que el argumento es
  **estructural** (coste ∝ N, incoherencia constante) y se confirma en los cinco
  topes de frescura, incluido el de n=11,520.
- El bucket de 12+ patas sale marcado `n<30` y **no concluye** por sí solo.
- El coste asume 0.95 pp de media horquilla por pata (paso 2) y **no modela
  impacto**: al tomar tamaño en las patas ilíquidas de un evento de 11, la
  horquilla efectiva sube. El número real es peor que éste, no mejor.
- No se modela el riesgo de ejecución parcial: si te llenan 7 de 11 patas, no
  tienes un arbitraje, tienes una posición direccional. Eso empeora el caso.

---

## El arco completo: cuatro pasos, cuatro números

| paso | pregunta | veredicto |
|---|---|---|
| 1 · oferta | ¿hay mercados capturables? | **SÍ** — 32,085 en 2026, $13.8B, h mediano 1.44d |
| 2 · horquilla | ¿el coste se come el edge? | **NO** — 1.90 pp adversos vs 4 pp de breakeven, margen 2.1x |
| 3 · Brier | ¿le ganamos al precio? | **NO** — advantage −0.0043 OOS, el mercado gana |
| 4 · neg_risk | ¿hay arb mecánico sin modelo? | **NO** — 1.00 pp de incoherencia vs 3.80 pp de coste |

**El venue es bueno y no tenemos nada que venderle.** El coste de operar en
Polymarket es genuinamente favorable comparado con los perps —ésa fue una
sorpresa real y está medida— pero las dos vías de edge que no requieren ser más
listo que el mercado están ambas muertas, y la vía de serlo más listo ya tenía
dos mediciones en contra (ésta y `marea/vault/MODEL.md`, 3.29 pp contra vara de 2).

---

## Lo único que queda, y por qué NO se persigue ahora

**Latencia de la fuente de resolución**: leer un feed público (marcador, METAR,
umbral de precio) antes de que el mercado repreecie. Es distinto en especie —no
va de pronosticar mejor sino de llegar antes— y encaja con la forma de este repo
(colectores no-críticos, invariante de frescura).

**Pero rompe la disciplina que hizo baratos los cuatro pasos anteriores.** Cada
uno se contestó con datos que ya estaban en disco, en horas de cómputo. La
latencia **no se puede medir con historia**: exige construir el sistema en vivo
para probar si el sistema en vivo funciona. Eso es precisamente el patrón que la
constitución evita — invertir antes de medir.

**Condición de desbloqueo** (formato E6): existe evidencia pública y verificable
de que el desfase entre la publicación de una fuente de resolución concreta y la
repreciación del mercado supera **1.90 pp** de forma consistente y medible con
datos históricos. Sin eso, no se abre.

---

_Herramienta: `tools/polymarket_negrisk.py`. Tests: 12, con las dos trampas
reconstruidas en sintético y la aritmética coste∝N fijada. Suite completa verde
(1342 passed). Medido 2026-08-17. Cero capital, cero código en el path del motor._
