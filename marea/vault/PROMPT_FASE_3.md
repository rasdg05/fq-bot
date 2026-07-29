# PROMPT — Fase 3 de Marea

Prompt de arranque para una sesión nueva de Claude Code. Copiar íntegro como
primer mensaje. Está escrito para que una sesión sin contexto previo pueda
ejecutar sin volver a descubrir lo ya decidido.

---

## CONTEXTO

Eres el ingeniero responsable de **Marea**, mercados de predicción móviles para
Latinoamérica, en español. El producto ya está **en producción** y funcionando:
`fq-bot-production.up.railway.app`.

**Antes de escribir una sola línea, lee en este orden:**

1. `marea/vault/AGENTE.md` — tu especificación operativa. Manda sobre cualquier
   impulso de ir rápido. Incluye la función objetivo, la tabla de invariantes,
   los presupuestos numéricos y el protocolo de verificación de 6 peldaños.
2. `marea/vault/RULINGS.md` — 64 reglas permanentes. Violar una es hallazgo
   crítico automático, no una discusión.
3. `marea/vault/INTERFAZ.md` — el análisis comparado contra Kalshi y el flujo
   de dinero con las tres arquitecturas de custodia.
4. `marea/vault/ESTRATEGIA.md` — liquidez, datos y social.
5. `marea/vault/SOFT_LAUNCH.md` — estado actual y qué falta.

**Stack:** Vite 5 + React 18 + TypeScript 5 + Tailwind 3. Servidor propio en
TypeScript corriendo con `tsx` (`marea/server/`), persistencia en JSON atómico
sobre un volumen de Railway. 213 pruebas en vitest, `npm run validate` con
verificaciones estáticas y de comportamiento, `npm run perf` con presupuestos.

**Rama de trabajo:** `claude/marea-autonomous-build-96mklt`.

**Lo que ya funciona y NO se rompe:** cuentas con usuario y contraseña, saldo
que persiste, pozo parimutuel compartido, liquidación automática con oráculos
(Kraken, BCB, Banxico, ESPN), tabla de posiciones, ligas compartibles con vista
previa, recuperación por código, analítica propia, tesorería con asientos.

---

## OBJETIVO DE ESTA FASE

Cuatro entregables, **en este orden estricto**. No empieces el siguiente hasta
que el anterior pase su puerta de aceptación.

### F3.1 · Mercados de resultados múltiples

**Por qué:** hoy sólo sabemos hacer preguntas de sí/no, y las preguntas
culturales y políticas que abren el mercado latino no son binarias. "¿Quién
gana La Casa de los Famosos?" tiene 8 opciones; "¿quién sale esta semana?",
cuatro; "¿quién gana la Liga MX?", dieciocho. Sin esto, la categoría entera
queda fuera. Es también más señal de calibración por mercado.

**Diseño obligatorio — generalización, no camino paralelo:**

El binario tiene que quedar como **caso particular** de N resultados, con los
identificadores `si` y `no`. Un segundo motor en paralelo sería dos fuentes de
verdad para la misma matemática de dinero, y eso no se hace.

```ts
// de esto
interface Pool { si: number; no: number; feeBps: number }
// a esto
interface Pool { outcomes: Record<string, number>; feeBps: number }
```

- `impliedProbability(pool, outcomeId)` = `pool.outcomes[id] / total`.
- `payoutMultiplier(pool, id, stake)` = `(total + stake) × (1 − fee) / (pool[id] + stake)`,
  con la apuesta incluida (R-023).
- `settle(pool, bets, winnerId)`: el denominador es **todo** el lado ganador,
  semilla incluida (R-044). Lo que reparte tiene que ser exactamente lo que
  prometió el multiplicador; ya hay una prueba que lo fija (V45).
- Los mercados del catálogo declaran sus resultados:
  `outcomes: [{ id, label }]`, con `si`/`no` por defecto.
- Los oráculos devuelven un `outcomeId`, no `"si" | "no"`.
- **Migración de datos:** el volumen de producción tiene pozos guardados en el
  formato viejo. El `Store` debe leer ambos y escribir el nuevo, sin perder un
  solo pozo ni una sola apuesta. Escribe la prueba de migración **antes** del
  código: cargar un archivo con el formato viejo y verificar que sale íntegro.

**Interfaz:** un mercado binario sigue mostrando los dos lados como hoy
(R-063). Uno de N muestra la lista de resultados ordenada por probabilidad,
cada uno con su porcentaje y su multiplicador — el patrón de Kalshi, que ya
está analizado en `INTERFAZ.md`.

**Contenido:** publica al menos **dos mercados culturales reales** de N
opciones, con fuente pública citada y criterio inequívoco (R-025). Respeta el
tope de tres mercados de confirmación humana simultáneos (R-062).

**Puerta de aceptación:**
- Las 213 pruebas siguen verdes, sin reescribir su intención.
- Prueba de migración desde el formato viejo, con datos reales del volumen.
- Prueba de que un mercado de 4 opciones reparte exactamente lo prometido.
- Prueba de que la suma de probabilidades de todos los resultados da 1.
- `npm run validate` en PASS, `npm run perf` en PASS.
- Recorrido en navegador real sobre la build de producción.

### F3.2 · Tesorería híbrida y plataforma lista para dinero real

**Decisión del dueño del producto, ya tomada:** arquitectura **híbrida** si la
regulación lo permite — el pozo vive en un contrato y nosotros sólo operamos la
resolución, como Polymarket. Si el marco legal lo impide, **no custodial**.
Custodial queda descartado.

**Lo que se construye ahora, que es válido en las dos arquitecturas:**

1. **Contabilidad de partida doble.** Toda cuenta con dos lados y todo cuadra:
   `usuario`, `pozo:<marketId>`, `tesoreria`, `entrada`, `salida`. Cada
   movimiento es un asiento con fecha, monto, contraparte y motivo. Debe existir
   una función `cuadre()` que sume todo y devuelva cero, y una prueba que la
   ejerza después de cientos de operaciones aleatorias.
   *Razón:* sin esto no hay auditoría posible, y sin auditoría no hay dinero.
2. **Depósito y retiro como solicitudes con estado**, no como llamadas:
   `pendiente → confirmando → acreditado | rechazado`. El retiro además pasa por
   `en_revision`. Así la parte de cadena se enchufa después sin tocar el resto.
3. **Puerta de elegibilidad activa.** `parimutuel_money` sigue exigiendo la
   opinión legal por país (`COMPLIANCE.md`) y la validación ya falla si alguien
   lo enciende sin eso. **No la debilites.**
4. **Interfaz del contrato definida, sin desplegarlo.** Escribe el puerto
   (`depositar`, `apostar`, `resolver`, `retirar`) con una implementación
   simulada que declare que lo es (R-022). El contrato real espera a la opinión
   legal.

**Lo que NO se construye todavía y hay que decir por qué si alguien lo pide:**
el contrato desplegado, la firma de transacciones con fondos de usuarios, y
cualquier retiro automático. Todo eso depende de la opinión legal por país.

**Puerta de aceptación:**
- `cuadre()` devuelve cero después de una prueba de propiedades con al menos
  500 operaciones aleatorias — apuestas, liquidaciones, anulaciones, recargas.
- Ningún camino de dinero real accesible sin la puerta de elegibilidad.
- La tesorería reconcilia contra la suma de comisiones por mercado.
- Documento corto en `vault/` con el diagrama de estados de depósito y retiro.

### F3.3 · Que el feed se sienta lleno

De `INTERFAZ.md §2`, por orden de impacto sobre costo:

1. **Participantes por mercado** — "17 personas" dice más que un volumen en
   puntos, y es la prueba social que hoy falta.
2. **Fecha de cierre explícita** además del relativo: `Cierra el 2 ago, 23:59`.
3. **Escudos y banderas** en deportes. ESPN ya sirve los logos de los equipos en
   la misma respuesta que ya consumimos. Sin bloquear la pintada: si la imagen
   no carga, la card se ve igual de bien (R-047).
4. **Marcador en vivo** en los partidos en curso, con el badge LIVE que ya
   existe. ESPN da el marcador; falta refrescarlo y mostrarlo.

**Puerta de aceptación:** `npm run perf` en PASS — ninguna imagen puede empujar
el LCP arriba de 2500 ms, y el CLS no puede subir. Mídelo, no lo supongas.

### F3.4 · Tarjeta de resultado para redes

Imagen generada en el servidor con el logro del usuario — "le atiné 8 de 10",
racha, posición en la tabla — para compartir en Instagram, X y WhatsApp.

- SVG renderizado en el servidor y convertido a PNG, o SVG servido directo si
  la plataforma lo acepta. Sin dependencias pesadas de navegador headless.
- Ruta `/tarjeta/<usuario>.png`, con las mismas etiquetas de vista previa que
  ya existen para mercados (`server/compartir.mts`).
- **Nunca datos de otros:** la tarjeta muestra sólo lo del usuario que la pide,
  y sólo lo agregado (R-058).

---

## CÓMO TRABAJAR

### Subagentes — cuándo sí y cuándo no

Úsalos sólo donde ganan de verdad. Un agente que arranca en frío re-descubre
contexto que tú ya tienes, y eso cuesta más de lo que ahorra.

**Sí:**
- Un agente **Explore** al empezar F3.1, con esta tarea exacta: *"Mapea cada
  lugar del repo que asume que un mercado tiene exactamente dos resultados.
  Busca `si`, `no`, `Side`, `pool.si`, `pool.no`, `outcome` en `src/`,
  `server/`, `scripts/` y `tests/`. Devuelve una lista de archivo:línea
  agrupada por tipo de cambio, sin proponer soluciones."* Ese mapa es lo que
  evita que el refactor deje un rincón roto.
- Un agente **Plan** para la migración de datos de F3.2, con el archivo real
  del volumen a la vista.
- Un pase de **revisión independiente** sobre el diff de la matemática de
  dinero, antes de dar F3.1 por terminada. Que busque una sola cosa: dónde el
  reparto puede no cuadrar con lo prometido.

**No:** para escribir código de producto, para redactar documentos, ni para
tareas que ya sabes hacer. La coordinación cuesta más que el trabajo.

### Invariantes que no se tocan

De `AGENTE.md §4`. Si una se rompe, se arregla antes que cualquier otra cosa:

| # | Invariante |
|---|---|
| I1 | Explorar nunca pide cuenta, dinero ni permiso |
| I2 | Sin lectura independiente no hay Edge |
| I3 | El número que se muestra es el que se cobra |
| I4 | No se paga con la ventana de disputa abierta |
| I5 | Ninguna acción de dinero se ejecuta dos veces |
| I6 | Lo que el usuario hizo sobrevive a cerrar la app |
| I7 | Jugando con puntos no aparece un símbolo de moneda |
| I8 | Nada finge haber hablado con un proveedor que no existe |

### Protocolo de verificación

Nada se declara terminado sin recorrer los seis peldaños de `AGENTE.md §9`:
tipos → pruebas (con al menos una que **falle antes** del cambio) → validación
→ proceso real con `curl` → navegador real con Playwright → reinicio del
proceso confirmando que los datos siguen ahí.

Los tres últimos son los que atrapan lo que las pruebas no ven. En esta base ya
encontraron tres defectos que ninguna prueba vio: el servidor sin comprimir, el
feed bloqueado esperando a una casa externa, y la comisión que desaparecía.

### Lo que no se hace

- Bajar un umbral para que pase una prueba.
- Reescribir la intención de una prueba existente para que deje de estorbar.
  Si una prueba vieja falla por un cambio legítimo, la corrección se justifica
  en el commit.
- Presentar una estimación como medición.
- Declarar que algo no se puede automatizar sin haber buscado la API pública.
- Mover dinero de gente sin el marco legal resuelto.
- Tocar `railway.toml` sin entender qué corre en cada servicio: el de la raíz
  es un bot de Python, el de `marea/` es esta app.

### Cómo reportar

Primero **qué cambió para el usuario**, luego cómo. Los números medidos van con
su método y su fecha. Un error propio se corrige en una línea y se sigue: sin
ceremonia y sin repetirlo. Lo que necesites del dueño del producto va en una
lista corta y accionable al final.

---

## ARRANQUE

Empieza por F3.1. Lanza primero el agente Explore con el mapeo de supuestos
binarios, y mientras corre, lee `src/domain/parimutuel.ts`,
`src/domain/settlement.ts` y `server/store.mts`, que son los tres archivos
donde vive la matemática que vas a generalizar.

No preguntes si continúas. Continúa hasta que F3.1 pase su puerta de
aceptación, y entonces reporta antes de seguir con F3.2.
