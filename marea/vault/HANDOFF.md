# HANDOFF — estado de soft launch

## Veredicto

**SOFT_LAUNCH_READY** para la superficie construida, sobre datos simulados.
`npm run validate` → `PASS` (V1–V24, RT/1–RT/10, más S1/T1/C1).
`npm run perf` → `PASS` en laboratorio, ambos recorridos.

**No listo para dinero real.** Los bloqueantes están en §5 y ninguno es de
código.

## Checklist de soft launch

- [x] Wallet: crear (primario) y conectar (secundario), con error accionable
- [x] Feed con Edge visible, regla de 4 pp aplicada en dominio
- [x] Detalle con criterio de resolución antes del CTA
- [x] Iniciar depósito, con caída de proveedor cubierta
- [x] Portafolio vacío y con datos
- [x] Errores accionables en español
- [x] Métricas móviles: targets ≥ 44 px, cero desborde a 390 px, contraste ≥ 4.5:1
- [x] Adapters de agregación reales, verificados contra APIs vivas
- [x] Sinks de analítica y errores reales, con lista blanca de datos
- [x] Elegibilidad por país y juego responsable en el dominio
- [x] Rendimiento medido, no declarado

## Rendimiento medido

Laboratorio: Chromium headless, 390×844, CPU 4× más lenta, 1600 kbps, 150 ms de
latencia. Reproducible con `npm run perf`.

| Recorrido | LCP | INP | CLS | Al feed | Transferido |
|---|---|---|---|---|---|
| Usuario nuevo | 1596 ms | 96 ms | 0.003 | 2.2 s | 170 kB |
| Usuario recurrente | 1560 ms | 96 ms | 0.003 | 1.6 s | 169 kB |
| Presupuesto | 2500 ms | 200 ms | 0.1 | 75 s | — |

La primera medición dio **2656 ms de LCP para el usuario nuevo, sobre
presupuesto**. La causa era nuestra: el splash de P0 esperaba 1400 ms fijos y
retrasaba el primer pintado grande. Ahora P0 tiene techo en lugar de duración
(R-021) y avanza en cuanto el shell pintó: LCP bajó 40 % y el tiempo al feed
pasó de 3.3 s a 2.2 s.

Dos salvedades honestas: es medición de laboratorio, no de campo — los números
de usuarios reales sólo salen del sink en producción — y el TTFB de 5 ms no es
representativo porque el servidor corre en la misma máquina.

## Caminos documentados

**Camino feliz (con fondos).** Splash → promesa → crear wallet → depositar →
feed → detalle → lado → monto → operar → portafolio.

**Camino sin fondos (explore-before-fund).** Splash → promesa → crear wallet →
`Explorar mercados` → feed → detalle completo → intento de operar → hoja de
depósito en contexto. Nunca se pide dinero, documento ni frase semilla antes.

## Qué es real y qué es simulado

| Pieza | Estado |
|---|---|
| Datos de mercado | **Real disponible** (`VITE_DATA_SOURCE=aggregated`), default en simulado a propósito — ver `DATA_SOURCES.md` |
| Analítica y errores | **Real**, activo al configurar endpoint; sin él, memoria |
| Web Vitals | **Real**, medido en dispositivo y en laboratorio |
| Elegibilidad por país | **Real** en el dominio, con la puerta apagada mientras no se mueva dinero |
| Wallet y depósito | **Simulado.** Requiere contrato con proveedor: es un bloqueante legal, no técnico |

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

## §5 — Lo que falta y no puede resolverse desde el código

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
