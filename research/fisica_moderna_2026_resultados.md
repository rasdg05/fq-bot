# Resultados — physics_validation (run 28287771057, 2026-06-27, 28m55s, ✓)
Data: 2021-01-01 → 2026-06-27 (2003 días). SOL 976 ev (base +0.165R, WR26%), BTC 1005 ev (base +0.240R, WR29%). ETH: sin cube, skip.

## GANADOR — BTC F2 persist (memoria del flujo, ac1) — ORTOGONAL ✓
| thr | conf n | conf R | uplift std | DSR std | within-CVD uplift | premium n | premium DSR |
|-----|--------|--------|-----------|---------|-------------------|-----------|-------------|
| 0.0 | 321 | +0.545R | +0.305R | **0.997 ✓** | F2✓+0.562 vs F2✗−0.045 → **+0.607R** | 299 | **0.995 ✓** |
| 0.05| 184 | +0.501R | +0.261R | **0.972 ✓** | +0.339R | 165 | **0.959 ✓** |
| 0.10| 172 | +0.481R | +0.241R | **0.966 ✓** | +0.287R | 154 | **0.952 ✓** |
| 0.20| 57  | +0.413R | +0.173R | 0.841 | +0.068R | 49 | 0.812 |
→ Pasa standalone Y ortogonal Y premium-DSR en 3 umbrales (0.0/0.05/0.10). NO knife-edge.
→ Clave: dentro de CVD-confirmado, el NO-persistente es break-even (−0.045R); el persistente +0.562R. F2 RESCATA el CVD.

## F1 impacto — REAL pero REDUNDANTE con CVD (sustituto, no complemento)
- BTC coiled thr 0.0/0.10/0.20/0.30: standalone DSR 0.994/0.993/0.990/0.985 ✓ (fortísimo) PERO within-CVD uplift −0.186/−0.157/−0.022/+0.010 → redundante.
- BTC fragile thr0.5: standalone 0.985✓, within-CVD +0.028, premium 0.969✓ (apenas apila). thr1.0: 0.962✓, +0.220 within, premium 0.940 (casi).
- BTC extended: catastrófico (DSR 0.0–0.32, R negativo).
- SOL coiled thr0.0/0.10: standalone 0.964/0.960✓ pero redundante within-CVD.

## SOL — NADA apila (cementerio)
- F2 persist: DSR 0.791/0.466/0.771/0.640. hurst: 0.833/0.838/0.837. revert: cementerio. F1 extended/fragile: cementerio.
- Teoría: order-splitting/memoria larga = firma de metaórdenes INSTITUCIONALES → fuerte en BTC, débil en SOL (más retail/momentum). Símbolo-específico, como global_ls.

## Validación interna (señal de real, no ruido)
- BTC F2 `revert` (anti-persistencia): DSR=0.000, R fuertemente negativo (−0.21 a −0.28R). Persistencia=bueno, anti=malo. Signo consistente → confirma.
- BTC F2 `hurst`: standalone 0.984/0.970✓ pero redundante within-CVD (la versión ac1=`persist` es la que apila, no el Hurst).

## CONFIRMADO — re-corrida honesta n_trials=44 (run 28298460194, 2026-06-27)
La vara real de multiple-testing del barrido es 44, no 16. Re-corrido BTC F2 persist:
| thr | standalone DSR(44) | within-CVD | premium DSR(44) | veredicto |
|-----|--------------------|------------|-----------------|-----------|
| **0.0** | **0.988 ✓** | +0.607R ORTOGONAL ✓ | n=299 +0.562R **0.985 ✓** | **SOBREVIVE** |
| 0.05 | 0.933 ✗ | +0.339R ortogonal | 0.917 | al cementerio |
| 0.10 | 0.929 ✗ | +0.287R ortogonal | 0.914 | al cementerio |
→ **thr=0.0 aguanta el bar honesto** (standalone Y premium). Es además el límite natural
de la teoría (ac1>0) y el de mayor muestra (n=299) — no un threshold cherry-picked. Los
umbrales más altos NO sobreviven n=44 (por eso se hizo el re-check). 2×2 fuera del CVD:
F2✓ +0.307 vs F2✗ +0.149R (n=22, no se cuelga de eso).

LUZ VERDE para cablear BTC thr=0.0 (FQ_PERSIST_THR=0.0 ya es el default). Activación:
FQ_CVD_FILTER=1 + FQ_CVD_BOOST_TIER=1 + FQ_PERSIST_BOOST=BTC en Railway. El motor paper
lo sigue midiendo forward.
