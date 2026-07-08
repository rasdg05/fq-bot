# ROADMAP — post madrugada NASDAQ (2026-07-08)

> Estado tras la noche: motor de continuación descubierto, gateado en NASDAQ (Sharpe ~1.0 OOS),
> afilado con el arsenal cripto. Oro cerrado como cosecha. El plan de aquí prioriza por EV/esfuerzo.

## El insight que ordena todo (CORREGIDO 2026-07-08 — medido esa misma noche)

La hipótesis original era: "el motor de continuación de NASDAQ es la mitad que le falta a cripto,
taparía las sequías VIP". **MEDIDO Y REFUTADO esa madrugada.** La firma intradía por mercado:

| mercado | corr(apertura→resto) | firma |
|---|---|---|
| NASDAQ | +0.053 | momentum (pasa gate) |
| Oro | +0.040 | momentum débil |
| **Cripto** | **−0.032** | **REVERSIÓN** |

**El signo está invertido en cripto.** Es mean-reverting intradía — lo OPUESTO de los índices. La
continuación pierde en cripto en toda forma (breakout −0.13R, time-anchored −0.09R, DSR 0.000,
CPCV 0% paths+). No se puede portar un motor de momentum a un mercado que revierte. Por eso el
motor cripto en vivo (reversión) funciona: está montado sobre la firma REAL de cripto.

**Lo que SÍ recicla no es la señal — es el MÉTODO:** el gate DSR/CPCV/PBO, el detector KL, las
capas de ejecución (parcial+BE, breakout como filtro), y la disciplina. La dirección del edge NO
transfiere; la maquinaria de medirlo, sí. Cada mercado tiene su firma y hay que medirla, no asumir.

## Prioridad 1 (CORREGIDA) — Décimas de cripto en el edge que YA existe

La continuación queda descartada para cripto (medido). Las décimas de cripto están en **refinar la
reversión que ya paga**, no en un motor nuevo:
- **Portar la gestión parcial+BE** (que en NASDAQ bajó drawdown y subió WR) al motor de reversión
  EN VIVO — si el motor cripto aún no la tiene afinada, es una mejora de ejecución medible y
  portable (no cambia la señal, mejora cómo se cobra). Measure-first: ¿parcial+BE mejora el Sharpe/
  drawdown de las señales de reversión sobre el cube? Si sí → cablear.
- Más símbolos validados (BNB en forward), mejor ejecución maker.
**Costo:** ~0. **Esfuerzo:** bajo-medio. **Nota:** el motor ya tiene ladder gestionado (parciales+
BE del "fantasma") — verificar si ya está optimizado antes de asumir mejora.

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
