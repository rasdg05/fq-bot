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
