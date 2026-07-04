# Adaptar el motor a ORO (XAU) y NASDAQ (NQ) — síntesis measure-first

> Deep-research adversarial (108 agentes, 20 claims sobrevivieron el voto 3-0/2-1 contra
> fuentes primarias). El paso de síntesis del harness murió por límite de sesión; esto es
> la síntesis hecha a mano sobre los claims verificados. **No re-deriva lo ya medido** —
> traduce a decisión: qué cablear, qué extrapolar, qué es quant-envy.
>
> Regla de oro intacta: nada opera sin pasar DSR>0.95 + CPCV + PBO. Esto sólo dice **qué
> vale la pena meter al cubo**, no qué ya pasó el gate.

---

## TL;DR — shortlist priorizado (mayor→menor probabilidad de sobrevivir el gate)

| # | Módulo | Por qué | Riesgo |
|---|--------|---------|--------|
| **1** | **Order-flow CVD/OFI nativo de CME** (multi-nivel) en MNQ+MGC | Era tu mejor edge en cripto; el único bloqueo era "el CVD es propiedad del libro del venue". **Falso para CME**: el libro consolidado ES obtenible (Databento MBO + tag 5797 aggressor). Literatura: OFI multi-nivel explica el price-impact en equities. | Bajo-medio |
| **2** | **Lead-lag ES↔NQ con OFI REZAGADO** | Evidencia directa: el OFI cross-asset *rezagado* mejora el forecast de retornos futuros (causal, samplable). | Medio |
| **3** | **KL-irreversibilidad como GATE de régimen** (no señal) en NQ/XAU | Validado en índices como señal de inestabilidad/régimen. Espeja lo que ya mides en cripto → cablearlo es casi mecánico. | Bajo (confirmatorio) |

**Quant-envy — NO malgastes cubo (marcado abajo):** KL como predictor *direccional*, POC-distance (ya falló PBO 0.76), OFI cross-asset *contemporáneo* (mismo bar), y los overlays macro-narrativa (DXY/tasas/COT/VIX-term/GEX) sin evidencia causal en esta pasada.

---

## (1) Infraestructura — qué feed, qué venue, cuánto

### Feeds de datos (decisión por caso de uso)

| Feed | Cubre | Granularidad | Costo | Veredicto |
|------|-------|--------------|-------|-----------|
| **Databento GLBX.MDP3** | Todo CME/CBOT/NYMEX/COMEX (NQ/MNQ **y** GC/MGC), desde 2010, 650k+ símbolos | **MBO/L3 (libro completo por orden)**, MBP-10, tick trades, **aggressor side nativo** | pay-as-you-go **$0.50/GB** (CME), **$125 crédito gratis** | **EL feed** para order-flow. Es el único que carga el libro firmado. |
| **Dukascopy Historical Export** | Forex, **Commodities (oro)**, **Índices** | tick bid/ask (retail FX/CFD, no libro CME) | **GRATIS** | Deep-history barata para price/estructura/KL/overlays. NO da order-flow de CME. |
| **FirstRate Data** | NQ desde 2-ene-2008 (18+ años), contratos + continuos | **sólo barras 1-min→1-día** (sin tick/footprint) | $ barato | OHLCV profundo para NQ. Confirma empíricamente: sin libro → sin CVD. |
| **Polygon/Massive** | CME/COMEX (oro + e-mini) | tick/agg | historia **plan-gated**: Developer=5y, Advanced=todo | Alternativa; para 5y hace falta Developer+. |

**Regla de feed:** order-flow → **Databento** (el único paid que vale, porque es el único con el libro firmado). Todo lo demás (KL, estructura, macro) → **Dukascopy gratis** o FirstRate/Polygon.

### Venues / contract specs (ejecución en micros = footprint de capital barato)

- **Oro:** **MGC** (Micro Gold) = **10 oz troy** (1/10 del GC de 100 oz). Incremento base de sizing.
- **NASDAQ:** **MNQ** (Micro E-mini NDX-100) = **$2 × índice**; tick **0.25 pts = $0.50/tick**. Input directo al modelado de costos/edge-neto.
- Sesión ~23h con gaps (vs cripto 24/7): las killzones ICT hay que re-anclar al reloj CME (RTH/ETH), no copiar las de cripto. *(No salió claim primario en esta pasada — pendiente de medir.)*

---

## (2) Qué de lo EXISTENTE transfiere (contrastado con literatura)

### Order-flow CVD → **SÍ transfiere, RECOMPUTÁNDOLO del feed de CME** (matiz clave)
Tu prior era "CVD NO transfiere (propiedad del libro del venue)". La investigación lo **refina, no lo tumba**:
- En cripto el CVD es del libro *fragmentado* de cada exchange → no generaliza.
- En **CME hay UN libro centralizado** y **es obtenible**: Databento MBO/L3 + **Tag 5797-AggressorSide** (0=none, 1=buy, 2=sell) firma cada trade en la fuente; el Trade Summary da la orden agresora + `Tag 346-NumberOfOrders` → **footprint/CVD reconstruible del propio feed del exchange**.
- Respaldo académico (arXiv 2112.13213): **OFI** (order-flow imbalance, el análogo LOB del CVD) **explica el price-impact en equities**, y el **OFI multi-nivel** (integrando los primeros niveles del libro) explica mejor que sólo el nivel-1.
- **Traducción:** no portas el CVD de cripto — lo **recomputas** de CME, y lo construyes **multi-nivel**.

### KL-irreversibilidad → **SÍ, pero como GATE de régimen, NO como edge direccional**
- Validado (PMC12026002): DHVG + divergencia KL forward/backward sobre **series de retorno de índices** = señal de inestabilidad/régimen. Confirma tu medición interna (KL + estructura base transfieren).
- **Caveat crítico (el mismo paper):** el método es **coincidente/descriptivo, no forecasting** — la señal sólo se mueve *cuando* llega el valor anómalo. Úsalo como filtro de régimen/veto (como en cripto), jamás como entrada.

### POC-distance → sigue MUERTO en TradFi
Ya lo mediste (PBO 0.76). Nada en la investigación lo resucita. No lo reintentes.

---

## (3) Módulos NUEVOS TradFi-nativos (con evidencia causal)

### 3.1 — OFI multi-nivel propio (MNQ, MGC) — **el módulo estrella**
- **Hipótesis:** el order-flow firmado del libro CME predice/confirma dirección igual que el CVD en cripto.
- **Qué computar por barra:** OFI integrado sobre los top-N niveles del MBP-10 (Δ de tamaño en bid vs ask por nivel, firmado), + CVD acumulado del aggressor tag 5797.
- **Datos:** Databento MDP3 (MNQ, MGC), 5y.
- **Experimento:** feature causal por barra → mismo gate DSR/CPCV/PBO. Construir **multi-nivel** (no top-of-book) por la evidencia de arXiv.

### 3.2 — Lead-lag ES↔NQ con OFI **rezagado**
- **Hipótesis:** el OFI pasado de ES carga info predictiva del retorno futuro de NQ.
- **Evidencia:** arXiv 2112.13213 — el **OFI cross-asset REZAGADO mejora el forecast de retornos futuros**; el **contemporáneo (mismo bar) NO añade nada** sobre el modelo propio multi-nivel.
- **Qué computar:** `OFI(ES, t−k)` como feature para `ret(NQ, t)`, varios k.
- **Datos:** Databento (ES + NQ). **Experimento:** gate. ⚠️ Debe ser **rezagado** — el mismo-bar es redundante (ver quant-envy).

### 3.3 — KL-régimen como capa de veto (NQ/XAU)
- **Hipótesis:** el filtro de régimen que ya usas mejora el neto también en índices/oro.
- **Qué computar:** DHVG-KL sobre retornos, ventana deslizante → flag de régimen (no dirección).
- **Datos:** Dukascopy gratis (cierre de barras). **Experimento:** como capa (veto/size), medir Δ del expectancy con vs sin.

---

## Quant-envy / NO sobrevivirá (marcado explícito)

- **KL como predictor DIRECCIONAL** — el paper es explícito: coincidente, no forecasting. Falla un gate direccional. (Sólo régimen.)
- **POC-distance** — ya falló (PBO 0.76).
- **OFI cross-asset CONTEMPORÁNEO** (mismo-bar ES→NQ) — la evidencia dice que no añade poder explicativo. No construyas la versión mismo-bar.
- **Overlays macro-narrativa** (DXY, tasas reales/TIPS, COT/CFTC, flujos de bancos centrales, VIX term-structure, GEX/dealer gamma) — **sin evidencia causal verificada en esta pasada**. Fascinantes, pero: (a) baja frecuencia (COT semanal, posicionamiento diario) que **no samplea limpio** a tu cadencia de 5m/15m — ahí muere el quant-envy; (b) son narrativa, no microestructura. Si acaso, entran como features lentos de contexto, no como edges. Medir con escepticismo, al final de la cola.

---

## Cómo cablear (orden operativo sugerido)

1. **$125 de crédito gratis de Databento** → jalar MNQ + MGC (+ ES para lead-lag) MDP3, 5y.
2. Construir el **loader de OFI multi-nivel + CVD por aggressor tag** (espeja tu pipeline de CVD cripto).
3. Correr **3.1 (OFI propio)** por el gate primero — es el que más se parece a tu edge probado.
4. Si pasa: **3.2 (lead-lag rezagado)**. En paralelo, **3.3 (KL-régimen)** como capa.
5. Ejecutar forward en **micros (MGC/MNQ)** — capital mínimo, mismo camino CVD: gate ✓ → dormido → forward → producto.

---

### Fuentes verificadas (voto adversarial 3-0 salvo nota)
- Databento GLBX.MDP3 (MBO/L3, aggressor): databento.com/datasets/GLBX.MDP3 · databento.com/futures
- CME MDP 3.0 Tag 5797 AggressorSide / Trade Summary order-level: cmegroupclientsite.atlassian.net (EPICSANDBOX/457225774)
- OFI multi-nivel + cross-asset lagged: arXiv 2112.13213
- KL-irreversibilidad en índices (DHVG-KLD): pmc.ncbi.nlm.nih.gov/articles/PMC12026002
- Dukascopy histórico gratis (FX/Commodities/Índices): dukascopy.com/swiss/english/marketwatch/historical
- FirstRate NQ (2008→, sólo OHLCV, 2-1): firstratedata.com/i/futures/NQ · Polygon plan-gated (2-1): polygon.io/futures
- Specs micros: MGC (10 oz) e MNQ ($2/pt, 0.25 tick): cmegroup.com contractSpecs

*Nota measure-first: las killzones/estructura de sesión CME (RTH/ETH, gaps) y los overlays macro NO trajeron claim primario verificado — pendientes de medir, no asumidos.*
