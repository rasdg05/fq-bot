# Marea — protocolo de liquidez, cámara de compensación y cadena

> **Obra nueva del proyecto** (directiva RasDG 2026-06-29: toda obra entra a la memoria).
> Marea es la app de mercados de predicción que vive en `marea/` del mismo repo.
> Esta página es la memoria durable de la decisión de liquidez; el documento largo
> —asientos, plan por fases, reglas propuestas— vive en `marea/vault/LIQUIDEZ.md`.
> Aquí se rutea, no se repite.

**Estado: diseño. Nada desplegado.** Volumen 0, facturación 0, se juega con puntos,
elegibilidad `pendiente` en todos los países. Rama `claude/marea-liquidity-flow-8ybf5l`.

---

## 1. La decisión central

El boceto de RasDG describía un pozo que "arbitra entre el taker y el maker y al final
vuelve a su monto original". Esa frase tiene dos lecturas y sólo una sobrevive:

| | **Cámara de compensación** ✔ | Creador de mercado ✘ |
|---|---|---|
| Qué hace | Guarda el colateral de las dos partes y paga al que acertó | Cotiza los dos lados y se queda el residual |
| ¿Toma posición? | **Nunca**, por construcción | Sí: el inventario neto es una apuesta |
| Varianza del capital propio | **Cero exacta, por mercado** | Real; vuelve al origen sólo en promedio |
| R-057 | Cumple | **Rompe** |

**Decidido: cámara de compensación.** Y una consecuencia estructural: **el pozo
pertenece a la capa de compensación, no a la de precio**. El parimutuel de hoy y un
libro maker/taker futuro son dos formas de fijar precio **encima del mismo
compensador** — así no hay dos matemáticas de dinero (R-044).

---

## 2. La aritmética

```
q            conjuntos completos acuñados en el mercado
C = q        colateral retenido
O = q × 1    obligación al resolver (un contrato de cada resultado; uno paga 1)
P&L pozo = C − O = 0        ∀ resultado

Σ pᵢ = 1     taker aporta q·p · maker aporta q·(1−p) · suman q
```

El ganador no entra en la ecuación del pozo. No es que la varianza sea baja: es que el
resultado del mercado no aparece en la cuenta.

**Ingreso:**

```
Ingreso = V · (f − r)            V volumen cruzado · f fee taker · r rebate maker
R       = V / colateral vivo     rotación
V       = U · t · k              usuarios · ticket · operaciones por usuario
Equilibrio: V ≥ (M·S + G) / f    M mercados · S subsidio · G coste en cadena
```

Ejemplo aritmético (**no pronóstico**): `U=5,000 · t=$25 · k=6` ⇒ `V=$750,000/mes`.
A 300 bps son $22,500/mes; ese mismo volumen a 6 bps son $450/mes.

---

## 3. Fees: base, escalera y regla de bajada

**Base = varianza**, no la prima ni el nocional:

```
fee = f · q · p · (1−p)
```

Es la forma que usa Kalshi (`0.07·C·P·(1−P)`, verificado sep-2026). Su virtud es la
simetría: cobra igual comprar SÍ a 0.80 que NO a 0.20 — que es **el mismo trato visto de
los dos lados**. Sobre la prima, el taker pagaría 4× lo del maker por la misma operación;
sobre el nocional, a `p = 0.02` un fee de 10 bps sería el 5% de lo que el usuario puso.

| Fase | Cuándo | Neto casa | ≈ bps de nocional @ p=0.5 | Rotación que exige |
|---|---|---|---|---|
| **A · arranque** | hoy · sin libro, sin makers | f = 12% | ~300 | ninguna |
| B · libro joven | cuando exista libro con dos lados | f−r = 4% | ~100 | R ≥ 3× |
| C · líquido | el boceto (10/4 bps) | f−r ≈ 0.24% | ~6 | R ≥ 50× |

**La regla, que es el invariante de esta sección:**

```
bajar de f₀ a f₁  ⟺  R_medida ≥ f₀ / f₁
```

La fase A **no es un cambio de precio**: hoy el 3% ya sale del pozo antes de repartir, así
que cada apostador ya financia el 3% de su parte. Cobrarlo al cruzar es la misma
incidencia movida en el tiempo — lo que compra es desacoplar el ingreso del resultado, y
eso es lo que hace continuo el salto a B y a C en vez de una reescritura.

---

## 4. La arquitectura en cadena

No custodial: la llave es del usuario, el colateral vive en un contrato y Marea sólo
opera la resolución. **Tres cosas cruzan a la cadena** y con esas tres se audita todo:

1. **El dinero** — conjuntos completos ERC-1155 sobre una bóveda de colateral.
   `supply(conjuntos) == balance(USDC)`, leíble en cualquier bloque sin API nuestra.
2. **La operación** — hash-chain SHA-256 (`hᵢ = SHA256(hᵢ₋₁ ‖ hecho)`), raíz de Merkle
   por época, anclada en una tx. Al usuario se le da su hoja y su prueba.
   *Es el mismo patrón que ya usa el ledger del bot* (`execution.py`, CONSTITUCIÓN §III).
3. **El resultado** — commit al crear (`SHA256(regla ‖ fuente ‖ sal)`), reveal al
   resolver, más ventana de disputa on-chain con oráculo optimista. Es el *provably fair*
   de un casino cripto aplicado a la resolución.

**Forma:** libro fuera de cadena, liquidación dentro — la arquitectura de Polymarket
(CLOB off-chain + Conditional Token Framework ERC-1155 on-chain + oráculo optimista,
verificado sep-2026).

### La cadena

| Cadena | Veredicto | Por qué |
|---|---|---|
| **Base** | **la cámara** | USDC nativo de Circle, gas en centavos, rampa Coinbase fuerte en Latam, ecosistema consumer |
| Polygon | alternativa | Donde vive Polymarket: el CTF ya está probado ahí para este caso exacto |
| Arbitrum | sólo rendimiento | DeFi profundo, rampa consumer más floja en la región |
| Tron · USDT | **rampa de depósito** | Es el riel real de USDT en Latam, pero sin CTF, herramientas pobres y perfil que complica la opinión legal. Se acepta el depósito y se convierte a USDC al entrar |
| BNB · PancakeSwap | swap, no cámara | Un AMM no es una capa de liquidación |
| **Monero** | **no** | No tiene contratos y es privado por diseño: lo contrario de auditable, que es el argumento de venta. Además cierra la puerta legal con casi cualquier rampa fiat |

### Tres líneas de ingreso, no una

1. **Fee de operación** — `f · q · p · (1−p)`, la escalera de §3.
2. **Float del colateral** — `C̄ · APY · días/365`. El colateral vive días o semanas
   esperando la resolución. **Escala con el colateral vivo, no con la rotación** — que es
   justo lo que hoy no tenemos. Es la línea que hace que esto se parezca a un índice y no
   a una acción. Sujeta a L11.
3. **Reparto de rebate** — cuando entren makers de terceros. Después.

---

## 5. Invariantes (L1–L14)

| # | Invariante | Estado |
|---|---|---|
| L1 | Neutralidad: `colateral == conjuntos emitidos` | nueva |
| L2 | El pozo nunca es contraparte; no existe API que le abra posición | nueva |
| L3 | Fee y colateral no comparten cuenta | nueva |
| L4 | `cuadre(libro) == 0` antes y después de toda operación | **viva** (`contabilidad.test.ts`) |
| L5 | Conservación: `Σ pagos + fees == Σ colateral` | nueva |
| L6 | Idempotencia: liquidar dos veces paga una | nueva |
| L7 | Ninguna fase se salta; no se paga con la disputa abierta | **viva** (`settlement.test.ts`) |
| L8 | Frescura del oráculo: una fuente parada no resuelve | **deuda previa** |
| L9 | El subsidio vivo nunca excede el presupuesto; cruzarlo detiene la creación | nueva |
| L10 | `saldo(usuario) ≥ 0`; se bloquea antes de cruzar | nueva |
| L11 | El rendimiento nunca retrasa un pago (sólo excedente + colchón) | nueva · on-chain |
| L12 | Marea no puede mover fondos: la función no existe | nueva · on-chain |
| L13 | Todo número publicado nombra la raíz anclada de la que sale | nueva · on-chain |
| L14 | `supply(conjuntos) == balance(colateral)` en todo bloque | nueva · on-chain |

**L8 no la trae este diseño**: hoy `onRead` acepta una lectura sin comprobar cuán vieja
es la fuente — el mismo fallo que en el bot obligó a cablear `cvd_confirmation`.

---

## 6. El camino de $0 a plataforma activa

**Tramo A · cablear** (hoy, en puntos, sin tocar la puerta de elegibilidad)
1. Compensador puro — *puerta:* mil secuencias aleatorias, capital propio idéntico.
2. Asientos cableados — *puerta:* `cuadre() = 0` en toda operación.
3. Funding con freno — *puerta:* sin presupuesto no se crea mercado.

**Tramo B · abrir** (el bloqueo real)
4. **Opinión legal por país.** No es código.
5. Pozo en contrato · USDC en L2 — *puerta:* el colateral se lee en cadena.
6. Depósito y retiro non-custodial.

**Tramo C · cobrar y medir** (el dinero empieza aquí)
7. Fee al cruzar (fase A). Primer peso facturado.
8. Medir R ocho semanas.
9. Bajar a taker/maker sólo si `R ≥ f₀/f₁`.

La cifra que decide todo es `V`, y `V` hoy es 0: el trabajo está en el tramo B, no en
afinar el fee.

---

## 7. La advertencia que no se olvida

**Descentralizar no quita la obligación.** Si nosotros ponemos el frontend, creamos los
mercados y operamos el oráculo, somos el operador — no custodios, pero operador. Ser
no-custodial baja el riesgo de custodia y de hackeo; el riesgo regulatorio sigue donde
estaba, y la puerta 04 sigue siendo la puerta 04.

---

## 8. Decisiones de RasDG (2026-09-01)

| Pregunta | Decisión |
|---|---|
| ¿Base o Polygon para la cámara? | **Base.** Tron entra sólo como rampa de depósito, con conversión a USDC al entrar |
| ¿Subsidio declarado o LPs? | **Subsidio declarado.** Los LPs quedan para después; reabren COMPLIANCE §2 |
| ¿La semilla se convierte en subsidio? | **Sí.** La casa deja de cobrar del lado ganador |

Con eso quedan escritas **R-065 a R-068** en `marea/vault/RULINGS.md` (68 reglas).
L0 del plan cierra: la decisión ya no es una nota, es una regla.

### Qué implica la semilla → subsidio

```
hoy        winnerStake = Σ apuestas ganadoras + semilla_ganadora
           payout_i    = stake_i / winnerStake × distributable      ← la casa cobra la parte de la semilla

subsidio   payout_i    = stake_i / (winnerStake − semilla_ganadora) × distributable
```

Tres cosas que no se pueden separar de esa línea:

1. **El multiplicador se mueve en el mismo commit.** `payoutMultiplier` tiene que
   descontar la semilla del denominador, o la app muestra menos de lo que paga —
   mentir en la dirección generosa sigue siendo mentir (R-023, R-044). *El test:*
   `quote(...).toWin == settle(...).payouts[esa apuesta]` para cualquier pozo.
2. **El coste sube, y es el precio de la frase.** Hoy la semilla vuelve cuando cae
   del lado ganador; como subsidio **no vuelve nunca: cuesta S en todos los
   mercados**. Con puntos da igual; con dinero es justo lo que el tope de L9 debe
   acotar, así que el freno deja de ser opcional.
3. **No se migran los mercados abiertos.** Cambiaría el multiplicador ya mostrado a
   quien apostó. Va como campo de la semilla (`seedMode: "apuesta" | "subsidio"`) y
   cada mercado termina con las reglas con las que nació.

Detalle en `marea/vault/LIQUIDEZ.md` §6.1.

## 8bis. Lo que sigue abierto

1. **¿Se acepta la escalera de fees de §3?** La base (varianza) y la regla
   (`R ≥ f₀/f₁`) son aritmética; los peldaños 12% / 4% / 0.24% son propuesta.
2. **¿El pozo vive en un contrato?** No es una decisión técnica: espera la opinión
   legal por país (paso 04).

---

## Figuras

- `fig-aritmetica-camino.png` — la aritmética, el camino de $0 a activa y la escalera de fees.
- `fig-arquitectura-cadena.png` — las tres pruebas, el mapa de contratos, la cadena y los ingresos.

Se regeneran con `marea/vault/liquidez-flujo.html` y `marea/vault/cadena-arquitectura.html`
(Chromium headless, ancho 1720, escala 2).

## Fuentes de verdad

`marea/vault/LIQUIDEZ.md` (documento largo) · `marea/vault/RULINGS.md` (R-024, R-044,
R-057, R-059, R-064) · `marea/vault/COMPLIANCE.md` · `marea/src/domain/parimutuel.ts` ·
`contabilidad.ts` · `settlement.ts` · `marea/src/adapters/custodia/contrato.ts` ·
commits `c1f936d`, `a16fa9c`, `56d99b7`.

Referencias externas verificadas sep-2026: arquitectura de Polymarket (CLOB + CTF + UMA),
esquema de fees de Kalshi (`0.07·C·P·(1−P)`).

_Actualizado: 2026-09-01 (decisiones de cadena, subsidio y semilla)._
