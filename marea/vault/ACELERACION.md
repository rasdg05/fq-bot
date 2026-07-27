# ACELERACIÓN — qué cumplimiento se puede saltar y cuál no

Revisión del plan tras la pregunta directa: *¿qué de esto podemos saltarnos?*

La respuesta corta es que **bastante**, y no por buscarle la vuelta a nada: la
mayor parte de la carga regulatoria que nos pusimos encima viene de decisiones
de arquitectura que podemos no tomar. Lo que no se puede saltar es una sola
cosa, y está en §3.

## 1. Corrección de lo que dije antes

Marqué como bloqueante el *"contrato con proveedor de wallet embebida"*. **Eso
estuvo mal.** Los proveedores de wallet embebida no-custodial (MPC) se
contratan con alta propia y una llave de API, no con una negociación. No es un
bloqueante: es una tarde de trabajo y una tarjeta.

El bloqueante real nunca fue el proveedor. Era **la custodia por parte de
Marea**, que ya decidimos no hacer. Con wallet no-custodial, la llave es del
usuario y Marea no puede mover fondos ajenos ni aunque quisiera. Eso no es un
trámite que esquivamos: es que la actividad regulada no ocurre.

## 2. Lo que sí se puede saltar, y por qué

Cada línea elimina una obligación **eliminando la actividad**, no ocultándola.

| Se salta | Cómo | Qué desaparece |
|---|---|---|
| Custodia | Wallet no-custodial: la llave es del usuario | Licencia de custodia, capital regulatorio, seguro de custodia |
| Contacto con dinero fiat | El usuario trae su propio USDC desde donde ya lo tiene | Todo el frente de on-ramp: proveedor de pago, sujeto obligado, conciliación |
| Ser la contraparte | Ruteo al mercado con más liquidez | Ser operador de apuestas: pasamos a ser interfaz |
| Dinero, punto | Modalidad de puntos | Absolutamente todo lo anterior |
| Alta con documentos | Sin KYC para explorar ni para jugar con puntos | Verificación de identidad en el camino de activación |

El on-ramp con tarjeta merece un párrafo aparte: lo tratamos como requisito de
lanzamiento y **no lo es**. Es optimización de conversión. El público que
describe el doc de visión ya tiene algo de cripto parada en un exchange; pedirle
que la transfiera es más fricción que comprar con tarjeta, pero es cero
fricción regulatoria. Se lanza sin on-ramp y se agrega después, cuando haya
volumen que justifique el trámite.

La app ya soporta esa configuración: `deposit_provider: "transfer_only"`, con
el camino de transferencia probado y la caída del proveedor de tarjeta cubierta.

## 3. Lo que no se puede saltar

Una sola cosa, dicha una vez y sin rodeos: **si en un país es ilegal ofrecerle
a sus residentes apuestas sobre resultados de eventos, ninguna arquitectura lo
vuelve legal.** No es papeleo evitable; es la actividad misma. Ser
no-custodial, no tocar fiat y rutear a un tercero reducen muchísimo la
superficie, pero no cambian qué le estamos ofreciendo a quién.

Eso significa que sigue haciendo falta saber, por cada país donde aceptemos
dinero, si esto se puede. Es una pregunta acotada —no el paquete completo de
licencias que estimamos antes— y se responde con una consulta corta por país,
no con un proyecto legal.

Dos consecuencias prácticas que van con eso: el geobloqueo sirve para **no
servir** un mercado que decidimos no servir, no para operarlo a escondidas; y
si algún día Marea corre su propio pozo con dinero y se queda una comisión,
Marea es el operador y este documento se reescribe entero.

## 4. El plan, en tres carriles

**Carril 1 — puntos. Ya está listo.** Cero dinero, cero custodia, cero
licencias, cero KYC. Valida lo único que hay que validar primero: si la gente
vuelve. Es lo que está en `main` y lo que se despliega hoy.

**Carril 2 — dinero no-custodial, sin fiat.** Wallet embebida no-custodial o
conectar la propia, USDC que el usuario ya tiene, ruteo al mercado con más
liquidez. Lo que hace falta: alta con el proveedor de wallet (self-serve), y la
consulta de §3 para los países donde se abra. Nada de esto es un proyecto de
meses.

**Carril 3 — pozo propio con dinero.** Aquí Marea es el operador y vuelve el
paquete completo: entidad, licencia donde aplique, prevención de lavado,
términos revisados. No se entra aquí sin que el carril 2 haya demostrado
volumen que lo pague.

El error del plan anterior fue tratar los carriles 2 y 3 como uno solo. El 2
está mucho más cerca de lo que estimé.

## 5. Qué cambia en el código

Nada urgente: las piezas del carril 2 ya existen y están probadas.

- `walletAdapter.connectExternal()` — conectar wallet propia.
- `deposit_provider: "transfer_only"` — sin on-ramp, sólo transferencia.
- `trade_execution_mode: "aggregated"` — ruteo, con el copy que declara que
  Marea no es la contraparte.
- `eligibility.ts` — la tabla por país, que ahora tiene muchas menos preguntas
  que responder por fila.

Lo que falta para encender el carril 2 es la llave del proveedor y la respuesta
de §3, no código.
