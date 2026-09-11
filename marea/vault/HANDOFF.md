# HANDOFF — estado de soft launch

> ## ⚠ Lo primero, antes de tocar nada (2026-09-11)
>
> **Producción NO corre `main`.** Corre `claude/marea-redesign-v6-b0240n`. Esa
> rama tiene el rediseño v6 y la cripto en vivo (velas de 5 y 15 min), que nunca
> se fusionaron a `main`. Si trabajas sobre `main`, tu código **no llega a la
> app**; y si fusionas `main` a producción sin reconciliar, te llevas el
> rediseño por delante.
>
> Se comprobó así: `curl https://fq-bot-production.up.railway.app/api/mercados`
> sirve `shortTitle` y mercados `live`, y ninguno de los dos existe en `main`.
>
> Retomar desde cero: **`RETOMAR.md`**.

> **Estado: en puntos, con el ciclo de vida cerrado de verdad (2026-09-11).**
> Ver [`SOFT_LAUNCH.md`](SOFT_LAUNCH.md).
>
> **Corrección de lo que decía este documento.** Hasta el 2026-09-10 aquí ponía
> que los dos agujeros de ciclo de vida estaban «cerrados y **automatizados**»
> con `npm run settle`, `npm run roll` y `npm run cron:install`. Era falso en la
> mitad que importa: `cron:install` escribe un launchd o un crontab **en la
> máquina de quien lo corre**. Nadie lo corrió desde principios de agosto, y el
> 10 de septiembre la app tenía **cuatro** mercados duraderos y apuestas de hace
> un mes sin resolver.
>
> Ahora sí es automático **y dentro del servidor**: el liquidador ya vivía ahí y
> la reposición se le unió (`server/reposicion.mts`), por el mismo reloj y al
> mismo volumen persistente. `roll` y `settle` siguen existiendo para hacerlo a
> mano; ya no son de lo que depende el producto.

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
| Usuario nuevo | 1704 ms | 56 ms | 0 | 1.8 s | 180 kB |
| Usuario recurrente | 1676 ms | 56 ms | 0.001 | 1.7 s | 180 kB |
| Presupuesto | 2500 ms | 200 ms | 0.1 | 75 s | — |

El tiempo al feed bajó de 2.2 s a 1.8 s al quitar la wallet del camino: en modo
puntos no hace falta, y pedirla era fricción por costumbre (R-028).

La primera medición dio **2656 ms de LCP para el usuario nuevo, sobre
presupuesto**. La causa era nuestra: el splash de P0 esperaba 1400 ms fijos y
retrasaba el primer pintado grande. Ahora P0 tiene techo en lugar de duración
(R-021) y avanza en cuanto el shell pintó: LCP bajó 40 % y el tiempo al feed
pasó de 3.3 s a 2.2 s.

Al enchufar la liquidación, la medición volvió a atrapar un defecto: el feed
esperaba a la casa externa antes de pintar, y con Polymarket inalcanzable eso
eran **20 s de pantalla en blanco**. Los mercados no dependen de esa lectura —
sólo el Edge — así que ahora salen sin ella y el Edge se enciende cuando llega
(R-047). El tiempo al feed pasó de 20.4 s a 0.8 s en ese escenario.

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
