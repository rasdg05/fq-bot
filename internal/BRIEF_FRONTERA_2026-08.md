# BRIEF — ¿Cuánto falta para la frontera? (agosto 2026)

> Encargo para una sesión nueva. `CLAUDE.md` y `MEMORY/ESTADO.md` ya cargan el
> estado, los números vigentes y las invariantes: **no los repitas ni los
> re-derives**. Esto es solo dónde está la frontera, qué palancas quedan vivas
> con su prior YA medido, y cómo distinguir filo de espejismo.
>
> Rama: `claude/v3-capacidad-velas-rp3v9u` (contiene E1–E9 + V1–V4).
> **Nada a `main` sin decírselo a RasDG** — despliega a producción con
> suscriptores de pago.

---

## La frontera, en una cifra

Todo el proyecto cabe en esta resta:

```
bruto VIP tp4/h288   +0.2706R
coste de ejecución   -0.2607R      (fees 5bps x2 + slip 1bps x2, sobre stops de 0.45-0.63%)
                     ---------
neto                 +0.0099R      IC95% [-0.060, +0.080]
```

Está **por encima de breakeven y por debajo de demostrable**. Para que el IC95%
quede entero sobre cero con la n actual (3.774) hace falta mover el neto a
**~+0.07R**.

> ⚠️ **CORREGIDO 2026-08-08 — la frontera NO es una constante.** Es **`-IC_lo`**,
> y eso depende de la **n de la configuración que lo pretenda cruzar**. Toda
> palanca que FILTRA señales sube la media **y encarece la vara a la vez**.
> Medido: cortar el tercil bajo de convicción sube el neto de tp4 en +0.022R y
> encarece la vara en +0.017R — **un tercio de lo que aparenta ganar es
> contabilidad**. A la n de partida la brecha es **+0.0599**; cada fila de
> cualquier tabla lleva la suya. Cableado en `tools/frontier_report.py`
> (`frontier_gap` / `require_own_bar` → `FrontierBarMovedError`).

Esa cifra es la vara de cualquier propuesta. Una idea que mueva +0.01R no acerca
la frontera: la decora. Y una idea que mueva la media tirando muestra hay que
juzgarla por la **brecha**, nunca por la media.

---

## Las palancas vivas, con su prior medido

Ordenadas por (retorno esperado / riesgo de research). Ninguna es especulación:
todas tienen número detrás en `MEMORY/CEMENTERIO.md` o `internal/GHOST_MAP_2026-07.md`.

| # | Palanca | Efecto estimado | Medido (2026-08-08) | Estado |
|---|---|---|---|---|
| 1 | **Bajar comisiones** (tier / venue / rebate) | ~~+0.06 a +0.09R~~ | **+0.030R alcanzables** (techo: HL+referral 4.32bps) | **MEDIDA — pared, ver abajo** |
| 2 | **Cortar el tercil BAJO de convicción** | sube el bruto del conjunto | **+0.005R de brecha** en tp4; **NO rescata tp1** | **MEDIDA — decoración** |
| 3 | **Funding-gate, medido NETO** | +0.05–0.07R bruto | pendiente (falta la serie de funding en el cube) | dormido, **nunca medido neto** |
| 4 | Re-etiquetar más allá de tp4 | desconocido | — | alto (devuelve concurrencia) |

> ⚠️ **CORREGIDO 2026-08-08 — la #1 NO es del tamaño de la frontera.** La
> aritmética se confirma (cada bp de fee taker = **+0.0436R**), pero el tier no
> es aritmética: **Binance VIP1 pide $15M/30d y la estrategia genera
> $970.973/30d** a la capacidad neta de V3 (~45 señales/mes, stop mediano
> 0.51%). El techo alcanzable es **4.32 bps → +0.0396R, brecha +0.0303**.
> **El edge no sostiene la cuenta que haría falta para abaratar el edge: la #1 y
> V3 son la misma pared por los dos lados.** Cableado:
> `require_reachable` → `FeeTierUnreachableError`, que falla **cerrado**.
>
> **Apilando #1 + #2** (lo mejor alcanzable hoy, tp4/h288, n=2.510):
> **NETO +0.0620, IC95% [−0.0250, +0.1463] → brecha +0.0250.** Se cierra el
> **58%** de la distancia y **sigue sin cruzar**.
> → `internal/EVALUACION_V1_V4_FRONTERA_2026-08.md`

**Y el aviso que va pegado a la #2 y la #3:** cinco cosas pasaron el gate por
separado (CVD, F2, KL, funding, convicción) y el neto sigue en cero. Apilar
condicionadores correlacionados suele dar **menos** que la suma. El prior honesto
es que 2+3 juntas dejen la cosa cerca de cero, no claramente arriba.

---

## Lo que NO hay que volver a proponer

Está todo medido y en `CEMENTERIO.md` con su n. Si una idea nueva cae aquí, la
respuesta es el número, no otra corrida:

- **ML / más features** — el GBM pierde 0/4 contra `p_master` OOS.
- **Concentrar en los mejores símbolos** — el liderazgo rota; los rezagados ganan OOS.
- **Símbolos nuevos** — GATE-F: ninguno califica con los datos actuales.
- **Stops más anchos / mover el eje TP** — señal confirmada, producto inviable (V1 + geometría ancha).
- **Arreglar el maker por ejecución** — no hay dónde ponerse en la cola (V2).
- **Escalar capital** — la capacidad neta se acaba en $22k (V3).
- **Copy-trading de leaderboard** — 1 candidata de 100.
- **"Bajar de tier de comisiones"** como palanca grande — medido: el techo
  alcanzable son +0.030R; los escalones que cruzan piden un volumen que la
  capacidad neta de V3 no genera (2026-08-08).
- **Encender el corte de convicción para arreglar el producto vivo** — en tp1
  deja el IC entero bajo cero (−0.0589R, n=2.510).
- **Encoger la cuenta para "abaratar"** — el coste fijo por trade no escala, y
  bajar capital solo aleja más el tier.

---

## Cómo saber si es filo o espejismo

El repo tiene **15 invariantes cableadas** (tabla en `CLAUDE.md`). No son higiene:
**cada una es un espejismo que YA ocurrió aquí**. Un candidato nuevo pasa por
todas antes de llamarse edge:

1. **n ≥ 30**, y la n citada en cada afirmación.
2. **IC95% entero sobre cero** — no "el punto es positivo".
3. **DSR > 0.95** con `n_trials` contados honestamente + CPCV + PBO. La vara no
   se degrada para que quepa nada (`CONSTITUCION.md`).
4. **Cartera antes que candidata** (`screen_cell`): un R por trade sin su cuenta
   detrás no describe nada operable.
5. **Neto, nunca bruto suelto** — el coste es más grande que el edge entero.
6. **Fill modelado, no asumido** — el supuesto de fill al 100% ya volteó un signo.
7. **Liquidez medida, no de catálogo** — el default estaba 8x fuera.
8. **`g`, `f*` y P(acabar arriba)** junto al E[R] — la media es del ensemble; la
   cuenta vive una trayectoria.
9. **Desglose por régimen/año** — el agregado lleva el asterisco, no el desglose.
10. **La vara es la de SU n** (`require_own_bar`) — una config que filtra sube la
    media y aleja la frontera; júzgala por la **brecha**, nunca por la media.
11. **Toda puerta se comprueba, y falla cerrado** (`require_reachable`) — un tier
    de fees, un tramo de volumen o un requisito de capital que no se puede
    evaluar **no** es un requisito cumplido.

Y las dos heurísticas que más han valido:

- **Una métrica demasiado limpia es un bug, no un hallazgo.** Separación perfecta
  por una variable, distribución imposible → fallo de medición ANTES que edge.
- **Máximo en la esquina = extrapolación.** Si el mejor valor es el último
  probado, la tabla no dice que sea el óptimo; dice que el rango se acabó.

---

## Preguntas legítimas para esta sesión

Las tres que este brief planteó están **CONTESTADAS (2026-08-08)** por
`python tools/frontier_report.py` — ver el bloque corregido de arriba y
`internal/EVALUACION_V1_V4_FRONTERA_2026-08.md`. La #3 (funding-gate neto) sigue
abierta porque el cube no trae la serie de funding.

**La que queda viva: la REGLA DE SALIDA.** → `internal/BRIEF_SALIDA_2026-08.md`
(pre-registrado: hipótesis, rejilla, `n_trials` y criterio fijados antes de
correr).

> ⚠️ **Ojo, que aquí se propuso mal una vez (2026-08-08).** Se apuntó primero al
> `stop_frac` como "el denominador del coste que nadie miró". **Falso por dos
> lados:** (1) está medido y muerto — `tools/geometry_sweep.py`, 84 celdas,
> `DSR = 0.000` con `n_trials=84`, riesgo de cartera decisivo; y (2) la
> aritmética lo desactiva de todos modos: bruto y coste escalan **los dos** por
> `1/s`, así que **reescalar el stop no mueve el t-estadístico**. Solo puede
> ayudar cambiando la COMPOSICIÓN de desenlaces, y eso ya se barrió.
> **Lee `CEMENTERIO.md` antes de proponer, incluido tú.**

Lo que **sí** queda sin medir es cambiar la **regla de salida** (trailing /
breakeven / techo de tiempo) sobre la celda ancha ya identificada. Es la
condición de reviving que el propio cementerio dejó escrita — *"un mecanismo que
baje la CONCURRENCIA sin tirar la cadencia"* — y tiene una propiedad que ninguna
otra palanca viva tiene: **no cambia ninguna entrada, así que `n` es constante,
la vara no se mueve y toda mejora del neto es real**.

Reproducibles (todo local y gratis; el cube ya está en `cosecha_cubes/`):

```
python tools/frontier_report.py               # escalera de fees + brecha + atribución
python tools/vip_report.py                    # universo + eje TP + g/P(arriba)
python tools/cube_report.py cosecha_cubes/    # celdas del cube CON costes
python tools/capacity_analysis.py --vip       # a qué tamaño se muere
python tools/fill_quality.py --klines data/binance
```

Las velas NO están en el repo (`.gitignore`). Se bajan en ~40 s por símbolo:
`python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance`

---

## El estado honesto, para no confundir "resultados malos" con "proyecto malo"

- **El método está muy por encima del retail**: DSR deflactado, CPCV con purga y
  embargo, PBO, cementerio, medición forward con fees, ledger encadenado, y ahora
  15 invariantes que hacen cumplir lo aprendido. Eso es metodología de fondo
  pequeño. **No se degrada para que salgan números bonitos** — es el activo real.
- **La señal SÍ separa** (E7: asimetría de recorrido +1.011R, IC95% [+0.825,
  +1.199], ambos lados, ocho años). El problema nunca fue la señal.
- **Y no hay edge demostrado**: ninguna configuración medida tiene el IC95% del
  neto entero sobre cero. Decirlo no es pesimismo, es el estado del arte del repo.

**No uses el `n=12` del track record publicado para afirmar nada** — ni con
clientes ni con inversores. Está bajo el `MIN_N=30` del propio repo y no concluye
en ninguna dirección.
