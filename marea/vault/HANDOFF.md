# HANDOFF — estado de soft launch

> **Estado actual: SOFT_LAUNCH_READY en modalidad de puntos.** Ver
> [`SOFT_LAUNCH.md`](SOFT_LAUNCH.md), que manda sobre este documento. Los dos
> agujeros de ciclo de vida —los mercados cerraban sin liquidarse y el catálogo
> se vaciaba solo— están cerrados y **automatizados**: `npm run settle` liquida
> contra la fuente citada y `npm run roll` repone el catálogo, las dos cada hora
> con `npm run cron:install`.

## Veredicto anterior (superficie construida)

**SOFT_LAUNCH_READY** con mercados propios de Latam y motor parimutuel,
jugando con **puntos, no dinero** (Fase 1 del roadmap de la visión).
`npm run validate` → `PASS` (V1–V24, RT/1–RT/10, S1/T1/C1, P1/P2).
`npm run perf` → `PASS` en laboratorio, ambos recorridos.

Esta modalidad **no necesita** los bloqueantes de §5: sin dinero no hay
custodia ni licencia. Pasar a `parimutuel_money` sí los exige, y la validación
falla si alguien lo intenta sin encender la puerta de elegibilidad.

## Checklist de soft launch (modo puntos)

- [x] Catálogo propio de Latam, cada mercado con su fuente pública citada
- [x] Motor parimutuel: pozo, pago con la apuesta incluida, comisión de 3 %,
      liquidación proporcional y devolución íntegra si nadie acertó
- [x] Contrato de resolución que rechaza lo discrecional y exige ventana de disputa
- [x] Puntos: bienvenida, sin crédito, sin canje, recarga diaria acotada
- [x] Onboarding de un tap hasta el feed, sin wallet
- [x] Detalle con reparto del pozo y criterio de resolución antes del CTA
- [x] Portafolio con pago potencial, no con un resultado inventado
- [x] Errores accionables en español
- [x] Métricas móviles: targets ≥ 44 px, cero desborde a 390 px, contraste ≥ 4.5:1
- [x] Rendimiento medido, no declarado

Lo construido para el camino con dinero sigue vivo y probado (wallet, depósito,
elegibilidad, agregación), fuera del camino mientras el motor sea de puntos.

## Rendimiento medido

Laboratorio: Chromium headless, 390×844, CPU 4× más lenta, 1600 kbps, 150 ms de
latencia. Reproducible con `npm run perf`.

| Recorrido | LCP | INP | CLS | Al feed | Transferido |
|---|---|---|---|---|---|
| Usuario nuevo | 1752 ms | 80 ms | 0.001 | 1.8 s | 175 kB |
| Usuario recurrente | 1356 ms | 104 ms | 0 | 1.5 s | 175 kB |
| Presupuesto | 2500 ms | 200 ms | 0.1 | 75 s | — |

El tiempo al feed bajó de 2.2 s a 1.8 s al quitar la wallet del camino: en modo
puntos no hace falta, y pedirla era fricción por costumbre (R-028).

La primera medición dio **2656 ms de LCP para el usuario nuevo, sobre
presupuesto**. La causa era nuestra: el splash de P0 esperaba 1400 ms fijos y
retrasaba el primer pintado grande. Ahora P0 tiene techo en lugar de duración
(R-021) y avanza en cuanto el shell pintó: LCP bajó 40 % y el tiempo al feed
pasó de 3.3 s a 2.2 s.

Dos salvedades honestas: es medición de laboratorio, no de campo — los números
de usuarios reales sólo salen del sink en producción — y el TTFB de 5 ms no es
representativo porque el servidor corre en la misma máquina.

## Caminos documentados

**Camino feliz (puntos).** Splash → promesa, con la unidad declarada → feed →
detalle → lado → monto → se ve el pago → apostar → portafolio.

**Sin puntos.** El CTA del detalle ofrece recargar en contexto y abre la hoja de
puntos. Explorar el catálogo completo nunca cuesta nada.

**Camino con dinero (cuando se habilite).** Splash → promesa → crear wallet →
depositar → feed → … → portafolio. `Explorar mercados` en P3 lo salta entero.

## Qué es real y qué es simulado

| Pieza | Estado |
|---|---|
| Datos de mercado | **Real disponible** (`VITE_DATA_SOURCE=aggregated`), default en simulado a propósito — ver `DATA_SOURCES.md` |
| Analítica y errores | **Real**, activo al configurar endpoint; sin él, memoria |
| Web Vitals | **Real**, medido en dispositivo y en laboratorio |
| Elegibilidad por país | **Real** en el dominio, con la puerta apagada mientras no se mueva dinero |
| Wallet y depósito | **Simulado**, y fuera del camino en modo puntos. Requiere contrato con proveedor: bloqueante legal, no técnico |
| Motor de mercado | **Real.** Parimutuel propio, con pozo, comisión de 3 % y liquidación probada |
| Catálogo de Latam | **Real.** 12 mercados de 6 países, cada uno con su fuente pública citada |
| Puntos | **Real.** Bienvenida de 1,000, sin crédito, sin canje por dinero |

## Hallazgos que se volvieron regla

| Hallazgo | Severidad | Regla |
|---|---|---|
| Doble tap disparaba dos veces las acciones de dinero | Crítico | R-016 |
| Colores de token con opacidad no pintaban fondo: chrome transparente | Crítico | R-017 |
| Los separadores de millar partían `71,000` y rompían el emparejamiento | Crítico | — (corregido en `matchKeyFor`) |
| El clasificador de categoría era ciego a los acentos | Importante | — (corregido en `classify`) |
| Kalshi colapsaba una escalera de strikes en un solo mercado | Importante | — (corregido con `yes_sub_title`) |
| El splash fijo costaba 1060 ms de LCP | Importante | R-021 |
| Un Edge negativo mostraba icono al alza | Importante | R-018 |
| `onboarding_completed` podía marcarse sin llegar al feed | Importante | R-015 |
| El portafolio mostraba un resultado no realizado que en parimutuel no existe y salía siempre en verde | Crítico | R-029 |
| El mosaico de volumen filtraba un símbolo de dólar en modo puntos | Importante | R-026 |
| La liquidación repartía sin contar la semilla y pagaba 6× lo que el multiplicador había prometido | Crítico | R-044 |
| Dos cargas del portafolio en el mismo tick acreditaban el pago dos veces | Crítico | R-016 (extendida) |
| Se citaba Binance en el criterio y se iba a leer Kraken | Importante | R-046 |
| "Cierra cerrado" en mercados vencidos, y HOT en todas las cards | Menor | — (corregido) |

## Pendiente número uno de producto

**El Edge todavía no existe en los mercados de Latam puro.** Necesita una
lectura independiente del pozo, y hoy sólo la hay para las preguntas que
también cotizan en una casa global. Las opciones son un modelo propio de
probabilidad o ampliar el catálogo con preguntas que tengan referencia externa.
Ninguna se resuelve sin decidir cuál queremos.

## §5 — Lo que falta para pasar a dinero real

1. **Opinión legal por país.** `COMPLIANCE.md` §3 lista las preguntas concretas.
   Cada respuesta es una línea en `src/domain/eligibility.ts`. Sin esto no hay
   depósitos: la tabla arranca entera en `pendiente`.
2. **Contrato con proveedor de wallet embebida y de on-ramp**, incluyendo quién
   es el sujeto obligado de cada requisito regulatorio.
3. **Decisión de fuente de mercados.** `DATA_SOURCES.md` mide que la agregación
   sola no entrega ni Latam, ni español, ni Edge. Es decisión de producto.
4. **Capa de traducción con revisión**, si se usa inventario agregado.
5. **Endpoints de telemetría** en producción (`VITE_ANALYTICS_ENDPOINT`,
   `VITE_ERROR_ENDPOINT`) y medición de campo que sustituya a la de laboratorio.
