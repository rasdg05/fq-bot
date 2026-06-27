# Física y matemática moderna → motor FQ
### Deep research, junio 2026 — qué transfiere de verdad, qué es humo con bata de laboratorio

**Cómo se hizo:** 107 agentes, 2.67M tokens, ~83 min. 25 fuentes primarias → 121 afirmaciones extraídas → 25 verificadas con 3 votos adversariales cada una (cada voto intentaba *refutar*; 2/3 refutaciones mataban la afirmación). Sobrevivieron 21, murieron 4. Solo cito lo que pasó ese filtro.

---

## Veredicto en una línea

La física que **sí** mejora el motor es la que ya estás usando sin ponerle nombre cuántico: **microestructura / order-flow** (la familia del CVD). Lo explícitamente "cuántico" es, casi todo, **reetiquetado** — mate que funciona *solo cuando suelta su contenido cuántico*. La regla de oro (Yee, EJPS 2021, 3-0): **se transfiere la MATEMÁTICA cuando es empíricamente adecuada; importar el MECANISMO físico (el mercado "es" un sistema cuántico, "sufre" una transición de fase) es sobreventa.**

---

## 1. Lo que SÍ transfiere — y es de la familia del CVD

### 1.1 Ley de raíz cuadrada del impacto (δ≈0.5) — el núcleo robusto
Impacto ∝ σ·R^δ, con δ≈0.5. Una de las regularidades empíricas más replicadas de los últimos 30 años.
- **Confirmada en Bitcoin específicamente**: Donier & Bonart 2015 (arXiv:1412.4503), >1M de metaórdenes BTC/USD reconstruidas, aguanta sobre cuatro décadas de tamaño.
- **Reconfirmada 2025**: Sato & Kanazawa, *Phys. Rev. Lett.* 135:257401 (arXiv:2411.13965) — toda la Bolsa de Tokio, 8 años, δ=0.489±0.0015 a nivel acción y 0.493±0.0050 a nivel *trader*. "Universalidad estricta".
- Bouchaud (co-descubridor): el exponente está "tercamente anclado en δ=1/2".

**El límite crítico:** la ley da la **MAGNITUD** del impacto dado un signo conocido. **No predice dirección.** El signo es el *input*. Esto es exactamente lo que hace el CVD: te da el signo; la raíz cuadrada te da cuánto *debería* moverse. La divergencia entre ambos es samplable (ver shortlist F1).

### 1.2 Memoria larga del order flow — el candidato a feature más CVD-adyacente
El flujo firmado es un proceso de **memoria larga** (autocorrelación positiva de largo alcance del signo de los trades), porque las órdenes grandes se ejecutan en pedacitos durante horas/días.
- Bouchaud-Farmer-Lillo 2008 (arXiv:0809.0822 / SSRN 1266681), 3-0. Hurst H~0.65–0.9 en LSE/Euronext; sobrevivió tests explícitos de ruptura estructural. Reconfirmado hasta 2026 (arXiv:2606.16269 lo llama "establecido").
- **Es falsable y directamente samplable**: autocorrelación de signos / Hurst del flujo firmado. Misma estirpe que el CVD.
- *Caveat:* la escala de meses está documentada en acciones/FX institucional; aplicarla a perps cripto 24/7 es extrapolación que hay que **medir hacia adelante**.

### 1.3 La regla de oro para no engañarnos (Yee 2021, 3-0)
"El traspaso de física se justifica a nivel de transferencia matemática, pero no a nivel de transferencia mecanística." Lévy/power-laws y path integrals (como herramienta de cómputo) ganan su lugar con datos. Decir que el mercado *es* cuántico o *sufre* una transición de fase es decorativo. **Este es el filtro con el que juzgo todo lo de abajo.**

---

## 2. El cementerio cuántico — humo con bata de laboratorio

- **Quantum finance de Baaquie (QFT/path integrals para opciones)** — 3-0. Funciona *solo en la medida en que suelta su contenido cuántico*. La parte que sirve son path integrals de Feynman **como herramienta clásica de cómputo**. Arioli & Valente: Black-Scholes no usa números imaginarios; la superposición sale *de* los imaginarios; "el éxito numérico de Baaquie viene de efectos que no son cuánticos". **Tu Monte-Carlo de timelines YA es el contenido path-integral legítimo (clásico). Llamarlo "cuántico" no agrega nada.**
- **LPPL de Sornette (predicción de cracks log-periódica)** — 3-0 ×6 afirmaciones. Curve-fit de 7 parámetros con muchos mínimos locales; el mecanismo de "fenómeno crítico" aplica a ~la mitad de las burbujas; los parámetros caen en el rango "teórico" (puesto *post hoc*) en solo 7 de 11 cracks del Hang Seng; t_c es un proceso estocástico (O-U) → solo sacas un *rango* de fechas, no una predicción out-of-sample nítida. **Diagnóstico, no predicción.** No pasaría el DSR como feature.
- **Test de mercado "quantum-like" de Khrennikov** — 3-0. **Cero datos de mercado** (es un *diseño* de experimento que el propio autor admite irrealista). Y está amañado: cualquier λ≠0 cuenta como "cuántico", y si λ>1 (imposible para interferencia cuántica real cos-θ) el marco *salta a un "espacio de Hilbert hiperbólico"* para absorberlo. "Quantum-like, no quantum" se elige explícitamente para esquivar las restricciones de la mecánica cuántica real. **Infalsable por diseño.** Esta es LA idea seductora ("interferencia cuántica en el flujo retail") que hay que NO perseguir.
- **Quantum cognition / igualdad QQ** — 3-0. El único resultado cuántico-adyacente con dientes predictivos *de verdad*: una predicción **a priori y sin parámetros** (los efectos de orden en dos preguntas binarias suman cero), confirmada en 70 encuestas nacionales de EE.UU. **PERO** solo para **preguntas binarias de encuesta**; los modelos no-degenerados más ricos *fallan* el test (Grand Reciprocity: 65 de 72 experimentos fallan) y sobreviven solo volviéndose degenerados con parámetros libres. No es samplable en order flow. Fascinante; no es para el motor.

---

## 3. Lo que el filtro NO alcanzó a adjudicar (honesto)

7 temas quedaron sin las 3 verificaciones (solo había 25 cupos de verificación). **Ausencia ≠ evidencia en contra.** Lo que la fase de extracción (sin verificar a 3 votos) sugiere:

- **Random Matrix Theory / Marchenko-Pastur** — el research lo marca como *"probablemente el puente física→finanzas no examinado más fuerte"*. RIE (Bun-Bouchaud-Potters) es el estado del arte para limpiar matrices de correlación. **Real.** Pero limpia correlación de un *cross-section* de muchos activos — tú corres un motor direccional por símbolo. Útil solo si construyes un feature cross-asset (ver nota ETH).
- **Rough volatility (Hurst H~0.1)** — Gatheral-Jaisson-Rosenbaum. **Contestado**: Cont-Das 2022 (arXiv:2203.13820) dice que la "rugosidad" es un artefacto de estimación, no real. No apostaría.
- **Critical-slowing-down / early-warning (AR(1) sube antes del crack)** — un estudio (5 mercados, 4 cracks) encontró **sin tendencia** pre-crack → los cracks financieros **no** son transiciones críticas. Mata la versión ingenua.
- **TDA / homología persistente (Gidea-Katz)** — la L^p-norm de los landscapes crece antes de cracks, pero es índice/diario y **retrospectivo**.
- **Path signatures (Chevyrev-Kormilitzin)** — feature map universal no-paramétrico para series temporales. Mate real, se usa en ML. Riesgo: overfitting; necesita el gate con disciplina.
- **Termodinámica estocástica** — "Segunda Ley Financiera" (arXiv:2512.03123): un round-trip *es* un ciclo termodinámico; la convexidad del impacto ⇔ no-arbitraje de round-trip. Y la **irreversibilidad temporal vía grafo de visibilidad + divergencia KL** (arXiv:1601.01980): samplable por barra, sin parámetros libres — pero **retrospectiva** (detecta la inestabilidad *después*). Útil quizá como descriptor de régimen (ya usas KL para régimen), no como señal líder.

---

## 4. SHORTLIST — lo que más probable sobrevive el DSR (con experimento measure-first)

### F1 — Residual de impacto raíz-cuadrada (absorción vs fragilidad) ★ máxima convicción
- **Qué computar por barra (5m):** signo y tamaño del flujo R_t (ya lo tienes del CVD); impacto predicho I_pred = Y·σ·√(R/V); retorno real; **residual = real − I_pred**.
- **Hipótesis:** flujo que mueve el precio **menos** de lo que la raíz cuadrada predice = absorción (hay un muro del lado contrario) → reversión/trampa. Flujo que mueve **más** = libro frágil/thin → continuación.
- **Data:** gratis — aggTrades (los mismos del CVD) + klines.
- **Cómo se mide:** mismo gate que validó el CVD (DSR/CPCV/PBO) + cruce de ortogonalidad: ¿suma *dentro* de lo ya CVD-confirmado?

### F2 — Persistencia del flujo firmado (Hurst / autocorrelación de signos) ★ máxima convicción
- **Qué computar por barra:** Hurst o autocorrelación lag-1..N de la serie de signos de trades (o de los incrementos de CVD) en una ventana.
- **Hipótesis:** persistencia alta = se está trabajando una metaorden = el flujo **continúa** → ventaja de continuación cuando se alinea con la dirección del CVD. (Subir cadencia de calidad: solo dispara alta convicción cuando CVD + persistencia coinciden.)
- **Data:** gratis — aggTrades.
- **Cómo se mide:** DSR + ortogonalidad vs CVD; test "dentro de CVD-confirmado".

### F3 — Reloj de volumen/flujo en vez de wall-clock ("emergent time" hecho rigor) ★ alta
- Tu postulado de "tiempo emergente / horizonte deformable" tiene una versión **rigurosa y samplable** que NO es tiempo imaginario: **muestrear barras en tiempo-de-volumen o tiempo-de-flujo** (cubetas de volumen firmado constante) en lugar de reloj de pared. Es el debate event-time vs physical-time de la literatura de memoria larga (arXiv:2606.16269) y la familia de los volume clocks / VPIN (Easley-López de Prado).
- **Por qué te encaja:** un reloj de flujo se acelera en los estallidos donde vive la ventaja y se duerme en el grindeo institucional muerto que odias en BTC. Naturalmente prioriza ETH-densidad sobre BTC-lento.
- **Experimento:** re-muestrea el cube en tiempo-de-volumen; mide si las mismas reglas dan mejor expected-R / menor prob-stop que en tiempo de reloj.

---

## 5. Cómo conecta con tu tesis de ETH

- La raíz cuadrada y la memoria larga son **universales** → los *features* transfieren a ETH.
- Pero el coeficiente de impacto Y y la escala de memoria son **específicos del activo** → ETH tendrá su **propia calibración** (otra razón para cosechar su cube y medir, no asumir).
- Hipótesis encouraging y testable: un activo **más denso y más retail** como ETH debería mostrar firmas de **order-splitting más fuertes** (más metaórdenes trabajándose = más persistencia = más muestras de continuación de alta convicción). Justo lo que pediste: subir calidad *y* cantidad de alta convicción aunque baje la cadencia base.
- Tu incomodidad con BTC tiene base micro real: en el activo lento/institucional la ventaja direccional del flujo es más débil y el stop-hunting del MM domina. ETH como gallo es defendible *desde la microestructura*, no solo desde el gusto.

---

## 6. El ángulo "premio" (honesto, sin vendehumos)

Lo publicable/novel aquí **no es** nada "cuántico". Es la intersección donde ya vives: un motor direccional en **perpetuales cripto 2026**, donde la ley de raíz cuadrada y la memoria larga están **sub-testeadas** (la evidencia BTC es spot 2013-2015), validado con un gate serio (DSR/CPCV/PBO). Re-confirmar ambas en perps con tu gate, y publicar el residual de impacto + la persistencia como **ventajas direccionales validadas**, es una contribución real. Ese es el camino al reconocimiento — no el espacio de Hilbert hiperbólico.

---

## Qué propongo construir (mismo patrón que OI/metrics)

Dos validators nuevos sobre el harness que ya existe (cube + aggTrades, sweep de umbrales, DSR, ortogonalidad vs CVD):
- `tools/validate_impact_flow.py` → F1 (residual raíz-cuadrada)
- `tools/validate_persistence_flow.py` → F2 (Hurst/autocorrelación de signos)

Backtest gratis sobre el sample que ya tienes. Lo que pase el DSR y sume *ortogonal* al CVD, se cabla a capa 3 → motor 1 igual que el CVD. Lo que no, al cementerio, honesto.
