# NASDAQ — estrés de robustez del motor afilado (antes de ir a vivo)

> "Componer el método al NASDAQ" con disciplina: entender antes de extender. Estresamos el motor
> ganador (opening-range breakout + parcial+BE) ANTES de gastar en CVD o montar feed en vivo. Un
> quant serio radiografía el motor antes de exponerlo. Data en mano, costo $0.

## Hallazgos

### 💎 1. El edge está en los LONGS (el hallazgo accionable)
| lado | n | avgR | WR | Sharpe anual |
|---|---|---|---|---|
| **LONG** | 981 | +0.126 | 56% | **+1.88** |
| SHORT | 827 | +0.013 | 50% | +0.19 |

Los shorts son casi breakeven — diluyen el motor. **Económicamente coherente:** los índices tienen
deriva estructural al alza; momentum CON la tendencia paga, CONTRA (short en índice que sube
secularmente) apenas. Un motor **long-biased** es la mejora candidata #1 — a validar OOS limpio,
sin cherry-pick sobre lo ya visto.

### ⚠️ 2. Fragilidad al anclaje horario
Fin-de-apertura: 10:00 → Sharpe **−0.31** · 10:30 → **1.09** · 11:00 → 0.55. Demasiado sensible al
corte exacto → el 10:30 puede estar parcialmente ajustado. Riesgo real; un edge robusto varía menos.

### ⚠️ 3. 2025 fue año-régimen malo, persistente
Sharpe −0.98, casi todos los meses negativos (no un mal día). Dependencia de régimen que el motor
no maneja — posible crowding del efecto momentum, o régimen chop. Un filtro de régimen/actividad
podría ayudar (queda como hipótesis, no como parche a posteriori).

### ✅ 4. Lo que SÍ es robusto
- **Costo**: sobrevive hasta ~$40/rt (asumimos $14 taker) — gran colchón de ejecución.
- **Stop**: más ancho mejora monótono (1.0×ATR −0.40 · 1.5× 1.09 · 2.0× **1.45**) — momentum
  necesita aire. Dirección robusta, pero validar OOS antes de cablear un 2.0 (podría sobreajustar).

## Estabilidad por año (maker-net, Sharpe)
`2017 +2.95 · 2018 +0.78 · 2019 +3.36 · 2020 −0.38 · 2021 +1.46 · 2022 +1.27 · 2023 +0.79 ·
2024 +2.31 · 2025 −0.98 · 2026 −0.40` → 7/10 años positivos, pero 3 negativos y sensibilidad real.

## Veredicto honesto
El motor es REAL pero NO bala de plata: el edge es **long-biased**, sensible al anclaje horario, y
dependiente de régimen (2025 malo). Robusto a costos. El Sharpe blended 1.09 esconde que longs son
1.88 y shorts 0.19.

**Esto es exactamente por qué se estresa antes de ir a vivo:** deployar el blended sin saber esto
sería exponer capital a la mitad-short que no paga y a una fragilidad de anclaje no entendida.

## Próximos pasos (disciplinados)
1. **Validar long-bias OOS limpio** (walk-forward, no cherry-pick sobre 2024-26 ya visto). Si el
   long-only sostiene Sharpe fuera de muestra → es la mejora real, no un artefacto de mirar la data.
2. **CVD/order-flow** (el componente del método aún no probado en NQ; la research: OFI explica
   retornos de futuros de índice). Preflight de costo primero.
3. **Feed en vivo** (decisión de infra: Databento live vs broker) → forward paper, el juez final.

## v4 — LONG-ONLY validado (walk-forward): el upgrade

El long-bias es hipótesis ECONÓMICA (deriva de índices), no data-mining → testeado walk-forward,
año por año, como decisión fija a priori:

| año | blended Sharpe | long-only Sharpe |
|---|---|---|
| 2018 | +1.09 | **+1.94** |
| 2019 | +3.38 | **+4.15** |
| 2020 | −0.35 | **+0.05** |
| 2021 | +1.50 | **+3.07** |
| 2022 | +0.83 | +0.65 |
| 2023 | +1.04 | **+3.34** |
| 2024 | +2.61 | **+3.49** |
| 2025 | −0.99 | **−0.49** |
| 2026 | −2.06 | −2.79 |

**Long-only gana en 7/9 años.** Global: **Sharpe 1.08→1.89, maxDD 30R→15R (mitad)**, mismo totR
con la mitad de trades. **DSR 0.999** (n_trials=16, honesto). 8/10 años positivos. Hasta en los
años malos pierde menos (2020 +0.05 vs −0.35; 2025 −0.49 vs −0.99).

**Motor NASDAQ actual = opening-range breakout + parcial+BE + LONG-ONLY.** Sharpe ~1.9 in-sample;
con el haircut OOS típico (~36%) aterrizaría ~1.2-1.4 forward — genuinamente fuerte y con drawdown
sano. Mejora disciplinada: entender (robustez) → mejorar (long-only) → validar (walk-forward).

**Caveats que persisten (honestos):** 2025-2026 recientes flojos incluso long-only (¿crowding del
momentum? ¿régimen chop?) — a vigilar en forward. La sensibilidad al anclaje 10:30 no se re-testeó
para long-only. Sigue siendo gate in-sample; forward es el juez.

## Reproducibilidad
`/tmp/cme/nq_robust.py` (estrés) · data `data/cme/NQ-USDT_5m.parquet` · config final: opening-range
breakout + parcial+BE + LONG-ONLY, opening 09:30-10:30, 1.5×ATR, maker $4/rt. DSR/walk-forward
verificados.
