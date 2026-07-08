# ORO — Fase 2 CVD: veredicto FINAL del arco "adaptar el motor cripto al oro"

> Compra dirigida ejecutada: trades GC.v.0 de los **181 días con fire** ($23.76; total del arco
> oro = $11.59 ohlcv + $23.76 CVD = **$35.35**). CVD firmado 5m con aggressor nativo (Tag 5797,
> solo 1.8% sin agresor → data impecable). Gate causal (j+1). Cierra la pregunta abierta desde
> ORO_GATE_V3 (corregido): ¿la confirmación order-flow sube la señal débil (SR 0.17) sobre el
> umbral?

## Resultado: el CVD NO concentra el edge en el oro

| Subset | n | WR | avgR | SR/trade |
|---|---|---|---|---|
| BASE (todos, CME clock) | 232 | 56.9% | +0.160 | 0.170 |
| **CVD confirma** (imb_min 0.50) | 88 | 56.8% | +0.165 | **0.165** |
| CVD no-confirma | 144 | 56.9% | +0.156 | 0.173 |

- El subset confirmado es **estadísticamente idéntico** a la base y al no-confirmado. El flujo
  firmado **no separa** ganadores de perdedores en GC.
- DSR del confirmado = **0.000** (n=88) — sigue sin pasar. Umbrales 0.55/0.60 ni juntan n.
- Data limpia (1.8% none-aggressor, 232/232 con CVD) → negativo REAL, no artefacto.

## Por qué (coincide con la literatura que ya reunimos)

La deep-research del oro (ORO_SESION_KILLZONES) ya lo anticipaba, ahora medido en casa:
- Gold tiene el **menor price-impact por dólar** de 6 commodities (0.22 bps/$1M) — libro profundo,
  poco sensible al flujo.
- En futuros de oro el flujo firmado es **contemporáneo, no predictivo rezagado** (Ready & Ready).
  El CVD *describe* el movimiento, no lo *anticipa* — por eso confirma-o-no da igual.
- Es el mismo patrón que en cripto validó el CVD como gate de régimen (magnitud/toxicidad), NO
  como señal direccional — y en oro, sin siquiera el edge direccional base fuerte, no hay qué
  concentrar. **Dos caminos independientes (nuestra medición + la academia) convergen otra vez.**

## VEREDICTO DEL ARCO COMPLETO: el motor cripto NO transfiere al oro al nivel de certificar

Recorrido measure-first, honesto de punta a punta:
1. **Data**: comprada bien (GC.v.0 full-density, $11.59). ✅ El bug era simbología (GC.c.0 muerto).
2. **Killzones re-ancladas al reloj CME**: FUNCIONA — avgR +0.085→+0.160, CPCV 80%→100%. ✅
3. **Etiquetado**: el 96.6/5.6 era look-ahead de mi harness, no del oro. Corregido → señal real,
   balanceada, débil (+0.160, SR 0.17). ✅
4. **CVD firmado (Fase 2, $23.76)**: NO concentra. ❌ Última palanca de la caja cripto, agotada.

**Conclusión:** el motor de reversión cripto (order-flow + ICT + KL), incluso re-anclado y
filtrado por CVD, produce en oro una señal **real pero sub-umbral** que ninguna palanca existente
sube sobre el gate honesto. **No entra al cubo.**

## El único camino que queda (y es un proyecto, no un tweak)

Un **motor de oro con anatomía propia**, lo que la investigación de sesión ya apunta:
- **Continuación en sesión NY/COMEX**, no reversión con niveles de cripto (la microestructura del
  oro es de tendencia intradía en ventanas de evento, no de mean-reversion 24/7).
- Features causales gold-específicas: illiquidez de Amihud, variance-ratio de eficiencia (W-shape
  hora-del-día), ventanas de evento macro (08:30/14:00 ET), el PM fix (10:00 ET).
- Su propio cube triple-barrier + su propio gate. NO comparte señales con el motor cripto.
- **Prior honesto**: es I+D especulativa. La literatura dice que el edge intradía de oro existe
  pero es chico y frágil a costos (igual que el momentum cripto que ya medimos). Probabilidad de
  pasar un gate honesto: media-baja. Se prioriza contra otros bets (más símbolos cripto validados,
  que son EV más seguro).

## Estado y recomendación
- **Oro: COSECHA.** El arco "adaptar cripto→oro" queda CERRADO con veredicto medido: no certifica.
- Gasto total del arco: **$35.35** — barato para cerrar definitivamente una hipótesis que, sin
  medir, habría tentado a shippear (3 veces estuvo cerca: data rota, look-ahead, señal débil).
- **No recomiendo** arrancar el motor-de-oro-propio ahora: es el bet de menor EV/mayor esfuerzo de
  la mesa. Primero los símbolos cripto en forward (BNB) y el forward de lo cableado esta semana.
- La data comprada queda en `/tmp/cme/` (no commiteada — working data); si algún día se hace el
  motor propio, el cube de oro y el CVD ya están pagados y listos.

## Reproducibilidad
`/tmp/cme/cvd_GC_v0.parquet` (48,560 buckets firmados), `/tmp/cme/cvd_gate.py`,
`/tmp/cme/cvd_gate_results.parquet`. Eventos `/tmp/cme/events_full_after.parquet`. Gate causal
via `bt_labeler` (j+1) + `fetch_cvd.confirms_direction` (imb_min 0.50, el validado en cripto).
