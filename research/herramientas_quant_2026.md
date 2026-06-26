# Herramientas, data y algoritmos de los pros/fondos quant — qué mueve el rendimiento

> Deep-research verificada adversarialmente (jun 2026): 5 ángulos, ~22 fuentes,
> **13 claims confirmados a 2/3 votos, 0 refutados.** Foco: qué puede adoptar un bot
> de perps chico (Python, OKX/Binance) para mejorar el rendimiento OOS neto. Citas al final.

## TL;DR — el #1 no es data nueva, es VALIDACIÓN rigurosa
La investigación invierte el instinto de "más señales". El lever mejor evidenciado
y más barato es **tooling de validación** (Deflated Sharpe + CPCV) — la versión formal
de la disciplina que ya practicamos. Después: **data de microestructura** (CoinGlass,
y el signal evidenciado es **CVD/order-flow firmado, NO volumen crudo**). Después:
**sizing** (vol-targeting + HRP). El ML/regime va **último** (hasta una buena combinación
ML+HMM no pasó significancia tras corregir multiple-testing).

## 1. VALIDACIÓN — el lever subestimado (free, gatea todo) ⭐
- **Deflated Sharpe Ratio (DSR)** es el go/no-go decisivo: corrige el Sharpe observado
  por las 2 fuentes de inflación — **multiple-testing** (overfitting de backtest) y
  retornos no-normales. [1][2]
- **Multiple testing hace casi inevitable un Sharpe espurio alto:** ~**20 trials** ya dan
  un "5% significativo" falso; un Sharpe 2.5 sobre 5a diario puede ser **insignificante**
  una vez que declarás N. El umbral DEBE subir con N. [2]
- **Purging + embargo** (embargo ≈1% de las barras) para data no-IID; el k-fold normal
  filtra. **CPCV (Combinatorial Purged CV) supera a walk-forward** (menor PBO, mejor DSR)
  — el backbone recomendado. (Caveat: la superioridad de CPCV se probó en entorno
  sintético controlado, no en vivo.) [3][4]
- **Implicación para NOSOTROS:** ya hacemos walk-forward purged+embargo (vamos bien).
  El upgrade formal: **DSR sobre nuestras corridas** — esta sesión probamos MUCHAS ideas
  (F3, volumen, momentum, trailing, pairs, carry...). DSR nos diría **cuánto deflactar**
  el +0.10R / el Sharpe del carry por el número de trials. Es el gate honesto que falta.

## 2. DATA de microestructura — CoinGlass, y el signal es CVD/OFI (no volumen)
- **CoinGlass = el upgrade de data prioritario:** agrega OI, funding, liquidaciones
  (+heatmaps), long/short, taker buy/sell, **CVD**, opciones (Max Pain), ETF flows, sobre
  **30+ exchanges**. Precisión sólida (funding match exacto, OI <60s latencia). [5]
- **Costo (decisión real de negocio):** Hobbyist **$29/mo** y Startup $79/mo son
  **personal-use-only**; uso comercial (el bot ES un producto) exige **Standard $299/mo**. [5]
- **El hallazgo de oro:** el **order-flow imbalance FIRMADO (OFI), no el volumen crudo**,
  mueve el precio a corto plazo. La relación es **LINEAL con pendiente ~1/profundidad**
  (R² contemporáneo 65-87%). [6][7]
- **Implicación para NOSOTROS:** nuestro trigger de volumen (`FQ_USE_VOL_LIQ_TRIGGER`)
  usa **volumen sin firmar** — justo lo que la evidencia dice que es más ruidoso. El
  upgrade evidenciado es **CVD/OFI** (CoinGlass da CVD agregado). Y el **colector de OI
  agregado que acabo de armar** es el aparato para medir forward si el OI-divergence
  predice precio (la investigación dejó *eso* como pregunta abierta → lo medimos nosotros).

## 3. SIZING — el lever que flagueé, ahora con evidencia
- **Vol-targeting es el sizing mejor evidenciado**, PERO **específico por clase de activo**
  (equities 0.40→0.48-0.51; commodities/FX/bonos ≈nulo) → **hay que validarlo en crypto**,
  no asumirlo. [8]
- **Su beneficio de TAIL-RISK es casi universal:** reduce retornos extremos y la vol-de-vol
  aun donde el Sharpe no cambia. → vale para control de drawdown aunque sea Sharpe-neutral. [8]
- **HRP (Hierarchical Risk Parity)** = robustez, no máquina de Sharpe: comparable a
  mean-variance, pero **evita invertir la covarianza** (el paso más frágil cuando los
  activos están MUY correlacionados — BTC/ETH/SOL ~0.8). [9]
- **Kalman** para hedge-ratio variable en el tiempo (pairs/market-neutral) — más principista
  que rolling-OLS, pero **sin edge OOS propio probado**. [10]

## 4. ML / REGIME — ÚLTIMO, y con cautela
- Un LightGBM regime-aware sobre HMM rolling dio Sharpe 1.18, pero el **DSR cayó a 0.69 —
  NO alcanzó significancia** tras corregir multiple-testing. **Lo predictivo/ML va detrás
  de la significancia corregida por overfitting, no adelante.** [4]

## El ranking (evidencia × accesibilidad para un operador chico)
| Prioridad | Upgrade | Evidencia | Costo | Para nosotros |
|---|---|---|---|---|
| **1** | **DSR + CPCV** (gate) | alta, domain-agnostic | free (lo construimos) | deflactar el +0.10R/carry por #trials |
| **2** | **CVD/OFI features** (CoinGlass) | alta (OFI>volumen) | $29-299/mo | reemplaza el trigger de volumen-sin-firmar |
| 3 | **OI agregado forward** | abierta (la medimos) | free (Railway) | colector ya armado |
| 4 | **Vol-targeting** (validar en crypto) | alta (tail-risk universal) | free | control de drawdown |
| 5 | **HRP** correlación-aware | media | free | book BTC/ETH/SOL ~0.8 |
| 6 | **ML/regime** | cautela (falló DSR) | — | sólo tras el gate DSR |

## Criterio go/no-go (lo que pediste — cuándo un upgrade es real vs ruido)
Antes de adoptar CUALQUIER feed o algoritmo nuevo: **¿el Sharpe sobrevive el DSR** dado
el número de trials que corrimos**? ¿Replica multi-régimen OOS con purged+embargo/CPCV?
¿Aguanta neto de costos?** Si no pasa los tres, es ruido overfit — no importa lo lindo
que se vea el backtest.

## Caveats honestos
- **Transferencia cross-asset:** OFI>volumen y vol-targeting se derivan en **equities US**.
  OFI replica en crypto-perps; el Sharpe de vol-targeting **NO se asume** — se valida en
  nuestra serie con el gate DSR/CPCV.
- **CoinGlass barato = personal-use;** comercial $299/mo (decisión de negocio real).
- **OI agregado:** que aporte edge OOS sobre OKX-solo quedó **sin probar** en la literatura
  → nuestro colector forward es el que lo contesta.

---
**Fuentes (primarias, verificadas):**
[1][2] Bailey & López de Prado — Deflated Sharpe Ratio / backtest overfitting (SSRN 2460551).
[3] CPCV / purged-embargo CV (MDPI Electronics 15/6/1334).
[4] Validación + regime-ML negativo (Knowledge-Based Systems, S0950705124011110).
[5] CoinGlass API (coinglass.com/CryptoApi) + review DEV 2026.
[6][7] Cont, Kukanov & Stoikov — price impact of order-book events / OFI (arXiv 1011.6402).
[8] Harvey et al. — *The Impact of Volatility Targeting* (Duke P135).
[9] Hierarchical Risk Parity (López de Prado) + corroboración crypto (AnserPress JEA).
[10] Kalman pairs-trading (Palomar, Portfolio Optimization Book §15.6).

_Radar honesto, sólo claims que pasaron verificación adversarial 2/3. Jun 2026._
