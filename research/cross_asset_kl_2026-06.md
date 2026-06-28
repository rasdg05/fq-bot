# Barrido cross-asset — base + KL (13 símbolos) · 2026-06

Set completo: 3 anclas (BTC/SOL/ETH) + 10 curadas (Tanda 1: DOGE/XRP/LTC/BCH/BNB ·
Tanda 2: LINK/DOT/ADA/AVAX/TRX). Cubos tp4/h576 (OKX, Hetzner). Medido con
`tools/measure_tiers.py` + `tools/validate_regime_irreversibility.py`.

## 1) Edge BASE (del cubo, neto −0.15R de coste)
Caveat: spans distintos (viejos cargan 2019-20, jóvenes no) → sesga a favor de los recientes.

| sym | net R | cad/sem | desde |
|---|--:|--:|--:|
| AVAX | +0.23 | 3.54 | 2022 |
| ETH | +0.19 | 4.05 | 2019 |
| BCH | +0.18 | 4.45 | 2019 |
| BTC | +0.16 | 3.57 | 2019 |
| BNB | +0.12 | 3.37 | 2023 |
| DOT | +0.11 | 3.38 | 2021 |
| DOGE | +0.07 | 3.43 | 2022 |
| LTC/ADA/LINK/SOL | +0.05…+0.01 | ~3.7 | |
| TRX | −0.08 | 2.67 | 2022 |
| XRP | −0.09 | 3.53 | 2019 |

## 2) Readiness tier CALIDAD (KL)
Bar: KL separa con **DSR>0.95** Y el edge vive en **irrev-BAJO** (el lado que el filtro difunde).

| sym | régimen ganador | sep | DSR | calidad neto | veredicto |
|---|---|--:|--:|--:|---|
| BTC | irrev-BAJO | — | 0.999 | +0.16 | ✅ LIVE |
| SOL | irrev-BAJO | — | 0.950 | +0.06 | ✅ LIVE |
| ETH | irrev-BAJO | — | 1.000 | +0.29 | ✅ LIVE |
| **BNB** | **irrev-BAJO** | **0.285** | **0.992** | **+0.17** | ✅ **PASA (fuerte)** |
| **LINK** | **irrev-BAJO** | 0.075 | **0.969** | +0.07 | ✅ **PASA (marginal)** |
| DOT | irrev-BAJO | 0.017 | (base) | +0.14 | ❌ KL no discrimina |
| TRX | irrev-BAJO | 0.092 | 0.768 | −0.07 | ❌ no significativo + neto rojo |
| XRP | irrev-BAJO | 0.078 | 0.815 | −0.03 | ❌ no significativo + neto rojo |
| ADA | irrev-ALTO | 0.095 | 0.984 | −0.02 | ❌ edge en lado OPUESTO (trending) |
| AVAX | irrev-ALTO | 0.076 | 1.000 | +0.20 | ❌ edge en lado opuesto (base fuerte) |
| BCH | irrev-ALTO | 0.030 | (base) | +0.20 | ❌ KL no discrimina (base fuerte) |
| LTC | irrev-ALTO | 0.012 | (base) | +0.08 | ❌ KL no discrimina |

## Conclusiones
- **El set Calidad crece de 3 a 5: + LINK + BNB** (irrev-BAJO, DSR>0.95). BNB el más fuerte
  (separación 0.285R, DSR 0.992) pese a ser el cube más corto. Candidatos a cablear **midiendo
  forward** (cube, aún no forward), igual que BTC/SOL/ETH en su día.
- **KL NO tiene dirección universal:** en ADA/AVAX/BCH/LTC el edge vive en **irrev-ALTO (trending)**,
  el lado OPUESTO. Aplicarles el filtro KL-bajo los perjudicaría. El régimen es **symbol-specific**
  (refuerza la refutación de la "ley" cross-asset del barrido F2).
- **BCH/AVAX:** base fuerte (+0.20 neto) pero KL no es su herramienta — son edge de BASE, no de KL.
- Cabling = scaffold de motor por símbolo (como BCH) + forward. No se promete del backtest.
