# ORO (GC) — Gate v2: killzones re-ancladas al reloj CME

**Fecha:** 2026-07-06 · **Spec:** `internal/ORO_SESION_KILLZONES_2026-07.md` · **Generador:** el MISMO runner real del motor (`tools/run_research_real.py`, fires-only, `--tf-id 5m --seed 42 --min-lookback 300 --step 1`); lo único que cambió entre ANTES y DESPUÉS es el reloj de killzones (monkeypatch runtime de `killzones_pd`, cero cambios al repo).

## 0. Data y advertencia de honestidad

- OHLCV 5m GC (Databento GLBX.MDP3, UTC naive): 31905 barras, rango 2021-01-03 23:00:00 → 2025-12-31 18:00:00; ventana evaluada por el replay: 2021-01-28 12:00:00 → 2025-12-31 18:00:00 (**59.07 meses**).
- ⚠️ OHLCV 5m sub-muestreado (~532 barras/mes vs ~8600 reales de GC): fires/mes es sobre HISTORIA MUESTREADA, igual para antes y despues -> la comparacion A/B es valida; el nivel absoluto NO es densidad de produccion.
- CVD firmado con aggressor side REAL (Tag 5797 vía Databento `side`), buckets 5m; 73% de los buckets con volumen firmado.

## 1. Killzones v2 (ET, DST por-timestamp) y gate-outs

- **LONDON_OPEN**: 3.00–5.00 ET
- **NY_COMEX**: 8.00–10.50 ET
- **FOMC_PM**: 14.00–15.00 ET
- GATE-OUT **SETTLE_1325_1335**: 13.42–13.58 ET (veto duro)
- GATE-OUT **HALT_1655_1805**: 16.92–18.08 ET (veto duro)

## 2. Fires: ANTES (reloj cripto) vs DESPUÉS (reloj CME)

| métrica | ANTES | DESPUÉS (strict KZ) |
|---|---|---|
| señales únicas (59 meses) | 4 | 3 |
| señales/mes | 0.0677 | 0.0508 |

**Cadencia: ×0.8** respecto al reloj cripto. El motor v2 disparó 3 señales en total; 0 cayeron fuera de las killzones ORO (vía confluencia≥5) y se DESCARTARON del cube v2 (estricto): {}.

- ANTES por killzone (labels cripto): {'london_open_kz': 2, 'fuera': 1, 'ny_am_kz': 1}
- ANTES mapeado al reloj ORO: {'fuera': 3, 'NY_COMEX': 1}
- DESPUÉS por killzone ORO: {'NY_COMEX': 2, 'LONDON_OPEN': 1}
- DESPUÉS por dirección: {'-1': 2, '1': 1}

## 3. Outcomes (triple-barrier idéntico al cube cripto: SL del motor, ladder tp1..tp4, horizontes 96/288/576 velas 5m, empate pesimista)

Celda canónica (**tp1 / h96** — definición de win del ledger):

- ANTES:   n=4  WR=100%  avgR=+1.186  totalR=+4.74  SR/trade=2.116
- DESPUÉS: n=3  WR=100%  avgR=+1.524  totalR=+4.57  SR/trade=2.812
  - dirección +1: n=1  WR=100%  avgR=+0.925  totalR=+0.93
  - dirección -1: n=2  WR=100%  avgR=+1.824  totalR=+3.65  SR/trade=8.202

Por killzone (DESPUÉS, tp1/h96):
- LONDON_OPEN: n=1  WR=100%  avgR=+1.667  totalR=+1.67
- NY_COMEX: n=2  WR=100%  avgR=+1.453  totalR=+2.91  SR/trade=1.947

Referencia cube viejo entregado (`gold_cube_test.parquet`): 1 señal(es); celda canónica n=1  WR=100%  avgR=+1.175  totalR=+1.17; killzones {'london_open_kz': 1}

Grid TP×horizonte (DESPUÉS):

| tp | horizonte | n | WR | expectancy_R | total_R |
|---|---|---|---|---|---|
| tp2 | 576 | 3 | 1.00 | 2.467 | 7.40 |
| tp2 | 288 | 3 | 1.00 | 2.467 | 7.40 |
| tp2 | 96 | 3 | 0.67 | 2.078 | 6.23 |
| tp4 | 576 | 3 | 0.67 | 1.929 | 5.79 |
| tp4 | 288 | 3 | 0.67 | 1.929 | 5.79 |
| tp1 | 576 | 3 | 1.00 | 1.524 | 4.57 |
| tp1 | 96 | 3 | 1.00 | 1.524 | 4.57 |
| tp1 | 288 | 3 | 1.00 | 1.524 | 4.57 |
| tp3 | 288 | 3 | 0.67 | 1.497 | 4.49 |
| tp3 | 576 | 3 | 0.67 | 1.497 | 4.49 |
| tp4 | 96 | 3 | 0.33 | 1.231 | 3.69 |
| tp3 | 96 | 3 | 0.33 | 0.954 | 2.86 |

## 4. Gate CVD firmado (Tag 5797 real; metodología de `tools/validate_cvd_signed_flow.py`: ventana causal 48 buckets, win=24)

- **imb_0.55** (n=3): confirmado [n=0] vs no-confirmado [n=3  WR=100%  avgR=+1.524  totalR=+4.57  SR/trade=2.812]  → uplift avgR n/a
- **imb_0.50** (n=3): confirmado [n=0] vs no-confirmado [n=3  WR=100%  avgR=+1.524  totalR=+4.57  SR/trade=2.812]  → uplift avgR n/a

## 5. Gate estadístico (honesto, con n's)

Trials declarados: {'relojes': 2, 'celdas_tp_x_h': 12, 'umbral_cvd': 2, 'n_trials_seleccion_celda': 24, 'n_trials_con_cvd': 26} — la tabla de killzones v2 se fijó A PRIORI desde la deep-research (1 variante, sin tuning loop; ver la trampa nombrada en la spec: no re-afinar hasta que dispare).

- Dispersión de Sharpes entre trials computados: n=21, std=1.104
- **DSR** (celda canónica v2): {"sr": 2.8120282948026682, "sr0": 2.1855088423419544, "dsr": 0.6884318873076237, "significant": false, "n": 3, "n_trials": 24, "skew": -0.44896896390766, "kurt": 1.4999999999999993, "tag": "v2 celda tp1/h96, n_trials=24", "verdict": "UNDERPOWERED/NO-PASA (n=3)"}
- Poder estadístico: {"sr0_vara_azar": 2.1855088423419544, "estimacion": {"n_req": 56.459984016302855, "n_obs": 3, "extra_months_estimate": 1052.3618900847018}}
- **PBO**: {"verdict": "UNDERPOWERED: matriz [3, 12] < 8 filas"}
- **CPCV**: {"verdict": "UNDERPOWERED: n=3 < 12 trades para 6 grupos"}

## 6. Veredicto

**UNDERPOWERED — el gate no se puede decidir con esta muestra; el cuello de botella es la DENSIDAD de la data, no el reloj.**

- El re-anclaje hace su trabajo cualitativo: con el reloj cripto **3 de 4 fires caían FUERA** de las killzones reales del oro; con el reloj CME **3 de 3 caen dentro** (NY_COMEX×2, LONDON_OPEN×1). El motor ahora muestrea donde el oro vive.
- Pero la cadencia total no sube (×0.8) porque el OHLCV está sub-muestreado ~1:16 (532 vs ~8600 barras/mes reales de GC): el motor simplemente no ve suficientes barras para disparar más. Con esta densidad, más meses de calendario no arreglan nada.
- Lo que disparó, pegó: 4/4 antes y 3/3 después ganan en tp1 (avgR v2 +1.52) — pero n=3 no es evidencia, es anécdota (DSR 0.69 < 0.95; PBO y CPCV incomputables con n=3).
- CVD: 0/3 señales confirmadas por el flujo firmado (umbral 0.50 y 0.55) — la capa CVD ni siquiera engancha con esta densidad de buckets.

**Próximo paso real (decisión de compra, no de ingeniería):** bajar la historia GC a densidad completa de Databento (GLBX.MDP3, trades + ohlcv-1m, 2017→hoy — el aggressor side solo existe desde MDP3.0 ~mar-2017; CME va a ~$0.50/GB y hay $125 de crédito) y re-correr ESTE MISMO pipeline, que ya quedó construido y determinista (driver + análisis + gate). Hasta entonces el oro queda en **COSECHA**: nada opera sin DSR>0.95 + CPCV + PBO.

## Archivos

- `/tmp/cme/gold_cube_v2.parquet` — cube re-anclado (estricto, evento × tp × horizonte, esquema canónico + `gold_kz`)
- `/tmp/cme/gold_cube_before_repro.parquet` — baseline reproducido mismo rango (control)
- `/tmp/cme/gold_gate_v2_results.json` — todos los números
- `/tmp/cme/events_before.parquet`, `/tmp/cme/events_after.parquet` — eventos crudos del replay
- driver: `/tmp/cme/run_gold_v2_driver.py`; análisis: `/tmp/cme/analyze_gold_v2.py`
