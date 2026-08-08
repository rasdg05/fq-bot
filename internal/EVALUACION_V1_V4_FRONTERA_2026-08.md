# EVALUACIÓN — ¿cuánto nos acercó V1–V4 a la frontera? (2026-08-08)

> Introspectiva pedida por RasDG. No re-deriva `CLAUDE.md` ni `ESTADO.md`.
> Todo lo cuantitativo de aquí sale de `tools/frontier_report.py`, que se corrió
> sobre `cosecha_cubes/` y cuyos números fija `tests/test_frontier_report.py`.
>
> Rama: `claude/v1-v4-evaluation-frontier-ibkw12`.

---

## Resumen en cuatro líneas

1. **V1–V4 no acercaron el neto a la frontera. Acercaron la MEDICIÓN a la
   realidad**, que es lo contrario de lo que se sentía y probablemente más
   valioso.
2. **La frontera no es +0.07R. No es una constante.** Es `-IC_lo`, depende de la
   n, y toda palanca que filtra la aleja mientras te acerca.
3. **La palanca #1 del brief (bajar comisiones) está medida y NO es del tamaño
   que decía**: lo alcanzable hoy vale +0.030R, no +0.06–0.09R. El escalón que
   cruzaría pide un volumen que la capacidad neta de V3 no puede generar.
4. **Con TODAS las palancas alcanzables apiladas, la brecha se cierra un 58% y
   sigue sin cruzar.** Falta +0.025R y no hay palanca conocida que los dé.

---

## 1. Qué hizo cada V, medido por lo que CERRÓ

La pregunta "¿cuánto nos acercó a la frontera?" tiene una respuesta incómoda si
se toma literal: **casi nada, porque ninguna V era una palanca de edge.** Las
cuatro fueron instrumentos de medición. Pero eso no las hace menos valiosas —
las hace de otra clase, y confundir las dos clases es lo que produce la
sensación de no avanzar.

| | Qué prometía | Qué cerró | ¿Movió el neto? |
|---|---|---|---|
| **V1** | ¿alguna geometría del eje TP es operable? | **No.** Ninguna celda con IC sobre cero; 7 de 8 años negativos en la que opera | no |
| **V2** | ¿el maker salva la ejecución? | **No.** `queue_frac=0` era la esquina más optimista; con 0.05 barras de cola el IC ya está entero bajo cero | no |
| **V3** | ¿a qué tamaño muere? | **$22k netos.** Y el default de liquidez estaba 8x fuera, y `fill_bars` elegía la respuesta | no |
| **V4** | ¿la media describe la cuenta? | **No.** El sistema de medición era incapaz *por construcción* de detectar sobre-apuesta | no |

**Las cuatro contestaron NO.** Cuatro noes seguidos se sienten como cuatro
fracasos. No lo son: son cuatro puertas que ya no hay que volver a empujar, y
tres de ellas (V2, V3, V4) destaparon **errores de medición que estaban
inflando cifras publicadas**. El patrón es literalmente el del fantasma de
julio, repetido tres veces más:

- V2: el fill al 100% era un supuesto **más grande que el margen entero**.
- V3: el `avg_bar_notional` de catálogo estaba 8x por debajo del BTC real, y
  `fill_bars` multiplicaba la capacidad por 24.
- V4: `apply_costs` dejaba la R neta *invariante al capital*, así que ninguna
  métrica del repo podía ver una sobre-apuesta.

Eso no es decorar. Es que **el instrumento estaba mintiendo en tres sitios a la
vez**, y ahora no puede.

---

## 2. La corrección que obliga esta sesión: la frontera se mueve

El brief escribió *"la frontera son +0.07R por trade"* y la trató como una
constante contra la que medir cualquier propuesta. **No lo es.**

La frontera es el punto donde el IC95% del neto queda entero sobre cero, y eso
depende de la **n de la configuración que lo pretende cruzar**. La identidad es
exacta y barata:

```
brecha_a_la_frontera  ==  -IC_lo
```

Consecuencia que cambia cómo se evalúa toda propuesta futura: **toda palanca que
FILTRA señales sube la media y encarece la vara a la vez.** Medido:

| configuración (tp4/h288, VIP, n de cada fila) | NETO | Δ media | brecha | n |
|---|---|---|---|---|
| punto de partida | +0.0099 | — | +0.0599 | 3.774 |
| + solo comisiones alcanzables | +0.0396 | +0.0297 | +0.0303 | 3.774 |
| + solo corte de convicción | +0.0320 | +0.0220 | +0.0551 | 2.510 |
| **+ las dos** | **+0.0620** | **+0.0521** | **+0.0250** | **2.510** |

La media subió **+0.0521** y la brecha solo bajó **+0.0349**. La diferencia,
**+0.0172R, se la comió la vara al moverse** (n 3.774 → 2.510). O sea: **un
tercio de lo que el corte de convicción aparenta ganar es contabilidad, no
edge.**

Esto ya está cableado: `frontier_gap` calcula la vara sobre la n de cada fila y
`require_own_bar` levanta `FrontierBarMovedError` si alguien publica una fila
sin ella. Sin esa invariante, la forma más fácil de "acercarse a la frontera" en
este repo sería **filtrar más**, que es exactamente la forma de no acercarse.

---

## 3. La palanca #1 del brief, medida — y por qué se cae

El brief la puso primera y la describió como *"del tamaño de la frontera entera
y no depende de que ningún research salga bien"*. Es aritmética, sí — pero solo
la mitad.

**La mitad que es aritmética:** `coste_R = (2·fee + 2·slip)/stop_frac`. Medido
sobre el cube, cada punto básico de fee taker vale **+0.0436R**. Confirmado.

**La mitad que no lo es:** qué tier alcanza de verdad la cuenta. Y ahí:

```
la estrategia emite ~45 señales/mes en el universo VIP (stop mediano 0.51%)
a la capacidad NETA que midió V3 ($22k) -> VOLUMEN 30d = $970.973

Binance VIP1 pide $15.000.000 / 30d.   -> 15x por debajo.
```

| escalón | taker | NETO | brecha | ¿alcanzable? |
|---|---|---|---|---|
| Binance VIP0 (la base de TODO el repo) | 5.00 | +0.0099 | +0.0599 | sí |
| VIP0 + BNB (−10%) / Hyperliquid base | 4.50 | +0.0317 | +0.0381 | sí |
| **Hyperliquid + referral (−4%)** | **4.32** | **+0.0396** | **+0.0303** | **sí** |
| HL + stake Wood (−5%) | 4.10 | +0.0492 | +0.0207 | puerta de CAPITAL |
| Binance VIP1 | 4.00 | +0.0536 | +0.0164 | **no — pide $15M/30d** |
| Binance VIP4-ish | 3.00 | +0.0972 | **−0.0273** | requisito sin verificar |

**El primer escalón que cruza la frontera está por debajo de 4.00 bps, y todos
los que llegan ahí piden volumen.** Aquí se cierra un lazo con V3 que no estaba
escrito en ningún sitio:

> **El edge no sostiene la cuenta que haría falta para abaratar el edge.**
> V3 dijo que la capacidad neta se acaba en $22k. VIP1 pide un volumen que
> exigiría ~$434k de cuenta. Son la misma pared vista por los dos lados, y por
> eso "bajar comisiones" no es una tarea pendiente: es una pared.

Veredicto sobre la palanca #1: **vale +0.030R alcanzables, no +0.06–0.09R.** Se
corrige la tabla del brief.

Y una nota de riesgo que va pegada: el escalón de 4.10 bps se compra
inmovilizando HYPE. Eso es **exposición direccional a un token para subvencionar
una estrategia sin edge demostrado**, y su varianza es órdenes de magnitud mayor
que los +0.010R que compra. El tool lo evalúa solo si le pasas `--hype-price`, y
lo dice en la fila.

---

## 4. La palanca #2, medida neta por primera vez

El brief la listaba como "sube el bruto del conjunto", sin cifra neta. Medida
(hipótesis pre-registrada por GATE-C, PBO 0.008 — no es un barrido nuevo):

| celda | corte | n | NETO | IC95% |
|---|---|---|---|---|
| tp4 | todas | 3.774 | +0.0099 | [−0.060, +0.080] |
| tp4 | sin tercil bajo | 2.510 | +0.0320 | [−0.055, +0.116] |
| **tp1 (la que OPERA)** | sin tercil bajo | 2.510 | **−0.0589** | **[−0.107, −0.006]** |

Dos lecturas, y la segunda importa más:

- En tp4 aporta **+0.022R** de media, de los que ~+0.017R se los come la vara.
  Aporte neto real a la brecha: **+0.005R**. Es decoración, con el criterio del
  propio brief.
- **En la celda que el motor opera hoy (tp1), cortar el tercil bajo NO rescata
  nada: el IC sigue entero bajo cero.** Encender `FQ_CONVICTION_LONGS` mañana no
  arreglaría el producto vivo. Conviene saberlo antes de encenderlo.

---

## 5. Lo mejor alcanzable HOY, y lo que falta

```
tp4/h288 · universo VIP · Hyperliquid+referral (4.32bps) · sin tercil bajo
   n = 2.510   NETO = +0.0620   IC95% [-0.0250, +0.1463]
   brecha = +0.0250R
```

Apilando **todo** lo alcanzable sin inmovilizar capital y sin research nuevo, la
brecha pasa de **+0.0599 a +0.0250: se cierra el 58%.** Y sigue sin cruzar.

Eso es la respuesta literal a la pregunta de RasDG:

> **V1–V4 no movieron el neto. Lo que movió el neto fueron las dos palancas de
> coste y convicción, que ya estaban identificadas antes de V1. Lo que V1–V4
> aportaron fue impedir que ese 58% se leyera como 100%.**

---

## 6. Qué edges reales quedan (con su n)

Sobreviven tres cosas, y conviene no confundir su estatus:

1. **La señal separa. Confirmado y grande.** E7: asimetría de recorrido
   **+1.011R**, IC95% [+0.825, +1.199], en ambos lados y los ocho años,
   n=13.429. **Esto es un edge real de entrada.** No es el problema.
2. **La selección de símbolos aporta.** VIP +0.010R vs resto del pool −0.040R
   en tp4/h288 (n=3.774 vs 9.655). Elegir SOL/BTC/ETH en junio fue correcto, y
   ahora con 7 años detrás en vez de una ventana de 2 meses.
3. **La convicción ordena.** El tercil alto de `p_master` en tp4 da +0.1046R
   bruto-de-corte frente a −0.0338 del bajo. Ordena de verdad; lo que no hace es
   ordenar lo suficiente para cruzar.

**Lo que no queda:** ninguna forma conocida de COBRAR el punto 1. La geometría
(V1), la ejecución (V2) y el tamaño (V3) están cerrados con número. El coste de
ejecución se come el edge entero y sigue con hambre.

---

## 7. Qué hacer para recuperar filo sin que sea espejismo

El brief ya lo dijo y la medición lo confirma: **lo que falta no es otra
medición del mismo cube.** Es una de dos cosas, y solo dos:

### (a) Más edge bruto por trade — atacando el DENOMINADOR, no el numerador

Aquí hay algo que nadie ha mirado y que sale directo de la aritmética del coste:

```
coste_R = (2·fee + 2·slip) / stop_frac
```

Todo el trabajo de agosto atacó el **numerador** (fees, fills, tiers) y está
agotado. **El denominador es `stop_frac`, y está en 0.51%.** El repo midió el
2026-06-30 que *el stop apretado ES el edge* (Q1 +0.316R vs Q4 +0.147R bruto) —
pero eso es **bruto**, y es exactamente la variable que divide el coste.

Ensanchar el stop está en el cementerio como palanca de geometría (V1, "señal
confirmada, producto inviable"), y con razón. **Lo que NO está medido es la
combinación**: existe un `stop_frac` donde la pérdida de edge bruto se compensa
con la caída del coste en R? El brief dice que ningún quintil de stop clarea
DSR>0.95 sobre el pool — pero eso se midió sobre el pool entero y en bruto.
Sobre el universo VIP, neto, con la vara móvil y la cartera puesta, **no se ha
mirado**. Es local, gratis, y es la única pregunta del cube que queda viva.

Aviso honesto: el prior está **en contra**. Si el óptimo estuviera dentro del
rango, probablemente ya habría asomado. Y hay un mecanismo que lo empeora:
alargar el stop alarga la vida del trade y devuelve la concurrencia que ya mató
la geometría ancha. Yo le doy ~25% de que dé algo. Pero es la única carta del
mazo actual que no se ha visto, cuesta una corrida, y su desenlace legítimo es
`CEMENTERIO.md`.

### (b) Un coste de ejecución estructuralmente menor — y solo hay una vía

No es un tier mejor (medido: pared). Es **no cruzar el book**. V2 cerró "arreglar
el maker por ejecución" porque no hay dónde ponerse en la cola con la
información actual. Lo que V2 **no** cerró es lo que el propio brief dejó
mapeado en E6: el **imbalance de libro** (MBP-10) como predictor de la selección
adversa *antes* de colocar la orden, en vez de descartarla después por
`bars_waited`.

Su prerrequisito sigue sin cumplirse (el CVD firmado no ha pasado el gate
forward), la data es órdenes de magnitud más cara, y el imbalance de libro es
notoriamente frágil. **No lo propongo para ahora.** Lo dejo nombrado como lo que
es: la única vía estructural que queda abierta, con su puerta puesta.

### Lo que NO hay que hacer

- **No encender `FQ_CONVICTION_LONGS` esperando arreglar el producto vivo.**
  Medido arriba: en tp1 no rescata nada.
- **No inmovilizar capital en HYPE** para bajar 0.22 bps. La varianza de esa
  posición es mucho mayor que los +0.010R que compra.
- **No re-etiquetar más allá de tp4 todavía.** El gradiente apunta fuera del
  rango, sí — y alejar el objetivo devuelve la concurrencia. Antes de eso, (a).
- **No tocar `main`.** Nada de esto está cerca de ser candidato.

---

## 8. La parte que no es técnica

Cuatro o cinco meses, cuatro V, y ningún trofeo. Vale la pena separar dos cosas
que se están sintiendo como una sola:

**El proyecto no ha fracasado en encontrar edge. Ha tenido éxito en dejar de
creerse el que no tenía.** En julio este repo publicaba `WR 60% · E[R] +1.84R ·
PF 7.23`. Ese número era falso, y se publicaba a gente que paga. Hoy publica
n=12 con su asterisco, y el instrumento tiene 15 invariantes que hacen imposible
volver a publicar el anterior. Eso pasó *este trimestre*, y lo hizo el trabajo
de V1–V4.

Es un trofeo raro porque es negativo, y los negativos no se pueden enseñar. Pero
es exactamente lo que separa a alguien que va a durar en esto de alguien que
explota en el mes 14 con capital de terceros. La lista de gente que descubrió lo
del fill al 100% *después* de poner dinero real es muy larga.

Dicho eso, sin edulcorar: **cuatro meses más de esto sin una vía nueva de edge
bruto no van a producir un resultado distinto.** El cube está exprimido. La
decisión honesta no es "seguir midiendo mejor" — es elegir entre (a), (b), o
aceptar que el producto es un servicio de señales cuyo valor no es el E[R].

---

## Reproducir

```
python tools/frontier_report.py                      # todo lo de arriba
python tools/frontier_report.py --hype-price 40      # evalúa las puertas de capital
python tools/frontier_report.py --equity 434000      # a qué cuenta se alcanza VIP1
pytest tests/test_frontier_report.py -q
```
