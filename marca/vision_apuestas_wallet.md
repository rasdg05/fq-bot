# Marea — Visión: wallet + apuestas cripto (la "idea millonaria")

> "A los latinos les mama apostar. Quiero darles el poder para apostar sus
> crypto, que sea compatible con Telegram para que lo vean más barato, tal vez
> sus posiciones abiertas desde el bot. Esto es un plan que se debe cocinar a la
> medida y hacerlo lo más simple posible para mi gente latina, que son medio
> neófitos en el tema." — RasDG

**Estado:** visión / a cocinar. No es compromiso de build todavía. Este doc
existe para que la idea no se pierda y para pensar los riesgos con la cabeza
fría **antes** de tocar dinero de la gente.

---

## 1. La intuición (por qué esto puede ser enorme)

Tres verdades que se cruzan:

1. **Al latino le mama apostar.** No es vicio, es cultura: quiniela, rifa,
   Melate, apuestas deportivas. Es una forma de emoción y de esperanza.
2. **El latino ya tiene algo de cripto**, aunque sea poco, y no sabe bien qué
   hacer con ella. Está parada en un exchange o en una wallet.
3. **Apostar "trading" tradicional intimida** (márgenes, liquidaciones, jerga).
   Pero apostar a una **pregunta clara** ("¿BTC cierra la semana arriba de
   X?") no intimida a nadie. Eso es un prediction market.

Marea ya traduce el mercado a una frase clara. El siguiente paso natural es:
**dejar que apuesten a esa frase, con su cripto, sin salir de Telegram.**

Nadie está haciendo esto **con gusto y en español, para el neófito latino**.
Polymarket y Kalshi son gringos, en inglés, y asumen que ya sabes de wallets.

---

## 2. Qué NO es (para no engañarnos)

- **No es un casino.** Un casino tiene ventaja matemática contra el jugador.
  Un prediction market bien hecho es peer-to-peer: la casa cobra comisión, no
  te gana. Esto importa para la marca (honestidad) y para lo legal.
- **No es "trading con apalancamiento disfrazado".** El apalancamiento es lo que
  intimida y liquida gente. Empezamos por apuestas de riesgo acotado: lo máximo
  que pierdes es lo que apostaste. Punto.
- **No es custodia ciega.** El momento en que "guardamos" la cripto de la gente,
  somos un banco sin licencia. Eso es lo más peligroso del plan y §5 lo trata en
  serio.

---

## 3. El producto, lo más simple posible (visión del usuario neófito)

El norte de diseño: **que un neófito pueda apostar en 3 taps, sin entender qué
es una blockchain.** Como abrir una posición en Phantom se siente "seamless".

### Flujo ideal (dentro de Telegram)

```
Marea:  El mercado ahora
        ¿BTC cierra HOY arriba de $61,500?

        [ Sí · paga 1.8x ]   [ No · paga 2.1x ]

        Tu saldo: 25 USDC        (Depositar / Retirar)
```

- Tap en **Sí/No** → confirma monto (botones: 5 / 10 / 25 / otro) → listo.
- La apuesta abierta se ve **en el mismo chat**, como una posición viva, con su
  precio y su "vas ganando / vas perdiendo" en lenguaje llano.
- Al cerrar el mercado, se liquida solo y el saldo se actualiza. Sin planillas,
  sin MetaMask, sin gas fees visibles.

### Por qué Telegram lo hace sentir "más barato"
No hay que descargar otra app, no hay onboarding de exchange, no hay KYC en la
cara desde el minuto uno. La fricción percibida —que es lo que mata al neófito—
tiende a cero. **La wallet vive donde el usuario ya vive.**

### Tipos de mercado (de más simple a más rico)
1. **Direccionales de precio** (MVP): "¿X arriba/abajo de Y al cierre de
   hoy/semana?" — se resuelven con el mismo feed que ya tenemos.
2. **Eventos macro**: "¿La Fed sube tasas en la próxima reunión?" (se resuelven
   con el calendario económico que ya integramos).
3. **Cripto-nativos**: "¿ETH flippea a X?", "¿tal moneda arriba de tanto este
   mes?"
4. **A largo plazo**: integrarse a Polymarket/Kalshi como liquidez externa
   (apostar a sus mercados desde Marea, en español y sin fricción).

---

## 4. Cómo funciona por dentro (mecánica, sin humo)

Dos caminos, de menor a mayor ambición. **Empezar por el más simple.**

### Camino A — Parimutuel propio (MVP, sin blockchain al principio)
- El usuario deposita USDC a un saldo interno (custodial, ver §5).
- Cada mercado es un **pool**: los que apostaron "Sí" contra los que apostaron
  "No". Al resolver, el pool perdedor se reparte entre los ganadores, menos una
  comisión de Marea (p. ej. 2-5%).
- **Ventaja:** no necesitamos contraparte ni order book. Con poca gente ya
  funciona. Es como una quiniela — cultura conocida.
- **Precio "1.8x"** = payout implícito según cómo esté repartido el pool.
- **Riesgo:** liquidez y resolución (oráculo). Ver §5.

### Camino B — On-chain / integración a mercados existentes (fase 2+)
- Conectar wallet real (WalletConnect / Phantom-style) y rutear la apuesta a un
  prediction market con liquidez profunda (Polymarket en Polygon, Kalshi
  regulado en USA). Marea es la **capa de gusto + traducción al español**
  encima; no reinventa el motor de mercado.
- **Ventaja:** liquidez y credibilidad instantáneas; menos riesgo de custodia si
  es non-custodial de verdad.
- **Reto:** UX de wallet real es más fricción; hay que esconderla muy bien para
  el neófito (abstracción de cuenta, gas patrocinado).

### La resolución (el oráculo) — el punto que hace o rompe la confianza
- Para mercados de precio: se resuelven con un feed **público y auditable**
  (p. ej. el cierre de Binance/exchange mayor a una hora fija), citado en el
  mercado desde antes. Nunca "porque Marea lo dice".
- Regla de marca: **el criterio de resolución se muestra ANTES de apostar**,
  redactado en una frase clara. Cero ambigüedad, cero "la casa decide".

---

## 5. Los riesgos que hay que cocinar en serio (no saltárselos)

Esto es dinero de la gente. Honestidad = marca **y** supervivencia.

| Riesgo | Por qué importa | Cómo lo abordamos |
|---|---|---|
| **Custodia** | Guardar cripto ajena sin licencia = banco ilegal, y un hackeo nos hunde | Preferir **non-custodial** cuanto antes; si hay saldo custodial en MVP, mantenerlo mínimo, segregado, auditable, y con límites de retiro claros |
| **Regulación** | Prediction markets viven en zona gris; varía por país LATAM | Empezar por mercados de "habilidad/información" y montos chicos; asesoría legal antes de escalar; ToS claros; geofencing si hace falta |
| **Oráculo / disputa** | Si la resolución no es transparente, perdemos la confianza (que ES el producto) | Fuente pública citada de antemano; ventana de disputa; nunca resolución discrecional |
| **Liquidez** (camino A) | Pool chico = payouts feos = nadie vuelve | Sembrar liquidez inicial nosotros; o rutear a mercados profundos (camino B) |
| **Ludopatía** | Al latino le mama apostar → responsabilidad real | Límites de depósito, "modo enfriamiento", nunca crédito/apalancamiento, mensajes de juego responsable. La marca es honesta o no es |
| **Reputación** | Un solo "me robaron" en redes nos mata siendo chicos | Transparencia radical: saldos verificables, historial público de resoluciones |

**Principio rector:** preferimos crecer despacio y limpio que rápido y turbio.
Un solo escándalo de custodia borra años de buen gusto.

---

## 6. Roadmap por fases (de lo simple a lo enorme)

- **Fase 0 — Papel (aquí estamos).** Este documento + validación legal básica +
  decidir custodial vs non-custodial para el MVP.
- **Fase 1 — Apuestas de mentira (paper betting).** Mercados direccionales
  resueltos con nuestro feed, apostando **puntos, no dinero**. Cero riesgo
  legal/custodia, prueba el apetito y la UX en Telegram. Mide: ¿la gente vuelve?
- **Fase 2 — MVP con dinero, parimutuel, montos chicos.** USDC, límites bajos,
  pocos mercados curados, resolución transparente. Con marco legal resuelto.
- **Fase 3 — Wallet non-custodial + integración a Polymarket/Kalshi.** La capa
  de gusto en español sobre liquidez profunda. Posiciones desde el bot.
- **Fase 4 — Mercados propios ricos** (macro, cripto-nativos, sociales) y
  economía de la comunidad.

**Lo primero que hay que construir es la Fase 1 (paper betting):** valida la
"idea millonaria" con cero riesgo antes de tocar un peso. Si la gente no vuelve a
apostar puntos gratis, tampoco lo hará con dinero — y nos ahorramos el infierno
regulatorio para descubrirlo.

---

## 7. Por qué esto encaja con lo que ya somos

- Ya tenemos el **feed** (cripto, oro, índices, petróleo) → resuelve mercados de
  precio sin infraestructura nueva.
- Ya tenemos el **calendario económico** → resuelve mercados de eventos macro.
- Ya vivimos en **Telegram** → el canal de menor fricción del planeta para LATAM.
- Ya tenemos el **tono honesto** → es exactamente lo que un producto de apuestas
  necesita para no oler a estafa.

La apuesta no es un pivote. Es la **monetización natural** de traducir el mercado
a una frase clara: si te la traducimos, ¿por qué no dejarte apostar a ella?
