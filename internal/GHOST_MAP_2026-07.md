# El Fantasma — mapa medido del motor FQ (2026-07-05)

> Radiografía measure-first del motor por dentro, contra su propia cosecha. **Cube bruto**
> (etiquetas triple-barrera, sin coste de ejecución). Es el MAPA, no el veredicto: cada
> hallazgo accionable termina en "correr el gate honesto (DSR/CPCV/PBO)". Visual:
> `scratchpad/fantasma.html`. Data: `cosecha_cubes/*.parquet` + `data/**/kl_hist_*.parquet`.

## Data a la mano (el lienzo)
- **Cubos etiquetados:** 2019-06 → 2026-06, **7.0 años**, **13 símbolos**, **13,429 señales
  canónicas** (fired=True, dedup por entry_ts; 161k filas con ×tp×horizon).
- **Klines 5m crudos:** **5.58M velas** (~53 símbolo-años), 2020/2021 → 2026, 12 símbolos
  (falta DOGE en 5m; tiene daily).
- **Order-flow (CVD):** 6-7 símbolos, ~200k barras c/u (`data/cvd_hist_*.parquet`).
- **Funding:** 13 símbolos, ~7k puntos 8h (`data/longgates/fund_*.parquet`).
- **Daily + on-chain BTC:** `data/longgates/daily_*`, `onchain_btc.parquet`.

## Método
Por cada señal `fired` (tp4/h288) se recomputó la **irreversibilidad KL** (grafo de
visibilidad, `tools/validate_regime_irreversibility.irreversibility`) sobre las **64 velas
previas a la entrada**, alineando `entry_ts` con el klines más ancho por símbolo. 11,729 de
13,429 señales quedaron taggeadas (resto = pre-historia de klines o DOGE). Barrido de umbral,
corte direccional por año, escalera de TP, MFE/MAE, por símbolo.

## Hallazgos

### H1 · La dirección es simétrica a escala (el espejismo de mayo)
- Live mayo: 16/16 shorts ganan, 7/7 longs pierden → parecía ley direccional.
- 7 años, pool: **SHORT +0.225R (n=6,692) vs LONG +0.223R (n=5,037)**. Un volado.
- Se voltea por año: 2020-22 pagó LONG (+0.36–0.46 vs +0.05–0.29), 2023-25 pagó SHORT
  (+0.21–0.32 vs +0.08–0.11). 2026 casi empata (+0.28 vs +0.26).
- **Lectura:** cualquier sesgo direccional del motor es apuesta de RÉGIMEN, no edge
  estructural. El short-compulsivo de junio-26 (7 shorts al stop, −8.1R en paper) fue el
  motor peleando el régimen equivocado.

### H2 · El filtro KL cuesta cadencia sin salvar de pérdidas
- Baseline sin filtro: **+0.224R** × 11,729 = **+2,628R**.
- Con KL thr=0.34 (el del bot): **+0.253R** × 6,782 = **+1,715R** (pasa 57.8%).
- Suprimidos (KL-high): **+0.185R** — POSITIVOS. El filtro no separa ganadores de
  perdedores; separa ganadores-grandes de ganadores-chicos.
- **Neto capturas MENOS R total con el filtro** (1,715 vs 2,628) porque cortas 42% del flujo.
- Valor real del KL: en las **colas** (regímenes tipo junio-26), no en el agregado.

### H3 · El umbral óptimo es más flojo que 0.34
- Barrido: totR capturado sube hasta thr≈0.40 (**+2,248R**, pasa 74%) y **la separación
  low−high es MÁXIMA ahí (+0.138R)**. A 0.50-0.60 satura (~2,300R).
- El bot a 0.34 gatea de más: menos captura Y peor separación que a 0.40.
- **Candidato #1 a gate:** "aflojar KL de 0.34 → 0.40".

### H4 · El scoring maestro no separó (en la muestra live)
- 23 señales live: longs perdedores (p_master 1.85–2.15) y shorts ganadores (1.8–3.7)
  indistinguibles por p_master. La dirección+régimen explican el outcome; la convicción
  numérica, poco.
- **Candidato a auditar en cube:** ¿p_master separa avgR fuera de la muestra chica? (correr
  decil de p_master vs pnl_r sobre los 13k).

### H5 · Forma del edge: baja WR, alta R, swings grandes
- Escalera TP (pool, h288): tp1 48.5%/+0.141R · tp2 37.0%/+0.168R · tp3 31.7%/+0.201R ·
  tp4 27.9%/+0.231R. Sube R al estirar objetivo.
- MFE medio **+6.66R**, MAE medio **−5.65R**, duración media **3.2h**. Corre lejos en ambos
  sentidos antes de resolver.
- **Lectura:** motor de pocos aciertos grandes. La gestión de stop/parciales es donde se
  gana o se tira el edge (MAE −5.65 dice que muchos ganadores pasan MUY en contra primero).

### H6 · El edge no está parejo entre símbolos
- Top R total: BCH +531, ETH +324, AVAX +313, LTC +295, BTC +226. Cola: XRP +100, TRX +27.
- Mismo motor, misma cosecha — el edge vive con distinta fuerza en cada tape. Candidato a
  ponderar exposición por símbolo (con cuidado de no sobreajustar al pasado).

### H7 · El silencio del VIP no es falta de setups
- Backtest dispara 140–183 señales/mes en 2026 (pool). VIP live: 10 días mudo.
- El abismo = **stack de gates del live** (KL 0.34 + ruteo de tier + solo 3–5 símbolos
  activos), no ausencia de señal. El motor tiene flujo de sobra en la cosecha.

## GATE HONESTO (2026-07-05) — corridas DSR/CPCV/PBO sobre H2 y H4

> El gate hizo su trabajo: frenó DOS sobreajustes. Ambos módulos tienen edge REAL pero
> MODESTO, enterrado en ruido. La jugada honesta: usarlos como **diales gruesos**, no como
> perillas finas. Harness: `tools/validation_gate.py`.

### GATE-A · Filtro KL: 0.34 vs 0.40 vs sin-filtro (n=11,729)
- **CPCV OOS (15 caminos):** sin-filtro +0.224R · KL-0.34 +0.254R · KL-0.40 +0.261R.
  El filtro le gana a sin-filtro en **14/15 folds** (+0.037R) → el filtro KL es EDGE REAL OOS.
- **0.40 vs 0.34:** gana solo 10/15 folds por +0.007R → **indistinguibles**.
- **PBO = 0.897 (ALERTA):** optimizar el umbral ES sobreajuste. El thr ganador salta bloque a
  bloque (0.05→0.6, sin patrón). El "0.40 óptimo" del pool era ruido.
- **DSR = 1.000** para los tres (incl. sin-filtro): el edge base sobrevive multiple-testing.
- **Bootstrap sep(low−high)@0.40:** +0.138R, IC95%[+0.049,+0.224], P(>0)=100%.
- **VEREDICTO:** el filtro KL PASA como filtro (guardarlo), FALLA como parámetro fino.
  Aflojar 0.34→0.40 es un **dial de cadencia seguro** (mismo edge OOS, pasa 74% vs 58% →
  más señales) — NO porque 0.40 sea óptimo, sino porque el edge es insensible al umbral en
  [0.10, 0.40]. **Es la respuesta segura al "bot muy lento": más cadencia sin perder edge OOS,
  mucho más barato que saltar a 1m (que exige re-validar todo).**

### GATE-B · ¿p_master separa? (n=13,429)
- **Decil:** monótono-ruidoso. Decil-1 +0.129R/25.5%WR → decil-10 +0.347R/30.7%WR (extremos
  sí difieren ~2.7×), pero con dip en decil-5 (+0.068).
- **Spearman rho=+0.025 (p=0.003):** significativo SOLO por n gigante; efecto **≈ cero**. Por
  señal, p_master casi no rankea. (El "no separó" de las 23 live fue muestra chica, otra vez.)
- **CPCV OOS top-30% vs bottom-30%:** spread +0.101R, top gana **13/15 folds**, bootstrap
  P(>0)=97.5% → en las COLAS sí separa, y aguanta OOS.
- **Por dirección:** LONG rho=+0.039 (p=0.003), top-bot +0.155R → **separa en longs**.
  SHORT rho=+0.015 (p=0.18), +0.052R → **NO separa en shorts**.
- **VEREDICTO:** p_master NO es decoración pero es un **ranker débil**. Sirve como dial grueso
  de 3 buckets (confiar el tercil-alto), sobre todo en LONGS. NO como score fino de convicción.
  Candidato: size por tercil de p_master en longs; ignorarlo en shorts.

### Lección transversal
Los dos módulos + el sesgo direccional (H1) cuentan la misma historia: **edge real, modesto,
ahogado en ruido; la muestra chica miente (mayo, 23 señales) y el n grande revela el susurro.**
El gate previno dos overfits (umbral KL, score p_master). Measure-first funcionó.

## Preguntas abiertas para deep-search / gate
1. ¿"Aflojar KL 0.34→0.40" pasa DSR/CPCV/PBO out-of-sample, o el barrido está sobreajustado
   al pool completo? (correr CPCV con folds temporales).
2. ¿El motor debe ser **direccionalmente neutro** (tomar long y short según régimen) en vez
   de sesgado? ¿Qué señal de régimen predice qué lado gana el próximo trimestre?
3. ¿p_master aporta separación real fuera de muestra, o es decoración? (decil vs pnl_r en 13k).
4. ¿La gestión de MAE (−5.65R medio antes de ganar) se puede mejorar sin matar los ganadores
   grandes? (¿stops más anchos + size menor?).
5. ¿Por qué XRP/TRX no separan? ¿Microestructura, o el edge es cripto-beta disfrazada?
6. Coste de ejecución real: el cube es bruto. ¿Cuánto del +0.224R sobrevive slippage/funding/
   fills parciales? (el showcase asumió ~0.15R; validar contra el ledger real).

## Reproducción
```
# tag KL por señal + barrido:  (script ad-hoc, ver historial de sesión)
# cubos:   cosecha_cubes/tp_cube_{SYM}_USDT.parquet   (cols: direction, pnl_r, tp, horizon, fired, ...)
# regimen: tools/validate_regime_irreversibility.irreversibility(closes[-64:])
# thr bot: FQ_KL_THR=0.34 ; filtro activo por FQ_KL_FILTER
```
