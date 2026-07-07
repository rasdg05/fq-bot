# EXPERIMENT — π_blade: escalera de TPs adaptativa al régimen KL ("el otro filo")

> RasDG 2026-07-07: *"contra-ingeniería a nuestras desventajas para sacar filo al otro
> extremo del cuchillo — que no solo corte mantequilla, también pan y mantequilla."*
> Diseño v2 (pre-registrado ANTES de correr el gate). Regla intacta: **nada se cablea sin
> DSR>0.95 + CPCV + PBO**, y este doc fija la política y cuenta los trials A PRIORI para
> que el gate no sea teatro.

## 1. Hallazgos exploratorios que motivan (cube 7yr, majors BTC/ETH/SOL, n=3,159 señales × tp × h)

**(a) La inversión está REFUTADA.** En KL alto (irrev>0.50, n=742), 582 señales alcanzan
+1R a favor antes que −1R en contra → la señal espejo pierde −0.78R. El filo opuesto no es
operar al revés.

**(b) El régimen mata la escalera desde la punta (h96, avgR):**

| TP | KL bajo (≤0.34) | KL alto (>0.50) | delta |
|---|---|---|---|
| tp1 | +0.230 | +0.164 | −0.066 |
| tp2 | +0.252 | +0.085 | −0.167 |
| tp3 | +0.272 | +0.057 | −0.216 |
| tp4 | +0.282 | +0.032 | **−0.250** |

**(c) El crossover define la hoja en irrev ≈ 0.50 (no 0.34/0.40):**

| bin irrev | tp1 | tp2 | tp3 | tp4 | mejor | n |
|---|---|---|---|---|---|---|
| 0.00–0.15 | +0.256 | +0.304 | +0.304 | +0.314 | tp4 | 1344 |
| 0.15–0.34 | +0.137 | +0.079 | +0.164 | +0.170 | tp4 | 383 |
| 0.34–0.50 | +0.126 | +0.109 | +0.136 | **+0.185** | tp4 | 680 |
| 0.50–0.75 | **+0.137** | +0.042 | +0.027 | +0.021 | tp1 | 408 |
| 0.75–1.20 | **+0.159** | +0.145 | +0.088 | +0.012 | tp1 | 231 |
| 1.20+ | **+0.282** | +0.121 | +0.104 | +0.119 | tp1 | 103 |

La estructura es monótona y estable entre bins: escalera completa hasta ~0.50, reversión
corta después. **θ_blade = 0.50 queda fijado por esta tabla, una sola vez — no se re-tunea.**

## 2. Políticas candidatas (EXACTAMENTE dos; nada más entra al gate)

- **π_blade** (agresiva): irrev ≤ 0.50 → escalera completa (gestión actual);
  irrev > 0.50 → **señal tomada all-out en TP1, maker-only**. Nota: esto además
  *rescata* la banda 0.34–0.50 que el filtro actual suprime (+0.185 tp4 in-sample) —
  el rescate es parte de π_blade y se evalúa dentro de la política, NO como cambio de
  umbral aparte (GATE-A: PBO 0.897 al tunear umbrales — no threshold-shopping).
- **π_blade⁻** (conservadora): status quo hasta 0.40 (supresión 0.40–0.50 intacta) +
  TP1-only en irrev > 0.50. Aísla el efecto "hoja corta" del efecto "rescate de banda".

Baseline: política actual (suprimir todo irrev > FQ_KL_THR).

## 3. Gate (pre-registrado)

1. **Costos DENTRO del gate**: TP1 es el take más sensible a ejecución (medido: TP1 taker
   = ruina). π_blade nace maker-only: fill maker con probabilidad de fill MEDIDA del
   ledger del motor paper (maker_sim/maker_exec); no-fill → señal perdida (no taker
   fallback en el modo TP1). SL siempre taker.
2. **CPCV temporal** (15 caminos, purge+embargo por solape de labels) por símbolo, y
   **holdout cross-symbol** (política evaluada en cada símbolo sin re-fitear nada — no
   hay parámetros que fitear, θ_blade es constante).
3. **DSR** con **n_trials declarado = 37**: 8 celdas del grid TP×régimen + 24 celdas de
   la tabla de crossover + 2 políticas + 3 de análisis previos de inversión/alineación.
   Todo lo mirado cuenta.
4. **PBO** sobre la familia de configs {baseline, π_blade, π_blade⁻} × celdas del grid.
5. Veredicto binario por política. Si ambas pasan, gana π_blade⁻ (conservadora) para el
   primer cableado; π_blade queda para el forward.

## 4. Ejes pre-registrados PARA DESPUÉS del gate primario (no se miran antes)

- **Alineación con la tendencia**: signo del retorno de 64×5m en la entrada (la MISMA
  ventana del detector KL — el detector define su propia dirección). El cube no lo trae
  (field_bias_4h llegó NEUTRO del harvest); se computa del OHLCV (data/okx). Hipótesis:
  en KL alto, la señal CONTRA la tendencia es la que pierde la escalera; la alineada
  podría conservarla. Se mide como refinamiento de π_blade con su propio conteo de trials.
- **Sizing por régimen** (barbell tipo conviction): NO entra en v1. Un knob a la vez.

## 5. Forward (si el gate pasa)

- Runtime paper π_blade en majors (la infra YA existe: `MotorPaperRuntime(tp_key=...)` +
  `kl_regime_live()` por barra; el tp_key se vuelve función del irrev del fire).
- 30 días, criterio de aceptación pre-registrado: avgR forward dentro del IC 80% del
  estimado del cube para la celda correspondiente, y cero envíos VIP (paper, 0% real).
- Cableado eventual: `FQ_KL_TP_ADAPTIVE` (default **OFF** → byte-idéntico).

## 6. Qué esperar (honesto)

- **NO arregla las sequías por colapso de fires** (jun-2026 fue eso: el motor no disparó).
  Convierte en señal los periodos tendenciales CON fires: ~+43% de señales en majors
  (742 sobre 1,727 en 7yr) a ~+0.164R in-sample antes del gate.
- El +122R acumulado in-sample es techo optimista pre-costos y pre-deflación. El gate
  dirá el número real.
- La deep-research del filo momentum (regime-switching continuation) corre en paralelo;
  si trae un motor de continuación genuino con evidencia, se diseña con SU propio doc.

## Datos y reproducibilidad

Pool: `/tmp/ghost_tagged.parquet` (11,729 fires 12 símbolos con irrev, ventana 64×5m) +
`cosecha_cubes/tp_cube_{BTC,ETH,SOL}_USDT.parquet` (celdas tp×h, mfe/mae). Los números de
las tablas de arriba salen del join por (entry_ts, symbol), h=96, fired=True.
