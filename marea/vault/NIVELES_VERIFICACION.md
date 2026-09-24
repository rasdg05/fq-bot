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
aunque se pida saltándose la app. Cableado en **R-069**.

**N2 admite dos orígenes, mismo trato.** Dentro de N2 conviven el usuario que llega con USDC que
ya vivía en su wallet (cripto nativo) y el que lo trae de una rampa/proveedor que ya le hizo KYC
(Bitso y similares). Se pensó premiar el KYC heredado con un tope más alto, pero **detectar la
procedencia automáticamente no es viable**: los exchanges rotan cientos de wallets, no publican
sus direcciones vigentes, y el USDC suele pasar por una wallet intermedia que borra el rastro por
hopping. Conclusión: **mismo tope y misma experiencia para ambos**. El KYC heredado queda como
argumento de riesgo interno, no como una función que dependa de adivinar de dónde vino el dinero;
si tiene reconocimiento legal para topes más altos lo dice **P18**, no nosotros.

**Anti-structuring (R-070).** El tope de nivel no basta si se puede fragmentar. Varios retiros que
individualmente quedan bajo el umbral pero acumulados lo cruzan disparan verificación **como una
sola operación**, sobre una **ventana móvil** (30 días como valor de trabajo hasta P15); el cambio
recurrente de dirección destino en ventana corta también la dispara. Se detecta el patrón, no la
operación aislada.

**Lo que no tiene nivel:** el **screening de sanciones** (aplica a todos desde N0, siempre; rechaza
en ambos sentidos y rechazar no es confiscar — **R-071**) y **explorar** (R-002). El KYC nunca
aparece de forma arbitraria: sólo lo disparan tope acumulado, anti-structuring o subir de nivel
voluntariamente — lista cerrada (**R-072**).

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

## 5. Preguntas P11–P18 (se suman a las diez del encargo)

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
15. ¿Cuál es la ventana móvil correcta para el anti-structuring bajo régimen mexicano? *30 días
    es nuestro valor de trabajo (R-070); confírmalo o corrígelo.* → *Fija el parámetro de la
    ventana acumulada. Sin número del abogado, R-070 corre con 30 días como provisional.*
16. Un retiro a wallet cripto propia del usuario, ¿cae **fuera** del régimen de identificación de
    la LIC y de la Ley Antilavado (LFPIORPI), o hay algún matiz que se nos escape? → *Si cae
    fuera, la escalera es control de riesgo propio; si hay matiz, define qué obligación entra y
    desde qué monto.*
17. Siendo **no custodiales**, ¿qué obligación de reporte tiene Marea ante **SAT o UIF** sobre las
    operaciones de sus usuarios? → *Define si generamos avisos/reportes, cuáles, con qué
    periodicidad y qué disparadores automatizar.*
18. El **KYC heredado del proveedor de rampa** (ej. Bitso), ¿tiene reconocimiento legal explícito
    para justificar **topes propios más altos**, o es sólo un argumento de riesgo interno que no
    cambia obligaciones legales? → *Decide si N2 puede diferenciar topes por origen. Si no, se
    queda como está: mismo tope para ambos orígenes (§3).*

## 6. Qué se puede construir ya

| Pieza | Estado |
|---|---|
| La escalera N0–N3 como estructura | **hecho** · `domain/niveles.ts` (`ESCALERA`) |
| Tope efectivo `min(país, nivel)` | **hecho** · `effectiveCapUsd` (R-069/L16) |
| Screening de sanciones desde N0 | **ya** — 2–3 días (fuente de la lista, pendiente) |
| Screening bidireccional (R-071) | **hecho** · `screenDestino` — política de firma, no umbral |
| Lista cerrada de disparadores de KYC (R-072) | **hecho** · `kycTrigger` |
| Anti-structuring por ventana móvil (R-070) | **hecho** la estructura · `detectStructuring` — el número de ventana espera P15 |
| Recordatorio fiscal en el retiro (VOICE) | **ya** el copy — el monto que lo dispara espera P16/P18 |
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

_Actualizado 2026-09-24 tras revisión de un colaborador: se cablearon R-069 (tope en contrato),
R-070 (anti-structuring), R-071 (screening bidireccional) y R-072 (lista cerrada de KYC) en
`RULINGS.md`; se resolvió el doble origen de N2 (mismo tope, la detección de procedencia no es
viable); se sumó el recordatorio fiscal a `VOICE.md`; y se agregaron P15–P18 al encargo. Nota de
unidades para el abogado: el régimen de cuentas por niveles del art. 115 LIC va en **UDIs**, y el
de actividades vulnerables (LFPIORPI) va en **UMA** — no mezclar; cuál aplica es P11/P16._
