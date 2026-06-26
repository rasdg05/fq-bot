# Backlog QUANT — la pista pro (jun 2026)

Ideas de contenido **decompuestas de las sesiones reales de backend** (validación, order-flow,
carry, microestructura). Es la pista de arriba: para el operador que ya pasó el novato y quiere
ver *cómo piensa una mesa*. Tono **confiado, directo, TJR** — no humo, no jerga sin traducir,
la matemática a la vista. Cada idea = un video/post/carrusel.

> **El norte de esta pista** (distinto al de la serie liquidez): *"No te vendo señales. Te enseño
> a distinguir una ventaja real de una casualidad bonita. Esa es la única habilidad que importa."*

## La regla de oro del backend (no se negocia)

Cada pieza puede **enseñar el principio** y **gesticular hacia lo sofisticado** (eso construye
autoridad), pero **NUNCA revela la receta**: ni fórmulas internas (P_master, Θ(D), τ, κ_evo, pesos
de killzone), ni parámetros, ni el cómo exacto. Regla práctica por idea: marcá **🎁 REGALAMOS**
(el principio universal, gratis) vs **🔒 QUEDA DENTRO** (lo que nos hace a nosotros).

Lo bello: el principio honesto **vende más** que el secreto. "Validamos out-of-sample" da más
confianza que cualquier captura de ganancias.

---

## Pilar A — Validación: la máquina que mata mentiras *(nuestro moat, el oro)*

- [ ] **Tu backtest probablemente te está mintiendo** ⭐ *(ya sembrado en el ebook, Paso 05)*
  - Gancho: *"Si tu backtest se ve perfecto, lo más probable es que sea mentira. Te explico por qué."*
  - Beats: sobreajuste = encontrar un patrón en el ruido · la curva linda de Twitter · probar mil
    variantes garantiza que UNA brille por suerte · la prueba real = datos que el sistema nunca vio.
  - 🎁 REGALAMOS: el concepto de out-of-sample / overfitting. 🔒 QUEDA DENTRO: qué validamos y con qué umbrales.

- [ ] **El espejismo del +1.47R** ⭐ *(historia real, brutal, honesta)*
  - Gancho: *"Encontramos un setup de +1.47R. Lo matamos nosotros mismos. Te cuento por qué fue lo correcto."*
  - Beats: el número se veía espectacular · pero salía de 17 trades (muestra chica) · cuando probás
    muchas combinaciones, alguna brilla por azar · la métrica que descuenta la suerte lo tumbó · el
    edge REAL era más chico, pero real. *La disciplina de matar tu propia idea ganadora = el activo.*
  - 🎁 REGALAMOS: small-n + multiple testing en simple. 🔒 QUEDA DENTRO: el setup, los símbolos, los números finos.

- [ ] **Out-of-sample: el test que separa al fondo del influencer**
  - Gancho: *"Cualquiera ajusta una estrategia al pasado. La pregunta es: ¿funciona en lo que nunca vio?"*
  - Beats: in-sample (donde diseñás) vs out-of-sample (donde probás) · walk-forward · "si solo gana
    donde lo afinaste, es memoria, no ventaja".
  - 🎁 REGALAMOS: todo el concepto. 🔒 nada sensible.

- [ ] **El Sharpe deflactado, sin matemáticas feas**
  - Gancho: *"Hay un número que descuenta tu suerte. Si tu estrategia no lo sobrevive, no tenías nada."*
  - Beats: mientras más intentos, más alto el listón · la idea de "penalizar por cuántas veces probaste"
    · por qué un Sharpe alto solo no significa nada.
  - 🎁 REGALAMOS: la intuición. 🔒 la implementación exacta (DSR/CPCV/PBO) y cómo la aplicamos.

- [ ] **¿Qué es una ventaja? (en una frase)**
  - Gancho: *"Edge no es 'ganar mucho'. Es una expectativa positiva que sobrevive a datos nuevos. Punto."*
  - Beats: definición limpia · por qué casi nada de lo que ves cumple las dos partes · checklist mental.

## Pilar B — Order-flow y microestructura *(la física del precio)*

- [ ] **El volumen te miente; el order-flow firmado no** ⭐
  - Gancho: *"Todos miran el volumen. Pero el volumen no tiene dirección. Lo que mueve el precio es quién empuja."*
  - Beats: volumen sin firmar = cuánto se movió · order-flow firmado (CVD) = compradores − vendedores
    agresivos · el precio reacciona casi lineal a ESO · por qué es una pista más honesta que el volumen.
  - 🎁 REGALAMOS: qué es el CVD / order-flow firmado, conceptual. 🔒 QUEDA DENTRO: cómo lo cableamos a la señal y su peso.

- [ ] **Econofísica: el precio como un sistema físico** *(la "física" que querés contar)*
  - Gancho: *"¿Y si el mercado se comporta como un fluido? Liquidez, impacto, difusión. La física que casi nadie aplica."*
  - Beats: impacto de mercado (empujar el precio cuesta) · el precio "difunde" como una partícula ·
    liquidez = el medio · por qué pensar en física da mejores preguntas que pensar en "indicadores".
  - 🎁 REGALAMOS: las analogías físicas (impacto, difusión). 🔒 nuestro modelo concreto.

- [ ] **El imán de liquidez, en versión pro**
  - Gancho: *"El precio no va a donde 'debería'. Va a donde hay órdenes que llenar."*
  - Beats: pools de liquidez · por qué el precio los caza · cómo eso convierte 'predecir' en 'medir destino'.

- [ ] **OFI: el siguiente nivel del order-flow** *(teaser de frontera, sin receta)*
  - Gancho: *"Si el order-flow firmado es bueno, el desbalance del libro es el jefe final. Pero hay un costo."*
  - Beats: trades (CVD) vs libro (OFI) · por qué OFI es más fuerte pero más caro/rápido de capturar ·
    la disciplina de pagar por un dato SOLO cuando el gratis ya demostró que vale.
  - 🎁 REGALAMOS: la jerarquía CVD→OFI. 🔒 si/cómo lo usamos.

## Pilar C — Riesgo, sizing y la matemática de sobrevivir

- [ ] **La matemática de la ruina** *(ya en el ebook, Paso 02 — versión video/short)*
  - Gancho: *"No es el apalancamiento lo que te funde. Es el tamaño sin control. Te muestro el número."*
  - Beats: riesgo 1% → decenas de errores aguantados · 20% → ~5 y afuera · arriesgar poco = comprar intentos.

- [ ] **Por qué el win rate es una métrica de vanidad** *(ya en el ebook, Paso 00 — versión short)*
  - Gancho: *"Puedes acertar el 70% y quebrar. Puedes acertar el 40% y forrarte. Te explico la trampa."*
  - Beats: la ecuación de expectativa E = p·b − (1−p) · ejemplo 40%/3R vs 70%/0.5R · asimetría > acierto.

- [ ] **Vol-targeting: el experimento que NO funcionó** ⭐ *(negativo honesto = credibilidad brutal)*
  - Gancho: *"Probamos una técnica que usan los fondos para subir el rendimiento. En lo nuestro, no sirvió. Te cuento."*
  - Beats: qué es ajustar tamaño por volatilidad · por qué en teoría ayuda · por qué en nuestro R por
    trade no movió la aguja · *la lección: medir antes de creer, aunque lo use "todo el mundo".*
  - 🎁 REGALAMOS: el concepto + el resultado honesto. 🔒 nada (es un negativo, regalalo entero).

## Pilar D — Régimen, tiempo y ejecución

- [ ] **El mercado cambia de juego: regímenes**
  - Gancho: *"El mismo setup que paga en tendencia te sangra en lateral. El truco es saber en qué juego estás."*
  - Beats: toro / oso / lateral = reglas distintas · detectar el cambio de régimen · por qué una ventaja
    'que solo vive en un régimen' se apaga con el primer viento.
  - 🎁 REGALAMOS: la idea de régimen. 🔒 nuestro detector.

- [ ] **La hora del día es un edge** *(killzones, en simple)*
  - Gancho: *"No todas las horas pagan igual. Operar siempre es regalar ventaja."*
  - Beats: ventanas de liquidez (Asia/London/NY) · por qué unas tienen mejor expectativa · paciencia = edge.

- [ ] **No predecimos: simulamos cientos de futuros** *(teaser Monte Carlo, sin receta)*
  - Gancho: *"En vez de adivinar a dónde va, simulamos cientos de caminos y sacamos la probabilidad de cada nivel."*
  - Beats: qué es una simulación Monte Carlo en simple · probabilidad de tocar el stop vs el target ·
    EV en R · "el sistema no dice 'va a subir', dice 'la probabilidad juega así'".
  - 🎁 REGALAMOS: la intuición de simular. 🔒 cómo generamos los caminos (drift, vol, magnetic pull, etc.).

- [ ] **El edge que se te escapa en el spread** *(maker vs taker / adverse selection)*
  - Gancho: *"Cruzar el mercado es pagar de más en cada trade. Y eso se come tu ventaja en silencio."*
  - Beats: maker (límite, esperás) vs taker (cruzás, pagás) · fill-rate · la 'selección adversa'
    (te llenan justo cuando no querías) · por qué medirlo decide si tu edge es real al 100%.
  - 🎁 REGALAMOS: el concepto entero. 🔒 nuestros números de fill.

## Pilar E — Bot, proceso y mentalidad

- [ ] **Un bot no es magia, es quitar el cortisol** *(ya en el ebook, Paso 04 — versión video)*
  - Gancho: *"Un bot no adivina el futuro. Hace algo más aburrido y más poderoso: tu proceso, sin miedo."*
  - Beats: el bot = tus reglas ejecutadas sin emoción · "si no podés escribirla como 'si X → haz Y',
    no es una regla, es una corazonada" · automatizar te obliga a volver explícito tu criterio.

- [ ] **Cómo se cobra yield sin apostar a la dirección** *(carry / market-neutral)*
  - Gancho: *"Hay una forma de ganar en cripto sin importar si sube o baja. No es magia: es estructura."*
  - Beats: funding de perpetuos en simple · delta-neutral (largo spot + corto perp) · por qué cobra
    yield · honestidad: rendimiento modesto y constante, no fuegos artificiales.
  - 🎁 REGALAMOS: qué es funding / delta-neutral. 🔒 el basket y la operativa fina.

- [ ] **Los 6 pasos para construir una estrategia** *(= el ebook; versión video-serie)*
  - Gancho: *"Te regalo el proceso completo que sigue una mesa para convertir una idea en un sistema."*
  - Beats: asimetría → invalidación → tamaño → plan → automatizar → validar. Un video por paso.

---

## Formatos sugeridos

| Formato | Para qué piezas |
|---|---|
| **Video largo (5-8 min)** | Pilar A (validación), econofísica, los 6 pasos. Lo que construye autoridad. |
| **Short (60-90s)** | Win rate vanidad · ruina · "el volumen miente" · "qué es una ventaja". Una idea, un golpe. |
| **Carrusel/post** | La ecuación de expectativa · el espejismo +1.47R · vol-targeting que no sirvió. |
| **Lead magnet (PDF)** | `ebook/como-se-construye-una-ventaja.html` — ya hecho. El siguiente: uno de validación. |

## Próximos lead magnets candidatos (después del primero)

1. **"Cómo saber si tu backtest miente"** — todo el Pilar A en un PDF. Es nuestro tema más fuerte.
2. **"El volumen no basta: leé el order-flow"** — Pilar B, microestructura en simple.
3. **"Gana sin adivinar la dirección"** — el carry, para el público más sofisticado.

> Cada lead magnet termina igual: el marco gratis, la disciplina a la vista, y el CTA al canal.
> El producto que se vende primero es **el método y la confianza**, nunca un % de ganancia.
