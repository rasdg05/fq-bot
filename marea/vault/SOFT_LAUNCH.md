# SOFT LAUNCH — qué falta, en orden

Estado al 27 de julio de 2026, segunda revisión. `npm run ci` en verde: **192
pruebas**, `VALIDATION_REPORT` en PASS con dos verificaciones nuevas (L1 y M1), y
`npm run perf` en PASS en los dos recorridos.

**Veredicto: SOFT_LAUNCH_READY en modalidad de puntos.** Los dos bloqueantes de
ciclo de vida están cerrados y automatizados. Lo que queda para publicar no es
código: es una sesión tuya en el hosting.

---

## Los dos bloqueantes, cerrados

### B1 · Los mercados ahora se liquidan y pagan, solos

El ciclo completo existe y corre sin que nadie se acuerde:

```
abierto → cerrado → leído → en disputa → pagado
                              ↘ atorado (espera a una persona)
```

- **Oráculo de precio** (`kraken-ohlc`): lee las velas diarias públicas de
  Kraken y resuelve por programa. No interpreta el criterio en español —ejecuta
  una regla que declara el mismo umbral, y el catálogo no se publica si las dos
  no coinciden (R-042).
- **Oráculo institucional**: lo que publica el INEGI, Banxico, el BCRA o el
  DANE en un boletín no se puede leer sin interpretar un PDF. No se adivina: el
  mercado queda `atorado` con la liga a la fuente para que una persona lo
  confirme en dos taps. Se resuelve a mano, no se resuelve solo.
- **Ventana de disputa**: no se paga mientras siga abierta, aunque el resultado
  ya se conozca. Esa espera es la promesa, no una demora.
- **Pago al ledger**: acreditado una sola vez por posición, con guarda síncrona
  además de la del ledger — el mismo defecto del doble tap (R-016) aplicaba aquí.
- **En pantalla**: el portafolio muestra `Ganaste / Perdiste / Devuelto` con la
  lectura exacta que lo justifica ("cierre 72,500 USD frente al umbral de
  71,000"). Cobrar no es un acto de fe.

Corre con `npm run settle`, y cada hora vía `npm run cron:install`.

### B2 · El catálogo se repone solo

- `npm run roll` escribe los mercados de la semana a partir del precio de hoy,
  con umbrales redondos ("¿Bitcoin cierra la semana arriba de 64,000?").
- Sólo genera preguntas que el oráculo sabe resolver por programa: un mercado
  que se crea solo pero necesita a una persona para pagarse mueve el problema
  de lugar.
- Sin precio no inventa umbral: genera un mercado menos.
- Los vencidos salen del feed (`mx-mundial-grupo`, que llevaba un mes muerto,
  ya no está en el catálogo).
- La verificación **M1** falla si quedan menos de 6 mercados abiertos, contando
  el catálogo escrito a mano y el generado. El feed vacío deja de ser una
  sorpresa.

---

## Lo que se encontró al construirlo

**El motor pagaba distinto de lo que la pantalla prometía.** `settle()` repartía
sólo entre las apuestas de usuarios e ignoraba la semilla del pozo, así que una
apuesta ganadora de 100 puntos cobraba 1,067 cuando el multiplicador mostrado
antes de entrar decía 178. Los dos números tienen que ser el mismo, y ahora lo
son, con prueba que lo fija (R-044, V45).

**El feed esperaba a la casa externa antes de pintar.** Con Polymarket
inalcanzable eran 20 s de pantalla en blanco, medidos en el navegador. Los
mercados no dependen de esa lectura —sólo el Edge— así que ahora salen sin ella
y el Edge se enciende cuando llega: 20.4 s → 0.8 s (R-047).

**Se citaba Binance y se iba a leer Kraken.** Los dos mercados de cripto del
catálogo citaban un par de Binance que no tiene endpoint público estable. Ahora
citan exactamente el endpoint de Kraken que el oráculo consulta, verificable a
mano desde el navegador (R-046).

---

## Listo y verificado

| | Estado |
|---|---|
| App móvil completa, español Latam | ✓ 192 pruebas |
| Motor parimutuel, con lo que reparte igual a lo que promete | ✓ |
| Liquidación automática con oráculo y ventana de disputa | ✓ `npm run settle` |
| Reposición automática del catálogo | ✓ `npm run roll` |
| Contrato de resolución que rechaza lo discrecional | ✓ valida al cargar |
| Puntos: bienvenida, sin crédito, sin canje | ✓ |
| Onboarding de un tap, sin wallet ni KYC | ✓ |
| Edge sólo con referencia externa, se apaga si el venue cae | ✓ |
| Detección de país en el dispositivo, sin red ni dato personal | ✓ |
| Wallet conectada real por EIP-1193 | ✓ sin contrato con nadie |
| Métricas móviles y rendimiento medido | ✓ LCP 1.70 s, INP 56 ms, al feed 1.8 s |
| Publicar y operar desde tu máquina, sin CI | ✓ `npm run deploy` |

## Pendientes que no bloquean el lanzamiento con puntos

- **Telemetría en producción.** Sin `VITE_ANALYTICS_ENDPOINT` los eventos se
  quedan en memoria: se lanza, pero no se mide si la gente vuelve — que es justo
  lo que la modalidad de puntos existe para averiguar.
- **Rendimiento de campo.** Lo medido es laboratorio.
- **Modelo propio de Edge.** Gated en 3.29 pp contra un máximo de 2 pp. El Edge
  sale sólo de referencia externa; el modelo sigue en investigación con la
  superficie de volatilidad acumulándose a diario.
- **El pozo es local en esta build.** Cada dispositivo corre su propia copia del
  parimutuel sobre la semilla publicada: no hay pozo compartido entre usuarios
  porque no hay servidor. Con puntos es honesto y funciona; con dinero exige
  backend, y está declarado aquí para que nadie lo descubra después.
- **Segundo par de ojos sobre el copy.**

## Bloqueado sólo para dinero real (no aplica a puntos)

1. Consulta legal por país — `COMPLIANCE.md` §3.
2. Geolocalización con proveedor y verificación de identidad: la detección por
   zona horaria informa, no cumple (R-045).
3. Wallet embebida (custodia delegada): alta propia con el proveedor MPC. La
   wallet **conectada** ya funciona y no depende de nadie.
4. Pozo compartido en servidor.
5. Encender `eligibility_enforced`, que la validación exige para builds con
   dinero.

---

## Qué necesito de ti

**Para publicar hoy**, una sola cosa: entrar una vez al hosting desde tu
máquina. `npx wrangler login` y después `npm run deploy`. No lo puedo hacer yo
—no tengo tu cuenta, y publicar tu producto es tu decisión, no mía.

**Para que el producto se mantenga solo**: `npm run cron:install` en tu máquina.
Deja corriendo la liquidación, la reposición del catálogo y la toma diaria de
volatilidad, cada hora. Si tu máquina se apaga, no se pierde nada: la próxima
corrida retoma.

**Una decisión de producto, no urgente**: cuántos mercados de Latam puro
(elecciones, inflación, fútbol) quieres al mes. Los de cripto se generan solos;
los institucionales los escribimos a mano porque su fuente es un boletín, y ésos
son los que le dan cara local al producto.

**Opcional pero recomendado antes de lanzar**: una cuenta de analítica para el
endpoint. Sin eso lanzamos a ciegas.
