# ROADMAP — post madrugada NASDAQ (2026-07-08)

> Estado tras la noche: motor de continuación descubierto, gateado en NASDAQ (Sharpe ~1.0 OOS),
> afilado con el arsenal cripto. Oro cerrado como cosecha. El plan de aquí prioriza por EV/esfuerzo.

## El insight que ordena todo

El descubrimiento de NASDAQ NO es solo un mercado nuevo — es **la mitad que le falta al producto
cripto**. El motor cripto en vivo es de REVERSIÓN (dispara en KL-bajo, se calla en trending). El
motor de continuación dispara en KL-ALTO (trending). **Juntos cubren los dos regímenes.** Las
sequías de VIP (3-4 semanas mudas que frustraron al dueño) son exactamente el régimen donde la
reversión muere y la continuación viviría. Ese es el hilo de mayor EV.

## Prioridad 1 — Reciclar continuación → CRIPTO (mayor EV, más barato)

**Qué:** correr el motor de momentum/continuación (mismo diseño NASDAQ v3: breakout + parcial+BE,
gate KL-ALTO) sobre BTC/SOL/ETH, con el cube de 7 años que YA tenemos.
**Por qué es #1:**
- Resuelve el dolor real (sequías VIP) — el complemento que π_blade intentó ser y no era.
- Cripto YA está en vivo (feed OKX) → si pasa el gate, va a forward paper INMEDIATO en el bot
  actual (infra motor_paper + tiers ya existe). Cero data nueva que comprar.
- Es el interés compuesto puro: el hallazgo de NASDAQ hace mejor el producto core.
**Cómo:** experimento measure-first (gate DSR/CPCV/PBO + holdout), pre-registrado. Si pasa →
runtime paper `FQ_CONTINUATION` default OFF, mide forward junto al motor de reversión.
**Costo:** ~0 (data en mano). **Esfuerzo:** medio (1 sesión).

## Prioridad 2 — Forward paper NASDAQ (el juez definitivo)

**Qué:** montar feed en vivo de NQ + runtime paper para que el fantasma del NASDAQ respire OOS
en tiempo real.
**Bloqueo:** el bot corre en OKX (cripto); NQ es CME → necesita feed en vivo (decidir: Databento
live streaming vs broker paper Tradovate/IBKR). Es ingeniería + decisión de infra.
**Por qué #2 (no #1):** ya hicimos el holdout OOS (Sharpe ~1.0), que es la validación más fuerte
sin sangre. El forward en vivo confirma, pero no desbloquea producto hoy como sí lo hace P1.
**Esfuerzo:** medio-alto (montar feed). **Decisión pendiente del dueño:** qué feed.

## Prioridad 3 — Higiene + monitoreo (rápido, en paralelo)

- **Rotar la API key de Databento** — sigue expuesta en el chat. Seguridad, 2 min.
- **Revisar el forward de lo cableado esta semana**: ¿el echo `📤 FREE · N entregada(s)` muestra
  entregas? ¿la flota free late? ¿hay usuarios tier free en la BD (o el embudo está vacío)?
- **Poner `FQ_KL_THR=0.40`** en Railway si no está — el dial de cadencia VIP validado.

## Parqueado (bajo EV / esperar)

- **NASDAQ CVD** (comprar trades NQ, confirmación order-flow): puede afilar más, pero estamos a
  ~1.0 OOS — validar forward antes de apilar capas (multiple-testing).
- **Motor de oro propio**: el oro dio pulso marginal; su motor propio es el bet de menor EV.
  Data comprada y lista si algún día. No ahora.
- **Más símbolos cripto** al cubo/forward (BNB ya está).

## La secuencia recomendada para "mañana"

1. **Continuación en cripto** (P1) — el bet estratégico, barato, desbloquea producto.
2. En paralelo: rotar key + revisar forward free-fleet (P3, rápido).
3. Decidir feed NASDAQ (P2) — si el dueño elige, arrancar el montaje.

**Norte:** no perseguir mercados nuevos por brillo — hacer que cada descubrimiento **componga**
sobre lo que ya está en vivo. La continuación en cripto es eso: el mismo motor nuevo, en el
mercado que ya paga, tapando el hueco que más duele. Medida o muerte, décimas compuestas.
