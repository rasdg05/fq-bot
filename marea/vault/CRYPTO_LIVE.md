# Cripto en vivo — velas de 5 y 15 minutos

Mercados que nacen y mueren cada pocos minutos: *¿el cierre de esta vela queda
arriba o abajo del strike?* Es lo que hace que la app se sienta viva — quien
entra encuentra algo pasando **ahora**, no algo que resuelve en septiembre.

Este documento existe porque dos decisiones de este bloque tenían que quedar
escritas antes de que nadie apueste: **con qué precio se paga** y **de dónde
sale el precio que se enseña**.

---

## 1. Cómo funciona una vela

| | |
|---|---|
| Activos | BTC/USD y ETH/USD |
| Horizontes | 5 min y 15 min |
| Resultados | `arriba` / `abajo`, nombrados con el strike ("Arriba de 71,200") |
| Ventana | alineada al reloj UTC: `floor(ahora / W) * W` |
| Strike | precio del ticker al nacer el mercado, redondeado |
| Apuestas | cierran **10 s antes** del cierre de la vela |
| Liquidación | cierre de la vela pública de Kraken |
| Disputa | 60 s |
| Motor | parimutuel, comisión 300 bps — el mismo del resto del catálogo |

Línea de tiempo de una vela de 5 minutos que abre a las 16:35:

```
16:34:50  nace el mercado · se fija el strike · abre a apuestas
16:35:00  abre la vela en Kraken
16:39:50  cierran las apuestas · nace la vela de 16:40
16:40:00  cierra la vela
16:40:20  se lee el cierre (20 s de gracia)
16:41:20  cierra la ventana de disputa · se paga
```

### Por qué las apuestas cierran 10 s antes

Apostar con un segundo de vela por delante es apostar sobre algo que ya pasó, y
en parimutuel esa apuesta la pagan los demás (R-043). Diez segundos es el mínimo
que corta el caso más burdo sin volver inútil el último minuto, que es justo
cuando la gente juega. **Es una decisión revisable**: si aparece juego de
francotirador en los últimos segundos, el número sube — vive en una sola
constante, `BLOQUEO_MS` en `src/domain/vela.ts`.

Ese mismo instante es cuando nace la vela siguiente, así que nunca hay un
segundo sin mercado abierto por activo y horizonte.

### Por qué el strike se redondea, y a cuánto

El strike se dice en voz alta ("arriba de 71,200"), así que se redondea. Pero
redondear mucho inclina el mercado antes de empezar: si el paso es grande frente
a lo que se mueve el precio en cinco minutos, la pregunta ya viene contestada.

El criterio es que **el paso no pase del 0.1 % del precio**: BTC redondea a 100
(0.07 % a 71 k), ETH a 5 (0.11 % a 4.5 k). Está en `pasoDeStrike()`.

### Por qué el strike no se recalcula nunca

El mercado nace 10 s antes de que abra su vela, con el precio de ese momento. A
partir de ahí el strike es inmutable, aunque el precio se mueva. Corregirlo al
abrir la vela —para que fuera literalmente la apertura— le cambiaría la pregunta
a quien ya apostó, que es peor que la imprecisión de diez segundos que evita.

---

## 2. Decisión de liquidación: **cierre exacto**, no promedio

Se paga con el **cierre exacto** de la vela de Kraken (`interval=5` o
`interval=15`), no con un promedio de los últimos 30-60 segundos.

**Por qué.** El cierre es un número que Kraken sella y que cualquiera vuelve a
leer con una sola consulta a la URL que citamos antes de aceptar apuestas. Un
promedio exigiría que el usuario rehiciera *nuestra* aritmética para
comprobarnos — bajar velas de un minuto, decidir cuántas, promediarlas como
nosotros — y eso es exactamente lo contrario de lo que vende este producto. La
verificabilidad de un clic vale más que la robustez marginal contra una mecha de
un segundo.

El contra conocido: un cierre puntual es más sensible a un pico que un promedio.
Lo asumimos, y por eso el criterio publicado nombra la vela por su hora exacta.

**Casos borde, escritos antes de que ocurran:**

- **Empate exacto** (cierre == strike) → resuelve `abajo`. `arriba` exige cierre
  *estrictamente mayor*, y así está en el criterio que se publica.
- **Kraken todavía no publica la vela cerrada** → `sin_dato`, se reintenta. No se
  inventa un resultado ni se usa la vela en curso: se exige ver **la vela
  siguiente** en la respuesta como prueba de que la nuestra ya cerró.
- **Kraken caído** → `sin_dato`, se reintenta cada 10 s. El mercado no se paga
  hasta poder leerlo.
- **Menos de dos apostadores** → se anula y se devuelve todo, íntegro (R-059).
  Con velas de cinco minutos éste va a ser el caso común al principio.
- **Nadie del lado ganador** → se devuelve el pozo entero, sin comisión (R-024).

**Fuente citada = fuente leída.** El criterio dice Kraken y el oráculo lee
Kraken. Nunca citamos un exchange y leemos otro.

---

## 3. Decisión de precio en pantalla: dos fuentes, una declarada

El número que se mueve mientras la vela corre **no** es el que liquida. Son dos
cosas distintas y conviene tenerlo claro:

| | Qué es | De dónde sale |
|---|---|---|
| **Spot en la card** | el precio de ahora, cada 3 s | motor propio si está configurado; si no, Kraken |
| **Strike** | contra qué se compara | el spot del ticker al nacer el mercado |
| **Cierre** | **lo que paga** | siempre la vela pública de Kraken |

**Precedencia del ticker** (`server/precios.mts`):

1. **Motor propio** — el que ya analiza las monedas grandes. Es la fuente
   primaria cuando `MAREA_FQ_PRECIOS_URL` está configurada.
2. **Kraken público** — respaldo. Entra si el motor tarda más de 5 s, falla, o
   simplemente no está configurado. Tras un fallo el motor queda castigado 60 s,
   para no reintentar contra algo que está caído en cada vuelta.

Una lectura se sirve mientras esté fresca (3 vueltas del ticker, 10 s). Pasada
esa ventana el ticker responde "no sé" y **la card enseña ausencia**, no el
último número que tuvo. Un precio viejo presentado como de ahora es mentira con
forma de dato (R-022).

**El caveat que hay que tener a la vista.** Si el motor propio y Kraken difieren,
alguien puede ver el spot un pelo arriba del strike y que la vela liquide abajo.
Por eso el bloque vivo viaja con su `fuente`, `/salud` publica qué ticker está
sirviendo, y el criterio de resolución nombra Kraken en todos los casos. Si la
divergencia resulta molesta en la práctica, la salida no es cambiar la fuente de
liquidación —que es la que se puede auditar— sino enseñar el spot de Kraken.

Una lectura para todos, en el servidor, cada 3 s. No una por dispositivo: con
mil personas mirando la misma vela, un ticker por navegador es mil veces la misma
pregunta al mismo endpoint.

---

## 4. La ventana de disputa de 60 segundos

`MIN_DISPUTE_HOURS` son 12 h y no se toca. Los mercados vivos usan una excepción
declarada por mercado: `liveVerification: true`, con piso de 60 s
(`MIN_DISPUTE_SECONDS_LIVE`).

**Por qué la excepción no afloja la promesa.** Las 12 h existen porque un dato
institucional se corrige: el INEGI revisa, el BCRA republica, y pagar antes de
que el dato se asiente sería pagar sobre algo que puede cambiar. El cierre de una
vela de cinco minutos no se revisa: o está en la respuesta de Kraken o no está.
Sesenta segundos alcanzan para abrir la URL citada y mirar la vela, que es todo
lo que la ventana puede ofrecer con este tipo de dato.

Un mercado de cinco minutos con 12 h de disputa no sería más honesto: sería un
mercado que no se puede pagar.

---

## 5. Dónde vive cada cosa

```
src/domain/vela.ts                     ventanas, strike, cuenta regresiva (puro)
src/domain/oracleRule.ts               VelaRule + su validación
src/domain/resolution.ts               liveVerification y su piso
src/adapters/ownMarkets/cryptoLive.ts  el mercado de una vela
src/adapters/oracles/velaOracle.ts     lee el cierre en Kraken
src/components/CryptoLiveCard.tsx      la card viva
server/precios.mts                     ticker de spot con precedencia y respaldo
server/vivos.mts                       planificador: siembra, purga, pulso
server/index.mts                       los tres relojes
```

**Tres relojes, tres trabajos:**

| Reloj | Cada | Qué hace | Variable |
|---|---|---|---|
| ticker | 3 s | lee el precio | `MAREA_PRECIO_MS` |
| planificador | 1 s | siembra y purga velas | `MAREA_PLAN_VIVO_MS` |
| ciclo vivo | 10 s | lee cierres y paga | `MAREA_CICLO_VIVO_MS` |

El ciclo de 15 min del catálogo normal sigue igual: una cadencia sana para un
mercado que cierra el domingo y absurda para uno que dura cinco minutos.

---

## 6. Qué no engorda el disco

Se generan ~768 velas al día y casi todas mueren sin que nadie las toque. Por eso
un mercado vivo **no escribe nada** hasta que alguien apuesta:

- el pozo se crea con la primera apuesta (`asegurarPozo` en `/api/apostar`);
- desde ahí el mercado se persiste, para que un reinicio a mitad de vela no deje
  esa apuesta sin quién la resuelva;
- se olvida en cuanto se paga;
- las velas vencidas que nadie tocó salen del feed en el acto, y del
  planificador cinco minutos después.

Una vela con dinero adentro **nunca** desaparece del catálogo por haber vencido:
quien apostó tiene derecho a ver en qué terminó.

---

## 7. Lo que este bloque no hace

- **El score de `nivel_live`.** Hoy el orden es el mínimo para que lo vivo se vea:
  primero lo que está corriendo, y entre eso, lo que cierra antes. El score con
  deportes, momentum e histéresis es el bloque siguiente — y con él llega el
  techo de 2 slots para cripto, que es lo que va a evitar que cuatro velas casi
  idénticas ocupen el feed entero cuando las ventanas de 5 y 15 min coinciden.
- **La preselección al abrir el detalle.** Tocar una pill abre el mercado, pero
  la hoja todavía no llega con ese lado elegido.
- **El Edge en la card viva.** Queda para el detalle, más adelante (regla 6).
