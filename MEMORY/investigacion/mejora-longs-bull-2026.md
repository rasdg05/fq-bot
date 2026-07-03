# Mejorar los LONGS para el bull Q3-Q4 — deep-research verificado (2026-07-02)

> Encargo de RasDG ("se viene un bull run y el bot es malísimo para longs — deep search").
> **Método:** medición propia sobre los cubos (n≈13,000 fires, 13 símbolos, 2019-2026) + deep-research
> de 108 agentes en 5 pasadas (25 claims extraídos → **15 confirmados 3-0**, **5 refutados**, 5 sin
> verificar), síntesis final citada. Regla de la casa: nada se cabla sin pasar el gate DSR/CPCV/PBO.

---

## §1 — Lo MEDIDO en nuestros cubos (el diagnóstico fino)

- **NO es "el bot es malo para longs en bull":** en el bull 2020-21 los longs fueron EXCELENTES
  (+0.27R/+0.21R, ganándole a los shorts). Es **deriva de era post-2023**: 2023 longs +0.03R vs shorts
  +0.15R · 2025 longs **+0.02R** vs shorts +0.21R.
- **Es de ALTS, no de majors:** 2025-26 → BTC longs **+0.33R** y ETH longs **+0.32R** (ganan a sus
  shorts); **SOL longs +0.01R (WR 42%)**, LINK +0.03, DOGE +0.08 lifetime. **BTC/ETH ya están
  bull-ready; el hueco es SOL/alts.**
- Ya descartado con datos: TP más profundo NO rescata longs post-2023 (planos +0.05-0.08 en TP1-4,
  mientras shorts escalan +0.16→+0.25); el filtro KL tampoco los arregla consistente.

## §2 — POR QUÉ murieron (verificado, citado)

1. **El premium se lo arbitraron (estructural, no cíclico)** [alta confianza — BIS WP1087 (Management
   Science) + arXiv 2212.06888]: las desviaciones perp-spot se comprimieron ~11%/año 2020-22; el lado
   long pasó de retail a institucional (ETF futuros oct-2021); el **ETF spot ene-2024 comprimió el carry
   causalmente 36-97% de su media** (DiD). El viento de cola que cosechaban los longs 2020-21 ya no existe.
2. **Las cascadas bajistas ejecutan longs de stop apretado** [alta — Amberdata verificado verbatim +
   SSRN 5611392]: 10-oct-2025 = $2.3B liquidados en un día, **86% cierres forzados de longs** (récord
   histórico); loops reflexivos leverage→liquidez→volatilidad. Nuestro stop ~0.5% vive en esa zona.
3. **Los alts se DESACOPLARON de BTC post-ETF** [media — Cogent Econ&Fin 2026]: correlación BTC↔18 alts
   cayó marcado post ene-2024; mecanismo "independent inflows" (el capital institucional entra a BTC sin
   comprar alts). **Explica majors-fuertes/alts-muertos** (ojo: nuestro decaimiento empezó 2023, un año
   antes del ETF — el mecanismo explica 2024+, no todo).
4. **El carry alto es AVISO de crash, no confirmación alcista** [alta — BIS]: el carry sube con retornos
   pasados y atención (trend-chasers retail apalancados en long); carry alto predice crashes e IV↑.
   **La entrada long de momentum compra sistemáticamente el premium que pagan los longs.**

## §3 — Los FIXES priorizados (cada uno con su experimento measure-first)

| # | Fix | Evidencia | Experimento (gate DSR/CPCV/PBO) |
|---|---|---|---|
| 1 | **Gate de funding/basis para longs** | ⭐ la más fuerte (BIS causal) | Por fire: funding de Binance + su percentil 30/90d + flag "APR>15% sostenido" (umbral vendor Amberdata, sin backtest publicado — candidato a cutpoint). Hipótesis: el expR long se concentra en funding negativo/neutral y muere en la cola crowded. **Data YA la tenemos** (`fetch_binance_vision_funding.py`). |
| 2 | **Gate de alt-season/breadth SOLO para longs de alts** | régimen real (decoupling verificado); estrategia SIN validar en ningún lado → test propio | Por fire: breadth 90d (% del universo tradeado que le gana a BTC, de klines diarias Binance — reconstruible histórico) + ETH/BTC. Umbral CMC replicable: ≥75% altseason / ≤25% BTC-season. Hipótesis: longs de SOL/alts solo pagan en breadth alto. OJO: CoinGecko `/global` es snapshot sin histórico (cache 10min) → sirve LIVE, no para backtest. |
| 3 | **Ortogonalizar el CVD contra retornos concurrentes** | J. Financial Markets 2026 (verificado) | El flujo spot firmado tiene componente PERMANENTE (informado) solo tras separar el componente transitorio de "chase" correlacionado con retornos recientes (flujo crudo t=0.62 insignificante; controlado por retornos t=2.58; retornos solos revierten t=-3.25). Residualizar nuestro CVD vs retorno de la ventana y re-gatear: ¿sube el uplift long? |
| 4 | **Throttle on-chain LENTO (solo BTC, nivel portafolio)** | RIBF 2026 peer-reviewed: MVRV-Z/NUPL/CVDD rule-based baten buy&hold y Monte-Carlo random-entry (Sharpe 0.45→1.28) en 3 ciclos | Como dial de exposición long global (no intradía, no alts). Computable de data gratis. Es la versión CON evidencia de la tesis aixbt. |

**Bonus del research:** "spot-led vs perp-led" queda como **hipótesis a testear** (el descubrimiento de
precio es históricamente derivatives-led — Alexander & Heck 2020, JIMF 2025 — y el claim "post-ETF ahora
lidera spot" **falló la verificación 1-2**). No asumirlo: medirlo.

## §4 — Lo que NO sobrevive (no perseguir)

- **Stock-to-flow y modelos de valuación de influencer**: falsificado out-of-sample (Shelton 2024, JRFM)
  y sigue con cientos de miles de views — "social media no tiene retracción de journal" (arXiv 2606.00071).
- **Titulares de acumulación ballena / lecturas puntuales de LTH-SOPR** (la tesis aixbt cruda): narrativa
  sin validación como señal; la versión CON evidencia es el throttle lento del fix #4.
- **Refutados por el panel adversarial de este research** (transparencia): "post-ETF el spot domina el
  descubrimiento de precio" (1-2) · "$31.4B liquidados 2025, 60% longs" (0-3, la cifra del año; la del
  crash 10-oct 86% SÍ pasó 3-0) · "momentum explica el gap perp-spot con R²>50%" (0-3) · los números del
  backtest EMA-gate 5/50 y del quintil de momentum cross-sectional (SSRN 4322637, 1-2 c/u).

## §4.5 — VEREDICTOS DEL GATE (2026-07-03 · `tools/validate_long_gates.py` · 13,348 fires tp1/h96)

Los 4 experimentos CORRIDOS por el gate de la casa (DSR deflactado + CPCV + PBO), data gratis y causal
(funding+klines 1d de data.binance.vision · kl_hist 5m local · CoinMetrics community):

| # | Experimento | Resultado | Veredicto |
|---|---|---|---|
| 1 | **Funding-gate (percentil 90d)** | LONG & funding pctl≤0.5 → **+0.173R vs +0.121 base** (n=1538) · **DSR 1.000 ✓ · CPCV 80% paths>0 ✓ · PBO 0.04 ✓** | ✅ **PASA — el único** |
| 2 | Breadth/alt-season (alt-longs) | altseason ≥75%: uplift **+0.002** · ≥50%: −0.014, **PBO 1.00** | ❌ **REFUTADO operativamente** (el decoupling macro es real pero no baja a gate de 5m — horizon mismatch) |
| 3 | CVD-ortho (flow sin chase) | dirección PRO-tesis (sin-chase +0.085 vs +0.003; CPCV 60%>0) pero **n=34** · DSR 0.607 | ⚠️ **Sin poder** — el CVD de barra confirma poco (imb≥0.55 raro); hallazgo colateral: CVD-barra-confirmado rinde PEOR que no-confirmado (+0.003 vs +0.090) = contaminación de chase REAL |
| 4 | NUPL throttle | **Gradiente monotónico perfecto**: capitulación +0.317 → esperanza +0.137 → optimismo +0.119 → codicia +0.072 (shorts al revés) · NUPL<0.5: uplift +0.029, DSR ✓, CPCV 80%>0 ✓, **PBO no computable** (régimen lento: bloques enteros de un solo lado) | ⚠️ **PROMETEDOR** — 2/3 checks; falta PBO adaptado a régimen lento + forward |

**Detalles honestos del ganador (funding pctl):** el gate por NIVEL crudo (≤baseline / veto ≥15%APR) NO
pasa (PBO 0.75) — exactamente lo que decía el estudio del R²=0.003: el nivel crudo no informa; **lo que
paga es el funding RELATIVO a su propia historia 90d del símbolo**. Retiene ~33% de los longs. GROSS,
in-cube: el juez final es forward. **Bonus para shorts:** funding caliente = shorts +0.215R (gradiente
inverso) — lead para un boost de shorts en cola crowded (no gateado hoy).

## §5 — Plan para Q3-Q4 (orden de ejecución)

1. **Ya cubierto:** los longs de BTC/ETH funcionan HOY (+0.33/+0.32) — el bull nos agarra con esa pata sana.
2. **Experimento #1 (funding gate)** — data ya descargable, validador estilo CVD: taggear los ~13k fires
   con funding/percentil y gatear. Si DSR/CPCV/PBO pasan en el subset long-gateado → cablear dormido.
3. **Experimento #2 (breadth gate para alts)** — reconstruir breadth 90d de klines diarias (gratis) y
   gatear los longs de SOL/LINK/DOGE. Es el candidato #1 para resucitar el long de SOL.
4. **Experimento #3 (CVD ortogonalizado)** — refinamiento del edge ya validado; barato de correr.
5. **#4 (throttle MVRV-Z)** — dial lento de exposición; útil también como narrativa honesta de producto.

_Fuentes primarias verificadas: BIS WP1087 · arXiv 2212.06888 · SSRN 5611392 · Amberdata (corroborado
CoinGlass/CNBC) · Cogent Economics & Finance 2026 · J. Financial Markets 2026 · RIBF 89 (2026) · Alexander
& Heck JFS 2020 · JIMF 157 (2025) · CMC altcoin-season · CoinGecko docs · JRFM 17(10) Shelton 2024.
Run wf_778c0fe3-5dd (108 agentes, 5 pasadas por límites de sesión, 2026-07-01→02). Medición propia:
cubos tp1/h96 (por año, por símbolo, por dirección). **Hipótesis a gatear, no promesas.**_
