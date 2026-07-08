# La matriz mercado × señal — qué significa "adaptar el método" (medido)

> Origen: el dueño intuyó (correctamente) que yo NO estaba adaptando el método de reversión cripto
> a NASDAQ — había construido un motor de momentum en su lugar. La crítica forzó el test que
> faltaba, y lo hizo TODO más riguroso. Resultado: la matriz 2×2 completa, medida en las 4 celdas.

## La matriz (medido, maker-net, gate honesto)

| | **Reversión** (método cripto: fade/sweep en KL-bajo) | **Momentum** (continuación) |
|---|---|---|
| **CRIPTO** | ✅ **+26.8R en vivo** (VIP, el edge real) | ❌ −0.13R, DSR 0.000 (falla) |
| **NASDAQ** | ❌ −0.43 Sharpe fiel ICT, DSR 0.0001 (falla PEOR) | ✅ **Sharpe 1.9 long-only**, DSR 0.999 |

**Anti-diagonal perfecta.** Cada mercado tiene UN edge, y son OPUESTOS.

## La reversión en NASDAQ — probada a fondo (por la crítica)
- **Cruda** (fade breakout en KL-bajo): plana, Sharpe 0.02, DSR 0.23.
- **Fiel ICT** (sweep + reclaim: barre el extremo con mecha, cierra de regreso — la confirmación
  del método cripto), gateada KL-bajo: **NEGATIVA, −0.43 Sharpe, DSR 0.0001.**
- **Patrón clave: mientras MÁS fiel el port de reversión, PEOR.** Comprometerse más con la tesis
  de reversión (sweep+reclaim = apuesta fuerte a que revierte) pierde más en un mercado que tiende.

## La firma que lo explica (medido antes)
Regresión intradía apertura→resto: cripto **−0.032 (revierte)** · oro +0.040 · NASDAQ **+0.053
(tiende)**. La DIRECCIÓN del edge la fija la autocorrelación del mercado, NO el motor. No se puede
forzar reversión a un mercado que tiende, ni momentum a uno que revierte — lo medimos en ambos
sentidos.

## Qué significa "adaptar el método" (la lección de la crítica)

**NO significa portar la SEÑAL cripto (reversión) a NASDAQ.** Eso falla — medido, peor cuanto más
fiel. **Significa portar la MAQUINARIA** y dejar que el edge propio de cada mercado emerja por
ella:
- Detector de régimen KL (irreversibilidad) — universal.
- Triple-barrier + gate DSR/CPCV/PBO — universal.
- Gestión parcial+BE / ladder — universal (aunque el óptimo por mercado difiere).
- La disciplina measure-first — universal.

Lo que NO transfiere es la **dirección del edge**: la fija la firma del mercado, y se MIDE, no se
asume. Cripto → reversión. NASDAQ → momentum. Cada uno con su maquinaria compartida.

**Esta conclusión es más fuerte que si la reversión hubiera funcionado:** establece el PRINCIPIO.
El método (máquina + disciplina) es universal; el edge es específico del mercado y se descubre
midiendo las 4 celdas, no forzando la señal que ya conoces. Eso es lo que protege de montar una
estrategia perdedora sobre un mercado que no la quiere.

## Crédito
La intuición del dueño ("no estás adaptando bien la reversión") forzó las 2 celdas de reversión-
NASDAQ (cruda + fiel ICT). Sin esa presión, la matriz habría quedado con un hueco y la conclusión
sería "elegí momentum" en vez de "momentum es el ÚNICO edge de NASDAQ, la reversión es negativa —
medido". La crítica hizo el trabajo riguroso.

## Reproducibilidad
`/tmp/cme/nq_reversion.py` (cruda) + sweep+reclaim inline (fiel ICT). Data
`data/cme/NQ-USDT_5m.parquet`. Firma intradía: los 3 mercados en ROADMAP/experimentos previos.
