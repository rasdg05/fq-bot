# RULINGS — append-only

Cada línea es una regla permanente. Violarla es hallazgo **crítico** automático.
Se agrega una línea cuando un hallazgo de audit es recurrente o de producto.

- **R-001** — Nunca mostrar Edge si `abs(prob_Marea - prob_Market) < 4 pp`.
- **R-002** — Nunca forzar depósito, KYC ni seed phrase para explorar.
- **R-003** — Nunca usar lenguaje de copiloto / señales / metodología (FQ,
  Fibonacci, DSR) en la superficie de producto.
- **R-004** — La probabilidad es el nodo tipográfico dominante de la card y del
  detalle; el Edge es el segundo ancla, nunca el primero.
- **R-005** — Todo color con significado (Edge, LIVE, subida/bajada) lleva
  además texto o forma; el color nunca es el único portador.
- **R-006** — Todo CTA crítico expone `idle | loading | disabled | error`; todo
  listado expone `loading | empty | data | error`.
- **R-007** — Los strings visibles viven en `src/lib/strings.ts`; ningún texto
  de UI se escribe inline en un componente.
- **R-008** — Ningún error muestra stack trace ni código técnico como mensaje
  principal: siempre `user_message_es`, y `Reintentar` si es `retryable`.
- **R-009** — Analytics y errorReporter caídos nunca bloquean ni rompen la UX.
- **R-010** — Los targets táctiles son ≥ 44×44 pt con separación ≥ 8 pt, y los
  CTA primarios viven en la zona del pulgar (60 % inferior).
- **R-011** — Si `trade_execution_mode` no es ejecución propia, el copy declara
  que Marea no es la contraparte. Nunca prometer matching nativo.
- **R-012** — Fase 2 no altera los tokens de Fase 1: cero drift de design system.

<!-- ciclo de audit fase 1 -->
- **R-013** — El detalle de mercado muestra siempre el criterio de resolución
  (`resolution_summary`) antes de cualquier CTA de operar. (audit_cycle F1-A1)
- **R-014** — El feed no monta más de un estado a la vez: `loading`, `empty`,
  `error` y `data` son excluyentes. (audit_cycle F1-A1)

<!-- ciclo de audit fase 2 -->
- **R-015** — `onboarding_completed` solo se marca al llegar al feed (P4), nunca
  al crear la wallet: un fallo de wallet no puede dejar el onboarding cerrado.
  (audit_cycle F2-A1)
- **R-016** — Toda acción de dinero (crear wallet, depositar, operar) es
  idempotente frente a doble tap: mientras está `loading` no se re-dispara.
  (audit_cycle F2-A1)

<!-- pase visual de audit (fase 1 + 2) -->
- **R-017** — Ningún color de token lleva modificador de opacidad de Tailwind
  (`bg-bg/95`, `border-teal/40`): un color declarado como `var(--x)` no admite
  alfa y la declaración se descarta, dejando la superficie transparente. Las
  superficies de chrome (header, tabs) son sólidas. (audit_cycle F2-A2, visual)
- **R-018** — Todo indicador con dirección (icono de Edge, flechas de resultado)
  sigue el signo del dato: un Edge negativo nunca apunta hacia arriba.
  (audit_cycle F2-A2, visual)

<!-- ciclo de integraciones reales -->
- **R-019** — El Edge nunca se muestra sin una base declarada (`mareaBasis`):
  si no hay lectura propia auditable, no hay Edge. Una sola casa no produce
  consenso: comparar un precio consigo mismo daría cero. (integraciones)
- **R-020** — La telemetría sale por lista blanca, nunca por lista negra:
  direcciones, montos, saldos, texto del usuario y el mensaje de error que ve
  el usuario no salen del dispositivo. (integraciones)
- **R-021** — Un splash tapa trabajo real; nunca fabrica espera. P0 tiene
  techo, no duración fija, y avanza en cuanto el shell pintó. (perf)
- **R-022** — Ninguna integración sin credenciales finge hablar con un
  proveedor: degrada a su camino simulado y lo declara. (integraciones)

<!-- ciclo de mercados propios (parimutuel) -->
- **R-023** — El pago que se muestra incluye la apuesta que se está por hacer.
  Enseñar el multiplicador de antes de entrar sería enseñar un pago que el
  usuario no va a recibir. (parimutuel)
- **R-024** — Si nadie acertó, se devuelve el pozo íntegro y la casa no cobra
  comisión. Quedarnos con un pozo que nadie ganó es lo que hace una casa.
- **R-025** — Un mercado propio no se publica sin fuente pública verificable,
  criterio inequívoco y ventana de disputa. La resolución nunca es
  discrecional: "porque Marea lo dice" no existe. Se valida al cargar el
  catálogo, no en producción.
- **R-026** — Jugando con puntos no aparece ningún símbolo de moneda en la
  interfaz, y el canje por dinero no existe como función. Habilitarlo exige
  borrar código, no cambiar copy.
- **R-027** — Si la lectura contra la que se compara el precio no es nuestra,
  el Edge lleva el nombre de quien la da. Llamar "Marea" al precio de otra
  casa sería mentir.
- **R-028** — No se pide wallet cuando el producto no la necesita. En modo
  puntos el onboarding llega al feed en un tap.
- **R-029** — En parimutuel no se muestra resultado no realizado: no existe
  hasta que el mercado resuelve, y saldría siempre en verde. Se muestran las
  dos cifras honestas: lo que cobras si aciertas y lo que arriesgas.

<!-- ciclo del modelo propio -->
- **R-030** — La lectura de Marea es una cuenta reproducible con datos
  públicos, nunca una opinión. Su base se muestra al usuario y se puede
  rehacer. (modelo)
- **R-031** — Ningún modelo produce Edge sin calibración medida **fuera de
  muestra** por debajo del máximo admisible. La puerta está en el código y se
  abre bajando el error, nunca bajando el umbral. (modelo)
- **R-032** — Toda partición de datos para medir un modelo es temporal y por
  activo. Partir por posición en el arreglo separa por activo y devuelve un
  número inflado. (modelo)
- **R-033** — La calibración se mide agrupando todas las predicciones fuera de
  muestra sobre varios regímenes. Promediar pliegues cortos mide si adivinamos
  la tendencia del período, que es otra cosa y no es lo que hacemos. (modelo)
- **R-034** — Una corrección de calibración sólo se aplica si mejora el error
  fuera de muestra. Ajustada en un régimen y aplicada en otro puede empeorar,
  y en la medición del 27 de julio lo hizo. (modelo)
- **R-035** — Los hiperparámetros del modelo (colas, ventanas) se eligen con el
  tramo de ajuste, nunca mirando el número que después se reporta. (modelo)
- **R-036** — No se agrega deriva ajustada a la historia reciente para bajar el
  error medido: sería una apuesta direccional disfrazada de calibración. (modelo)
- **R-037** — La superficie de volatilidad por vencimiento se guarda a diario
  desde hoy: su historia no existe en ningún endpoint público y cada día que no
  se guarda es un dato que no se recupera. (datos)
- **R-038** — El Edge sale sólo de referencia externa medida. Un modelo propio
  entra únicamente si su error fuera de muestra baja del máximo admisible, y la
  validación falla si alguien lo enchufa antes. Si la referencia se cae, el
  Edge se apaga: nunca se muestra una lectura vieja como fresca. (producto)
- **R-039** — El producto se lanza y se opera desde la máquina de quien lo
  construye. El CI es opcional: `npm run ci`, `npm run deploy` y `npm run daily`
  hacen lo mismo sin depender de una cuenta de pago. (operación)
- **R-040** — Un mercado que cierra tiene que liquidarse y pagar. Publicar
  mercados sin proceso de resolución rompe la única promesa que sostiene el
  producto, más que cualquier funcionalidad que falte. (producto)
- **R-041** — Un catálogo con fechas fijas caduca. Antes de lanzar se define
  el ritmo de reposición y quién escribe los mercados nuevos. (producto)
- **R-042** — Un mercado con regla automática publica el mismo umbral en el
  criterio en español y en la regla que ejecuta el oráculo. Si se separan, se
  paga distinto de lo prometido; se valida al cargar el catálogo. (liquidación)
- **R-043** — Las apuestas cierran antes de que el resultado sea observable. Un
  mercado que acepta dinero mientras el precio ya se ve deja de ser predicción.
  (liquidación)
- **R-044** — Lo que reparte la liquidación es exactamente lo que prometió el
  multiplicador que se mostró antes de entrar, semilla incluida en el
  denominador. El número que se enseña es el que se cobra. (parimutuel)
- **R-045** — El país se infiere del dispositivo para hablarle a la gente de su
  mercado, nunca como control de cumplimiento: no abre ningún permiso que la
  tabla legal no dé, y el usuario puede corregirlo. Mover dinero exige
  geolocalización con proveedor y verificación de identidad. (cumplimiento)
- **R-046** — Ninguna fuente se cita si no es la que se lee. Citar una casa y
  resolver con otra es resolver con una fuente distinta de la prometida.
  (liquidación)
- **R-047** — El contenido principal nunca espera a un dato secundario. Los
  mercados se muestran sin la referencia externa y el Edge se enciende cuando
  llega: una casa lenta dejaba el feed 20 s en blanco, medido. (perf)
- **R-048** — Lo que alguien apuesta tiene que sobrevivir a cerrar la app. Un
  saldo que vive en la memoria del navegador no es un saldo: es una demo. Toda
  mutación se persiste **antes** de responderle al usuario. (servidor)
- **R-049** — El pozo es uno solo para todos. Una copia del parimutuel por
  dispositivo no es un mercado, es un simulador de un jugador: nadie mueve el
  precio de nadie y el Edge no significa nada. (servidor)
- **R-050** — La cuenta se pide cuando hay algo que guardar —al apostar—, nunca
  antes. Explorar el catálogo completo sigue sin pedir nada (R-002), y crear la
  cuenta son dos campos: sin correo obligatorio y sin esperar un mail. (producto)
- **R-051** — Antes de declarar que algo necesita a una persona, se busca la
  API pública. Brasil publica la Selic y el IPCA sin llave; Banxico da token
  gratis. "Hace falta un humano" sin haber corrido un `curl` es pereza con
  disfraz de prudencia. (liquidación)
- **R-052** — Un dato viejo no resuelve un mercado nuevo. La observación leída
  tiene que ser la de la fecha del mercado, o no hay lectura. (liquidación)
- **R-053** — Toda liga compartible lleva vista previa rellena en el servidor:
  los rastreadores de WhatsApp y Telegram no ejecutan JavaScript, y un enlace
  sin vista previa no lo abre nadie. Lo que entra al HTML se escapa. (producto)
- **R-054** — La tabla mide precisión y racha, no cuánto apostaste. En un
  producto de predicción el marcador es cuántas veces le atinaste; ordenar por
  volumen premiaría lo contrario de lo que vendemos. (producto)
- **R-055** — El servidor comprime lo que sirve. Sin gzip mandaba 426 kB donde
  el preview mandaba 180 kB: 1.3 s de LCP regalados en red lenta. Medir contra
  el servidor real y no contra el preview es lo que lo destapó. (perf)
- **R-056** — La categoría se elige por dos ejes: cuánto se comparte y si se
  puede leer sola. El futbol da los dos, y por eso la Liga MX se genera y se
  resuelve sin que nadie escriba nada. Lo que se comparte mucho pero no se lee
  solo entra acotado y con su costo declarado. (producto)
- **R-057** — La semilla del pozo corre la misma suerte que el usuario y la casa
  nunca toma el lado contrario para "dar liquidez": el día que la casa gana
  cuando el usuario pierde, dejamos de ser lo que prometimos. (liquidez)
- **R-058** — Los datos que se publican o se venden son agregados: probabilidad,
  volumen, resultado y calibración. Quién apostó qué no sale nunca. Un usuario
  no es un producto. (datos)
