# Marea — Visión: el Psicólogo de mercado (análisis de tu trading)

> "Que puedas bajar tus trades o que la plataforma se conecte a tu broker y
> analice tu psicología —eso lo tiene HybridTrader y está bueno—. Analiza tus
> patrones. Lo perro es que lo podemos hacer aún más verga." — RasDG

**Estado:** visión / a cocinar. Referencia directa: el "AI Psychologist" de
HybridTrader (capturas en el brief de RasDG, 2026-07-24).

---

## 1. Qué hace HybridTrader (lo que estudiamos y respetamos)

Su "AI Psychologist" conecta/importa tus trades y te devuelve:

- **Discipline score** (ej. 85%) y **"impuesto psicológico"** (cuánto te cuesta
  al mes tu propia indisciplina: -$70.7k en su demo).
- **Patrones detectados con costo en $**, ordenados por lo que te sangran:
  - *"Tras una pérdida, reentras la misma sesión en 30 min; esas reentradas
    tienden a perder"* — Crítico ×11, **-$20,221**.
  - *"Días que abren en verde suelen cerrar en rojo"* — Crítico ×2, -$16,008.
  - *"Días que abren ganando tienden a alargarse; los trades extra pierden"* —
    Crítico ×1, -$9,121.
- **Ventanas de vulnerabilidad** (ej. Lun 22:00-24:00, 43% de tasa de error).
- **Tus fortalezas** (qué instrumento/sesión/duración te da win rate).
- **Checklist pre-trade** accionable (revisa trades previos, pausa 30 min tras
  pérdida, confirma setup, limita a 5 trades por sesión).
- **Un chat coach** ("Hey, ¿qué traes en mente?" con atajos: "rompe mi peor loop",
  "rutina post-pérdida", "foco de hoy").

Es bueno. Es denso, corporativo y en inglés. **Ahí está la grieta.**

---

## 2. Cómo lo hacemos "aún más verga" (nuestra ventaja injusta)

Cuatro palancas que HybridTrader no puede copiar fácil:

### 2.1 Cruzamos TU psicología con NUESTRA lectura del mercado
HybridTrader solo sabe de ti. **Nosotros sabemos de ti *y* del mercado**, porque
tenemos motor propio (régimen, funding, order-flow). Eso desbloquea insights que
ellos no pueden dar:

> "Tus peores reentradas post-pérdida pasan cuando el mercado está **caliente y
> sin dirección** (régimen que ya marcamos en el panel). En mercado **frío con
> estructura**, tu reentrada hasta gana. No es que reentrar sea malo — es que
> reentras en el peor clima."

Eso es oro: no te regaña por reentrar, te dice **cuándo** tu patrón es veneno y
cuándo no. Personalización contra el estado real del mercado. Ellos no lo tienen.

### 2.2 Coaching, no vergüenza (y en español de verdad)
Su dashboard te tira "-$50,691 de impuesto psicológico" en la cara. Duro, casi
humillante. Nuestro tono (ver `cultura_y_tono.md`) es **calma con autoridad**:
el mismo dato, enmarcado como quien te ayuda, no como quien te castiga.

> "Este mes tu indisciplina te costó ~$X. No para hacerte sentir mal — para que
> veas que el enemigo no es el mercado, eres tú a las 10pm de un lunes. Y eso
> **sí** se arregla."

### 2.3 Gusto y calma visual
Su UI es densa y oscura, muy "terminal financiera gringa". La nuestra: papel
cálido, tipografía propia, una lectura clara a la vez, respiración visual.
El análisis de tu peor pérdida no debería sentirse como una sala de urgencias.

### 2.4 Integración con el resto de Marea
El mismo usuario que recibe señales y (mañana) apuesta, ve su psicología en el
mismo lugar. Un solo producto coherente, no tres apps pegadas con cinta.

---

## 3. El producto (visión del usuario)

### 3.1 Cómo entran los datos (de más simple a más ambicioso)
1. **Importar CSV** (MVP): el usuario exporta su historial del broker
   (MT4/MT5, cTrader, Binance, Bybit…) y lo sube. Cero integración, funciona ya.
2. **Captura/foto del historial** → parseo (para el neófito que no sabe exportar).
3. **Conexión por API de solo-lectura** (fase 2): read-only keys del exchange, o
   agregadores tipo broker-connect. **Nunca** permisos de trading — solo leer.

### 3.2 Qué le devolvemos
- **Ritmo de disciplina** (nuestro "discipline score", pero con nombre de marca)
  y el **costo de la indisciplina** del mes, en frase honesta y calmada.
- **Tus patrones**, ordenados por lo que te cuestan, cada uno con:
  el patrón en una frase clara + su costo + **el clima de mercado en que ocurre**
  (nuestra diferencia) + una acción concreta.
- **Tus ventanas de vulnerabilidad** (día/hora) y **tus fortalezas** (dónde sí
  eres bueno — importante para no solo señalar lo malo).
- **Checklist pre-sesión** personalizado, que aparece en Telegram antes de que
  operes ("son las 10pm de un lunes, tu peor ventana: hoy máximo 2 trades").
- **Coach conversacional** en Telegram: "¿por qué perdí hoy?", "rompe mi loop",
  "prepárame para la sesión de NY". Con nuestro tono.

### 3.3 Dónde vive
Nativo en Telegram (checklist y coach) + una vista rica en el portal (los
patrones, las ventanas, la tendencia del costo).

---

## 4. Mecánica de detección (sin humo, reusa lo que ya sabemos hacer)

No es magia de "IA"; es estadística honesta sobre TUS trades — la misma
disciplina que ya aplicamos al ledger del motor (`entropy_cognition`,
`forward_measure`):

- **Segmentar** cada trade por: hora/sesión, día, instrumento, duración,
  contexto (¿fue post-pérdida?, ¿fue trade extra tras racha?, ¿en qué régimen de
  mercado estábamos según nuestro feed?).
- **Medir** win rate y P&L por segmento, con **n suficiente** antes de afirmar
  nada (misma regla del `forward_measure`: sin muestra, se dice "aún no
  concluyente" — no se inventa un patrón).
- **Rankear** patrones por costo esperado (frecuencia × pérdida media).
- **La capa "IA"** (Claude) solo **narra** el patrón ya medido y sugiere la
  acción — nunca inventa el número. Igual que el brief de sesión: el dato manda,
  la IA traduce.

Honestidad como en todo lo demás: **si no hay datos suficientes, lo decimos.**
Un patrón "×2 -$16k" con n=2 no es ley, y hay que enmarcarlo como hipótesis, no
como verdad. HybridTrader marca "Critical" con n=1-2; nosotros seremos más
honestos con la incertidumbre — y eso, paradójicamente, nos hace más creíbles.

---

## 5. Principios de privacidad y confianza (no negociables)

- **Tus trades son tuyos.** Se procesan para darte TU análisis, no para
  entrenar nada que se comparta ni para revender datos. Se puede borrar todo.
- **Solo lectura, siempre.** Si algún día conectamos por API, jamás pediremos
  permisos de operar. El que pide permiso de trading es el que te va a vaciar la
  cuenta; nosotros no.
- **Sin vergüenza pública.** Los números de nadie se muestran a nadie más. Nada
  de leaderboards de "quién perdió más".
- **Enmarcar con incertidumbre.** Ver §4: patrones con poca muestra van
  etiquetados como tales.

---

## 6. Roadmap por fases

- **Fase 0 — Papel (aquí).** Este doc + definir el formato CSV mínimo y las
  métricas v1.
- **Fase 1 — Import CSV + análisis básico. ✅ CONSTRUIDO** (`tools/psycho_analyzer.py`).
  Ingestión flexible de CSV de broker (MT4/MT5/cTrader/Binance/Bybit), segmentación
  por hora/día/sesión/instrumento, detección de la reentrada post-pérdida
  ("revenge"), ventanas de vulnerabilidad y fortalezas gateadas por n≥min, y costo
  acotado de la indisciplina. Python puro, sin IA generativa: pura estadística
  honesta. `python tools/psycho_analyzer.py --demo` para verlo.
- **Fase 2 — Cruce con régimen de mercado (nuestra ventaja). ✅ CONSTRUIDO**
  (`tools/regime_timeline.py` + cruce en `psycho_analyzer.py`). Cada trade se
  etiqueta con el clima de mercado —calculado con la MISMA irreversibilidad KL
  validada en producción (`validate_regime_irreversibility`)— y el análisis revela
  patrones **clima-dependientes**: p.ej. la reentrada revenge sangra en
  «caliente·sin dirección» y aguanta en «frío·con dirección». **Este es el momento
  en que superamos a HybridTrader** (ellos no tienen motor de mercado). Último
  cabo: OHLCV histórico por símbolo del usuario (crypto vía Binance Vision ya;
  índices/oro necesitan fuente). `python tools/psycho_analyzer.py --demo` lo muestra.
- **Fase 3 — Coach en Telegram + checklist pre-sesión** con nuestro tono.
- **Fase 4 — Conexión read-only a broker/exchange** para que sea automático.

**Empezar por Fase 1** con un CSV de ejemplo real (idealmente los propios trades
de RasDG) para calibrar métricas con datos de verdad, no inventados.

---

## 7. Por qué esto encaja con lo que ya somos

- Ya sabemos hacer **estadística honesta sobre un ledger** (motor →
  `entropy_cognition`, `forward_measure`, `/tphits`, `/forward`). El psicólogo es
  la **misma disciplina aplicada al ledger del usuario**.
- Ya tenemos **lectura de régimen de mercado** → la palanca que nos hace únicos.
- Ya tenemos **el tono** para hablar de pérdidas sin humillar.
- Ya vivimos en **Telegram** → el coach y el checklist llegan donde el trader ya
  está, en el momento en que van a operar.

HybridTrader te dice *qué* haces mal. Marea te dirá *qué haces mal, en qué clima
de mercado te pasa, y qué hacer al respecto* — más claro, más honesto, y más
bonito. Ese es el "aún más verga".
