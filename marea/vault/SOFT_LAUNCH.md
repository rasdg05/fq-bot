# SOFT LAUNCH — qué falta, en orden

Estado al 27 de julio de 2026. `npm run ci` en verde: 167 pruebas,
`VALIDATION_REPORT` en PASS, build de 391 kB.

**Veredicto: BLOCKED.** No por la app, que está terminada, sino por dos
agujeros en el ciclo de vida del producto que se detallan abajo. Con ésos
cerrados, la modalidad de puntos se lanza sin depender de nadie más.

---

## Bloqueantes reales

### B1 · Los mercados cierran y nunca se liquidan

El motor de liquidación existe y está probado —reparte el pozo perdedor entre
los ganadores, cobra comisión, y devuelve todo si nadie acertó— pero **nada lo
invoca**. `settle()` no se llama desde ningún lado.

Consecuencia: alguien apuesta, el mercado cierra, y no cobra nunca. Eso rompe
la promesa central, que no es el Edge ni el pozo: es que **la resolución sea
transparente y ocurra**.

Falta:
- Un proceso que detecte mercados cerrados, lea la fuente citada y registre el
  resultado.
- La ventana de disputa antes de pagar (la lógica existe, el disparador no).
- El pago al ledger de puntos y el estado de la posición en el portafolio.
- La pantalla donde el usuario ve qué se resolvió y por qué.

Es lo siguiente que hay que construir. Sin esto no se lanza.

### B2 · El catálogo se vacía solo

Doce mercados con fechas fijas. **Uno ya cerró** (`mx-mundial-grupo`, venció el
27 de junio) y sigue en el feed. Cuatro más cierran en los próximos once días:
el dólar en 4, Bitcoin en 6, el Imacec en 7, la inflación de México en 11.

Sin reposición, en dos semanas el feed queda casi vacío y en un mes está
muerto. Falta:
- Quitar del feed lo ya vencido (o mostrarlo resuelto, que depende de B1).
- Un ritmo de alta de mercados nuevos: quién los escribe, con qué frecuencia,
  con qué criterio de resolución. Es trabajo de producto recurrente, no una
  función.

---

## Listo y verificado

| | Estado |
|---|---|
| App móvil completa, español Latam | ✓ 167 pruebas |
| Motor parimutuel: pozo, pago, comisión, liquidación | ✓ probado (sin disparador — ver B1) |
| Contrato de resolución que rechaza lo discrecional | ✓ valida el catálogo al cargar |
| Puntos: bienvenida, sin crédito, sin canje | ✓ |
| Onboarding de un tap, sin wallet ni KYC | ✓ |
| Edge sólo con referencia externa, se apaga si el venue cae | ✓ |
| Errores en español con reintento | ✓ |
| Métricas móviles: 44 px, contraste, cero desborde a 390 px | ✓ |
| Rendimiento medido en laboratorio | ✓ LCP 1.75 s, INP 80 ms, CLS 0.001 |
| Red-team UX, 10 escenarios | ✓ |
| Publicar desde tu máquina sin CI | ✓ `npm run deploy` |
| Recolección diaria de volatilidad | ✓ `npm run cron:install` |

## Pendientes que no bloquean el lanzamiento con puntos

- **Telemetría en producción.** Sin `VITE_ANALYTICS_ENDPOINT` los eventos se
  quedan en memoria. Se lanza sin esto, pero entonces no se mide si la gente
  vuelve — que es justo lo que la modalidad de puntos existe para averiguar.
  Vale la pena antes del lanzamiento, no después.
- **Rendimiento de campo.** Lo medido es laboratorio. Los números reales salen
  del sink de arriba.
- **Modelo propio de Edge.** Gated en 3.29 pp contra un máximo de 2 pp. Decidido
  que el Edge sale sólo de referencia externa; el modelo sigue en
  investigación con la superficie acumulándose a diario.
- **Segundo par de ojos sobre el copy.** Nadie que no seamos nosotros lo ha
  leído.

## Bloqueado sólo para dinero real (no aplica a puntos)

1. Consulta legal por país — `COMPLIANCE.md` §3.
2. Llave del proveedor de wallet no-custodial — alta propia, no contrato.
3. Encender `eligibility_enforced`, que la validación exige para builds con
   dinero.

---

## Qué necesito de ti

**Para publicar hoy**, una sola cosa: entrar una vez al hosting desde tu
máquina. `npx wrangler login` y después `npm run deploy`. No lo puedo hacer yo
—no tengo tu cuenta, y publicar tu producto es tu decisión, no mía.

**Para cerrar B1**, una decisión de producto: quién resuelve los mercados y
cuándo. Lo automático es leer la fuente citada por programa; lo manual es que
alguien confirme antes de pagar. Recomiendo empezar manual con confirmación,
porque con puntos el riesgo es cero y se aprende cómo fallan las fuentes reales
antes de automatizar.

**Para cerrar B2**, un compromiso de ritmo: cuántos mercados nuevos por semana
y quién los escribe. Es lo único de esta lista que no se resuelve con código.

**Opcional pero recomendado antes de lanzar**: una cuenta de analítica para el
endpoint. Sin eso lanzamos a ciegas.
