# PRODUCT — Marea (app de mercados de predicción)

Fuente de verdad del producto para el ciclo ORCH → ARCH → BUILD → AUDIT.
Deriva de `marca/cultura_y_tono.md` y `marca/vision_apuestas_wallet.md`.

## Qué es

Marea es una app de **mercados de predicción para Latam**, en español, mobile-first.
Traduce el mercado a una pregunta clara y deja apostar a esa pregunta.

**El diferenciador es el Edge visible:** mostramos lado a lado la probabilidad
del mercado y la probabilidad estimada por Marea. Nadie más en la categoría le
enseña al usuario dónde el mercado y el modelo no coinciden.

Fusión de referencias:
- **Kalshi** — la probabilidad es el número rey.
- **Polymarket** — la card como unidad de descubrimiento.
- **Stake** — energía oscura, densidad con jerarquía.
- **FOMO value-first** — el valor se ve antes de cualquier muro.

## Qué NO es

- No es un copiloto ni un grupo de señales. (En la app de activación no se
  menciona metodología, FQ, Fibonacci ni "copiloto"; ver `VOICE.md`.)
- No es un casino: la casa cobra comisión, no le gana al usuario.
- No es trading apalancado: lo máximo que se pierde es lo apostado.
- No es un front genérico sin Edge.

> Nota de marca: `marca/cultura_y_tono.md` §7 define Marea como "el copiloto de
> mercado en español". Esa frase es de **marketing de la marca madre**, no de la
> app de mercados de predicción. En superficie de producto está prohibida
> (RULING R-003).

## Decisiones cerradas (no se re-litigan)

| # | Decisión |
|---|---|
| 1 | Edge se muestra solo si `abs(prob_Marea - prob_Market) >= 4 pp` |
| 2 | Card: `Marea +X%` · Detalle: `Mercado XX% · Marea YY% · Edge +Z%` |
| 3 | Explore-before-fund obligatorio: se explora sin fondos y sin cuenta cargada |
| 4 | Onboarding value-first, < 75 s hasta el feed |
| 5 | Seed phrase fuera del path principal |
| 6 | Sin KYC en onboarding |
| 7 | Soft launch sin market maker propio ni order book propio |
| 8 | Datos: mock → adapter de agregación (mismo contrato) |
| 9 | Trade puede ser agregación / deep-link al inicio, con copy honesto |
| 10 | **Mercados propios de Latam con motor parimutuel.** Marea escribe la pregunta, corre el pozo y cita la fuente de resolución. La agregación queda como suministro complementario |
| 11 | **Se arranca con puntos, no con dinero** (Fase 1 del roadmap de la visión). Sin custodia y sin riesgo regulatorio mientras se valida el apetito |

## Consecuencia abierta de la decisión 10

El Edge necesita una lectura independiente del pozo. Hoy sólo existe para las
preguntas que también cotizan en una casa global —y en ésas la lectura es de
ella, no nuestra, así que el copy la nombra (R-027)—. **En los mercados de Latam
puro no hay Edge todavía**: hace falta un modelo propio de probabilidad. Es el
pendiente número uno del producto, y está medido en `DATA_SOURCES.md`.

## Scope de soft launch

Dentro: wallet embebida (crear/conectar), feed con Edge, detalle de mercado,
inicio de depósito, portafolio, estados de error accionables.

Fuera: order book nativo, market maker propio, comentarios/social, multi-idioma
completo, notificaciones push avanzadas, rediseño de marca fuera de tokens.

## Métrica de éxito del soft launch

Time to Feed < 75 s · explore-before-fund 100 % del path · task success de abrir
detalle > 85 % · Edge visible en todos los mercados que superan el umbral.
