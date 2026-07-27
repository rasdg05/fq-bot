# Superficie de volatilidad implícita — historia propia

Un archivo por día, tomado de la cadena de opciones de Deribit. Para cada
moneda y cada vencimiento: la volatilidad en el dinero y la sonrisa a ±10 %.

**Por qué existe.** El índice DVOL es de 30 días constantes, y nuestras
preguntas vencen a 7, 14 y 30. Ese desajuste de plazo es el error más claro que
quedó abierto en `vault/MODEL.md`. La superficie por vencimiento sí resolvería
el plazo — pero su historia no está en ningún endpoint público, sólo el estado
de hoy. Así que la construimos nosotros, un día a la vez.

**Cómo se llena.** `.github/workflows/marea-iv.yml` corre a diario y hace
commit del archivo. A mano: `npm run collect:iv`.

**Cuándo sirve.** Con unos seis meses ya se puede recalibrar el modelo usando
la volatilidad del plazo de cada pregunta en vez del índice a 30 días, y volver
a medir con `npm run calibrate`. Antes de eso la muestra no alcanza.

Cada día que el cron no corre es un dato que no se recupera.
