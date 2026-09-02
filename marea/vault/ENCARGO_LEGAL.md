# ENCARGO — la mano que prepara lo legal

> **Esto no es asesoría legal ni la sustituye.** La mano prepara el terreno; la opinión la
> firma un abogado local con cédula. Si la mano termina opinando sobre legalidad, el
> encargo falló.
>
> Documento para entregarle a la persona. Bloque paralelo: no toca código, ni contrato, ni
> invariante. Ver `LIQUIDEZ.md` §12 para el contexto de por qué esto es el camino crítico.

## 0. Por qué existe esta mano

Las horas de abogado son el recurso **caro y lento**. Un abogado que recibe *"¿es legal una
app de apuestas?"* cobra por descubrir qué hacemos, y contesta despacio y en vago. Uno que
recibe un memo de hechos de cinco páginas y diez preguntas cerradas contesta rápido y por
escrito.

**El trabajo de la mano es convertir lo segundo en lo primero.** No es investigar la ley:
es hacer que cada hora de abogado rinda.

---

## 1. Entregable · El memo de hechos (semana 1)

Cinco páginas, sin adjetivos, describiendo el mecanismo. Tiene que contestar **sin que
nadie pregunte**:

- **Qué es un mercado** y cómo se resuelve: pregunta, fuente citada, oráculo automático,
  ventana de disputa antes de pagar.
- **Quién es contraparte de quién:** los usuarios entre sí. **La casa nunca toma lado**
  (R-057, R-065). Es el hecho que más cambia la calificación y el que más rápido se
  malentiende.
- **Dónde está el dinero:** contrato en Base, no custodial. **No existe función que mueva
  fondos de un usuario** (L12). Marea sólo *propone* resolución, tras multisig y timelock.
- **De qué cobra la casa:** fee sobre la varianza del cruce + rendimiento del colateral
  mientras espera. El subsidio de liquidez **nunca cobra** (R-067).
- **Qué unidad:** puntos hoy; USDC después. **Nunca fiat**, sin rampa bancaria, sin cuenta
  nuestra en ningún banco recibiendo dinero de usuarios.
- **Qué temas tienen los mercados.** Éste es el detalle que más pesa y el que más se
  olvida: el catálogo mezcla **fútbol (Liga MX)** con inflación, tipo de cambio y precios.
  El deporte es lo que más rápido se clasifica como apuesta en la región. El memo lista los
  temas **uno por uno** y pide respuesta **por tema**, no en bloque.

Los planos 01 y 03 de `MEMORY/marea/planos-construccion.pdf` van como anexo: son el
mecanismo dibujado, y ahorran una reunión entera.

**Cierra cuando:** RasDG lo lee de principio a fin y no tiene que corregir ni un hecho.

---

## 2. Entregable · Las diez preguntas (semana 1–2)

Escritas para que se puedan contestar. **Regla:** cada pregunta lleva anotado *qué haríamos
con cada respuesta posible*. Una pregunta cuya respuesta no cambia nada de lo que hacemos
no se pregunta — se está pagando por curiosidad.

1. **Calificación.** ¿Un mercado de predicción con resolución por oráculo y contraparte
   entre usuarios es juego/apuesta, instrumento derivado, otra figura, o nada regulado?
   ¿Cambia **por tema** (deporte vs inflación vs clima)?
2. **El sujeto regulado.** Si no custodiamos ni tomamos contraparte, pero operamos el
   frontend, creamos los mercados y operamos el oráculo: ¿somos operador de juego,
   intermediario financiero, proveedor de servicios de activos virtuales, o ninguno?
3. **La unidad.** ¿Cambia algo que sea con puntos **sin valor de rescate**? ¿Y si los puntos
   nunca se pueden canjear por nada?
4. **Licencia.** Si hace falta: cuál, coste, plazo, capital mínimo, y **si se puede operar
   mientras se tramita**.
5. **Captación y publicidad.** ¿Se puede promocionar a residentes? ¿Qué exige el copy?
6. **AML.** ¿Basta el screening de sanciones o se exige KYC completo? ¿Desde qué monto?
   ¿Hay obligación de reporte y ante quién?
7. **Impuestos.** ¿Retención en la fuente sobre la ganancia del usuario? ¿La practicamos
   nosotros?
8. **Estructura.** ¿Entidad local obligatoria, o se puede operar desde el extranjero
   atendiendo residentes? ¿Cómo se ve aquí la *reverse solicitation*?
9. **Bloqueo.** Si la respuesta es no: ¿qué nivel de bloqueo se considera suficiente — IP,
   declaración del usuario, KYC — para no estar operando ahí?
10. **El oráculo.** Operar la resolución, ¿nos convierte en árbitro o fiduciario frente al
    usuario? ¿Qué obligación de proceso o de publicidad genera?

---

## 3. Entregable · El mapa y la terna (semana 2–3)

- **Tabla** de los 15 países de `src/domain/eligibility.ts` con cuatro columnas: ¿existe
  régimen de juego? ¿de derivados? ¿de activos virtuales? ¿hay precedente o pronunciamiento
  público sobre mercados de predicción? **Con la fuente citada y sin conclusión propia.**
- **Recomendación de por cuál empezar — uno solo.** El criterio no es el mercado más
  grande: es **dónde la respuesta llega más rápido y más clara**. Un "sí" acotado en tres
  meses vale más que un "quizá" en un mercado grande a los nueve.
- **Tres despachos** para el país candidato, con presupuesto y plazo **por escrito**, y
  experiencia demostrable en juego, fintech o cripto local. No el conocido que es abogado.

**Cierra cuando:** hay tres presupuestos comparables sobre la mesa.

---

## 4. Entregable · La opinión, contratada y traducida (semana 4–12)

- Contratar con **alcance escrito**: las diez preguntas, respuesta por escrito, y una
  cláusula de actualización si cambia la norma.
- Cuando llegue, la mano hace la **última milla, que es la que importa**: traducirla a **una
  línea** de `src/domain/eligibility.ts` — `status`, `depositCapUsd`, `note` — y archivar la
  opinión firmada en `vault/` con fecha y autor.

El código ya tiene la puerta puesta, y no se puede abrir "sólo para probar":

```
eligibility.ts     los 15 países en `pendiente`; US y ES en `bloqueado`
validate.mjs       falla si la build deja de ser simulada con la puerta apagada
validate.mjs       falla si el motor pasa a `parimutuel_money` sin la puerta encendida
```

**Cierra cuando:** un país pasa de `pendiente` a `permitido` **con su tope de depósito**, y
`npm run validate` pasa.

> Una opinión legal que termina en un PDF guardado no cambió nada. Ésta termina en una línea
> de código que una prueba verifica. Es la misma regla del repo: *un hallazgo sin invariante
> que lo haga cumplir es una nota, no un arreglo.*

---

## 5. Trabajo paralelo que la mano sí puede hacer sola

Nada de esto necesita abogado, y todo baja la factura del que se contrate:

- **Screening de sanciones:** elegir la fuente de la lista, definir cada cuánto se actualiza
  y escribir el procedimiento. Son 2–3 días suyos, no del abogado.
- **Due diligence de proveedores:** puente, RPC, hosting, auditor. Quiénes son, dónde están
  constituidos, y **qué exigen ellos de nosotros** (varios piden KYB antes de dar acceso).
- **Borrador de términos y política de privacidad**, para que el abogado **revise** en vez
  de redactar. La diferencia de coste es grande.
- **Auditoría de declaraciones:** recorrer el copy de la app y listar cada afirmación que un
  regulador podría leer como promesa. R-011 dice que el copy se deriva de las flags; la mano
  verifica que siga siendo cierto.
- **Registro:** cada respuesta del abogado entra a `MEMORY/marea/` con fecha, para que nadie
  la vuelva a preguntar en seis meses.

---

## 6. Lo que la mano NO hace

- **No opina sobre legalidad.** Ni siquiera "yo creo que sí se puede".
- **No mete una conclusión propia en `eligibility.ts`.** Sólo traduce una opinión firmada.
- No negocia el alcance con el abogado sin RasDG.
- No contacta reguladores sin abogado.
- No habla del producto en público como si estuviera aprobado.

---

## 7. Cómo se sabe, pronto, si está funcionando

| Semana | Señal |
|---|---|
| 1 | Memo de hechos aprobado sin correcciones |
| 2 | Las diez preguntas, cada una con "qué haríamos según la respuesta" |
| 3 | Tres presupuestos comparables |
| **4** | **Abogado contratado.** Si en la semana 4 no hay abogado contratado, la mano no está funcionando — y hay que verlo en la semana 4, no en el mes 6 |
| 8–12 | Opinión escrita → una línea en `eligibility.ts` → `validate` verde |

---

## 8. Si sólo alcanza para una persona

Los dos bloques paralelizables son **la rampa Tron** y **esto**. No valen lo mismo:

- La **rampa** suma 2–3 semanas al final del calendario y no bloquea nada más.
- Lo **legal** está en el camino crítico entre M2 y el primer peso, y **no se puede
  acelerar con dinero una vez que empezó** — la cola es la cola.

**Si hay presupuesto para una sola mano, va a lo legal.** Corrige lo que dije antes: la
rampa era la respuesta cuando lo legal no estaba sobre la mesa; con las dos opciones
delante, la rampa espera.

---

## 9. Anexos (en el PDF)

`MEMORY/marea/brazo-legal.pdf` es este mismo encargo maquetado en A4 para entregar, y añade
dos piezas de trabajo que aquí sólo se nombran:

- **Anexo A · Los hechos ya redactados.** Doce hechos en lenguaje llano, listos para levantar
  el memo de la semana 1: qué es, cómo se resuelve, la ventana de disputa, quién es
  contraparte de quién, de qué cobra la casa, que la liquidez de arranque nunca cobra, dónde
  está el dinero, que no hay dinero de banco en ningún punto, cómo llega el dinero del
  usuario, la auditabilidad, y **los temas del catálogo enumerados uno por uno**.
- **Anexo B · La tabla de los 15 países**, vacía, con las cuatro columnas que hay que llenar
  con fuente citada y sin conclusión propia. US y ES no se investigan: ya están bloqueados
  por decisión tomada.

Y una tarea de la primera hora, antes que el memo: **confirmar que el producto hoy no recibe
dinero de nadie.** Si existiera algún camino en la app que acepte fondos, eso cambia la
urgencia de todo lo demás y hay que decirlo el mismo día.

_Escrito 2026-09-01. Contexto: `LIQUIDEZ.md` §12 · `COMPLIANCE.md` · `MEMORY/marea/README.md`._
