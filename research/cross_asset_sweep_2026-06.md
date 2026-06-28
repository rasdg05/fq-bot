# Barrido cross-asset de persistencia (F2) — la "tesis del premio", medida

**Fecha:** 2026-06-28 · **Tool:** `tools/cross_asset_sweep.py` · **Ventana:** CVD 2024-06 → 2026-06
**Símbolos:** BTC · ETH · LTC · BCH · SOL · XRP (cubos cosechados en Hetzner, OKX 84m/54m)

## La pregunta
¿La fuerza del edge de **persistencia del flujo (F2**, order-splitting Bouchaud-Farmer-Lillo)
**ESCALA con la institucional-idad** del activo? Anclas previas: **BTC** (institucional) F2 apiló;
**SOL** (retail) no. Si hubiera una curva monótona institucional→retail, sería un edge nuevo
cableable por símbolo — el "premio".

## Qué se midió (por símbolo, ventana común con CVD)
- **`ac1_flow`** — autocorrelación lag-1 del imbalance de flujo firmado por barra 5m (la *huella*
  de order-splitting: alto = flujo persistente).
- **`F2_uplift`** — `meanR(persist-confirmado) − meanR(base)`: ¿la memoria del flujo paga?
- Tiers base / calidad-KL / persist (n por símbolo: 81–126, alrededor del piso de 100).

## Resultado (orden por ac1_flow medido)

| sym | espectro | ac1_flow | base R | F2 uplift |
|-----|----------|---------:|-------:|----------:|
| BTC | institucional | +0.112 | +0.187 | **+0.257** ✓ |
| SOL | retail-rápido | +0.103 | +0.156 | +0.000 — |
| XRP | retail-rápido | +0.085 | +0.283 | **+0.349** ✓✓ |
| ETH | institucional/large | +0.082 | +0.206 | **−0.167** ✗ |
| BCH | institucional/lento | +0.055 | +0.312 | **+0.280** ✓ |
| LTC | institucional/lento | +0.054 | −0.005 | **+0.207** ✓ |

**corr(ac1_flow, F2_uplift) = −0.19** (n=6).

## Veredicto: la tesis del premio está REFUTADA
1. **El uplift NO escala con el order-splitting.** corr(ac1, uplift) ≈ 0 (−0.19). El ac1 más alto
   (después de BTC) es **SOL** — retail —, no las institucionales viejas (BCH/LTC tienen el ac1 más
   bajo y aun así apilan). El mecanismo "órdenes grandes partidas" **no explica** el edge.
2. **El uplift NO sigue el eje institucional→retail.** **XRP (retail) apila MÁS** (+0.349); **ETH
   (institucional) es NEGATIVO** (−0.167). El opuesto de lo que predecía la hipótesis.
3. **Pero F2 SÍ es un confirmador real** — paga fuerte en **4/6** (BTC, XRP, BCH, LTC: +0.21 a +0.35R),
   plano en SOL, y **daña en ETH**. No es ley de escala; es un **filtro por-símbolo idiosincrático**.

## Qué hacer con esto (honesto)
- **No hay "premio"** (curva limpia institucional). Otro caso de *measure-first → la data dijo no*,
  como el premium fuera de BTC y el régimen-KL al revés de lo hipotetizado.
- **Cablear F2 donde paga** (BTC/XRP/BCH/LTC), **nunca en ETH** — pero **forward primero** (esto es
  cube, ventana 2024-26, n≈100/símbolo; no está forward-validado).
- El ancla original (BTC apila, SOL no) **se reproduce**; lo que muere es la *interpretación*
  institucional, no el confirmador.

> Faltan BNB y DOGE (cosechando) + Tanda 2 (LINK/DOT/ADA/AVAX/TRX). Cuando caigan, el barrido los
> incluye solo (`tools/cross_asset_sweep.py --symbols ...`) y re-evaluamos con más puntos.
