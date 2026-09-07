# ENCARGO — la rampa USDT-TRC20 → USDC-Base

> Encargo del segundo desarrollador. Bloque **paralelo**: no toca el contrato, ni la
> matemática de liquidación, ni ninguna invariante del pozo.
>
> **Antes de tocar código:** `vault/AGENTE.md` (especificación operativa — manda),
> `vault/RULINGS.md` (68 reglas), `MEMORY/00-INDICE.md`, `MEMORY/CEMENTERIO.md`.
> Entregable maquetado para entregar en mano: `MEMORY/marea/manual-rampa-trx.pdf`.

Rama: `claude/marea-rampa-tron` · Estimado: 2–3 semanas (+1–2 la pata de vuelta).

## 1. La decisión que lo define todo

El usuario latinoamericano llega con **USDT en Tron**, no de un banco. Hay dos maneras de
construir la rampa y **sólo una es compatible con el proyecto**:

| Forma | Qué pasa | Veredicto |
|---|---|---|
| **Integración** | El usuario firma; los fondos van de él → al puente → **a su propia dirección** en Base. Nunca pasan por nosotros | **Ésta** |
| Dirección de depósito | "Manda a esta cuenta y te acreditamos" | **Prohibida**: nos vuelve custodios en la pata de Tron |

La segunda es más fácil, y por eso es la trampa. Tira abajo L12, R-065 y el argumento legal
entero. Está en `MEMORY/CEMENTERIO.md` con su razón. **Si el camino corto parece ser una
dirección nuestra, para y pregunta.**

**El patrón a copiar ya existe:** `src/adapters/custodia/contrato.ts` omite `firmar()` y
`retirar()` a propósito, con el motivo en el encabezado. El `Puente` se diseña igual.

## 2. La invariante nueva

**L17 · el beneficiario final de una transacción de rampa es siempre una dirección del propio
usuario.** *Test:* armar una transacción cuyo `beneficiarioFinal` no sea la dirección conectada
del usuario **lanza excepción**. Es la contribución más importante del encargo.

## 3. Interfaz propuesta

`src/adapters/puente/contrato.ts` — `cotizar()`, `armar()`, `estado()`, más `esSimulado` para
poder declararlo en la interfaz (R-022). **No existe `enviar()` ni `firmar()`**: no tenemos
llaves de nadie (L12).

## 4. Los siete caminos que fallan

Puente caído (degrada declarando, el camino directo sigue) · llegó menos de lo cotizado (se
acredita lo recibido) · se quedó a medias (consultable, no perdida) · el usuario cerró la app (el
estado vive en el servidor) · el proveedor reintenta (idempotencia **por referencia del puente**)
· llegó dos veces · confirmaciones insuficientes (configurable).

El camino feliz es un día. **El encargo son estos siete.**

## 5. Los pasos

1. Interfaz + proveedor simulado · *puerta:* `npm run ci` verde y la app declara que es simulado.
2. Máquina de estados enchufada a `domain/solicitudes.ts` — **se extiende, no se reescribe** ·
   *puerta:* el mismo aviso tres veces = un movimiento.
3. Cotizar y armar · *puerta:* el test de L17, roto a propósito una vez para verlo rojo.
4. Monitoreo del estado · *puerta:* puente sin responder ⇒ solicitud consultable.
5. Montos parciales y slippage · *puerta:* test de "llegó menos".
6. Pantalla, con el copy en `lib/strings.ts` · *puerta:* los siete caminos tienen texto y ninguno miente.
7. Proveedor real + documento en `vault/` · *puerta:* otra persona opera la rampa sin preguntar.

**Elegir el puente al final, no al principio.** Construir contra la interfaz con el simulado;
al llegar al paso 7 ya se sabe qué hace falta de verdad. Criterio de elección: TRC20 → Base con
USDC nativo · firma del usuario sin custodia · consulta de estado por referencia · comisión y
slippage declarados antes de firmar · y **qué exige el proveedor de nosotros** (varios piden
verificación de empresa: eso es cola, se avisa pronto).

## 6. Definición de terminado

Los siete caminos con prueba y texto · el test de L17 existe y se pone rojo · la suite pasa sin
tocar expectativas ajenas · `npm run ci` verde · documento de operación en `vault/` · y con el
proveedor sin configurar, la app lo declara y sigue usable.

## 7. Agenda

**Día 1, antes de la rampa:** correr `npm run roll` y dejar la suite entera en verde. Hay 4
pruebas rojas porque el catálogo caducó (R-041) — es un primer día real que enseña el ciclo
automático sin arriesgar nada.

**Después de la rampa, en orden:** la pata de vuelta (Base → Tron, 1–2 sem) · screening de
sanciones (3 días, camino crítico, se coordina con el brazo legal) · verificador de prueba Merkle
(1 sem) · vigilante externo de L14 (1 sem) · niveles de verificación N0–N3 (1–2 sem, el tope
espera la respuesta legal).

_Escrito 2026-09-07._
