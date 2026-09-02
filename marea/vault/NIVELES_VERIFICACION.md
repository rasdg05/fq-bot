# NIVELES DE VERIFICACIÓN — KYC por niveles

> **No es asesoría legal.** Investigación de campo para que el brazo legal llegue con las
> preguntas hechas. Los umbrales citados son de fuentes públicas con fecha y **cambian**.
> Entregable maquetado: `MEMORY/marea/niveles-verificacion.pdf`.

## 1. El hallazgo

La idea de RasDG —usuarios verificados con más credibilidad, no verificados «incompletos»—
**existe, tiene nombre y es estándar**: es *tiered KYC* dentro del enfoque basado en riesgo.

Pero funciona **al revés** de como se planteó. Lo que legitima el sistema no es el privilegio
del verificado, sino **el tope del que no lo está**: el nivel bajo es aceptable *porque* está
acotado. Las dos caras conviven —**el tope lo hace defendible, la insignia lo hace producto**—
pero sin tope no hay sistema de niveles, hay decoración.

## 2. Lo confirmado (sep-2026)

- **GAFI/FATF:** tres niveles de debida diligencia — simplificada (riesgo bajo), estándar,
  reforzada. El *tiered KYC* se promueve como herramienta de **inclusión financiera**.
- **México, con números:** las Disposiciones del art. 115 de la LIC manejan niveles de cuenta.
  **Nivel 2** = abonos hasta **3,000 UDIs por cliente al mes** con identificación simplificada.
  **Nivel 2 Bis** = **12,000 UDIs**, fondos desde medios de pago digitales, **apertura
  totalmente remota**, sin RFC ni e.firma (identificación oficial + CURP verificada ante
  RENAPO + comprobante de domicilio + manifestación de actuar por cuenta propia). La CNBV
  publicó una guía de Régimen Simplificado de Identificación en **octubre de 2025**.
- **Cripto — Travel Rule:** referencia GAFI **USD/EUR 1,000**; EE.UU. **3,000 USD**; UE
  **cero** entre proveedores; Canadá **1,000 CAD**; Reino Unido **£1,000** doméstico y **£0**
  transfronterizo; Singapur **1,500 SGD**; Japón **100,000 JPY**. **Regulan el intercambio de
  datos entre proveedores en una transferencia, no cuánto puede operar un usuario:** sirven
  como referencia para fijar nuestros topes, no como la regla que nos aplica.

## 3. La escalera propuesta

| Nivel | Se le pide | Puede | Tope |
|---|---|---|---|
| **N0** visitante | nada | explorar catálogo, precios, resultados | — (explorar nunca pide permiso) |
| **N1** jugador | alias + código de recuperación (ya existe) | jugar con **puntos** | sin dinero |
| **N2** operador | wallet propia + **screening de sanciones** + país declarado | operar con USDC, **sin documento** | tope de nivel + tope por operación (**lo fija el abogado**) |
| **N3** verificado | identidad verificada, voluntaria | sin tope de nivel + **insignia** y funciones que exijan confianza | sólo el tope del país |

**Encaje con lo construido:** `eligibility.ts` ya tiene `depositCapUsd` por país. La escalera
añade la dimensión del usuario y el tope efectivo pasa a ser
`min(cap_país, cap_nivel)` — una columna, no una arquitectura nueva.

**L16 (nueva) · el tope de nivel se hace cumplir donde está el dinero, no en la pantalla.**
Un tope que sólo vive en el frontend se salta con la consola. En arquitectura no custodial va
en el contrato o en el motor de cruce. *Test:* una operación que excede el tope se rechaza
aunque se pida saltándose la app.

**Lo que no tiene nivel:** el **screening de sanciones** (aplica a todos desde N0, siempre) y
**explorar** (R-002).

## 4. El P2P: la advertencia

La idea viene de un tablero P2P estilo Binance. La mecánica de reputación es buena; el tablero
no.

| | Mercado de predicción | Tablero P2P |
|---|---|---|
| Qué pasa | Usuarios apuestan entre sí; el contrato retiene el colateral | Usuarios **cambian cripto por moneda local** entre ellos |
| Qué actividad es | Discutible: la pregunta abierta | **Cambio de divisas / transmisión de dinero** |
| ¿Toca dinero de banco? | **No** | **Sí**, por definición |

**Si se añade el P2P deja de ser una función más: pasa a dominar todo el análisis legal.** El
plan actual llega a lanzamiento sin tocar dinero de banco en ningún punto, y ése es el
argumento más fuerte que tenemos.

**La buena noticia:** la reputación se puede tener **sin el tablero**. Insignia, historial y
confianza entre usuarios son mecánicas de producto sobre la escalera. Se queda lo que gustaba
de la idea y se deja fuera lo que la hace cara.

## 5. Preguntas P11–P14 (se suman a las diez del encargo)

11. ¿Se reconoce aquí un régimen simplificado o por niveles? ¿Umbral y expediente mínimo?
    → *Da el número del tope de N2. Si no existe, N2 desaparece y se salta de puntos a
    verificado: cambia el producto, no un parámetro.*
12. Sin custodia, sin fiat y sin tomar contraparte, ¿nos alcanza alguna obligación de
    identificación? ¿Cambia si el usuario llega desde otra red por un tercero que él firma?
    → *Si no nos alcanza, la escalera es voluntaria: se construye igual porque es barata, pero
    deja de ser bloqueante.*
13. ¿Qué obligación genera el screening de sanciones por sí solo — listas, frecuencia, qué
    hacer ante coincidencia, a quién se reporta? → *Define el procedimiento escrito.*
14. Si se añadiera un tablero P2P de cripto por moneda local: ¿qué actividad sería y qué
    exigiría? → *Decide si el P2P entra alguna vez. Se pregunta ahora aunque no se construya.*

## 6. Qué se puede construir ya

| Pieza | Estado |
|---|---|
| La escalera N0–N3 como estructura | **ya** — no depende de ningún umbral |
| Tope efectivo `min(país, nivel)` | **ya** |
| Screening de sanciones desde N0 | **ya** — 2–3 días |
| Insignia de verificado y sus funciones | **ya** — es producto, no cumplimiento |
| El número del tope de N2 | espera P11 |
| Proveedor de verificación de identidad (N3) | espera la jurisdicción elegida |
| Tablero P2P | **no** — P14 antes de considerarlo |

**Lo honesto:** el concepto existe, tiene nombre y tiene números públicos. Lo que nadie puede
decir sin abogado local es **cuál de esos regímenes nos aplica, si alguno**. Por eso el diseño
está hecho para sostenerse pase lo que pase: si no aplica nada, es control de riesgo propio y
buena función de producto; si aplica algo, ya estamos en la forma que el marco espera.

_Escrito 2026-09-01. Fuentes: FATF/GAFI · CGAP · Disposiciones art. 115 LIC (SIDOF/DOF) ·
Guía CNBV oct-2025 · resúmenes de Travel Rule por jurisdicción._
