# El "otro filo": continuación intradía en régimen KL alto — evidencia y decisión

> Deep-research (105 agentes; búsqueda + fetch + extracción). La verificación adversarial
> chocó DOS veces con límites de sesión (Fable 5); **2 claims sobrevivieron el voto 3-0**, el
> resto quedó **extraído-pero-no-verificado** (papers reales, con quote y fuente, pero sin el
> panel de refutación). La síntesis del harness no corrió — esto es a mano. Etiqueto cada
> hallazgo por nivel de confianza. Complementa `EXPERIMENT_KL_TP_ADAPTIVE.md` (que ya cerró:
> π_blade NO PASA el gate).

## TL;DR — la literatura confirma exactamente lo que medimos

El momentum intradía en cripto **existe pero es diminuto y muere en costos sin apalancamiento
ni ejecución maker**. Es la MISMA sentencia que nuestro gate de π_blade dictó ayer (+27R netos
en 5.5yr, DSR 0.006). Dos caminos independientes — nuestro cube y la academia — llegan al mismo
veredicto: **no hay un filo de continuación gratis esperando en KL alto.** Pero sí hay pistas
concretas de dónde podría vivir un motor de continuación GENUINO, si se construye con su propia
anatomía (no reciclando señales de reversión).

## Hallazgos VERIFICADOS (voto 3-0)

1. **El momentum intradía en BTC es real pero minúsculo.** En 5 exchanges BTC/USD (tick→1m,
   hasta dic-2020), el retorno overnight+primera-media-hora predice la última media hora:
   slope 0.968, **t de Newey-West = 4.38** (sig. 1%), R² in-sample 1.44%, R² OOS 1.09%.
   *Fuente: Bitcoin Intraday Time-Series Momentum (U. Reading, centaur.reading.ac.uk).*
2. **NO sobrevive costos spot sin apalancamiento.** El propio paper: breakeven de **3, 7 y
   10 bps/trade** vs los 25 bps de fee de Bitstamp → las estrategias sin leverage **no son
   rentables**. Solo se rescatan asumiendo margin 10:1 (breakevens 29/64/96 bps). *Misma
   fuente.* → **Es literalmente el mecanismo que mató a π_blade**: el edge bruto existe, la
   fricción se lo come.

## Hallazgos EXTRAÍDOS (no verificados — tratar como hipótesis con cita, no como hechos)

3. **Momentum y reversión COEXISTEN en el mismo día, a horizontes distintos.** Barras
   adyacentes de 30m son anti-persistentes (reversión corta), pero el retorno de apertura
   predice positivo la última barra (momentum de rango largo). *Es exactamente la anatomía de
   nuestro grid TP×régimen*: reversivo de cerca (TP1 sobrevive), tendencial de lejos.
   *(centaur.reading.ac.uk; sciencedirect S1062940822000833)*
4. **Cuál domina es STATE-DEPENDENT** — cambia con jumps de precio, releases FOMC, nivel de
   liquidez. Respaldo académico directo a **gatear con un detector de régimen** el motor que
   opera (nuestra tesis KL). *(S1062940822000833)*
5. **La continuación es condicional a ACTIVIDAD**: en BTC el efecto solo es significativo en
   días de alto volumen (R² 3.86% vs 1.09% no-sig en bajo) y alta volatilidad (R² 2.83%).
   → un motor de continuación se gatea por estado de alta actividad, no se corre siempre.
   *(centaur.reading.ac.uk)*
6. **Los periodos de momentum en cripto son más largos/fuertes que en acciones** (baja
   derivabilidad del valor intrínseco → más noise traders). *(S1062940821000590)*
7. **El mejor timing standalone fue FADEAR** la penúltima media hora (reversión corta): 17.3%
   anual, Sharpe 1.715, 56% aciertos — MEJOR que la señal de momentum pura (51.6%). Ojo: esto
   refuerza que en cripto la **reversión corta** es el filo más robusto, no la continuación.
   *(centaur.reading.ac.uk)*

## Traducción a decisión FQ

**Lo que NO haremos** (ya medido + corroborado):
- No reciclar señales de reversión con TP acortado en KL alto → π_blade ya falló el gate, y la
  literatura explica por qué (costos > edge bruto sin maker/leverage).
- No perseguir "momentum intradía genérico" → R² ~1%, breakeven 3-10 bps: es polvo neto.

**Lo que SÍ vale un experimento measure-first propio** (si algún día se prioriza sobre oro/
símbolos nuevos):
- **Un motor de CONTINUACIÓN con anatomía propia**, gateado por (KL alto **∧** alto volumen/
  volatilidad — hallazgo #5), maker-only, entradas en pullback dentro de tendencia, con su
  propio cube triple-barrier y su propio gate DSR/CPCV/PBO. NO comparte señales con el motor
  de reversión (evita el multiple-testing de re-usar el mismo pool — la trampa nombrada).
- **Features candidatas por barra** a probar en ese cube: persistencia de order-flow firmado
  (CVD que no revierte), Δfunding/ΔOI en la dirección, volumen direccional, estructura de
  pullback. Cada una entra al gate con su trial contado.
- **Prior honesto**: la evidencia dice que el edge de continuación es real pero chico y
  frágil a costos. Probabilidad de que pase un gate honesto neto de fricción: **baja**. Es
  I+D especulativa, no una mejora con retorno esperado — se hace solo si hay banda de cómputo
  ociosa, después de los bets con mejor EV (oro, más símbolos validados).

## Estado de confianza y reproducibilidad

- 2/21 claims con verificación adversarial completa (3-0); el resto es extracción de fuente
  primaria sin el panel de refutación (límite de sesión, 2 intentos). Para promover los
  extraídos a "verificado" hay que re-correr solo la fase verify (fetches cacheados) cuando
  haya cuota — pero los 2 verificados ya son los load-bearing y bastan para la decisión.
- Fuentes núcleo: *Bitcoin Intraday Time-Series Momentum* (U. Reading 2021), *Intraday
  momentum and reversal in Bitcoin* (J. Int. Financial Markets, S1062940822000833),
  *Momentum periods in crypto* (S1062940821000590).
- Workflow: `wf_662017c4-9d1`. Journal con los 198 claims crudos en el transcript dir.
