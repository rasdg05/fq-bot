# V5 — ¿El techo son $22k o son millones? EJECUTADO (2026-08-10)

> Encargo: `internal/BRIEF_CAPACIDAD_ANCHA_2026-08.md`, pre-registrado el
> 2026-08-09. Ejecutado tal como estaba escrito. Rejilla, hipótesis y `n_trials`
> sin tocar; la única corrección a la pre-registración está en §2 y va **por
> escrito y contando de nuevo**, como el propio brief exige.
>
> Reproducir:
> ```
> python tools/geometry_sweep.py --exits            # PUERTA 3 (pool de 13)
> python tools/capacity_analysis.py --ancha         # V5 sobre el VIP
> python tools/capacity_analysis.py --ancha --pool  # V5 sobre el pool de 13
> ```

---

## Veredicto en una línea

**El techo de $22k era de la GEOMETRÍA — eso queda confirmado y medido (70–200x).
Y no sirve de nada: sobre el pool entero el edge de la celda ancha se muere al
tamaño antes de llegar a ninguna parte, y ni un solo capital de la rejilla
sostiene una cuenta.** Es el **desenlace 2** de los cuatro que el brief
declaraba legítimos: *hay capacidad pero el edge muere al tamaño → la capacidad
nunca fue el cuello de botella. Cierra la línea y ahorra meses.*

| hipótesis | criterio pre-registrado | resultado |
|---|---|---|
| **H1** capacidad ancha ≥ 10x la de tp4/h288 | ratio ≥ 10 | **SÍ** — ETH 203x · AVAX 171x · BCH 73x |
| **H2** neto > 0 con impacto a $250k | E[R] > 0 | **por la letra sí, +0.0150R; el IC95% [−0.0066, +0.0357] cruza cero** |
| **H3** las tres a la vez (neto>0 + cartera + DSR) | todas | **NO — ningún capital** |

---

## 0. PUERTA 3 primero — el confundido del subconjunto, CERRADO

El brief lo puso como condición previa: *"Hacerlo ANTES de creerse cualquier
resultado de aquí."* Se bajaron las velas 5m de los 10 símbolos que faltaban
(ADA AVAX BCH BNB DOGE DOT LINK LTC TRX XRP) y se re-corrió el eje de salida
sobre el **pool entero**, con la misma celda pre-fijada y el mismo `n_trials=6`.

Los 13 símbolos pasan el gate de venue (corr MFE 0.995–1.000).

| | VIP (3 símbolos, n=3.565) | POOL (13 símbolos, n=12.941) |
|---|---|---|
| control, NETO | +0.1087 | **+0.0608** |
| control, brecha (−IC_lo) | −0.0368 | **−0.0246** |
| control, DD @ f viva | 30.6% | **75.6%** |
| A trail k=0.50, NETO | +0.0950 | **+0.0501** |
| A trail k=0.50, brecha | −0.0531 | **−0.0286** |
| A trail k=0.50, DD @ f viva | 11.1% | **34.2%** |
| A trail k=0.50, DSR (6 / 504) | 0.986 / 0.366 | **0.994 / 0.607** |

**La respuesta se parte en dos, y las dos mitades importan:**

1. **El CRUCE no era del subconjunto.** El control sigue cruzando sobre los 13
   (brecha −0.0246), y con 3.6x más muestra el DSR paranoico **sube** (0.366 →
   0.607) en vez de caerse. Restringir a 3 símbolos inflaba el NIVEL (el neto
   casi se dobla: +0.0950 vs +0.0501), pero no fabricaba el signo.
2. **El DRAWDOWN sí lo era, y es lo que se estaba citando.** El "la concurrencia
   ya se arregló (DD 30.6% → 11.1%)" del brief es una cifra de 3 símbolos. Sobre
   los 13 el control lleva **75.6%** y el trailing **34.2%** — justo en el borde
   de la cota del 35%. La frase del brief *"una ya está arreglada"* no se
   sostiene sobre el universo entero.

Además la mejor regla **rota** con el universo: sobre el VIP era `k=0.50`
(cierra +0.0163 de brecha); sobre el pool es `k=0.67` y cierra solo +0.0044. La
elección de `k` era del subconjunto. Se mantiene `k=0.50` en V5 porque es la que
el brief pre-fijó — cambiarla a posteriori sería reescribir la pre-registración.

**Ninguna regla sobrevive a contar los trials de verdad**, ni sobre el pool
(máx. 0.607 < 0.95).

**Invariante cableada:** `geometry_sweep.veredicto_exits` recibe ahora el número
de símbolos medidos y **cambia de aviso**: sobre un subconjunto dice que el
confundido sigue abierto y cómo cerrarlo; sobre el pool dice que está cerrado y
que lo que era artefacto es el DD. Un aviso que se imprime igual habiendo medido
que sin medir es ruido, no una guardia (`tests/test_geometry_sweep.py`).

---

## 1. La ley `capacidad ∝ stop_frac³` — CONFIRMADA en el exponente, 7x
   optimista en el ancla

La derivación del brief es correcta y ahora está fijada por un test
(`test_la_capacidad_va_con_el_cubo_del_stop`): despejando el capital de la ley
que `capacity_analysis` ya implementaba,

```
C = B²·1e8 · sf³ · V / (4·coef² · f)      →     C ∝ stop_frac³
```

Doblar el stop da 8x, quintuplicarlo 125x, exacto. **Pero la tabla de dólares
del brief no es reproducible con la liquidez que dice usar.** Sus $73.547 para
ETH salen únicamente con **σ = 20.3 bps (que es la de BTC, no la de ETH)** y con
**Y = 0.5** en vez del Y=1.0 que el repo publica como referencia:

| entrada | capital a 0.02R de impacto (ETH, kSL=1, f=0.25%) |
|---|---|
| brief literal (σ 20.3bps, Y=0.5) | **$73.547** ← la cifra publicada |
| σ MEDIDA de ETH (26.5bps), Y=0.5 | $40.698 |
| σ MEDIDA de ETH (26.5bps), **Y=1.0** | **$10.174** |
| σ MEDIDA de ETH (26.5bps), Y=1.5 | $4.522 |

El **exponente** aguanta; el **ancla absoluta estaba 7.2x arriba**. Los ratios
(8x / 125x / 512x) no se ven afectados porque son puro `stop_frac³`.

---

## 2. Corrección de la pre-registración, por escrito

El brief escribe **H1 como "≥ $220k"**, que son 10x el $22k de V3. Ese $22k está
medido a `risk_frac = 1%` (el default de `--vip`), y **la cuenta viva arriesga
0.25%**. Como `C ∝ 1/f`, el mismo sistema mide $88k a la `f` viva: el umbral
absoluto describe la convención con la que se escribió, no el sistema.

Peor: la primera corrida de V5 restaba impacto a f=1% y dejaba a `screen_cell`
buscar entre cuatro fracciones — o sea filas marcadas "cartera ok" cuyo drawdown
salía de una `f` a la que ese impacto no corresponde. **Es exactamente la
enfermedad que V4 cableó** (`GovernorConfig` ← `growth.configured_risk_frac`:
una sola `f`).

→ El experimento corre entero a la **`f` viva**, `screen_cell` se evalúa a **esa
misma `f`**, y **H1 se juzga por RATIO**, que es lo que la hipótesis dice de
verdad y lo único invariante a `f`. **`n_trials` no cambia: sigue siendo 6 y el
eje sigue siendo uno.** Fijado por `test_el_barrido_usa_UNA_sola_f` y
`test_la_capacidad_no_depende_de_f_pero_el_absoluto_si`.

Segunda trampa encontrada al correr, y no borrada: el "techo del conjunto" **no
es** el $22k de V3. Aquél es el C0 de **ETH**; el techo del conjunto que V3
imprimió fue `<$1k`, porque BTC salía a +0.0027R y su C0 cae en el suelo de la
rejilla. Dividir por ese suelo producía un ratio de **12.634x** en la primera
corrida. Ahora H1 se evalúa **símbolo a símbolo** y un símbolo sin neto
apreciable sale marcado `n/e`, no enorme (`test_el_ratio_contra_un_suelo_no_se_publica`).

---

## 3. H1 — la capacidad, símbolo a símbolo (pool, f=0.25%, Y=1.0)

Sólo hay ratio donde **las dos** celdas tienen neto apreciable.

| símbolo | neto tp4 | C0 tp4 | neto ancha | C0 ancha | ratio |
|---|---|---|---|---|---|
| **ETH** | +0.0586 | $86k | +0.0749 | **$17.5M** | **203x** |
| **AVAX** | +0.1453 | $28k | +0.1697 | $4.8M | **171x** |
| **BCH** | +0.0829 | $4k | +0.0629 | $269k | **73x** |
| BTC | +0.0027 | $1k | +0.1079 | $82.0M | n/e |
| SOL | −0.0539 | $1k | +0.1070 | $12.6M | n/e |
| ADA · BNB · DOGE · DOT · LINK · LTC · TRX · XRP | ≤0 o ~0 | suelo | — | — | n/e |

**H1 = SÍ.** Y la aritmética cuadra al decimal con la ley: para ETH,
`5³ × (0.0749/0.0586)² = 204` contra los **203x** medidos — la capacidad va con
`stop³` **y** con `neto²`.

> **El techo de $22k NO era del sistema. Era de la geometría más apretada, que es
> la que el bot opera por accidente histórico.** Esa parte del brief queda
> confirmada.

---

## 4. H2 y H3 — el barrido de capital, y por qué no sirve

`n_trials = 6` (los capitales). Geometría y salida **no se buscan**.
Cota paranoica: **3.024** = 84 geometrías × 6 salidas × 6 capitales.

**POOL — 13 símbolos, n=12.941** (el número que manda):

| capital | NETO | IC95% | brecha | DD @ f viva | $/año | ¿candidato? |
|---|---|---|---|---|---|---|
| $22k | +0.0397 | [+0.0182, +0.0604] | −0.0182 | **36.3%** | $4.355 | **no** |
| $100k | +0.0279 | [+0.0064, +0.0486] | −0.0064 | 38.7% | $13.919 | no |
| **$250k** | +0.0150 | [−0.0066, +0.0357] | +0.0066 | 45.0% | **$18.713** | no |
| $500k | +0.0005 | [−0.0211, +0.0212] | +0.0211 | 60.6% | $1.173 | no |
| $1.0M | −0.0201 | [−0.0418, +0.0006] | +0.0418 | 76.1% | −$100.193 | no |
| $2.0M | −0.0492 | [−0.0709, −0.0284] | +0.0709 | 89.3% | −$490.411 | no |

**VIP — 3 símbolos, n=3.565** (el subconjunto, para contraste):

| capital | NETO | brecha | DD @ f viva | $/año |
|---|---|---|---|---|
| $22k | +0.0921 | −0.0502 | 11.3% | $2.788 |
| $250k | +0.0854 | −0.0435 | 11.7% | $29.359 |
| $2.0M | +0.0678 | −0.0259 | 13.0% | $186.534 |

Sobre el VIP, H1+H2+H3 salen **SÍ/SÍ/SÍ**. Sobre el pool, **H3 = NO en todos los
capitales**. La diferencia entera es PUERTA 3: el subconjunto miente en la
dirección optimista por los dos lados a la vez (nivel del neto ×1.8, drawdown
÷3). **Ése es el resultado del experimento, no una nota al pie.**

**Ni un solo capital sostiene una cuenta**, ni siquiera el más chico: a $22k el
drawdown a la `f` viva ya es **36.3% > 35%**, la cota escrita en el cementerio
como condición para revivir esta geometría.

### El óptimo interior en dólares — la respuesta de negocio

El premio no es monótono: `$ = C·f·E[R]·cadencia` y `E[R]` cae como `√C`, así que
hay un máximo interior. Sobre el pool está en **$250k → $18.713/año (APY 7.5%)**.
Es la cifra más alta que esta línea puede dar, y **viene con 45% de drawdown y un
IC95% que cruza cero**.

Compárese con lo que V5 midió el 2026-08-09 para la geometría apretada:
**$2.079/año en la frontera**. Ensanchar el stop multiplica el premio ~9x en
dólares — y lo deja igual de indemostrable, con el triple de drawdown.

### El DSR de esta tabla NO es un gate, y se dice

Los 6 capitales **no son 6 estrategias**: son la misma serie con una constante
restada, monótona en el capital. Sus Sharpes casi no se separan (std 0.0264 en
el pool, **0.0070** en el VIP), y `deflated_from_trials` deflacta con esa
dispersión → el eje **se auto-deflacta a ~nada** y la columna sale en 1.000 por
construcción, no por evidencia. Es la puerta 7 del brief ("una métrica demasiado
limpia es un bug") aplicada al propio gate.

El multiple-testing real de esta celda ocurrió **aguas arriba** (84 geometrías ×
6 salidas), y es justo lo que cuenta la cota paranoica. Las cifras con las que se
juzga esta celda siguen siendo las publicadas: **DSR 0.432** con `n_trials=1`
(cementerio 2026-08-04) y **0.366 / 0.607** al contar los trials de verdad.
El informe lo imprime solo.

---

## 5. Las puertas anti-espejismo del brief, una a una

| # | puerta | resultado |
|---|---|---|
| 1 | el stop ancho no regala edge por escala | respetada: se reporta **brecha**, no solo neto; la ley se marca DERIVACIÓN |
| 2 | capacidad ≠ edge | **es exactamente lo que pasó**: H1 sin H2 útil → el informe lo dice en voz alta |
| 3 | confundido del subconjunto | **CERRADO** (§0), y cableado en el aviso del tool |
| 4 | el DSR ya se cayó una vez | se imprimen las dos cuentas **y** el aviso de que este eje no deflacta |
| 5 | impacto sobre serie bruta = TECHO | `require_measured` puesto en toda curva; todo es cota superior |
| 6 | máximo en la esquina | el máximo de NETO está en el primer capital (el edge sólo baja); el máximo en DÓLARES es **interior** ($250k), que es la forma de un techo real |
| 7 | métrica demasiado limpia | disparó **tres** veces: el ratio 12.634x, el DSR 1.000 y la `f` doble. Las tres corregidas antes de publicar |

---

## 6. La invariante nueva — dinero obligatorio (`RWithoutMoneyError`)

*Un hallazgo sin invariante que lo haga cumplir es una nota.* La de V5 no es de
capacidad: es de **lectura**.

`growth.money_stats` traduce cualquier E[R] a dinero a la capacidad **medida**:

```
$/mes = capacidad × f × E[R] × señales/mes
```

`ledger_stats.window_stats` lo adjunta **siempre**, y
`ledger_stats.format_expectancy` —el único renderizador sancionado de una
expectancy, el mismo choke point que ya levantaba sin desglose (E9) y sin
crecimiento (V4)— **levanta `RWithoutMoneyError` sin él**. Que sea imposible
enseñar un `+0.02R` sin ver al lado que son ~$50/mes.

Los dos parámetros (`FQ_CAPACITY_USD` = $22k medido por V3,
`FQ_SIGNALS_PER_MONTH` = 45) son **declarados y viajan dentro del bloque**, mismo
trato que `Y` en V3 y `queue_frac` en V2.

Tests: `tests/test_growth.py` (identidad aritmética al dólar — $294/año,
publicación imposible sin el bloque, el mismo R vale 1000x distinto según la
capacidad) y `tests/test_capacity_analysis.py` (cada fila del barrido trae su
cifra y coincide con `capacidad × f × E[R] × cadencia`).

---

## 7. Qué queda vivo y qué no

**MUERTO** — la capacidad como vía a producto. Va a `CEMENTERIO.md` con su n
(12.941), su rejilla (6 capitales) y su `n_trials` (6 / 3.024).

**VIVO, y ahora medido:**
- **`capacidad ∝ stop_frac³` es real** (ETH 203x, AVAX 171x, BCH 73x). Si algún
  día aparece edge bruto, la geometría ancha le da capacidad de siete cifras.
  Es la tercera palanca guardada de la misma familia: la salida dinámica (riesgo,
  2026-08-08) y el sizing (V4) fueron las dos primeras. **Ninguna crea edge.**
- El aviso del subconjunto y el bloque de dinero, cableados.

**Lo que NO cambia:** sigue sin haber edge demostrado. Ninguna configuración
medida en este repo tiene el IC95% de la expectancy entero sobre cero **y** una
cartera sostenible **y** DSR > 0.95 a la vez.

**La lectura de negocio.** El brief preguntaba si el proyecto es un negocio o un
pasatiempo caro. Con la geometría ancha, el pool entero y todo a favor, el techo
del premio es **$18.713/año con 45% de drawdown y signo indeterminado**. La regla
de decisión que el propio brief fijó — *si operar esto cuesta >$170/mes, es
EV-negativo incluso en la frontera* — sigue siendo la que manda, sólo que ahora
el numerador es 9x mayor y el riesgo 3x. **No es una tesis de negocio: es la
misma pared, más lejos.**
