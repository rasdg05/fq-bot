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
- **"$1.000 → $426.000"** es una curva bruta sin coste de ejecución. Es el mismo
  hueco que separa nuestro cube de 7 años (**+0.224R bruto**) del motor paper vivo
  (**−0.510R con fees**). El hueco no es un detalle contable: es del tamaño del
  edge entero.
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
alguien bautizó. Nadie ha probado quién la controla. Podemos seguirla — no podemos
decirle a un inversor de quién es. Ver §4, invariante I-2.

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
posibilidad teórica: es el resultado que ya tenemos en casa (+0.224R bruto vs
−0.510R neto). En copy-trading la enfermedad es peor, porque se añade el
*adverse fill*: entras después del que mueve el precio, y a menudo **porque** lo
movió.

**La métrica primaria del experimento no es el PnL de la wallet. Es el
deslizamiento de réplica**: distribución de (nuestro precio de entrada − su precio
de entrada) en R, y su cola. Si esa distribución se come el edge, el experimento
ha terminado y no hace falta discutir nada más.

---

## 3. Fase 0 — el espejo (sin un centavo, ni propio ni ajeno)

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

## 4. Invariantes a cablear ANTES de tocar capital

Un hallazgo sin invariante que lo haga cumplir es una nota, no un arreglo. Estas
cinco son la condición de entrada, no el trabajo posterior.

| # | Invariante | Qué impide | Dónde |
|---|---|---|---|
| **I-1** | **Sin `proof_ref` no hay trade.** Toda fila copiada lleva fill id / tx hash. Sin él → no auditable. | Acreditar una operación que solo existe en un tweet | `ledger_stats.is_auditable` |
| **I-2** | **Atribución ≠ identidad.** Toda wallet lleva `attribution_status`. Solo `verified` con filing oficial o prueba on-chain. El resto es `unverified` y **se muestra así en el dashboard**. | Decirle a un inversor que sigue a Trump cuando sigue a una address anónima | colector + contrato del cockpit |
| **I-3** | **Horizonte de réplica.** Un fill detectado con retraso > umbral no se copia y se registra como `missed`. | Que el backtest asuma una réplica que en vivo nunca habría ocurrido (misma forma que el horizonte de outcome) | colector + `PaperBroker` |
| **I-4** | **Lista de wallets congelada y sellada con timestamp.** Cambiar la lista abre una cohorte nueva; las cohortes no se mezclan. | Elegir ganadoras a posteriori — el error que mató la racha de mayo | test que falla si la lista cambia sin nueva cohorte |
| **I-5** | **Precio de réplica = mercado en `ts_detected`.** Nunca el precio de la wallet. | Fabricar el edge exacto que el experimento debe medir | `PaperBroker.open` |

Cada una necesita su test en `tests/`. Si un test no se puede escribir, la
invariante no está cerrada y la fase 0 no arranca.

---

## 5. El muro legal (y es un muro, no un trámite)

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
Hoy, el número que se puede enseñar es n=12 · WR 41.7% · E[R] +0.208 · PF 1.76 — y
la frase que lo acompaña es que ninguna configuración medida tiene el IC95% de la
expectancy por encima de cero.

---

## 6. Criterio de muerte

El experimento se cierra y se escribe en `CEMENTERIO.md` si, con n≥30 réplicas
cerradas y la lista de wallets congelada ex-ante, ocurre cualquiera de estas:

1. El IC95% de la expectancy de la **réplica** (no de la wallet) incluye cero.
2. El deslizamiento de réplica mediano supera el edge bruto de la wallet.
3. La tasa de `missed` (I-3) supera el 30% de los fills de la fuente: la señal
   existe pero no es alcanzable.

Se cierra igual, y antes, si el track record de una wallet vuelve a salir
"demasiado limpio". Eso ya no se investiga: se descarta.

---

## 7. Orden de ataque

1. **Nada de esto va antes que E1-E9** de `BRIEF_INSTRUMENTO_2026-08.md`. El
   instrumento que mediría este experimento es el que aún se está cerrando; medir
   copy-trading con el instrumento roto reproduce el fantasma en un dominio nuevo.
2. Congelar la lista de wallets **hoy**, sellada, aunque el colector tarde semanas.
   Cada día que pasa sin congelarla es un día de contaminación por selección.
3. Colector `fetch_onchain_follow.py` + los dos campos de ledger + I-1/I-5.
4. Correr el espejo hasta n≥30. No enseñar nada mientras tanto.
5. Solo si pasa el gate: hablar con un abogado sobre la estructura **no-custodial**.

_Fuentes externas consultadas (ago-2026): docs de la Info API y WebSocket de
Hyperliquid; cobertura de la STOCK Act y de la Stop Insider Trading Act aprobada
en la Cámara el 22-jul-2026._
