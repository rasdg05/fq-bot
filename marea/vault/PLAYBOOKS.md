# PLAYBOOKS — órdenes de fase y flujos críticos

## Fase 1 — orden de construcción

1. Design System (tokens, tipografía, primitivas UI)
2. Tabs (5, `Mercados` por defecto)
3. MarketCard (variantes `default | edge | live | compact`)
4. Home (`Hot ahora` + chips de categoría + cards)
5. Detalle de mercado (una sola zona de decisión)
6. Estados: empty / loading / error / sin fondos

## Fase 2 — orden de construcción

1. Onboarding P0–P4
2. Wallet (crear primario / conectar secundario)
3. Deposit sheet (on-ramp y/o transferencia)
4. Portfolio (empty + data)
5. Header sync con wallet
6. Post-operación
7. Tracking + errores

## Onboarding (P0–P4)

| Paso | Contenido | Salida |
|---|---|---|
| P0 | Splash ≤ 1.5 s | auto-avance |
| P1 | `Predice. Opera. Con edge.` | `Empezar` |
| P2 | `Crear wallet` (primario) / `Conectar wallet` (secundario) | wallet lista |
| P3 | Wallet lista → `Depositar` \| `Explorar mercados` | elección |
| P4 | Feed | `onboarding_completed = true` |

Reglas: sin KYC, sin seed phrase en el path, balance 0 puede explorar todo.
Presupuesto: ≤ 75 s de camino feliz (5 pasos, ninguno bloqueante).

## Deposit sheet

Se abre desde: header (`Depositar` cuando balance = 0), P3, detalle de mercado
al intentar operar sin saldo, portfolio empty.
Contenido: opción on-ramp + opción transferencia de cripto + cerrar siempre
disponible. Si el proveedor está caído: mensaje honesto + alternativa.

## Post-operación

Confirmación → dos salidas: `Ver portafolio` | `Seguir explorando`.
Nunca callejón sin salida.

## Camino sin fondos (explore-before-fund)

Splash → promesa → wallet → `Explorar mercados` → feed → detalle → intento de
operar → deposit sheet contextual. En ningún punto anterior se pide dinero.

## Mercados propios (motor parimutuel)

Orden de construcción: motor de pozo → contrato de resolución → ledger de
puntos → catálogo → adapter → interfaz.

**Publicar un mercado.** Se escribe la pregunta en español, cerrada (Sí/No), y
se declara antes que nada: institución que publica el dato, URL pública,
criterio en una frase, fecha de publicación y ventana de disputa. Sin eso el
catálogo no carga.

**Onboarding en modo puntos.** P0 splash → P1 promesa con la declaración de que
son puntos → feed. Un tap. No hay wallet porque no hace falta (R-028).

**Apostar.** Detalle → lado → monto → se muestra el pago con la apuesta ya
incluida → apostar → confirmación con dos salidas.

**Liquidar.** Cierra el mercado → se lee la fuente citada → ventana de disputa →
se reparte el pozo perdedor entre los ganadores menos comisión. Si nadie
acertó, se devuelve todo sin comisión.
