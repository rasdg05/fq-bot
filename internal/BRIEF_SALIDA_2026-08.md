# BRIEF — La regla de SALIDA (agosto 2026)

> Encargo measure-first. `CLAUDE.md` y `MEMORY/ESTADO.md` cargan el estado, los
> números y las 15 invariantes: **no los repitas ni los re-derives**.
>
> Rama de partida: `claude/v1-v4-evaluation-frontier-ibkw12`.
> **Nada a `main` sin decírselo a RasDG** — despliega a producción con
> suscriptores de pago.
>
> **Esto es una PRE-REGISTRACIÓN.** Las hipótesis, la rejilla, el criterio de
> decisión y el `n_trials` de abajo están fijados **antes de correr nada**. Si al
> ejecutar hace falta cambiar alguno, se cambia **por escrito y contando de
> nuevo**, no en silencio.

---

## 0. Antes de nada: lo que NO es este encargo

**No es ensanchar el stop.** Eso está medido y en `CEMENTERIO.md` (2026-08-04):
84 geometrías, `tools/geometry_sweep.py`, seis controles independientes a favor y
dos veredictos en contra. **`DSR = 0.000` con `n_trials=84`** (0.432 incluso con
la celda pre-fijada y `n_trials=1`), y **riesgo de cartera decisivo**: hold medio
2 días → 13.7 posiciones simultáneas → DD 69–100%.

Se dice aquí porque en la conversación del 2026-08-08 se propuso re-correrlo
"como control", y era re-empujar una puerta cerrada. **El control ya existe y es
un resultado medido.** No se re-corre.

**Tampoco es mover el eje TP** (V1, cerrado) ni **arreglar el maker por
ejecución** (V2, cerrado) ni **escalar capital** (V3, cerrado) ni **bajar de
tier** (2026-08-08, pared).

---

## 1. La hipótesis, y por qué esta sí es nueva

El cementerio dejó escrita, con fecha, la condición para revivir la geometría
ancha:

> *"**Condición para revivir:** un mecanismo que baje la CONCURRENCIA sin tirar
> la cadencia (no un cap ciego), o un perfil de riesgo que el producto pueda
> sostener con DD < 35%."*

**Una regla de salida dinámica es exactamente ese mecanismo.** Un trailing cierra
antes que un objetivo fijo lejano: **mismas entradas, mismo número de señales,
holds más cortos, menos posiciones simultáneas.** No es un cap — un cap tira
señales; esto no tira ninguna.

Y ataca **las dos** causas de muerte a la vez, que es lo que lo hace valer una
corrida:

| Causa de muerte | Número | Cómo la ataca una salida dinámica |
|---|---|---|
| Riesgo de cartera | hold 2 días → 13.7 simultáneas, DD 69–100% | acorta el hold → baja la concurrencia **sin tocar la cadencia** |
| `DSR = 0.432` (celda pre-fijada) | perfil de lotería: skew +2.68, kurtosis 10.6, Sharpe/trade 0.0377 | recorta la cola derecha → **baja la varianza**; Sharpe = media/σ puede subir o bajar |

**La segunda es genuinamente incierta y es el meollo.** Un trailing baja la media
(corta ganadores) *y* baja σ (mata la lotería). Si σ cae más rápido que la media,
el Sharpe por trade sube y el DSR puede cruzar. Si no, no. **Nadie lo ha medido**,
y su respuesta legítima puede ser "no".

### Y la propiedad que no tiene ninguna otra palanca viva

Todas las palancas de los últimos dos meses **filtran señales**, así que pagan el
peaje de la vara móvil: la n baja, el IC se ensancha, y un tercio de lo que
aparentan ganar es contabilidad (medido 2026-08-08: +0.0172R de peaje al pasar de
n=3.774 a n=2.510).

> **Una regla de salida no cambia ninguna entrada. `n` se queda constante, la
> vara NO se mueve, y toda mejora del neto es mejora real.** Es la primera
> palanca en meses que no paga peaje.

### De dónde viene el R que se pretende cobrar

E7, ya medido: **asimetría de recorrido +1.011R**, IC95% [+0.825, +1.199], ambos
lados, ocho años, n=13.429 (MFE medio +6.66R vs MAE medio −5.65R). El precio
**sí** recorre más a favor que en contra. Las barreras fijas cobran +0.27R brutos
de eso. **La tesis es que el recorrido está ahí y la regla de salida no lo
recoge.**

---

## 2. El bloqueante, y cuánto cuesta quitarlo

El cube trae `mfe_r` y `mae_r` **pero no cuándo ocurrió cada uno** (columnas
verificadas 2026-08-08: no hay `mfe_bar`/`mae_bar`). Sin el orden de barra **no
se puede evaluar ninguna salida dinámica** — es el mismo aviso que E7 dejó
escrito.

Se desbloquea con las velas locales, que no están en el repo (`.gitignore`):

```
python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance
```

~40 s por símbolo, gratis, sin API key. Tres símbolos (BTC/ETH/SOL) ≈ 2 minutos.

---

## 3. Las hipótesis PRE-REGISTRADAS

Sobre la geometría **pre-fijada por el resultado publicado** del cementerio —
`kSL=5.0, tpR=6.0, h=1152` (la de +0.0608R), con `kSL=5.0, tpR=10.0` como la
segunda declarada por su CPCV 13/15. **No se busca en el eje de geometría: esa
celda viene de un resultado con fecha, no de una búsqueda nueva.**

- **H1 — concurrencia.** La salida dinámica baja el hold medio y la concurrencia
  media lo bastante para que **`screen_cell` encuentre alguna `risk_frac` con
  DD < 35% y equity final > 1**, corriendo **sin cap** de concurrencia.
- **H2 — perfil.** La misma salida sube el **Sharpe por trade** frente al 0.0377
  de la barrera fija, bajando skew y kurtosis.
- **H3 — la que decide.** El neto tiene el **IC95% entero sobre cero a su propia
  n** (`brecha ≤ 0` vía `frontier_report.frontier_gap`), **y** pasa
  `screen_cell`, **y** clarea **DSR > 0.95** con el `n_trials` de abajo, **y**
  CPCV + PBO.

**H1 y H2 tiran del mismo mando en sentidos opuestos.** Trailing más apretado →
holds más cortos (bien para H1) pero corta ganadores (mal para el neto).
Trailing más suelto → mantiene el perfil de lotería. **El experimento es si
existe un punto donde las dos se cumplen.** Puede que no exista.

### La rejilla, declarada entera (esto ES el `n_trials`)

**Eje único: la regla de salida.** No se cruza con nada.

| Familia | Parámetro | Valores | n |
|---|---|---|---|
| A · trailing por retroceso del MFE | `k` = fracción del pico cedida | 0.33, 0.50, 0.67 | 3 |
| B · breakeven y luego trailing 0.50 | `m` = MFE en R que activa BE | 1.0, 2.0 | 2 |
| C · techo de tiempo agresivo | `T` barras | 96, 288 | 2 |

**`n_trials = 7`.** Nada más. La barrera fija de la celda es el **control** y no
cuenta como trial (es un resultado ya publicado).

**Prohibido en este encargo:** cruzar el eje de salida con el de geometría
(sería 84 × 7 = 588) o con el de convicción. Si el marginal sugiere un cruce,
eso es **otra pre-registración desde cero**, con su `n_trials` contado de nuevo.
Correrlo "ya que estamos" es el jardín de senderos que se bifurcan.

### Divulgación paranoica obligatoria

La celda de geometría se pre-fija, pero **salió de una rejilla de 84**. Junto al
DSR con `n_trials=7` hay que imprimir **también** el DSR con `n_trials=588`.
No es el criterio, es la cota. Que se vea.

---

## 4. Criterio de decisión, fijado antes de mirar

- **Coste primario: 5.00 bps taker + 1 bp slip** — el coste con el que están
  medidas TODAS las cifras del repo. Un config que pasa aquí pasa sin ambigüedad.
- **Coste secundario, reportado al lado: 4.32 bps** (Hyperliquid + referral, el
  techo alcanzable medido). Si algo pasa **solo** a 4.32, es un **pase
  condicionado** a que el cambio de venue sea real, y se etiqueta así. No se
  cuenta como pase.
- **Universo: VIP (`FQ_VIP_PAIRS`)**, que es el que se difunde.
- **Todo neto.** El bruto no sale solo (`cell_stats` levanta).
- **Toda fila con su vara** (`require_own_bar`). Se juzga por la **brecha**,
  jamás por la media.
- **Cartera antes que candidata** (`screen_cell`, sin cap).
- **Desglose por año** al lado del agregado (E9).
- **`g`, `f*` y P(acabar arriba)** junto al E[R] (V4).

---

## 5. Las puertas anti-espejismo de ESTE experimento

Además de las 11 generales del brief de la frontera:

1. **LOOK-AHEAD. Es el riesgo número uno y por goleada.** Un trailing necesita
   el máximo *hasta ahora*, no el de toda la vida del trade. Calcular el MFE
   completo y luego "salir en k×MFE" **usa el futuro** y produce una curva
   preciosa y falsa. **La salida se simula barra a barra, causalmente.**
   → test obligatorio: alimentar una serie cuyo futuro es espectacular y
   comprobar que la salida **no lo ve**.
2. **Orden intrabarra.** Con OHLC de 5m no se sabe si el máximo llegó antes que
   el mínimo. Se hereda la convención **pesimista** de la cosecha
   (`bt_labeler.label_event*`, `pessimistic=True`: empate → gana el stop) y el
   resultado se etiqueta **COTA INFERIOR**. Mezclar convenciones con las del cube
   invalida la comparación.
3. **La cadencia no se toca.** Una salida no filtra entradas: si alguna config
   reduce `n`, es un cap disfrazado y queda descalificada. **`n` constante es
   además la propiedad que hace que la vara no se mueva** — si se mueve, algo
   está mal implementado.
4. **La concurrencia se MIDE, no se asume.** `portfolio_risk.simulate_portfolio`
   **sin cap**. Capear para que el DD pase es el adorno que el repo ya prohibió.
5. **Máximo en la esquina.** Si la mejor `k` es el extremo de la rejilla, el
   rango se acabó y no hay óptimo demostrado. Se dice, no se extrapola.
6. **La trampa de escala.** Un cambio que multiplica bruto y coste por lo mismo
   **no mueve el t-estadístico** (R es un cociente; derivado 2026-08-08). Hay que
   reportar **brecha**, no solo neto: si el neto sube y la brecha no baja, es
   aritmética, no edge.
7. **Salida = taker, siempre.** Un trailing dispara a mercado. Nada de suponer
   maker en la pierna de salida — ese supuesto ya volteó un signo (V2).
8. **Una métrica demasiado limpia es un bug.** Si el WR salta a 70% o el DD cae a
   5%, se busca el fallo de medición **antes** de leerlo como hallazgo.

---

## 6. Qué significa "entregado"

Regla de la casa: *un hallazgo sin invariante que lo haga cumplir es una nota.*

- **Extender `tools/geometry_sweep.py`**, no crear un tool nuevo. Ya re-etiqueta
  con velas reales, ya reusa `bt_labeler.label_event_grid`, ya cuenta `n_trials`.
  Lo que le falta es el eje de salida. *Prefiere editar a crear.*
- **`tests/test_geometry_sweep.py` gana tres tests:**
  - la salida es **causal** (no ve el futuro) → `LookaheadExitError` o equivalente;
  - hereda la convención **pesimista** intrabarra de la cosecha;
  - una salida **no cambia `n`** (si lo cambia, falla).
- **El resultado se rutea** por `frontier_report.require_own_bar` y
  `vip_report.screen_cell`. Ninguna fila se publica sin su vara ni sin cartera.
- **Si sale que no:** a `MEMORY/CEMENTERIO.md` con su n, su rejilla y su
  `n_trials`, y actualizar `MEMORY/ESTADO.md`. **Un diagnóstico que mata una
  línea es buen resultado.**
- Suite completa verde (~45 s) antes de cada commit.

---

## 7. Los desenlaces legítimos

Los tres son buenos resultados. Solo uno es malo.

1. **Existe un punto donde H1+H2+H3 se cumplen** → primer candidato real del
   repo. Entonces: forward, `n≥100`, y **nada a vivo** hasta que el gate entero
   pase (`CONSTITUCION.md`).
2. **H1 sí, H2 no** (baja la concurrencia pero el perfil sigue siendo lotería) →
   el riesgo de cartera deja de ser la causa de muerte y queda **solo** el DSR.
   Es información: dice exactamente qué falta.
3. **Ni H1 ni H2** → la geometría ancha queda **doblemente cerrada** y la salida
   dinámica al cementerio. Se acaba el eje de barreras entero, para siempre, y el
   trabajo se mueve a la única vía estructural que queda (§8).
4. **Malo:** que salga "casi" y se maquille bajando la vara, capeando la
   concurrencia o contando el pase condicionado a 4.32 bps como pase. Eso no es
   un desenlace, es el fantasma otra vez.

---

## 8. (b) — el libro, NOMBRADA y con su puerta puesta. NO se toca aquí.

Se documenta para que nadie la proponga como idea nueva ni la empiece antes de
tiempo.

**Qué es.** `I = (V_bid − V_ask)/(V_bid + V_ask)` sobre órdenes **en reposo**.
**No es lo que ya mides:** `cvd_imbalance` es imbalance de volumen **ejecutado**
(qué se cruzó); esto es qué está **esperando**. Sirve para predecir la selección
adversa del maker **antes** de poner la orden, en vez de descartarla después por
`bars_waited`.

**Por qué importaría.** V2 midió el mecanismo: `corr(P(fill), R) = −0.2267`; los
que se llenan siempre rinden −0.3784R y los que casi no se llenan +0.8548R. Si el
libro predijera eso *ex ante*, se podría ser maker seguro en la pierna de entrada
(1.5 bps en HL vs 4.5 taker) ≈ **+0.065R**, tamaño de frontera.

**Sus cuatro puertas, y ninguna está abierta:**
1. **Prerrequisito del repo (E6):** el **CVD firmado debe pasar el gate forward**
   primero. Está cableado dormido, midiendo, sin veredicto.
2. **Coste real:** MBP-10 es órdenes de magnitud más pesada y cara que aggTrades
   (que es gratis). Se sale del "todo local y gratis".
3. **Fragilidad conocida:** spoofing, cancelaciones, latencia.
4. **Disonancia de escala temporal — la que más preocupa y no está en ningún
   brief previo:** el imbalance de libro decae en **milisegundos** y el motor
   decide sobre velas de **5 minutos**. Para cuando se coloca la orden, el
   desequilibrio medido puede haberse evaporado. **Antes de comprar data, hay que
   contestar si la señal sobrevive al horizonte de decisión** — y esa pregunta
   es barata comparada con la data.

---

## 9. Cómo arrancar

```
python tools/fetch_binance_vision_klines.py BTCUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance
python tools/fetch_binance_vision_klines.py ETHUSDT --start 2019-06-01 --end 2026-06-30 --out-dir data/binance
python tools/fetch_binance_vision_klines.py SOLUSDT --start 2020-08-11 --end 2026-06-30 --out-dir data/binance

python tools/geometry_sweep.py --klines data/binance        # el control ya medido
# ... extender con el eje de salida, y después:
python tools/frontier_report.py                             # la brecha, con su vara
pytest tests/ -q
```

**Coste total estimado: una sesión.** Todo local, gratis, sin API key, sobre data
que ya existe.
