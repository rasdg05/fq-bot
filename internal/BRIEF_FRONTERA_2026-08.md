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
**~+0.07R**. O sea:

> **La frontera son +0.07R por trade.** Da igual de qué lado vengan: +0.07R más
> de bruto, −0.07R menos de coste, o la suma de los dos.

Esa cifra es la vara de cualquier propuesta. Una idea que mueva +0.01R no acerca
la frontera: la decora.

---

## Las palancas vivas, con su prior medido

Ordenadas por (retorno esperado / riesgo de research). Ninguna es especulación:
todas tienen número detrás en `MEMORY/CEMENTERIO.md` o `internal/GHOST_MAP_2026-07.md`.

| # | Palanca | Efecto estimado | Riesgo | Estado |
|---|---|---|---|---|
| 1 | **Bajar comisiones** (tier / venue / rebate) | **+0.06 a +0.09R** | ninguno de research | sin cuantificar el tier ALCANZABLE |
| 2 | **Cortar el tercil BAJO de convicción** | sube el bruto del conjunto | bajo (GATE-C, PBO 0.008) | cableado dormido (`FQ_CONVICTION_LONGS`) |
| 3 | **Funding-gate, medido NETO** | +0.05–0.07R bruto | bajo (DSR 1.000, CPCV 100%, PBO 0.00) | dormido, **nunca medido neto** |
| 4 | Re-etiquetar más allá de tp4 | desconocido | alto (devuelve concurrencia) | `geometry_sweep`, velas ya bajables |

**La #1 es del tamaño de la frontera entera y no depende de que ningún research
salga bien.** Es aritmética: `coste_R = (2·fee + 2·slip) / stop_frac`, y con
stops de 0.45–0.63% cada punto básico de fee vale ~0.02R. Lo que NO es
aritmética es qué tier alcanza de verdad una cuenta pequeña — eso hay que
comprobarlo antes de contarlo como ganado.

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

---

## Cómo saber si es filo o espejismo

El repo tiene **13 invariantes cableadas** (tabla en `CLAUDE.md`). No son higiene:
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

Y las dos heurísticas que más han valido:

- **Una métrica demasiado limpia es un bug, no un hallazgo.** Separación perfecta
  por una variable, distribución imposible → fallo de medición ANTES que edge.
- **Máximo en la esquina = extrapolación.** Si el mejor valor es el último
  probado, la tabla no dice que sea el óptimo; dice que el rango se acabó.

---

## Preguntas legítimas para esta sesión

Las que el instrumento ya puede contestar sin construir nada nuevo:

1. **¿Cuánto neto compra cada escalón de comisiones, y qué tier es alcanzable?**
   (la cifra que quedó pendiente; es aritmética + una comprobación de venue).
2. **¿Qué dan 2+3 apiladas, medidas netas y con la cartera puesta?** Pre-registrar
   la hipótesis ANTES de correr, y contar `n_trials` de verdad.
3. **¿Qué distancia hay de aquí a la frontera por cada camino?** Es una tabla, y
   cabe en una corrida.

Reproducibles (todo local y gratis; el cube ya está en `cosecha_cubes/`):

```
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
  13 invariantes que hacen cumplir lo aprendido. Eso es metodología de fondo
  pequeño. **No se degrada para que salgan números bonitos** — es el activo real.
- **La señal SÍ separa** (E7: asimetría de recorrido +1.011R, IC95% [+0.825,
  +1.199], ambos lados, ocho años). El problema nunca fue la señal.
- **Y no hay edge demostrado**: ninguna configuración medida tiene el IC95% del
  neto entero sobre cero. Decirlo no es pesimismo, es el estado del arte del repo.

**No uses el `n=12` del track record publicado para afirmar nada** — ni con
clientes ni con inversores. Está bajo el `MIN_N=30` del propio repo y no concluye
en ninguna dirección.
