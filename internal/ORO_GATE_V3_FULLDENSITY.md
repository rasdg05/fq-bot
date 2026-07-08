# ORO (GC) — Gate v3 FULL-DENSITY

> ⚠️ **CORRECCIÓN (2026-07-08, misma sesión) — leer PRIMERO.** La sección §2-§4 de abajo
> concluyó "artefacto direccional / label roto / oro no sirve". Al pedir el usuario retomar el
> oro, diagnostiqué la causa raíz y **el veredicto cambió**: el split 96.6%/5.6% era un
> **look-ahead en `analyze_gold_v2.py`** (mi harness de análisis incluía la BARRA DE ENTRADA en
> el etiquetado; combinado con el fill maker-en-extremo — short llena alto 0.70, long llena bajo
> 0.38 — fabricaba la patología). **NO estaba en el motor de producción ni en `bt_labeler`; las
> validaciones cripto NO están afectadas.**
>
> **Re-etiquetado CAUSAL (desde la barra siguiente, j+1), n=232 (CME):**
>
> | reloj | n | WR | avgR | SR/trade | CPCV paths+ | DSR |
> |---|---|---|---|---|---|---|
> | ANTES (cripto) | 407 | 53.8% | +0.085 | 0.089 | 80% | 0.000 |
> | **DESPUÉS (CME)** | 232 | **56.9%** | **+0.160** | **0.170** | **100%** | 0.000 |
>
> Por dirección (CME): short +0.131 (n=137) · long +0.201 (n=95) — **BALANCEADO, sin patología.**
>
> **Veredicto corregido:** (1) el oro tiene señal **real, balanceada y débilmente positiva**;
> (2) el re-anclaje de killzones al reloj CME **MEJORA medible** (avgR +0.085→+0.160, CPCV
> 80%→100% paths positivos) — la tesis de sesión se valida; (3) **pero NO PASA el gate**: SR/trade
> 0.170 es genuinamente débil, DSR 0.000 tras deflación honesta. Es edge real, insuficiente para
> certificar.
>
> **La decisión cambia:** NO es "el pipeline está roto" — el motor está bien, mi harness tenía el
> bug. El oro es una señal débil-pero-real que el re-anclaje ayuda pero no empuja sobre la línea.
> **El próximo paso de mayor EV vuelve a ser la Fase 2 CVD** (comprar los trades dirigidos a los
> fires, ~$15-25): con labels limpios y re-anclaje funcionando, la confirmación order-flow podría
> concentrar el edge y subir el Sharpe sobre el umbral. Sí es, después de todo, una compra de data
> — me equivoqué al decir que ya no lo era. Oro sigue en cosecha hasta que el CVD (u otra
> concentración) lo suba, pero el camino está claro y es barato.
>
> ---
> *(Lo que sigue es el análisis ORIGINAL con la conclusión errónea, conservado como registro del
> error y su corrección — measure-first incluye documentar cuando uno mismo se equivoca.)*

# ORO (GC) — Gate v3 FULL-DENSITY [análisis original, corregido arriba]

> Compra Databento ejecutada ($11.59, ohlcv-1m GC.**v.0** 2017→2026 — la simbología correcta;
> GC.c.0 de julio era el bug de contrato muerto). 3.17M barras 1m → 640k barras 5m (densidad ×20
> real). Replay shardeado (8 shards, 2 relojes) sobrevivió DOS restarts de contenedor gracias a
> checkpoints por shard. Gate corrido con n REALES. Complementa ORO_GATE_V2 (que era underpowered
> por data rota) y ORO_SESION_KILLZONES (la spec de killzones).

## 1. Fires: la densidad despertó al motor (el re-anclaje funciona)

| | reloj cripto (antes) | reloj CME (después) |
|---|---|---|
| fires únicos (109 meses) | **407** | **232** (206 en killzone estricta) |
| fires/mes | 3.73 | 1.89 |
| en killzones ORO reales | 116 de 407 (**71% caía FUERA**) | 206 de 206 (**100% dentro**) |

Killzones después: NY_COMEX 87 · FOMC_PM 72 · LONDON_OPEN 47. El re-anclaje hace su trabajo
cualitativo: con reloj cripto el 71% de los fires caían fuera de las ventanas reales del oro; con
reloj CME, todos dentro. **Y ya no es n=3 — es n=206.** La compra valió por esto.

## 2. El gate: NO PASA — y el porqué es un ARTEFACTO, no "el oro no sirve"

**Celda canónica tp1/h96, después (CME), n=206:** avgR **+0.164**, WR 57%, Sharpe/trade 0.158.
- **CPCV** (15 caminos): 93% de paths positivos, SR mediana 0.150 — consistente.
- **PBO**: 0.0 — limpio.
- **DSR**: **0.042 — NO PASA.** El Sharpe observado (0.158) queda BAJO la barra deflactada por
  24 trials (SR0=0.277). "Más historia no arregla el signo": el efecto neto es real pero chico,
  por debajo del umbral de multiple-testing.

**Pero al abrir por dirección aparece la patología:**

| dirección | n | WR | avgR |
|---|---|---|---|
| SHORT (−1) | 117 | **96.6%** | +0.955 |
| LONG (+1) | 89 | **5.6%** | −0.875 |

Un split 96.6% / 5.6% sobre 206 trades **no es edge de mercado — es imposible que lo sea.** El
+0.164 agregado es el promedio de un libro-short falso-bueno con un libro-long falso-malo.

## 3. Diagnóstico: el etiquetado triple-barrier NO transfiere a la microestructura del oro

Descarté las causas triviales y aislé la real:
- **Geometría de niveles: LIMPIA.** Cero stops/tp1 invertidos; RR1≈0.9 simétrico en ambas
  direcciones (short risk 8.3 / tp1 7.75; long risk 7.4 / tp1 7.3). No es bug de signo.
- **Retorno forward real (ground truth de a dónde fue el precio) CONTRADICE el label:** el
  retorno a 96 barras (8h) post-fire es **~neutro** (mediana +4.9bps, media −3.7bps, 46% negativos).
  Peor aún para la tesis del artefacto: shorts van seguidos de −15.6bps y longs de **+13.6bps** —
  o sea, *en el precio real ambas direcciones aciertan levemente*. Por año, el sign-hit de shorts
  y longs es ~balanceado (30-67% vs 36-100%), NO el 96.6/5.6 que produce el label.

**Conclusión del diagnóstico:** el triple-barrier con estos niveles apretados (RR≈0.9) + el
tie-break pesimista intra-barra, aplicado a los rangos high-low reales del 5m de oro, **fabrica
outcomes que contradicen el movimiento real del precio.** El label dice "short gana 96.6%"; el
precio dice "ambas direcciones ~neutras". El label está roto para el oro, no el mercado.

## 4. Veredicto: **ORO SIGUE EN COSECHA. El bloqueo es de PIPELINE, no de data.**

- El gate NO PASA, y encima **no es interpretable** hasta arreglar el etiquetado — un pass o un
  fail sobre labels que contradicen el forward return no significan nada.
- Lo que la compra de densidad compró (y valió cada centavo): con n=3 habríamos *shippeado el
  espejismo* ("3 señales, todas ganaron +1.5R" era ESTA patología escondida en muestra chica).
  Con n=206 se ve que es un artefacto direccional del pipeline.
- **El verdadero próximo paso es ingeniería, no otra compra:** recalibrar el labeler + la mecánica
  de fill maker para la microestructura del oro (bar-range, tick size, RR mínimo viable), O aceptar
  que el oro necesita su motor propio (lo que apunta la investigación de sesión/killzones:
  continuación en NY, no reversión con niveles de cripto). Hasta entonces, oro NO entra al cubo.

## 5. Lo que quedó medido y es sólido
- Simbología correcta: **GC.v.0** (active-volume), no GC.c.0.
- Densidad: 640k barras 5m 2017→2026, en `data/cme/GC-USDT_{1m,5m,15m,1h}.parquet`.
- El re-anclaje de killzones al reloj CME **funciona** (71% fuera → 100% dentro).
- La patología short/long es **estable 9 años y en ambos relojes** → inherente al pipeline gold,
  no al re-anclaje.

## Reproducibilidad
Eventos: `/tmp/cme/events_full_{before,after}.parquet` (merge de 8 shards). Resultados:
`/tmp/cme/gold_gate_v3_results.json`. Driver: `/tmp/cme/run_gold_v2_driver.py`. Análisis:
`/tmp/cme/analyze_gold_v2.py`. Data comprada determinista: ohlcv-1m GC.v.0 2017-06-01→2026-07-05.
Fase 2 (trades dirigidos a fires para CVD, ~$0.18/día) queda EN PAUSA hasta arreglar el labeler.
