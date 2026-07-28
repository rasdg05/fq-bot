# PROMPT — Fase Dinero Real

## CONTEXTO

Eres el ingeniero responsable de **Marea**, mercados de predicción móviles para
Latinoamérica, en español. El producto está vivo en
`fq-bot-production.up.railway.app` y la app vive en `marea/` del repo
`rasdg05/fq-bot`.

Antes de escribir una línea, lee en este orden:

1. `marea/vault/AGENTE.md` — especificación operativa. Función objetivo, ocho
   invariantes, presupuestos, protocolo de verificación de seis peldaños.
   Manda sobre cualquier impulso de ir rápido.
2. `marea/vault/RULINGS.md` — 64 reglas permanentes. Violar una es hallazgo
   crítico automático.
3. `marea/vault/COMPLIANCE.md` — la decisión de custodia y las preguntas
   abiertas por país. **Este documento es el que gobierna esta fase.**
4. `marea/vault/DECISIONES_VISUALES.md`, `INTERFAZ.md`, `VOICE.md`.

Rama de trabajo: `claude/marea-dinero-real`, partiendo de
`claude/marea-multi-outcome-markets-vetiic`.

### Lo que ya funciona y no se rompe

Cuentas con contraseña y código de recuperación · saldo que sobrevive al
reinicio · pozo parimutuel compartido de **N resultados** (el binario es el
caso particular con los ids `si` y `no`) · liquidación automática con siete
fuentes de oráculo (Kraken, BCB, Banxico, INEGI, BCRA, BCRP, mindicador.cl,
datos.gov.co, ESPN) · **cero mercados de confirmación humana** · tabla de
posiciones · ligas compartibles con vista previa e imagen de marca · analítica
propia · **contabilidad de partida doble que cuadra en cero** · solicitudes de
depósito y retiro con estado · interfaz del contrato de custodia definida y
declarada como simulada.

269 pruebas, `npm run validate` PASS, y cinco puertas medidas en navegador
real: `perf`, `densidad`, `arranque`, `acceso`, más `contrast`.

Stack: Vite 5 + React 18 + TypeScript 5 + Tailwind 3 + Radix. Servidor propio
en `server/*.mts` con `tsx`, persistencia JSON atómica sobre volumen de
Railway. Vitest con jsdom para unidad; Playwright con el Chromium de
`/opt/pw-browsers/chromium` (con `--no-sandbox`) para navegador real.

---

## LA PREGUNTA QUE MANDA

**El producto no puede recibir dinero hasta que un abogado local diga que sí,
por país, por escrito.** No es una formalidad: `eligibility.ts` tiene todos los
países en `pendiente` y `validate` falla si alguno pasa a `permitido` sin que
conste la opinión. Esa puerta no se debilita, y ninguna tarea de esta fase la
toca.

Lo que sí se puede construir hoy, sin esperar a nadie, es **todo lo que hace
que el día que llegue la opinión legal se pueda encender en una tarde**. Ese es
el trabajo. Si en algún momento la forma más rápida de avanzar parece ser
abrir la puerta "sólo para probar", la respuesta es no: se construye contra la
puerta cerrada y se prueba con la puerta cerrada.

---

## ESTADO REAL DE LO QUE FALTA

Medido el 28 de julio de 2026. Lo que sigue es inventario, no plan.

| Pieza | Estado hoy |
|---|---|
| Contabilidad de partida doble | **Hecha.** `cuadre()` en cero con datos reales |
| Solicitudes con estado | **Hechas.** Máquina de estados y transiciones validadas |
| Puerta de elegibilidad | **Hecha y cerrada.** Ningún país en `permitido` |
| Interfaz del contrato | **Definida, sin desplegar.** Declara que es simulada |
| Proveedor de wallet embebida | **No existe.** No hay integración con nadie |
| On-ramp (meter dinero) | **No existe** |
| Off-ramp (sacar dinero) | **No existe** |
| Verificación de identidad | **No existe** |
| Geolocalización con proveedor | **No existe.** Sólo se infiere del dispositivo |
| Términos, privacidad, juego responsable | **No existen como documento** |
| Opinión legal por país | **No existe para ningún país** |
| Entidad legal constituida | Fuera del código; hay que preguntarle al dueño |

---

## OBJETIVO

Seis paquetes, en orden estricto. Cada uno se declara terminado con su puerta
de aceptación **medida**, no estimada.

### D1 · La reconciliación que hace auditable el dinero

**Por qué primero.** Hoy `cuadre()` da cero porque todos los asientos los
escribe el mismo proceso. Con dinero real hay una segunda fuente de verdad —el
proveedor, la cadena— y la pregunta deja de ser "¿mi libro es consistente?"
para ser "¿mi libro coincide con lo que de verdad pasó afuera?". Esa segunda
pregunta no tiene respuesta todavía.

- Toda solicitud de depósito o retiro lleva **referencia externa** (id del
  proveedor, hash de transacción) y estado del proveedor, además del nuestro.
- `reconciliar()` compara el libro contra un extracto externo y devuelve tres
  listas: sólo en el libro, sólo en el extracto, y en ambos con monto distinto.
  Las tres tienen que estar vacías para que la reconciliación pase.
- Una solicitud que el proveedor confirma pero el libro no tiene se llama
  **descuadre** y bloquea la corrida, con su alerta. Nunca se resuelve sola.
- Idempotencia por referencia externa: el mismo webhook llegando dos veces
  acredita una vez (I5).

**Puerta.** Prueba de propiedades con 500 operaciones y un extracto sintético
que incluye a propósito: un pago duplicado, uno perdido y uno con monto
distinto. Las tres se detectan. `cuadre()` sigue en cero.

### D2 · El proveedor de custodia, de verdad

`COMPLIANCE.md §1` ya decidió: **wallet embebida non-custodial**, con conectar
como camino secundario. Custodial descartado.

- Elegir entre Privy y Turnkey **con criterio escrito**: qué países soportan,
  qué pasa si el proveedor cae, si el usuario puede exportar su llave, y qué
  cuesta. La decisión va a `COMPLIANCE.md` con su fecha.
- Implementar detrás de `WalletAdapter`, que ya existe y no expone ninguna
  operación que mueva fondos sin el usuario. **Esa propiedad se mantiene.**
- Sin credenciales, degrada a su camino simulado y lo declara (R-022).
- El copy dice, **antes del primer depósito**, que si el usuario pierde el
  acceso Marea no puede devolverle su dinero. No en los términos: en pantalla.

**Puerta.** Prueba de que ninguna ruta del servidor puede mover fondos de un
usuario sin una firma suya. Auditoría automatizada que falla si aparece
`privateKey`, `signTransaction` o equivalente fuera del adaptador.

### D3 · Entrada y salida de dinero

- **On-ramp**: proveedor que acepte tarjeta y transferencia local en México
  primero (SPEI), porque es el mercado con más catálogo. Enchufado a la máquina
  de estados que ya existe.
- **Off-ramp**: el retiro pasa por `en_revision` — ya está en el código y no se
  salta.
- **Webhooks** del proveedor: firmados y verificados. Un webhook sin firma
  válida no mueve un peso.
- Tope de depósito acumulado por país, que ya vive en `eligibility.ts`.

**Puerta.** Ciclo completo en el entorno de pruebas del proveedor: depositar,
apostar, liquidar, retirar. `cuadre()` en cero al final y `reconciliar()`
limpio contra el extracto del proveedor. Con la puerta legal cerrada, el ciclo
corre en `sandbox` y lo declara en pantalla.

### D4 · Identidad y geografía, sólo donde la ley las pide

R-045 es explícita: el país se infiere del dispositivo **para hablarle a la
gente de su mercado, nunca como control de cumplimiento**. Mover dinero exige
geolocalización con proveedor y verificación de identidad.

- Proveedor de geolocalización real, no IP a ojo.
- Verificación de identidad **escalonada**: nada para explorar, nada para jugar
  con puntos, lo mínimo legal para depositar, más para retirar por encima del
  umbral que diga el abogado.
- Los datos de identidad **no pasan por nuestros servidores** si el proveedor
  permite evitarlo. Lo que no se guarda no se filtra.
- La telemetría sigue saliendo por lista blanca (R-020, R-061).

**Puerta.** Prueba de que explorar y jugar con puntos siguen sin pedir nada
(I1, R-002), y de que ningún dato de identidad aparece en la analítica.

### D5 · Los documentos que un usuario tiene derecho a leer

- Términos, privacidad y **juego responsable** en español, escritos con la voz
  de `VOICE.md`, no traducidos de una plantilla gringa.
- Autoexclusión y límites de depósito, accesibles desde el perfil en dos taps.
- Qué pasa con el dinero si Marea cierra. Se responde antes de recibirlo.

**Puerta.** Los tres documentos existen, se llegan desde el perfil, y `validate`
falla si una build con dinero real no los tiene.

### D6 · Encender un país

Sólo cuando exista la opinión legal escrita.

- Una línea en `eligibility.ts` pasa de `pendiente` a `permitido`, con el tope
  de depósito que diga el abogado.
- `COMPLIANCE.md` registra la opinión: quién la firma, cuándo, y qué condiciona.
- Lanzamiento con tope bajo y lista corta de usuarios.

**Puerta.** `validate` sigue en PASS con el país encendido. El ciclo completo de
D3 corre contra producción con dinero real y montos mínimos, y `cuadre()` da
cero.

---

## LO QUE HAY QUE PREGUNTARLE AL DUEÑO ANTES DE D2

No son detalles: cada uno cambia qué se construye.

1. **¿Hay entidad legal constituida, y dónde?** Sin sociedad no hay contrato
   con proveedor de pagos. `COMPLIANCE.md §3` sugiere Uruguay, Paraguay, Costa
   Rica o Panamá como jurisdicciones a evaluar, pero eso es una pregunta
   abierta, no una decisión.
2. **¿Hay presupuesto para la opinión legal?** Es el cuello de botella real, no
   el código. Un abogado de fintech en México cobra por esa opinión y tarda
   semanas.
3. **¿Qué país primero?** México tiene más catálogo y más mercado, pero la Ley
   Federal de Juegos y Sorteos es la pregunta más espinosa de la tabla.
4. **¿Cripto o moneda local?** Cambia el proveedor, el marco regulatorio y el
   público. El código está preparado para las dos, pero hay que elegir.
5. **¿Marea es la contraparte?** Con mercados propios parimutuel, sí lo es. Eso
   contradice la conclusión de `COMPLIANCE.md §2`, escrita cuando la ejecución
   era agregada. **Ese documento hay que reabrirlo antes de D2**, y es lo
   primero que hay que decirle al abogado.

---

## CÓMO TRABAJAR

### Invariantes que esta fase puede romper sin darse cuenta

De `AGENTE.md §4`:

- **I1** — explorar nunca pide cuenta, dinero ni permiso. Ni un muro suave.
- **I3** — el número que se muestra es el que se cobra. Con dinero real, un
  redondeo bonito es una mentira contable.
- **I5** — ninguna acción de dinero se ejecuta dos veces. Los webhooks llegan
  repetidos por diseño.
- **I7** — jugando con puntos no aparece símbolo de moneda. Los dos modos van a
  convivir: el código tiene que distinguirlos sin que el usuario dude.
- **I8** — nada finge hablar con un proveedor que no existe.

### Protocolo de verificación

Los seis peldaños de `AGENTE.md §9`: tipos → pruebas (con al menos una que
**falle antes** del cambio) → `npm run validate` → proceso real con `curl` →
navegador real con Playwright → reinicio confirmando que los datos siguen ahí.

En una fase de dinero, el cuarto y el sexto son los que cuentan. Un `cuadre()`
verde en una prueba de unidad no dice nada sobre lo que pasa cuando el
proveedor manda el mismo webhook dos veces mientras el proceso se reinicia.

Levantar el entorno:

```bash
cd marea && npm run build
MAREA_SECRETO=local PORT=8100 npx tsx server/index.mts &
curl -s --noproxy '*' -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8100/salud
```

No mates el servidor con `pkill -f tsx`: el patrón alcanza a tu propio shell.
Mata por PID confirmado.

### Subagentes — sólo donde ganan

- **Sí**: un `Explore` al empezar D1 con esta tarea exacta: *"Lista cada lugar
  del repo donde se mueve un saldo, se crea un asiento o se acredita un pago.
  Devuelve archivo:línea agrupado por tipo de movimiento, sin proponer
  soluciones."* Y un pase de revisión independiente sobre el diff de D3,
  buscando una sola cosa: dónde un webhook repetido puede acreditar dos veces.
- **No**: para escribir producto, redactar documentos legales, ni decidir el
  proveedor. Eso pide criterio, y un agente en frío no lo tiene.

### Lo que no se hace

- Bajar un umbral para pasar una prueba.
- Reescribir la intención de una prueba para que deje de estorbar.
- Presentar una estimación como medición.
- **Abrir la puerta de elegibilidad "para probar".** Se prueba contra la puerta
  cerrada.
- Mover dinero de gente sin marco legal resuelto.
- Guardar una llave privada de usuario, en ninguna forma, en ningún sitio.
- Tocar `railway.toml` de la raíz: ese servicio es un bot de Python, no esta app.

### Cómo reportar

Primero **qué cambió para el usuario**, luego cómo. Cada número con su método y
su fecha. Un error propio se corrige en una línea y se sigue. Lo que necesites
del dueño va en lista corta y accionable al final.

---

## ARRANQUE

1. `git checkout -b claude/marea-dinero-real`
2. Lee `AGENTE.md`, `RULINGS.md` y `COMPLIANCE.md` completos.
3. **Reabre `COMPLIANCE.md §2`**: dice que Marea no es la contraparte, y con
   mercados propios parimutuel sí lo es. Escribe la corrección antes de tocar
   código — es lo que va a leer el abogado.
4. Lanza el `Explore` del mapa de movimientos de saldo.
5. Escribe la prueba de reconciliación de D1 y déjala fallando.

No preguntes si continúas. Continúa hasta que D1 pase su puerta, y entonces
reporta antes de seguir con D2 — porque D2 depende de respuestas que sólo
puede dar el dueño.
