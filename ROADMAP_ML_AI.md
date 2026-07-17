# Roadmap ML/AI Engineer — 6 meses, orientado a ingresos altos

> Para: RasDG. Contexto: trader de futuros/crypto con sistema propio (FQ) en
> producción. Objetivo: rol ML/AI aplicado a finanzas/quant, remoto, USD
> $150k+ o equivalente alto. Sin título formal de CS.
>
> Fecha de arranque: julio 2026. Horizonte: enero 2027.

---

## 0. El diagnóstico honesto (leer primero)

Tu situación real es **mejor** de lo que tu propio resumen sugiere. Este repo
ya contiene cosas que la mayoría de los candidatos a "ML Engineer junior" no
tienen y que los entrevistadores quant valoran muchísimo:

- **Walk-forward purgado con predicciones out-of-fold** (`bt_walkforward.py`,
  `bt_train.py`): validación honesta sin fuga temporal. Esto es exactamente lo
  que enseña López de Prado y lo que un hedge fund pregunta en entrevista.
- **LightGBM en pipeline real** con AUC OOS y expectancy filtrada por umbral.
- **Pipeline de Numerai** (`tools/numerai_crypto_pipeline.py`): track record
  verificable por terceros.
- **Sistema live con pagos y suscriptores**: ingeniería de producción real
  (procesos, SQLite, reconciliación, backups, ~130 tests).
- **Deflated Sharpe, régimen por entropía/visibility graphs, ablations**:
  vocabulario de research quant que suena a nivel senior.

Lo que te falta no es "aprender ML desde cero". Te faltan cuatro cosas
concretas, y el plan entero se organiza alrededor de ellas:

1. **Fundamentos formales verificables** (poder explicar *por qué* funciona
   lo que ya usás: bias-variance, regularización, métricas, deep learning
   básico) — para pasar entrevistas técnicas.
2. **Credenciales** que compensen la falta de título (certs cloud + MLOps).
3. **Portafolio público** — hoy tu mejor trabajo está en un repo privado y
   mezclado con un negocio. Hay que extraer versiones públicas y limpias.
4. **Visibilidad y proceso de búsqueda en inglés** (LinkedIn, GitHub,
   aplicaciones dirigidas, señales verificables como Numerai/Kaggle).

**Expectativa realista de plata:** $150k–$250k es rango de *senior* en
US/remote-first. Entrando sin título y sin experiencia laboral formal en ML,
el primer rol probable es $60k–$120k (remoto LATAM para empresa US, fintech,
o prop shop) — y desde ahí el salto a seis dígitos altos toma 1–2 años, no
meses. Los atajos reales para acortar eso: (a) rol híbrido quant donde tu
dominio pesa más que el título, (b) contracting/freelance especializado
(quant tooling, backtesting infra) que paga por valor, (c) que tu propio
sistema genere ingresos mientras tanto. El plan apunta a los tres.

---

## 1. Estructura general: 3 fases de 2 meses

| Fase | Meses | Foco | Entregable que mueve la aguja |
|---|---|---|---|
| 1. Fundamentos + primera cert | Jul–Sep 2026 | ML formal, math mínima, AWS MLE-A | Cert AWS + 1 proyecto público estrella |
| 2. Especialización + MLOps | Sep–Nov 2026 | Deep learning, MLOps, Google PMLE | Cert Google + 2º proyecto + track record Numerai |
| 3. Mercado | Nov 2026–Ene 2027 | Aplicaciones, entrevistas, red | 50+ aplicaciones dirigidas, entrevistas activas |

Dedicación asumida: 20–25 h/semana (compatible con seguir tradeando).
Si podés meter 35–40 h/semana, comprimí cada fase ~3 semanas.

---

## 2. Fase 1 (semanas 1–8): fundamentos + AWS MLE Associate

### Por qué este orden
AWS ML Engineer Associate primero porque: es la cert con mejor ratio
esfuerzo/señal para empleadores, cubre el ciclo completo (data → training →
deploy → monitoring), y te obliga a aprender SageMaker/MLOps básico que el
90% de los "self-taught" no tiene. Google PMLE es más respetada pero más
difícil; va segunda, cuando ya tengas base.

### Semana a semana

**Semanas 1–4 — Fundamentos de ML (en paralelo con lo de abajo):**
- Curso ancla: **Machine Learning Specialization de Andrew Ng** (Coursera,
  3 cursos). Vos ya usás LightGBM; el objetivo acá es poder *explicar*
  overfitting, regularización, gradient descent, métricas, en entrevista.
  A tu nivel se hace en 3–4 semanas, no los 3 meses nominales.
- Complemento quant: **"Advances in Financial Machine Learning" (López de
  Prado)** — capítulos de labeling (triple barrier), purged CV, sample
  weights, feature importance. Vas a reconocer la mitad porque ya lo
  implementaste; ahora ponele los nombres canónicos. Esto es oro en
  entrevistas de quant/fintech.
- Math mínima viable: no hagas un curso entero de álgebra lineal. Usá
  3Blue1Brown (Essence of Linear Algebra + Neural Networks) y StatQuest para
  los huecos puntuales. Tu tiempo vale más en proyectos.

**Semanas 3–8 — AWS Certified Machine Learning Engineer – Associate (MLA-C01):**
- Curso: Stephane Maarek o Adrian Cantrill (Udemy) + práctica en free tier.
- Practice exams: Tutorials Dojo (Jon Bonso). Cuando saques >80% consistente,
  agendá el examen. Precio ~$150.
- **Agendá el examen para la semana 8 desde el día 1.** Deadline pago =
  estudio real.

**Semanas 1–8 — Proyecto estrella #1 (en paralelo, es lo más importante):**

> **`solana-regime-lab`** (nombre tentativo): repo público que extrae y
> generaliza tu detector de régimen. Visibility graphs + entropía +
> irreversibilidad temporal como features de régimen, comparado contra
> baselines (HMM, volatilidad realizada, reglas simples), evaluado con
> walk-forward purgado y deflated Sharpe sobre datos públicos (Binance
> Vision, que ya sabés bajar — `tools/fetch_binance_vision_*.py`).

Reglas del proyecto público (aplican a todos):
- **No publiques tu edge.** Publicás la *infraestructura y la metodología*
  (que es lo que te contrata), no los parámetros/gates que te hacen ganar
  plata. Datos públicos, features descritas en papers, señal de juguete.
- README de calidad paper-lite: motivación, metodología, resultados con
  intervalos, limitaciones. Un gráfico de equity OOS con y sin filtro de
  régimen vale más que mil líneas de código.
- Tests + CI (GitHub Actions) + type hints + `pyproject.toml`. Señal de
  ingeniería profesional, te diferencia del 95% de repos de "ML trading".
- Un notebook demo ejecutable end-to-end en Colab.

### Checklist de salida de Fase 1
- [ ] Cert AWS MLE-A aprobada
- [ ] Andrew Ng ML Specialization terminada
- [ ] `solana-regime-lab` público con README, tests, CI y notebook
- [ ] LinkedIn en inglés reescrito: "ML Engineer | Quantitative Trading
      Systems" con el proyecto pineado (ver §5)

---

## 3. Fase 2 (semanas 9–16): deep learning + MLOps + Google PMLE

**Semanas 9–12 — Deep learning práctico:**
- **PyTorch**, no TensorFlow (el mercado ya decidió). Curso: "Zero to
  Mastery PyTorch" (Daniel Bourke, gratis) o fast.ai Part 1.
- Objetivo mínimo: entrenar y explicar un MLP, una red convolucional y un
  transformer chico. Para tu nicho: secuencias (attention sobre series
  temporales) es lo que importa; visión no.
- **MLOps**: Machine Learning Engineering for Production (MLOps)
  Specialization de Andrew Ng (Coursera) — podés hacer solo los cursos 1 y
  4 si vas corto de tiempo. Complemento práctico: MLflow para tracking de
  experimentos, que además podés adoptar en FQ (tus corridas de
  `bt_optimize`/`bt_ablation` son experimentos perfectos para trackear).

**Semanas 11–16 — Google Professional ML Engineer:**
- Es la cert de más prestigio del rubro. Path oficial de Google Cloud Skills
  Boost + practice exams. Precio $200.
- Mismo truco: agendá el examen con fecha fija (semana 16).

**Semanas 9–16 — Proyecto estrella #2 (elegí UNO, no dos):**

Opción A — **`fib-features-ml`**: ¿las extensiones/retracements de Fibonacci
y la simetría de ondas tienen poder predictivo medible? Feature engineering
de tu framework (distancia a niveles fib, confluencia, simetría de piernas,
CHoCH) → LightGBM/transformer → feature importance con MDA/SHAP → test
honesto OOS contra baseline sin esas features. Gancho enorme: une tu
identidad de trader con rigor ML, y da para un artículo/post viral.
*(Recomendado: es tu diferenciador más único.)*

Opción B — **RL para ejecución**: agente de reinforcement learning
(PPO/DQN con stable-baselines3) para decidir entrada escalonada/trailing
sobre señales ya generadas, en un gym env construido sobre tu motor de
backtest. Más sexy en papers, más difícil de hacer bien en 6 semanas, y los
entrevistadores serios saben que el RL en trading retail suele ser humo —
solo elegila si el env y la evaluación son impecables.

**Todo Fase 2 — Track record externo (bajo esfuerzo, alta señal):**
- **Numerai**: ya tenés el pipeline (`tools/numerai_crypto_pipeline.py`).
  Enviá predicciones TODAS las semanas. Seis meses de submissions con
  correlación positiva = credencial verificable por terceros que ningún
  título reemplaza. Costo marginal: ~1 h/semana.
- Opcional: una competencia de Kaggle de series temporales/finanzas si
  aparece una buena. No fuerces; Numerai es más específico a tu nicho.

### Checklist de salida de Fase 2
- [ ] Cert Google PMLE aprobada
- [ ] PyTorch: 2–3 modelos entrenados y explicables
- [ ] Proyecto #2 público con la misma calidad que el #1
- [ ] 8+ semanas de submissions en Numerai
- [ ] MLflow (u otro tracker) integrado en tu workflow de research

---

## 4. Fase 3 (semanas 17–24): salir al mercado

### Qué roles atacar (en orden de fit)

1. **ML Engineer / Quant Developer en fintech y crypto** (exchanges,
   market-makers, plataformas de trading, data providers tipo Kaiko/Amberdata,
   protocolos DeFi con equipos quant). Tu dominio pesa al máximo acá y son
   los más abiertos a perfiles sin título.
2. **Quant Researcher junior / Trading Systems Engineer en prop shops**
   remotos o crypto-native. Menos vacantes, mejor pago, tu framework y
   Numerai son la puerta.
3. **ML Engineer generalista remoto** (US/EU contratando LATAM vía Deel/
   Remote). Más volumen de vacantes; tu portafolio financiero igual
   destaca. Rango típico LATAM-remote: $60k–$130k.
4. **Contracting/freelance quant** (Toptal, contactos directos, Twitter/X
   quant): backtesting infra, pipelines de datos, dashboards. Facturable
   desde el mes 1 de la Fase 3 a $50–$100+/h si el portafolio respalda.

### Proceso (semanas 17–24)
- **Volumen con puntería**: 10–15 aplicaciones/semana, cada una con 2–3
  líneas personalizadas que conecten tu proyecto con su stack. 50%
  fintech/crypto, 30% ML generalista, 20% tiros largos (prop shops, funds).
- **Canales**: LinkedIn + Wellfound + Web3 job boards (crypto.jobs,
  cryptocurrencyjobs.co) + HN "Who is hiring" (1º de cada mes) + referidos
  (ver visibilidad, §5). Los referidos convierten 5–10x más que aplicar
  frío: pedilos.
- **Prep de entrevistas** (paralelo, 5 h/semana):
  - ML conceptual: poder explicar todo lo de tus repos + López de Prado.
  - Coding: LeetCode easy/medium en Python, ~50 problemas. No hace falta
    grind de 300; para roles ML piden menos que para SWE puro.
  - System design ML básico: "Designing Machine Learning Systems" (Chip
    Huyen) — leelo en Fase 2 o 3.
  - Tu historia: 90 segundos que conecten trading live → sistema en
    producción → ML formal. Ensayala en inglés hasta que salga sola.
- **Inglés**: si tu inglés hablado no está a nivel entrevista técnica, esto
  es el bloqueador #1 para los rangos altos. Meté 3–4 mock interviews
  (Pramp, interviewing.io o un tutor) desde la semana 17.

---

## 5. Visibilidad (transversal, 2 h/semana desde la Fase 1)

Sin título, tu descubribilidad ES el currículum:

- **GitHub como escaparate**: perfil README, los 2 proyectos pineados,
  commits regulares. Los recruiters técnicos miran esto antes que el CV.
- **Escribí 1 post técnico por mes** (Medium/Substack/dev.to, en inglés):
  "Purged walk-forward validation for crypto signals", "Do Fibonacci levels
  carry predictive information? An honest ML test", "Regime detection with
  visibility graphs". Cada post enlaza al repo. Un solo post que pegue en
  HN/r/quant/QuantTwitter genera más leads que 100 aplicaciones frías.
- **Twitter/X quant + LinkedIn**: compartí resultados y gráficos de los
  proyectos públicos. La comunidad quant de X es chica y los que contratan
  están ahí.
- **CV de 1 página** orientado a resultados: "Built purged walk-forward ML
  pipeline (LightGBM, OOF AUC 0.XX) for live crypto signal system with
  paying subscribers" dice más que cualquier título.

---

## 6. Presupuesto y herramientas

| Ítem | Costo aprox. |
|---|---|
| AWS MLE-A examen | $150 |
| Google PMLE examen | $200 |
| Coursera (2–3 meses de suscripción) | $120–180 |
| Udemy cursos + practice exams | $50–80 |
| Compute (Colab Pro o GPU spot para Fase 2) | $30–100 |
| Mock interviews / tutor de inglés (opcional) | $100–300 |
| **Total** | **~$650–1.000** |

Stack a dominar (en orden): Python avanzado (ya ✔), pandas/numpy (ya ✔),
scikit-learn, LightGBM/XGBoost (ya ✔ parcial), PyTorch, MLflow, Docker
básico, GitHub Actions (CI), SageMaker (por la cert), FastAPI (servir un
modelo), SQL sólido.

---

## 7. Riesgos y cómo mitigarlos

- **Dispersión**: el plan tiene exactamente 2 certs, 2 proyectos, 1 track
  record externo. Todo lo demás es "no". Cada cosa nueva que quieras sumar
  tiene que reemplazar algo, no agregarse.
- **Perfeccionismo en proyectos**: 6–8 semanas por proyecto, timeboxed. Un
  repo terminado y publicado vale infinitamente más que dos a medias.
- **Publicar el edge por accidente**: revisá cada repo público con la regla
  "¿esto le sirve a alguien para replicar mis señales?" antes de pushear.
- **El mercado tarda**: 2–4 meses de proceso de búsqueda es normal. El
  contracting (rol 4 de §4) es el puente de ingresos mientras tanto.
- **Entrevistas de coding como filtro sorpresa**: no subestimes LeetCode;
  es el motivo #1 por el que perfiles no-tradicionales fuertes quedan
  afuera. 50 problemas bien hechos alcanzan para la mayoría de roles ML.

---

## 8. Resumen ejecutivo (si solo leés una sección)

1. Ya tenés el activo más difícil: sistema quant real en producción con
   validación honesta. El plan es empaquetarlo, credencializarlo y venderlo.
2. **Jul–Sep**: Andrew Ng ML + cert AWS MLE-A + repo público
   `solana-regime-lab` extraído de tu detector de régimen.
3. **Sep–Nov**: PyTorch + MLOps + cert Google PMLE + proyecto
   `fib-features-ml` (tu framework de Fibonacci bajo test ML honesto) +
   Numerai todas las semanas.
4. **Nov–Ene**: 10–15 aplicaciones/semana a fintech/crypto/quant remoto,
   1 post técnico/mes, mock interviews en inglés, contracting como puente.
5. Meta realista: primer rol $60k–$120k remoto en 6–9 meses; $150k+ en
   1–2 años apalancando el nicho quant. Camino paralelo: contracting
   especializado y tu propio sistema como fuentes de ingreso inmediatas.
