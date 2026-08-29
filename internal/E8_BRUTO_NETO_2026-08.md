# E8 — la brecha bruto/neto, contestada (agosto 2026)

> Pregunta abierta 6 del `GHOST_MAP`: el cube dice +0,224R bruto, el motor paper
> con fees dice −0,510R. ¿Cuánto del bruto sobrevive?
>
> **Respuesta: nada.** Y no hace falta un fill pesimista para verlo — ya es
> negativo con la hipótesis más optimista que existe.

Muestra: 13.429 señales, 13 símbolos, celda tp4/h288, cubos de esquema 2
(`cube_regrade_excursion`, reproducción 1,0000 contra el cubo original).

## Paso 1 — el mismo `CostModel` que usa el repo

| | n | bruto | **NETO** | IC95 % | P(≤0) | fees | slip |
|---|---|---|---|---|---|---|---|
| POOL | 13.429 | +0,231 | **−0,023** | [−0,060, +0,014] | 0,893 | −0,215 | −0,040 |

El bruto reproduce el +0,224R conocido. Los costes se lo comen entero y dejan el
neto **debajo de cero**, con el IC rozándolo.

**Y esto es la cota superior**, no el resultado: el cube asume que el stop se
llena EXACTO en `stop_price`.

### Por qué los fees pesan 0,215R

No es que las comisiones sean altas: es que **el stop es estrecho**. R = |entry −
stop| ≈ 0,25–0,50 % del precio, y el fee taker son 5 bps por pierna, 10 bps ida y
vuelta sobre el *notional*. El notional entre el riesgo es ~1/0,003 ≈ 300×, así
que 0,10 % de notional son ~0,2R.

Es el mismo cuerpo que `sl_noise_screen` ya señalaba por otro lado (stops de
0,24–0,31 % en el p10): **cuanto más fino el stop, más grande el fee medido en
R.** Apretar el stop no abarata el trade, lo encarece en las unidades en las que
se juzga.

## Paso 2 — dónde se llena realmente el stop

Una orden stop es MARKET: se llena entre el nivel y el extremo de la vela, y ese
punto **no está en el dato**. Así que esto es un barrido, no una estimación. El
número real está dentro.

| fill del stop | NETO | IC95 % | P(≤0) |
|---|---|---|---|
| 0 % — nivel exacto (lo que asume el cube) | −0,023 | [−0,060, +0,014] | 0,893 |
| 25 % del sobrepaso | −0,096 | [−0,134, −0,059] | 1,000 |
| 50 % del sobrepaso | −0,170 | [−0,209, −0,132] | 1,000 |
| 100 % — extremo de la vela | −0,317 | [−0,358, −0,276] | 1,000 |

El motor vivo mide **−0,510R**. El barrido cubre de −0,023 a −0,317: la mayor
parte del camino. Lo que queda hasta −0,510 es territorio del fill maker y la
selección adversa, que el repo ya tenía medido por otra vía (los límites que se
llenan en 1 barra pierden el 80 % del R).

**El TP no entra en el barrido.** Es orden límite: se llena a tu precio, y su
sobrepaso (+0,485R medido) ni se cobra ni se paga. La asimetría es de un solo
lado y va en contra — conviene no "compensar" una con otra.

## ¿Sobrevive algún subconjunto?

El brief lo pregunta explícitamente. Con el fill optimista había dos candidatos;
con uno realista no queda ninguno:

| símbolo | neto @ fill 0 % | P(≤0) | neto @ fill 50 % | P(≤0) |
|---|---|---|---|---|
| AVAX | **+0,145** | 0,034 | +0,014 | 0,449 |
| BCH | +0,083 | 0,058 | −0,067 | 0,879 |
| ETH | +0,059 | 0,160 | −0,094 | 0,929 |
| BTC | +0,032 | 0,277 | −0,113 | 0,964 |
| SOL | −0,054 | 0,799 | −0,214 | 1,000 |
| XRP | −0,180 | 1,000 | −0,347 | 1,000 |
| TRX | −0,278 | 1,000 | −0,395 | 1,000 |

AVAX era **1 de 13 a p=0,034** — exactamente lo que se espera por azar probando
trece. Y al fill realista se convierte en un volado (P=0,449). **Ninguno de los
trece sobrevive.** No hay subconjunto que sea la estrategia.

Los tres del VIP (SOL, BTC, ETH) están todos por debajo de cero al fill del 50 %.

## Qué significa, junto con E7

E7 dejó un solo sospechoso en pie para los 16 puntos de WR que faltan, y era
este. Ahora está medido:

- La **entrada** sí distingue: +3,6 pp de WR sobre un placebo emparejado, IC95 %
  [+2,5, +4,7]. La señal existe.
- La **trayectoria** no aporta nada: 8 de 8 celdas indistinguibles del placebo.
- El **coste de ejecución** se lleva el edge entero, y con margen.

O sea: hay señal, y no alcanza. El +0,231R bruto es real y es más chico que el
coste de cobrarlo. No es un problema de gestión del trade ni de elegir mejor
símbolo — es que la geometría actual (stop de ~0,3 %, salida taker) cuesta más de
lo que la señal vale.

**Lo que NO se sigue de aquí.** Que el sistema no pueda funcionar. Se sigue que
*esta* configuración no funciona, y se sabe por qué y cuánto falta. Las palancas
que el dato señala —no las que apetezca probar— son: stop más ancho (sube R y
diluye el fee en R, a costa de arriesgar más por trade), salida no-taker donde se
pueda, o menos trades con más edge por trade. Ninguna está medida todavía, y el
E6 del brief prohíbe tocar TP/SL sin pasar por el gate.

## Alcance y advertencias

1. **Cota superior, incluso al 100 %.** El cube no modela el fill de ENTRADA. La
   entrada maker con fill parcial es el otro agujero conocido y no está aquí.
2. **Cruce de venue.** El cube se cosechó sobre OKX **spot** y el `CostModel`
   modela un USDT-perp con funding. Es una mezcla heredada del repo, no de este
   tool. El funding pesa poco (+0,001R), así que no cambia el signo — pero está
   ahí y conviene arreglarlo en la cosecha, no en el informe.
3. **Una celda, no doce.** Todo es tp4/h288. `--rejilla` enseña las doce, y
   elegir la mejor de doce sobre el mismo set es selección: no se cita sin gate.
4. El barrido del fill **no es una estimación**. Quien cite "−0,170R" debe citar
   también que viene de suponer que el stop se come la mitad del sobrepaso.

## Cableado

| Invariante | Dónde | Qué impide |
|---|---|---|
| El sobrepaso solo empeora | `tests/test_cube_net_expectancy.py::test_mas_sobrepaso_nunca_mejora_el_neto` | Un signo invertido que haga el fill pesimista "rentable" |
| El fill cae entre nivel y extremo | mismo test, ambas direcciones | Un fill fuera del rango físico posible |
| El TP nunca se toca | mismo test | Compensar el sobrepaso del stop con el del TP |
| Esquema 2 obligatorio | `require_life_scoped` en `neto()` | Usar `mae_r` de VENTANA como extremo del fill (se iría a −9R) |
