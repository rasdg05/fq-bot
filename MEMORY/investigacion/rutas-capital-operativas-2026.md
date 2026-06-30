# Rutas de capital — planes operativos (decisión RasDG, 2026-06-30)

> RasDG dio luz verde a **arriesgar capital** por las rutas que SÍ fondean, y bajó la prioridad de la
> académica ("no regalar el algoritmo a académicos que no fondean"). Esto son los **planes operativos**
> de las 3 rutas de capital con mejor fit, cada una con su **capital-en-riesgo** explícito y su caveat
> honesto. Principio: **el track FORWARD es el activo** — las tres lo construyen, ninguna lo regala.

---

## §1 — Numerai Crypto — ⭐ GO (RasDG acepta arriesgar capital)

**Fit:** el más nativo — el bot produce *exactamente* un ranking por token (0–1). Pipeline ya listo:
`tools/numerai_crypto_pipeline.py` (formato confirmado: `symbol,signal`, 0–1, ≥100 símbolos).

**Plan (aun arriesgando, se mide 2-4 semanas antes de stakear fuerte — no es cobardía, es sizing):**
1. Crear cuenta en numer.ai/crypto; descargar `live_universe.parquet` (~300 tokens, dinámico).
2. Correr el pipeline a diario y **subir SIN stake 2-4 semanas** para medir tu **CORR/MMC live**. Esto NO
   paga (es paper) — pero mide si el edge transfiere al *target de Numerai* (su retorno ≠ nuestro R).
3. **Stakear NMR cuando el CORR live sea positivo** — empezar chico, escalar con la señal. Un score
   negativo **quema** el stake; el pago es en NMR (cripto volátil).

**Capital en riesgo:** el stake NMR (tu decisión de tamaño). **Por qué primero:** stakear sobre un edge
no-medido-en-su-target es arriesgar a ciegas; 3 semanas de CORR live convierten ciego en informado.

---

## §2 — Breakout (prop firm, perps cripto) — estrategia para PASAR el challenge

**Por qué es el mejor fit del bot tal-cual:** opera **perpetuos cripto reales con liquidez de Kraken**
(el hábitat nativo del motor) y la compró Kraken (confianza alta, verificado). Costo de entrada bajo.

**Reglas 1-Step (CONFIRMAR en checkout — fuente secundaria, el sitio da 403):** objetivo **+10%**,
**drawdown máx 6% estático** (piso fijo en 94% del balance inicial), **pérdida diaria máx 4%**, **sin
límite de tiempo**, split **80%**, leverage 5x BTC/ETH · 2x alts, fee ~$55 (5K) … ~$800 (100K), no
reembolsable.

**El problema central (y por qué la mayoría truena):** el edge del motor es **real pero chico por trade
y de WR BAJO** (BTC +0.24R / WR ~29%, SOL +0.165R / WR ~26% — perfil momentum: pocos ganadores grandes).
Un WR bajo implica **rachas perdedoras largas** → el límite de **6% estático es la restricción que
manda**. El sizing lo es TODO.

**La estrategia (disciplina sobre cadencia):**
- **Riesgo por trade: 0.3–0.5% del balance** (usar 0.4%). A 0.4%, romper el 6% exige **15 pérdidas-R
  seguidas** (P≈0.72¹⁵≈0.7%): sobrevives una racha P99. A 1% reventarías con 6 seguidas — NO.
- **Stop diario auto-impuesto en 2%** (la mitad del 4% legal): si caes 2% en el día, apagas. Nunca te
  acercas al límite que te descalifica.
- **Solo señales de máxima convicción apiladas:** CVD✓ **&** KL-bajo **&** POC-lejos, en **BTC/ETH**
  (donde los edges son más fuertes y el leverage 5x ayuda). Filtrar duro reduce trades pero sube el R/trade.
- **El "sin límite de tiempo" es tu mayor ventaja:** la paciencia es gratis. El 10% se muele despacio
  (decenas–cientos de trades a size chico); **no fuerces** para llegar rápido — forzar revienta el DD.
- **Venue:** la señal se computa de order-flow de **Binance**, la ejecución es en **Kraken** (perps). La
  **dirección transfiere** (mismo activo, arb-linked, como el híbrido TradFi); confirmar fills/slippage.

**Capital en riesgo:** solo el **fee del challenge**. **Plan:** comprar el **más chico ($5K, ~$55)** como
**test en vivo barato** de si el edge sobrevive a la ejecución real (fees+slippage Kraken). Si pasa,
escalar.

**🚩 Honestidad:** ~7% de traders de prop firms cobran; el fee es costo hundido; el edge es real pero
chico + WR bajo + path-dependency del DD = **chance real de truncar el challenge AUNQUE el edge sea
bueno**. Es +EV solo si (a) el edge aguanta forward y (b) el sizing respeta el 6%. No es dinero fácil.

---

## §3 — Darwinex Zero — cómo funciona + el plan (con el caveat grande)

**El modelo (3 pasos):**
1. **Operas en la infra de Darwinex** (su brokerage, vía MT4/MT5 o su API) — **NO** conectas tu Binance
   por API; el track de tu exchange externo **no cuenta**, tiene que generarse EN su plataforma.
2. Tu estrategia se envuelve en un **DARWIN**: un producto invertible donde Darwinex **normaliza tu
   riesgo** (VaR objetivo ~6.5%/mes) para que inversores puedan comparar y asignar.
3. Vía **DarwinIA** (su programa de asignación) recibes **capital REAL** sobre tu DARWIN.

**Los tiers (verificados):**
- **SILVER:** sin mínimo de historia, **rating ≥75** → asignación **30k–375k EUR** (ventana 3 meses).
- **GOLD:** **>8 meses de signal history** + hito de performance (p.ej. retorno 1-año >20%, Return/DD
  >2.5) → **50k–500k EUR** (6 meses).
- **Cobras:** ~**15% de los profits** que tu DARWIN genere (high-water mark), incluida la asignación de
  DarwinIA.

**El reloj:** GOLD pide 8 meses → **arrancar YA** para cosechar después. SILVER puede entrar antes (solo
rating ≥75).

**🚩 EL CAVEAT — VERIFICADO (2026-06-30): Darwinex Zero cripto = CFD, NO perps. Mal fit para el bot tal-cual.**
Confirmado (darwinexzero.com/assets + blog.darwinexzero.com/crypto-cfd-account): la cripto de Darwinex Zero
es **CFD en MetaTrader 5** (BTC/ETH/SOL/BNB/XRP/ADA/DOGE), **NO** perpetuos. Tres golpes al edge del bot:
1. **Sin order-flow:** un CFD no tiene el libro taker-buy/sell de Binance → el **CVD/F2 NO transfiere**
   (el desacople data/venue, confirmado). Solo sobrevivirían KL + precio + ICT — una versión mutilada.
2. **Lunes-Viernes, NO 24/7:** los CFD cierran fin de semana → rompe el supuesto 24/7 con el que se midió
   el edge (gaps de finde no medidos).
3. **Leverage 1:1** en la cuenta cripto CFD → no puedes dimensionar un edge chico (vs. 5x de Breakout).
→ **Veredicto: Darwinex cripto NO vale el reloj de 8 meses para este bot.** El order-flow (su edge más
fuerte) muere ahí, es M-V no 24/7, y 1:1 mata la eficiencia de capital de un edge pequeño.

**La alternativa REAL (si algún día se usa Darwinex):** su fuerte son los **futuros CME/Eurex** (oro,
NASDAQ, índices, metales) — justo donde el bot tiene edges TradFi (**KL/ICT/precio**) que **estamos
cosechando AHORA** (XAU/NQ/ES/WTI/plata). Esa pata SÍ podría encajar — **pero pendiente de que los edges
TradFi pasen el gate** (la cosecha sigue, POC-distance aún under-powered). → **Darwinex deprioritizado;
revisitar vía FUTUROS (no cripto CFD) solo si el gate TradFi pasa. NO arrancar el reloj en un venue
mutilado.**

**Fricción:** integrar la ejecución del bot con Darwinex (MT4/5 o API) es **más trabajo** que Breakout
(que opera perps directo). Darwinex da asignación tipo-institucional y un gate claro, a cambio de su
venue + las 8 semanas... meses de reloj.

**Capital en riesgo:** prácticamente none de entrada (no compras challenge); el costo es **tiempo** (8
meses) + el setup de integración. El riesgo es montar todo y que el edge no transfiera a su venue.

---

## §4 — La ruta académica (Ruta B) — la decisión de RasDG, registrada

**Pregunta de RasDG:** ¿publicar en Quantitative Finance **sin dar la salsa secreta** y mantener el mérito?
**Respuesta honesta:**
- **SÍ se puede** publicar la **metodología** (el gate DSR/CPCV/PBO sobre cripto-perps; las *familias* de
  edge como "irreversibilidad KL como condicionador de régimen") **sin** revelar los parámetros exactos,
  el stack de convicción (P_master), el feature-engineering fino ni la lógica de ejecución. Los papers
  rutinariamente omiten "detalles propietarios de implementación". El mérito (autoría, DOI, cita) es tuyo.
- **PERO tu instinto es correcto:** sin **resultados FORWARD**, un paper que afirma edge es **otro
  backtest** — poco creíble y poco valioso. Lo que casi nadie tiene (y te haría creíble) es justo el
  **ledger forward real** con validación honesta. El paper **vale la pena CUANDO exista el forward.**

**Decisión:** **academia DEPRIORIZADA** hasta tener track forward; **nunca** se regala el algoritmo; si se
publica algún día, va **método + resultados forward**, salsa adentro. **El capital primero** (Numerai +
Breakout). SSRN/Quant Finance quedan como *opción de prestigio para después*, no como la apuesta.

---

## Prioridad de capital (lo que mueve la aguja para el objetivo de RasDG: fondear)

| # | Ruta | Fit del bot | Capital en riesgo | Fricción | Acción |
|---|---|---|---|---|---|
| 1 | **Numerai Crypto** | nativo (ranking de tokens) | stake NMR (su decisión) | baja (pipeline ✓) | medir 3 sem sin-stake → stakear |
| 2 | **Breakout** | nativo (perps, Kraken) | fee ~$55 | baja | challenge $5K como test en vivo |
| 3 | **Darwinex Zero** | ✗ cripto = CFD (M-V, 1:1, sin order-flow) | tiempo (8 meses) | alta | **deprioritizado** (verificado); revisitar vía FUTUROS CME si pasa el gate TradFi |
| — | Academia (SSRN/QF) | publicar método sin salsa | none | baja | **parqueada hasta forward** |

_Fuente: `premios-competencias-2026.md` (deep-research verificado 2026-06-30), `tools/numerai_crypto_pipeline.py`,
`research/fisica_moderna_2026_resultados.md` (WR/R del motor), `MEMORY/CEMENTERIO.md` (edges y desacople
data/venue). Reglas de Breakout = secundarias (sitio 403), CONFIRMAR en checkout. Decisión RasDG 2026-06-30._
