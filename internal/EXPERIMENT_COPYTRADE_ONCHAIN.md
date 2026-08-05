# EXPERIMENT — Copy-trading verificable on-chain (fase 0: espejo sin capital)

> Origen: vídeo de TikTok (@guillesol_4, ago-2026) + encargo de RasDG: seguir las
> operaciones de "el insider de Trump" y de políticos, replicarlas automáticamente
> desde una cartera custodial, y enseñar el resultado a inversores privados en un
> dashboard alimentado por el ledger que ya medimos.
>
> Este documento **no propone desplegar nada**. Propone la única fase que se puede
> hacer sin mentirle a nadie: medir si la copia sobrevive a su propio coste de
> ejecución. Si no sobrevive, va al `CEMENTERIO.md` y se cierra la línea.

---

## 0. Por qué este experimento es exactamente el que este repo sabe fallar

El vídeo afirma dos cosas: que copiar cada operación de Trump durante un año
convierte $1.000 en $426.000, y que un trader "con un 100% de acierto en sus
operaciones públicas" acaba de abrir un short de $25,4M en BTC minutos antes de
la Fed.

Las dos son la misma estructura que ya nos costó tres meses en `GHOST_MAP_2026-07`:

- **"100% de acierto"** es una distribución imposible. Regla vigente del repo:
  *una métrica demasiado limpia es un bug, no un hallazgo*. Un WR de 100% sobre
  operaciones públicas significa que alguien eligió qué operaciones eran públicas.
- **"$1.000 → $426.000"** es una curva bruta sin coste de ejecución. Ese hueco es
  el que E8 midió en casa sobre las 13.429 señales del cube: **bruto +0.2305R →
  neto −0.0258R**, IC95% [−0.059, +0.013]. **El coste es −0.256R por trade**, o
  sea *más grande que el edge bruto entero*. Quien enseña una curva sin costes no
  está enseñando el 90% del resultado: está enseñando el 100% del que sobra.
- **Elegir hoy "los más rentables"** y medir su histórico es ordenar por resultado.
  Con muestra chica eso selecciona ruido, y lo dice `CLAUDE.md` en la línea que
  más caro nos ha salido.

Nada de esto dice que la idea sea mala. Dice que **la afirmación del vídeo no es
evidencia**, y que la única salida es medirlo nosotros con las invariantes puestas
antes, no después.

---

## 1. Separar tres cosas que el vídeo mezcla

El vídeo salta de un tweet sobre Trump → a un "insider" en un perp DEX → a seguir
una wallet en la app de pump.fun. Son tres fuentes con propiedades **opuestas** en
las dos dimensiones que importan: si la operación es verificable, y si es copiable
a tiempo.

| | Verificable | Latencia real | Identidad del operador |
|---|---|---|---|
| **A. Wallets on-chain** (Hyperliquid, Solana) | **Sí, criptográficamente**: el fill *es* la prueba | segundos | **No verificable** — la atribución a "Trump" es folklore |
| **B. Trades de políticos** (STOCK Act) | **Sí, oficialmente**: filing firmado | **hasta 45 días** | **Verificable** — es un documento público con nombre |
| **C. Calls de Twitter / Telegram** | No | variable | Irrelevante: no hay operación que verificar |

Esta tabla es todo el experimento. Léela otra vez: **A y B son complementarias y
mutuamente excluyentes.** Lo que se puede copiar en tiempo real no se puede
atribuir; lo que se puede atribuir no se puede copiar en tiempo real.

### A. Wallets on-chain — real, pero anónimas

Hyperliquid es un perp DEX donde **posiciones y fills de cada address son
públicos**. La Info API (`https://api.hyperliquid.xyz/info`) y el WebSocket son
gratuitos y sin autenticación: `clearinghouseState` da la posición abierta
(moneda, tamaño, dirección, apalancamiento, entrada, PnL no realizado) y el canal
`userFills` empuja cada fill en tiempo real. Presupuesto compartido de ~1.200
unidades de peso por minuto, la mayoría de queries de info cuestan 20.

Es decir: **la parte técnica de "copiar en tiempo real y verificar" está resuelta
y es gratis.** Un fill on-chain no necesita que nadie lo confirme; el fill es el
comprobante.

Lo que **no** existe es la atribución. "El insider de Trump" es una address que
alguien bautizó. Nadie ha probado quién la controla; el rastro público apunta al
ex-CEO de BitForex Garrett Jin, que **niega** vínculo con la familia Trump y niega
haber usado información privilegiada. Podemos seguir la address — no podemos
decirle a un inversor de quién es. Ver §5, invariante I-2.

### A-bis. La wallet única no existe: la unidad real es el clúster

Tres preguntas de RasDG (2026-08-05) que rompen la versión ingenua del plan:
*¿esa wallet es consistente? ¿no usan varias? ¿cómo estar al tanto?*

**Multi-wallet: confirmado, documentado, y en la misma wallet del vídeo.** El
10-oct-2025, la address famosa **transfirió $30M a otra address de Hyperliquid que
acto seguido abrió shorts de ETH**. No es una hipótesis sobre cómo operan las
ballenas: es el registro on-chain de esta ballena concreta. Motivos estructurales
para hacerlo (todos vigentes): en Hyperliquid **el precio de liquidación es
público**, así que una address grande y conocida es un objetivo; y una address
seguida por miles de copiadores es un activo explotable por su propio dueño.

**Consistencia: medible con exactitud, y la respuesta preliminar es que no.** El
histórico completo de fills de una address es público, así que aquí no hay que
adivinar nada — se calcula. Lo que ya se ve en fuentes públicas: el short del
arancel del 100% a China (oct-2025) rindió **~$200M**, y el total acumulado de la
cuenta en Hyperliquid se reporta después en **~$100M**. Las dos cifras vienen de
fuentes y fechas distintas y no deben tratarse como un balance auditado, pero la
dirección es inequívoca: **un trade legendario y una devolución posterior de la
mitad.** Eso no es "100% de acierto" — es n=1 con varianza enorme, que es
literalmente lo que este repo tiene prohibido llamar edge.

**El sesgo que esto crea es peor que elegir ganadores.** Si una entidad opera 10
addresses, la que hace +6.000% recibe el mote y la cuenta de Twitter; las 9 que
reventaron son invisibles. No estás seleccionando la mejor de un universo
conocido: estás seleccionando de un universo **cuyo denominador está oculto por
diseño**. Ninguna corrección estadística arregla un denominador que no observas.

**El riesgo adversario** (estructural, no documentado como caso probado: trátalo
como amenaza de diseño, no como hecho). Una address seguida por miles es una
palanca: abrir en la seguida, dejar que los copiadores empujen el precio, salir
por la otra. No hace falta que esté ocurriendo para que el diseño deba resistirlo.

**Cómo se está al tanto, entonces:** no se sigue una address, se sigue un
**clúster**, y se construye desde el flujo de fondos on-chain — que es
precisamente lo que delató a esta ballena. Señales de pertenencia, en orden de
fuerza:

1. **Transferencia directa** entre addresses (el caso de los $30M). Es la más
   fuerte y la más fácil de vigilar: basta con escuchar transfers de cada address
   seguida y promover el destino a candidato del clúster.
2. **Origen de fondos común**: mismo depósito desde Arbitrum, mismo puente, misma
   address de retiro de CEX.
3. **Sub-cuentas y vaults**, que en Hyperliquid están enlazados on-chain de forma
   explícita: es atribución, no heurística.
4. **Correlación temporal y estructural** de fills (mismo activo, mismo lado,
   ventana de segundos). La más débil: co-movimiento no es control.

Etiquetadores externos (Arkham, Nansen, Cielo — que RasDG ya usa) aceleran esto,
pero sus etiquetas son **heurísticas de terceros, no pruebas**. Entran al ledger
con su fuente y su fecha, y nunca como `verified` (I-2).

**Y el recordatorio incómodo:** hay plataformas siguiendo 4.800+ wallets de
Hyperliquid con clasificación neta de fees y funding, y trackers en vivo de las
addresses más rentables. Si tú lo ves, lo ven todos. No llegas temprano — llegas a
la vez que la multitud que mueve el precio contra tu fill. Eso no invalida el
experimento; es exactamente lo que mide el deslizamiento de réplica (§2).

### B. Trades de políticos — atribuibles, pero estructuralmente tardíos

La STOCK Act obliga a declarar operaciones de más de $1.000 **dentro de 45 días**.
Ese plazo sigue vigente en 2026. La *Stop Insider Trading Act* pasó la Cámara el
22-jul-2026 (prohibiría a miembros del Congreso, cónyuges e hijos comprar acciones
individuales, con aviso previo de 7-14 días antes de vender lo ya poseído), pero
llega muerta al Senado.

Consecuencia dura, y es la respuesta a la pregunta de "Autopilot o algo así":
**Autopilot y todo tracker de políticos copian filings, no operaciones.** Su
latencia mínima no es de milisegundos: es de días a semanas, por ley. No es un
defecto de su producto — es el único dato que existe. Cualquier dashboard que
sugiera a un inversor que está siguiendo a un político "en vivo" está describiendo
mal el producto.

Nota adicional: la misma prensa que alimenta el hype documenta el incumplimiento
(p. ej. 211 operaciones declaradas fuera de plazo por una sola representante en
ene-2026). La cola de latencia real es peor que 45 días.

### C. Bots de Twitter y agentes que "validen" — no son fuente

La pregunta era si hace falta "fuentes confiables o bots de Twitter y agentes que
validen cada trade". La respuesta es que **un agente no puede ser el validador**.

- Un tweet no es una operación. Como mucho es un **disparador** de una hipótesis.
- El validador es un chequeo determinista contra la cadena: si en los N segundos
  siguientes al disparador no aparece un fill on-chain con su identificador, el
  disparador se descarta y se registra como descartado.
- El rol legítimo de un LLM aquí es **clasificar y atribuir** (¿este texto afirma
  una operación? ¿sobre qué activo?), y su salida debe guardarse junto a la
  evidencia que usó. Nunca acredita un trade.

---

## 2. La pregunta falsable

Todo lo anterior se reduce a una sola pregunta, y no es "¿gana la wallet?":

> Dado un conjunto de wallets **congelado ex-ante**, ¿la réplica de sus fills
> —con nuestra latencia de detección real, nuestro precio de entrada real y
> nuestros fees reales— tiene una expectancy cuyo **IC95% queda por encima de
> cero** sobre n≥30 cierres?

La wallet puede ganar +6.000% y la réplica perder dinero. Eso no es una
posibilidad teórica: es **el resultado que ya tenemos medido en casa, dos veces**.

- **E8, sobre 13.429 señales:** bruto +0.2305R → neto **−0.0258R**. El coste de
  ejecución (−0.256R/trade) se come el edge entero.
- **El VIP, sobre el universo exacto del producto (n=3.774):** la geometría que
  opera en vivo da **−0.069R neto, IC95% [−0.112, −0.028]** — entero bajo cero.

En copy-trading la enfermedad es **peor**, y por una razón estructural que aquí no
teníamos: se añade el *adverse fill*. Entras después del que mueve el precio, y a
menudo **porque** lo movió. Nuestro `fill_quality.py` ya midió esa misma
enfermedad en su versión doméstica — **selección adversa −1.039R**: las órdenes
que llenan (+0.114R) llenan porque el precio va a atravesarte, y las que escapan
(+1.153R) eran las buenas. Copiar a una ballena seguida por miles es esa misma
dinámica con la multitud empujando en tu contra.

**La métrica primaria del experimento no es el PnL de la wallet. Es el
deslizamiento de réplica**: distribución de (nuestro precio de entrada − su precio
de entrada) en R, y su cola. Si esa distribución se come el edge, el experimento
ha terminado y no hace falta discutir nada más.

---

## 3. PRIMER RESULTADO MEDIDO (2026-08-05) — el embudo

No hizo falta construir el colector. La pregunta *"¿queda alguien copiable en el
top de un leaderboard?"* se responde con la API pública en diez minutos, y ese era
el resultado barato que había que ir a buscar antes de escribir nada.

**Método** (`tools/copytrade_screen.py`, tests en `tests/test_copytrade_screen.py`):

- **Cohorte congelada ANTES de medir** (I-4): top 100 por PnL *allTime* de las
  **41.276** cuentas del leaderboard de Hyperliquid, sellada
  `2026-08-05T08:20:28Z`. Es deliberadamente la población que un ranking bruto
  señala — o sea, a quién copiaría alguien que siga el vídeo.
- **Ventana común y cerrada** de 30 días para todas. Dentro del experimento no se
  ordena por resultado.
- Tres filtros en orden de coste: ¿opera? → ¿es alcanzable? → ¿pasa I-7?

**Embudo:**

| Filtro | Cuentas | Qué queda |
|---|---|---|
| Cohorte (top 100 allTime) | 100 | — |
| **Sin un solo fill en 30 días** | **59** | 41 |
| **Inalcanzables** (≥20 fills/día) | **35** | 6 |
| Sin PnL neto positivo en la ventana | 3 | 3 |
| **Fallan I-7** (top trade >50% del PnL) | **1** | **2** |

Y de esas 2 supervivientes, una ganó **$42 en 30 días** sobre 59 cierres: ruido, no
señal. **Queda 1 de 100** (129 fills, 125 cierres, ~$63k netos, resto tras quitar
su mejor trade: 81%).

**La distribución de cadencia es el hallazgo grande.** Entre las 41 activas, la
mediana es de **887 fills/día**, el p90 de **70.781** y el máximo de **212.245**.
El 49% supera los 1.000 fills diarios. El top de un leaderboard de perp DEX no
son traders direccionales: son **market makers**. No hay nada que copiar ahí —
su PnL *es* el rebate de maker y el spread, y replicarlo con latencia y fees
retail lo convierte en pérdida garantizada. Esto también explica por qué los
rankings brutos "apuntan al trader equivocado": el PnL enorme viene con volumen
enorme, y el volumen enorme es el negocio, no el edge.

**Las 59 inactivas son la mejor evidencia indirecta de I-6.** Una cuenta en el top
100 histórico que no hace un solo fill en un mes es compatible con dos cosas:
murió, o **rotó a otra address**. Para el copiador da igual — la address que sigue
no hace nada. Para el experimento no da igual: es el argumento más fuerte de que
la unidad de seguimiento tiene que ser el clúster.

**Lo que este resultado NO dice.** No dice que el copy-trading no tenga edge; esa
pregunta sigue abierta y necesita el espejo de §4. Dice que **el método de
selección del vídeo — mirar quién ha ganado más — apunta casi enteramente a cosas
muertas, inalcanzables o de un solo trade.** Con un solo snapshot y n=100, eso es
todo lo que se puede afirmar, y es suficiente para cambiar el orden de ataque.

**Sesgos declarados, todos en la dirección optimista:**

- El neto resta la fee del fill de cierre pero **no** la de apertura ni el
  funding: el PnL real de las supervivientes es *peor* que el reportado.
- El corte de copiabilidad en 20 fills/día es un **juicio, no una medición**. Con
  un corte más laxo entran más candidatas, todas peores.
- Las cuentas capadas en 2.000 fills reportan una **cota inferior** de su
  cadencia: son aún más inalcanzables de lo que dice la tabla.
- Un snapshot, una ventana, un venue. Repetirlo en otra ventana es barato y
  debería hacerse antes de tratar el 1/100 como estable.

---

## 4. Fase 0 — el espejo (sin un centavo, ni propio ni ajeno)

Un colector no-crítico que sigue wallets y simula la copia contra el `PaperBroker`
que ya cobra fees y slippage. Cero capital, cero terceros, cero promesas.

```
tools/fetch_onchain_follow.py      colector: WS userFills + poll clearinghouseState
                                   (mismo patrón no-crítico que fetch_cvd: si muere,
                                   el motor NI SE ENTERA)
      │
      ▼  evento con proof_ref (fill id / tx hash / bloque) + ts_source + ts_detected
entropy_cognition (ledger)         source='onchain:<addr>', schema_version
      │
      ▼
execution.PaperBroker.open()       réplica simulada AL PRECIO DE MERCADO
                                   EN ts_detected, no al precio de la wallet
      │
      ▼
ledger_stats.is_auditable          filtro único; sin proof_ref no entra
reconciler.SignalLedgerView        el mismo guardia que ya audita lo publicado
      │
      ▼
cockpit.html (FQ CAPITAL)          sección nueva en el data-contract existente.
                                   NO se construye un dashboard nuevo.
```

Reutiliza todo lo que ya está cableado. Lo único genuinamente nuevo es el
colector y dos campos en el ledger (`proof_ref`, `ts_source`).

**Duración mínima**: hasta n≥30 réplicas cerradas. Antes de eso el experimento no
concluye ni a favor ni en contra, y no se enseña a nadie.

---

## 5. Invariantes a cablear ANTES de tocar capital

Un hallazgo sin invariante que lo haga cumplir es una nota, no un arreglo. Estas
cinco son la condición de entrada, no el trabajo posterior.

| # | Invariante | Qué impide | Dónde |
|---|---|---|---|
| **I-1** | **Sin `proof_ref` no hay trade.** Toda fila copiada lleva fill id / tx hash. Sin él → no auditable. | Acreditar una operación que solo existe en un tweet | `ledger_stats.is_auditable` |
| **I-2** | **Atribución ≠ identidad.** Toda wallet lleva `attribution_status`. Solo `verified` con filing oficial o prueba on-chain. El resto es `unverified` y **se muestra así en el dashboard**. | Decirle a un inversor que sigue a Trump cuando sigue a una address anónima | colector + contrato del cockpit |
| **I-3** | **Horizonte de réplica.** Un fill detectado con retraso > umbral no se copia y se registra como `missed`. | Que el backtest asuma una réplica que en vivo nunca habría ocurrido (misma forma que el horizonte de outcome) | colector + `PaperBroker` |
| **I-4** | **Lista de wallets congelada y sellada con timestamp.** Cambiar la lista abre una cohorte nueva; las cohortes no se mezclan. | Elegir ganadoras a posteriori — el error que mató la racha de mayo | test que falla si la lista cambia sin nueva cohorte |
| **I-5** | **Precio de réplica = mercado en `ts_detected`.** Nunca el precio de la wallet. | Fabricar el edge exacto que el experimento debe medir | `PaperBroker.open` |
| **I-6** | **La unidad seguida es el CLÚSTER, no la address.** Toda address entra con `cluster_id` y el motivo de pertenencia (transferencia / origen de fondos / sub-cuenta / correlación). Una transferencia desde una address seguida promueve el destino a candidato **automáticamente**. | Medir 1 de las 10 wallets de una entidad y creer que mides a la entidad | colector + test de promoción |
| **I-7** | **Concentración de PnL.** Si al quitar el trade top el PnL de por vida del clúster cae por debajo del 50%, ese clúster es `n=1` y **no es copiable**, gane lo que gane. | Confundir un volado legendario con consistencia (es la lección de mayo, en dominio nuevo) | métrica del colector + gate |

Cada una necesita su test en `tests/`. Si un test no se puede escribir, la
invariante no está cerrada y la fase 0 no arranca.

**I-7 no es teórica.** Aplicada hoy a la wallet del vídeo con las cifras públicas
(~$200M en el short del arancel, ~$100M acumulado después), el clúster **no pasa**:
el trade top es más del 100% del PnL de por vida. Es el filtro más barato del
experimento y ya descarta al candidato estrella antes de escribir el colector.

---

## 6. El muro legal (y es un muro, no un trámite)

Esto es lo que separa "un dashboard" de "un fondo", y no es opinable:

**Cartera custodial + dinero de inversores privados + tú operando = estás gestionando
un fondo**, se llame Trust o se llame como se llame. En EE.UU. eso toca Investment
Company Act, Advisers Act y Reg D; si además opera perps o derivados, entra CFTC/NFA
(registro CPO/CTA). En España/UE es gestión de carteras o IIC, con autorización CNMV.
Custodiar fondos de terceros añade, por su cuenta, el frente de transmisión de dinero.

**No soy tu abogado y esto no es asesoramiento legal.** La parte que sí puedo
afirmar como ingeniería es cuál de las dos arquitecturas te deja opciones:

- **Custodial (el vídeo)**: tú tienes las llaves y el dinero de otros. Máxima
  exposición regulatoria y máxima exposición personal. No lo construyas sin que un
  abogado de tu jurisdicción lo haya firmado **antes** de la primera línea de código.
- **No-custodial**: cada inversor mantiene su propio capital en su propia cuenta
  o sub-cuenta con su API key; tú emites señales, ellos ejecutan. Sigue estando
  regulado en muchos sitios (asesoramiento / gestión), pero **no custodias**. Es la
  única variante que tiene sentido explorar antes de hablar con un abogado.

Y una nota que ya gobierna el repo: el dashboard para inversores **es material de
marketing de un producto financiero**. Le aplica `MEMORY/ROLES/MARKETING.md` entero.

**Qué se puede enseñar hoy, con precisión** (importa, porque este experimento nació
de la presión de un inversor impaciente):

- **NO el `n=12 · WR 41.7% · E[R] +0.208`.** Está por debajo del `MIN_N=30` del
  propio repo: no concluye ni a favor ni en contra. Enseñárselo a un inversor como
  evidencia es venderle ruido con cara de dato.
- **SÍ lo que concluye, aunque incomode:** la geometría viva del VIP está medida
  en **−0.069R neto sobre n=3.774**, con el IC95% entero bajo cero.
- **Y SÍ lo que concluye a favor:** la **entrada separa** — asimetría de recorrido
  **+1.011R, IC95% [+0.825, +1.199]**, en ambos lados y los ocho años (E7). El
  problema no es la señal: son las barreras, el coste y el capital simultáneo.

Ese trío es el pitch honesto, y es más fuerte que cualquier dashboard de wallets:
*sabemos qué funciona, sabemos qué no, y publicamos las dos cosas.*

---

## 7. Criterio de muerte

El experimento se cierra y se escribe en `CEMENTERIO.md` si, con n≥30 réplicas
cerradas y la lista de wallets congelada ex-ante, ocurre cualquiera de estas:

1. El IC95% de la expectancy de la **réplica** (no de la wallet) incluye cero.
2. El deslizamiento de réplica mediano supera el edge bruto de la wallet.
3. La tasa de `missed` (I-3) supera el 30% de los fills de la fuente: la señal
   existe pero no es alcanzable.
4. Todos los clústeres candidatos fallan I-7 (concentración de PnL): no hay a
   quién copiar, solo a quién admirar.
5. El clúster deja de ser observable — la entidad rota a addresses nuevas más
   rápido de lo que el detector de flujo las promociona. Si el denominador se
   esconde a voluntad, no hay medición posible y decirlo es el resultado.

Se cierra igual, y antes, si el track record de una wallet vuelve a salir
"demasiado limpio". Eso ya no se investiga: se descarta.

---

## 8. Orden de ataque

1. **Nada de esto va antes que E1-E9** de `BRIEF_INSTRUMENTO_2026-08.md`. El
   instrumento que mediría este experimento es el que aún se está cerrando; medir
   copy-trading con el instrumento roto reproduce el fantasma en un dominio nuevo.
2. ~~Congelar la cohorte y aplicar I-7~~ → **HECHO (§3).** Cohorte sellada
   `2026-08-05T08:20:28Z`, embudo corrido: **1 candidata de 100**. Costó diez
   minutos y vació la lista casi entera, que era el resultado barato que este
   paso existía para producir.
3. **Repetir el screen en otra ventana** antes de tratar el 1/100 como estable.
   `tools/copytrade_screen.py --top 100 --days 30`. Barato; hazlo un par de veces
   con semanas de separación. Si el superviviente cambia cada vez, la conclusión
   ya no es "queda uno" sino "no queda ninguno de forma persistente", y el
   experimento se cierra aquí sin escribir el colector.
4. **Solo si sobrevive alguien de forma persistente**: colector
   `fetch_onchain_follow.py` + los dos campos de ledger + I-1/I-5/I-6.
5. Correr el espejo hasta n≥30. No enseñar nada mientras tanto.
6. Solo si pasa el gate: hablar con un abogado sobre la estructura **no-custodial**.

_Fuentes externas consultadas (ago-2026): docs de la Info API y WebSocket de
Hyperliquid; cobertura de la STOCK Act y de la Stop Insider Trading Act aprobada
en la Cámara el 22-jul-2026._
