# ESTRATEGIA — liquidez, datos y red social

Documento de decisiones de negocio con consecuencia técnica. No es un plan de
marketing: es lo que hay que tener construido para que el marketing no queme
dinero. Cada sección dice **qué está resuelto hoy** y **qué falta**.

---

## 1. Liquidez sin ser market maker

**La pregunta:** si no somos creadores de mercado, ¿cómo garantizamos que haya
contraparte en los mercados que están en tendencia?

**La respuesta corta:** el parimutuel no necesita contraparte. Ésa es la razón
por la que se eligió y no un libro de órdenes.

En un libro de órdenes tu apuesta sólo existe si alguien toma el otro lado a tu
precio; sin creador de mercado, los libros de mercados nuevos están vacíos y la
experiencia es "no se pudo". En un pozo común **siempre puedes entrar**: pones
tu dinero de un lado, el precio se ajusta solo, y al final el pozo perdedor se
reparte entre los ganadores. No hay nadie a quien esperar.

Lo que sí se necesita es que el pozo no esté vacío, y eso se resuelve con tres
cosas, dos ya construidas:

| Mecanismo | Estado | Qué hace |
|---|---|---|
| **Semilla de la casa** | ✓ construido | Cada mercado nace con puntos nuestros de los dos lados, así que el primero que entra ve un precio y un pago reales, no un pozo en cero |
| **La semilla corre la misma suerte** | ✓ construido | Está en el denominador del reparto (R-044): si el lado de la casa pierde, la casa pierde. No es un adorno |
| **Mínimo de participación** | ✓ construido | Un mercado con menos de 2 apostadores distintos se anula y se devuelve todo, íntegro y sin comisión (R-059). Con uno solo, el pozo perdedor era nuestra semilla: esa persona no le ganó a nadie |

**El costo honesto de la semilla:** es capital en riesgo. Con puntos vale cero.
Con dinero, cada mercado nuevo inmoviliza capital nuestro que puede perderse.
La forma de acotarlo es **semilla proporcional a la tracción esperada** —
semilla chica en un mercado nuevo, y crecerla cuando el interés aparece.

**Lo que NO vamos a hacer:** cotizar contra el usuario. En el momento en que la
casa toma el lado contrario para "dar liquidez", el interés de la casa es que
el usuario pierda, y eso es exactamente lo que la marca promete no ser.

---

## 2. El feed que sí se comparte

Un mercado sobre el Imacec de Chile no se manda al grupo de WhatsApp. Uno sobre
si el América le gana al Santos, sí. La categoría importa tanto como la
mecánica.

**Lo construido hoy:** la Liga MX se genera sola cada semana desde el calendario
público de ESPN y se resuelve sola con el marcador final. Nueve mercados por
jornada, sin que nadie escriba nada.

**Lo que sigue, por orden de "se comparte / se puede leer solo":**

| Categoría | Se comparte | ¿Se lee por programa? | Estado |
|---|---|---|---|
| Liga MX | Altísimo | Sí, ESPN público | ✓ automático |
| Cripto | Alto | Sí, Kraken público | ✓ automático |
| Selección mexicana, Libertadores | Altísimo | Sí, misma fuente | Falta la plantilla |
| Inflación / tasas | Bajo | Brasil sí; México con token | ✓ automático |
| **Reality shows** (La Casa de los Famosos) | Altísimo | **No hay fuente estable** | Requiere confirmación humana |
| Política / mañanera | Alto | No, y además es delicado | No por ahora |

### 2.1 · Mercados de evento nacional (reality y sucesos)

La categoría con más tracción potencial de todo el catálogo, y la única
importante que hoy **no** se puede leer sola. Vale la pena escribir cómo se
haría, porque el día que se decida hay que hacerlo bien.

**Cuáles califican.** Un evento de relevancia nacional sirve como mercado si
cumple las tres condiciones de R-025, sin excepción:

1. **Fuente pública y única.** La cuenta oficial del programa, el organismo
   electoral, la federación. No "lo que digan los medios".
2. **Criterio numérico o de lista.** "Quién sale de la casa esta semana",
   "cuántos goles", "qué porcentaje". Nunca "si estuvo bien" ni "si cumplió".
3. **Momento de resolución conocido de antemano.** El domingo de la gala, el
   día del conteo. Sin eso, el mercado no se puede cerrar a tiempo.

| Evento | Fuente | Criterio | Automatizable |
|---|---|---|---|
| La Casa de los Famosos (quién sale) | Cuenta oficial del programa | Lista de nominados, uno sale | No — anuncio en vivo |
| Liga MX, Libertadores, selección | ESPN público | Marcador final | **Sí, ya construido** |
| Premios (Latin Grammy, Ariel) | Sitio oficial del premio | Ganador por categoría | No — anuncio en vivo |
| Elecciones | Organismo electoral (INE, CNE) | Conteo oficial | Parcial, y con cuidado |
| Precio de la gasolina, salario mínimo | Diario oficial | Cifra publicada | Sí, con lector nuevo |

**El costo real, dicho sin adorno.** Cada mercado de anuncio en vivo es **una
persona mirando** y confirmando en la app. Con la ventana de disputa de 12 h no
hay prisa, pero hay que hacerlo. Por eso la regla operativa que propongo:

> **Máximo tres mercados de confirmación humana a la vez**, y sólo de eventos
> con audiencia grande. Si un mercado no justifica que alguien se siente a
> verlo, no se publica.

**Lo que sube el techo:** si un reality publica su resultado en una API o en un
feed estable, se mueve al oráculo de series y deja de costar. Vale la pena
revisarlo cada temporada — igual que revisamos las APIs institucionales y
resultó que Brasil sí publicaba.

**Sobre los reality shows:** es la mejor idea de crecimiento de esta lista y
también la única sin fuente automática. Quien decide quién sale de la casa es
un programa de televisión: no hay endpoint, y el resultado se anuncia en vivo.
Se puede hacer con confirmación humana en minutos —el resultado es público y no
ambiguo— pero hay que decidirlo a sabiendas: **cada mercado de este tipo es una
persona mirando el programa y confirmando**. Vale la pena para dos o tres
mercados de mucho volumen, no para veinte.

**Sobre la política:** un mercado sobre lo que diga un presidente es fácil de
disputar y difícil de resolver sin discrecionalidad, que es justo lo que R-025
prohíbe. Si entra, entra con criterio numérico y fuente oficial, nunca con
"lo que se entienda de lo que dijo".

---

## 3. Los datos como activo

La tesis es correcta: lo que se acumula vale más que lo que se construye. Pero
"recopilar datos" sin decidir cuáles es cómo se junta basura cara de guardar.

**Lo que ya se está acumulando y no se puede comprar en ningún lado:**

| Dataset | Desde | Por qué es único |
|---|---|---|
| Superficie de volatilidad diaria | 27 jul 2026 | Deribit no publica historia de la superficie: sólo existe si la guardas cada día |
| Probabilidades del pozo, con marca de tiempo | Con el servidor | Cómo se movió la creencia colectiva latina antes de cada evento |
| Resoluciones con su evidencia | Con el liquidador | Un histórico auditable de qué pasó y con qué lectura se determinó |

**El dataset que de verdad vale, y que todavía no existe:**

> **Calibración de la multitud latinoamericana.** Cuando el pozo dice 70 %,
> ¿pasa el 70 % de las veces? Nadie tiene esa medición para Latam. Polymarket
> la tiene para el público global-anglo. Es un dato que se cobra, se publica y
> se cita — y nos hace la referencia de la región, que vale más que la comisión.

Para que exista se necesitan **mercados resueltos con volumen**, o sea usuarios.
Eso hace que la prioridad de datos y la de crecimiento sean la misma cosa: cada
mercado que se resuelve con gente adentro es una fila del dataset.

**Reglas que se fijan desde ahora, antes de que haya algo que vender:**

1. **Datos agregados, nunca personales.** Lo que se puede publicar o vender es
   la probabilidad, el volumen, el resultado y la calibración. Nunca quién
   apostó qué. Un usuario no es un producto.
2. **Ninguna venta de dato hasta que se pueda decir cómo se recogió.**
   Metodología publicable o no se vende.
3. **La telemetría sigue saliendo por lista blanca** (R-020). Ampliar lo que se
   recoge es una decisión explícita, no un efecto secundario.

---

## 4. Lo social

Compartir un mercado ya funciona. Lo que sigue tiene un orden claro por
relación valor/esfuerzo:

| Función | Por qué | Esfuerzo |
|---|---|---|
| **Tarjeta de resultado para redes** | "Le atiné 8 de 10" es lo que la gente presume; hoy sólo se puede compartir el mercado, no el logro | Medio — imagen generada en el servidor |
| **Código de referido** | Trae usuarios con costo cero y da una razón para volver | Bajo |
| **Seguir a alguien** | Convierte la tabla en una red: seguir al que le atina | Medio |
| **Aviso cuando alguien que sigues apuesta** | Es el bucle que trae a la gente de vuelta sin pagar publicidad | Medio |
| **Copiar la apuesta de otro** | Lo más pedido y lo más delicado: con dinero real es asesoría de inversión disfrazada | Alto, y con pregunta legal |

### 4.1 · Copiar apuestas — lo que hay que saber antes de construirlo

**Qué es:** ver lo que apostó alguien con buena precisión y repetirlo con un
tap, o en automático.

**Por qué se pide:** es el bucle social más potente que existe en este tipo de
producto. Convierte a los que le atinan en creadores de contenido con público,
y a los demás les da una razón para volver todos los días.

**Cómo se construiría, en orden:**

1. **Copia manual** — botón "apostar igual" en la posición de otro. Casi gratis
   de construir sobre lo que ya existe, y ya prueba si a la gente le interesa.
2. **Aviso al seguir** — te llega cuando alguien que sigues apuesta. Necesita
   notificaciones, que es infraestructura nueva.
3. **Copia automática** — con tope por apuesta y tope diario. Aquí empieza lo
   delicado.

**Los tres límites que hay que respetar:**

- **El que copia mueve el precio del que copió.** En parimutuel, cien personas
  copiando la misma apuesta empeoran el pago de todos, incluido el original.
  Hay que mostrarlo antes de copiar, no después.
- **La precisión pasada no predice.** Una racha de cinco aciertos es ruido con
  cinco mercados. La tabla ya muestra el denominador (`8/10`, no `80 %`) justo
  por esto, y la copia tiene que hacer lo mismo.
- **Con dinero real cambia el marco legal.** Ver el punto de abajo.

**La advertencia sobre copy-trade:** con puntos es un juego. Con dinero real,
"copia las apuestas de este usuario" puede caer en recomendación de inversión
según el país, y eso cambia el marco regulatorio entero. Se puede construir,
pero se decide con la opinión legal de `COMPLIANCE.md` en la mano, no antes.

**El orden que recomiendo:** tarjeta de resultado → referido → seguir → avisos.
Las dos primeras no necesitan nada nuevo del servidor y son las que mueven la
aguja de crecimiento.

---

## 5. Qué significa "listo desde el día uno"

No es que no tenga defectos. Es que **el ciclo completo funciona para el primer
usuario que llegue**:

- Entra sin cuenta y ve mercados que le importan. ✓
- Crea cuenta en dos campos cuando quiere apostar. ✓
- Su apuesta sigue ahí mañana. ✓
- El mercado se resuelve solo y le paga, con la evidencia. ✓
- Ve su lugar en la tabla y puede compartir. ✓
- El feed no se vacía. ✓

- Si olvida su contraseña, la recupera con su código. ✓
- Medimos si vuelve. ✓

Lo que falta para llamarlo producto terminado, en orden:

1. **Tarjeta de resultado para redes** — "le atiné 8 de 10" es lo que se
   presume, y hoy sólo se puede compartir el mercado, no el logro.
2. **Código de referido** — trae usuarios a costo cero.
3. **Seguir a alguien y avisos** — el bucle que trae de vuelta sin pagar
   publicidad.
4. **Panel de lo que mide la analítica** — los eventos ya se guardan; falta
   verlos sin abrir un archivo por SSH.
