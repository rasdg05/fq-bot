# El edge de RasDG — extraído de su historial real (MEXC, 1 año)

> Fuente: export de Historial de Órdenes de Futuros MEXC, 2025-06-29 → 2026-06-23.
> 6.397 órdenes · 2.332 cierres · UTC-06 (CDMX). Análisis: `mexc_orders.parquet`.
> **GROSS de la cuenta** (PnL de cierre + fees). No es backtest: es el track real.

## TL;DR
El edge de RasDG **no es dirección ni timing — es asimetría de riesgo**: corta
perdedores chico y deja correr ganadores. Es **real y sistemático a leverage sano**,
y el **leverage alto lo BORRA matemáticamente**. El año cerró −847 USDT no por falta
de edge, sino porque el edge se ejecutó a una palanca que lo destruye.

## 1. El edge: asimetría let-winners-run / cut-losers
- Win medio **+41.6** · Loss medio **−16.4** → ratio **2.5:1**.
- Win rate 27.7%. Breakeven para 2.5:1 = **28.3%**. **Gap = −0.6 pp.** A medio punto
  de win-rate de ser rentable.

## 2. La teoría: el leverage colapsa el ratio (el mecanismo)
| Leverage | WR | win$ | loss$ | **ratio** | BE-WR | **EV/trade** |
|---|---|---|---|---|---|---|
| **≤25x** | 25% | +220 | −30 | **7.44** | 12% | **+31.70** |
| 25-50x | 20% | +24 | −8 | 2.89 | 26% | −1.90 |
| 50-100x | 29% | +41 | −19 | 2.17 | 32% | −1.36 |
| **>100x** | 29% | +28 | −15 | **1.87** | 35% | **−2.54** |

El ratio baja monótono **7.44 → 2.89 → 2.17 → 1.87** con el leverage. Mecanismo:
a 100x, la **liquidación/margen** (a) saca del ganador antes de que corra y (b)
fuerza pérdida de margen completo en vez de un corte chico. El leverage no agrega
riesgo — **borra la asimetría que ES el edge.**

## 3. Prueba de que es sistemático (no un pump de suerte)
Bucket ≤25x: total **+3.487** · sin ASTER **+1.379** · sin los top-3 trades **+757**.
Sigue positivo sacando los grandes → es la asimetría real, no concentración.
(Caveat: los longs SIN top-5 son −2.222 → el edge **direccional** no es sistemático;
el edge es la **gestión**, no la dirección.)

## 4. Dónde sangra (confirmación cruzada con el bot)
- **Sesiones:** peor 12-16h (2PM, −2.808) y 04-08h (London, −1.636). **Son
  exactamente las killzones que el bot vetea** (`london_open_kz`, `is_dead_window`).
- **Día:** viernes −2.401 (WR 18%). Finde verde.
- **Dirección:** mejor long que short (longs +4.567 / shorts −5.334), pero el long
  no es sistemático (ver §3).

## 5. Los 3 diales para cerrar el gap — y el bot tiene los tres
1. **Leverage sano (≤25x)** → preserva el ratio. *(bot: `leverage_for_tier`)*
2. **Evitar el chop** (sube WR) → London/asia/2PM. *(bot: vetos de killzone)*
3. **Dejar correr** (sube ratio) → *(bot: tp4 / horizonte largo)*

## Síntesis
**El bot ≈ RasDG a ≤25x, sin tradear el chop, dejando correr.** No comparte la
ENTRADA (RasDG caza momentum/ruptura; el bot compra pullbacks en discount — opuestos,
y el pullback gana sistemáticamente). Comparte la **disciplina de riesgo** — la parte
buena. El aporte de RasDG al bot no es su entrada: es la asimetría let-winners-run,
ya cableada en el diseño.

_Generado del análisis de esta sesión (2026-06). Radar honesto, no promesa._
