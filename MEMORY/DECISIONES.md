# Decisiones clave y por qué — fq-bot

> Por qué el sistema está como está. Cada decisión cita el archivo / commit / PR real
> que la sostiene. Si vas a cambiar algo de esto, lee primero el razonamiento; muchas
> decisiones son contraintuitivas a propósito (la disciplina cuesta cadencia).

---

## 1. Measure-first: nada se despliega sin pasar el gate

**Decisión.** Nada va a clientes ni a capital real sin pasar un gate de validación
riguroso: **Deflated Sharpe Ratio (DSR) + CPCV + PBO**.

**Por qué.** El multi-testing (Bailey & López de Prado) garantiza falsos positivos: tras
~20 configuraciones probadas, el "5% significativo" es ruido. El DSR **deflacta** el
Sharpe por cuántas cosas probaste y obliga a pasar la vara real (DSR > 0.95) antes de
producción. Es el lever de mayor evidencia del research — no es data nueva, es validación.

**Evidencia.**
- `tools/validation_gate.py` (~221 líneas): PSR, `expected_max_sharpe`, `deflated_sharpe_ratio`,
  `cpcv_paths`, `pbo`. Pure stdlib + numpy, **sin scipy** (normal CDF vía `math.erf`, inverso
  por Acklam). `significant = dsr > 0.95`.
- Commit `3f0f497` ("MAX BUILD: gates quant — DSR/CPCV + CVD/OFI + sizing, validados", PR #68):
  primer gate cableado.
- `research/herramientas_quant_2026.md`: fundamento (López de Prado).

**Impacto.** Cada edge se valida forward ANTES de cablear. Es el moat: convierte "leads
lindos" en edge desplegable.

---

## 2. Order-flow (CVD firmado): de research a producción, midiendo forward

**Decisión.** Cablear el CVD (imbalance confirmado ≥0.50) como **capa 3 → capa 1**, en dos
fases: medir forward primero (sin client-facing), luego graduar conviction si replica en vivo.

**Por qué.** El research mostró que order-flow es la familia de features más robusta que
transfiere de física (Donier-Bonart BTC δ=0.5; Sato-Kanazawa, PRL 2025). El CVD es gratis
desde Binance aggTrades. El riesgo: medir en muestra chica y fallar forward. Solución: medir
ANTES de convencer a clientes.

**Evidencia.**
- Commit `29f3836` ("CVD histórico real gratis (Binance aggTrades) + validador DSR", PR #69):
  descarga aggTrades públicos (no paga), DSR en SOL ~0.98 y BTC ~1.00 a imb ≥0.50.
- Commit `fbce1e9` ("cablea el filtro CVD validado como medición forward", PR #73): integra
  `_cvd_confirm` en `motor_paper` (ver `motor_paper.py:325`). Causal (ventana ts < entrada).
  Gate `FQ_CVD_FILTER` default OFF → ledger byte-idéntico sin claves `cvd_*`. ON →
  `MOTOR_OPEN_META` sella `cvd_confirmed`, el reporte agrega `by_cvd`.
- Commit `0e89321` (badge VIP, PR #75) y `8c9187e` (boost +1 tier, PR #77): el cableado a
  conviction/size, **default OFF**.
- `research/plan_evolucion_2026.md` §1.1: criterio de graduación — **≥30 fires confirmados
  forward, uplift ≥ +0.1R, DSR ✓** → recién ahí sube conviction client-facing.

**Impacto.** R bruto confirmado: SOL +0.27R / BTC +0.34R (5 años, imb≥0.50). El +1.47R
estricto (n=17) lo **descartó el gate** (espejismo de muestra chica). Hoy mide forward, no
decide ni sube conviction.

---

## 3. Física → motor: F1 (impacto √) y F2 (persistencia), gratis y ortogonales

**Decisión.** De un deep-research de física/mate moderna, solo 2 candidatos sobreviven para
medir: **F1** (residual de impacto raíz-cuadrada) y **F2** (memoria larga / persistencia del
order-flow). Ambos familia CVD, ambos gratis en Binance Vision.

**Por qué.** El deep-research (`physics_validation.yml`: 107 agentes, 2.67M tokens, 25 fuentes
→ 121 afirmaciones → 25 verificadas a 3 votos adversariales, 21 sobreviven) filtró física
"soft" (LPPL, quantum-like) vs matemática transferible. Regla de oro (Yee 2021): "transfieres
la MATEMÁTICA cuando es empíricamente adecuada; importar el MECANISMO físico es sobreventa."

**Evidencia.**
- `research/fisica_moderna_2026.md`: síntesis de 25 fuentes primarias + cementerio.
- Commit `4176dd6` / `ba9f4d8` ("F1 impacto raíz-cuadrada + F2 persistencia — validadores
  measure-first", PR #84): `tools/validate_impact_flow.py` + `tools/validate_persistence_flow.py`.
- `research/fisica_moderna_2026_resultados.md` (run 28287771057, 2026-06-27): **BTC F2 persist
  ganador** — standalone DSR 0.997, premium DSR 0.995. **Ortogonal**: dentro de CVD-confirmado,
  no-persist = −0.045R (break-even), persist = +0.562R. **F2 rescata el CVD.** F1 es real (DSR
  0.994 standalone) pero **redundante** con CVD (sustituto, no complemento: within-CVD −0.186).

**Impacto.** F2-persist re-confirmado con n_trials=44 (commit `c355d25` "luz verde"), cableado
**dormido** (commit `7197ede`, PR #85) en `fq_bot_v3_2.py` (flag `FQ_PERSIST_BOOST=BTC`, default
OFF). F1 NO se cabló (pasa DSR, no pasa ortogonalidad). Caveat: F2 es **BTC-only** — SOL no apila
(firma retail/momentum, no memoria larga institucional).

---

## 4. Carry market-neutral: motor 2 (hedge contra el direccional)

**Decisión.** Construir un segundo motor **delta-neutral y descorrelacionado**: short-perp
funding carry en basket limpio (BTC/ETH/XRP/LTC/DOGE/ADA), **excluir SOL y BNB**. Medir
forward antes de vivo.

**Por qué.** El carry (cobrar funding siendo short-perp con hedge spot) es la ruta de mayor
durabilidad investigada. El direccional da Sharpe ~0.8; el carry neutral da Sharpe 13.6 bruto.
Y crucialmente **sobrevive el bear** (2022 +1.7% APY con basket limpio).

**Evidencia.**
- `research/carry_regime.md`: validación multi-régimen 2021-2026 sobre data.binance.vision.
  Basket CLEAN (6): +12.5% APY, Sharpe 13.6, maxDD 1.7%. Basket de 8 (con SOL/BNB): +9.4%,
  Sharpe 10.2, maxDD 10.5%. Limpiar sube retorno y Sharpe, divide el DD por ~6.
  - SOL: funding medio ~0, maxDD 43% (carry muerto). BNB: funding medio negativo (solo 22%
    de intervalos positivos — el que cobra es el LONG, no el short).
- Commit `c6a2c89` ("backtest de funding carry delta-neutral"): research + `CLEAN_BASKET`.
- Commit `4bae27c` ("carry market-neutral + fix cadencia + regime tag", PR #65): integra
  `carry_paper` + `tools/carry_backtest.py` + `carry_validate.py`. Mide forward en
  `/data/motor_carry_paper.jsonl`.

**Impacto.** Motor 2 cableado, midiendo forward sin capital real. Basket de producción =
`carry_backtest.CLEAN_BASKET` (`tools/carry_backtest.py:42`, una sola fuente de verdad).
**Honestidad**: es prima de régimen, NO arbitraje sin riesgo; el bruto resta ~2-4pp de APY al
neto (dos patas de fees + borrow + margen); en 2026 la prima se comprime a ~0.

---

## 5. ETH como 3er símbolo: cableado, no certificado

**Decisión.** ETH está cableado (motor paper, broadcast VIP gated, vetos, regime tag) pero
**no certificado**. Pendiente: cosechar el cube de ETH, correr la suite completa (DSR + CVD
signed-flow), y solo entonces broadcast pleno si pasa el gate.

**Por qué.** SOL/BTC son el pilar; ETH tiene microestructura distinta (más denso, más retail =
más order-splitting esperado). El carry validó que todos los símbolos del basket CLEAN tienen
funding sano, pero el edge **direccional es símbolo-específico**: el coeficiente de impacto Y y
la escala de memoria son del activo, no universales.

**Evidencia.**
- Commit `30f8ad0` ("motor paper ETH: 3er símbolo medido forward + broadcast gated", PR #56):
  cablea ETH/USDT en motor_paper. Tests en `tests/`.
- `research/plan_evolucion_2026.md` §1.3: (a) cosechar cube ETH (`eth_cosecha` → Hetzner);
  (b) correr validación completa; (c) si ETH pasa DSR → `FQ_ETH_VIP_BROADCAST=1`.
- `research/fisica_moderna_2026.md` §5: "raíz cuadrada y memoria larga son universales → los
  features transfieren; PERO coeficiente Y y escala de memoria son específicos → ETH tendrá su
  propia calibración."

**Impacto.** ETH cableado y broadcasting, pendiente cosecha del cube + validación DSR completa.

---

## 6. CVD → OFI: decisión de acceso, no de ejecución

**Decisión.** CVD validado en Binance aggTrades (gratis). **Solo si** el CVD demuestra edge
consistente FORWARD se evalúa pagar Tardis.dev por Order Flow Imbalance (L2, libro bid-ask).

**Por qué.** OFI es señal más fuerte que CVD, pero measure-first: primero pruebas el dato
gratis; solo pagas data premium si el gratis ya cerró el caso. No se pagan features especulativas.

**Evidencia.**
- `research/plan_evolucion_2026.md` §3 (FASE 3): "OFI verdadero (Tardis L2): SÓLO si el CVD
  validado lo justifica. Se paga sólo lo que el dato gratis ya demostró."
- Commit `a2de4d0` ("deck: capa 3 order-flow — 'ya cableado, midiendo forward'", PR #74).

**Impacto.** Cero gasto en data premium hasta que el dato gratis cierre el caso. Decisión
abierta: ¿paga OFI el uplift adicional sobre CVD?

---

## 7. Colectores forward (OI, CVD, carry): no-críticos, read-only

**Decisión.** Todos los colectores cuelgan de flags `FQ_*_COLLECT`/`FQ_*_FILTER`. Corren en
Railway/Hetzner, escriben parquets durables (`/data/*.parquet`). El motor y motor_paper LEEN
esos archivos, **nunca escriben** en ellos.

**Por qué.** Desacoplamiento crítico. Si un colector falla (API rota, timeout), el motor de
señales sigue — la señal jamás depende de un colector.

**Evidencia.**
- Commit `12abc00` ("agg-OI: colector forward de OI agregado multi-exchange", PR #67):
  `tools/fetch_agg_oi.py`.
- Commit `c79a6fb` ("ops: colector OI forward + señal VIP a maker", PR #54): integra en el
  launcher (`FQ_FETCH_OI_FORWARD`).
- Commit `2bde2d2` ("pipeline de validación de OI con DSR", PR #79): `tools/validate_oi_flow.py`.

**Impacto.** Motor lean, sin dependencias externas críticas. Colectores arrancados con flags
desde `launcher.py`.

---

## 8. Ejecución: taker inmediato + maker diferido (fill-rate honesto)

**Decisión.** Dos paths: (a) taker inmediato (entra YA, slippage pero fill 100%); (b) maker
diferido (limit-order, mejor precio pero puede no llenar). Motor paper mide ambos, sella el
fill-rate real y el R **neto** (fees + slippage).

**Por qué.** El edge +0.10R es un techo gateado por adverse selection (el MM ve tu orden y
corre). A 30-50 fills reales se sella si el edge es real al 100% o fue artefacto de backtest.

**Evidencia.**
- `motor_paper.py`: PaperBroker simula fills taker/maker, descuenta fees, resuelve NETO.
  Shadow maker con TTL; veto propio (`FQ_MOTOR_PAPER_VETO_*`) independiente del VIP.
- El reporte `/paper` discrimina stats por modo (maker vs taker) y mide el uplift forward.

**Impacto.** Motor paper mide R neto (no pretende ejecución perfecta). El fill-rate real es el
juez del edge en vivo.

---

## 9. Cerebro: analítica dedicada multi-símbolo (planificado)

**Decisión (planificada, por etapas).** El bot hoy es **SOL-rico** (ledger SQLite con 4 TP) pero
BTC/ETH solo viven en motor_paper (1 TP, vetos propios). Plan: añadir columna `symbol` al ledger
+ helper `_record_vip_signal` en los 3 sitios de broadcast (graba 4 TP + contexto + símbolo como
fuente de verdad). Luego un lago analítico DuckDB read-only que normaliza ledger + motor_paper +
CVD + cubes.

**Por qué.** Auditoría del registro forward (2026-06-27): es **asimétrico**. No puedes validar
integridad de 3 símbolos si el ledger es SOL-only. El cerebro lee los durables del bot sin tocar
el path crítico.

**Evidencia.**
- `research/cerebro_arquitectura.md` (commit `f0cce80`): 7 secciones (principios, estado, target,
  4 etapas, dónde corre, costo/riesgo, decisiones abiertas).
  - Etapa 0: fix de confianza (add `symbol`, `_record_vip_signal` en SOL/BTC/ETH).
  - Etapa 1: lago DuckDB/parquet read-only. Etapa 2: jobs background (mapa convicción, prometido
    vs realizado, edge-health DSR-rolling, integridad). Etapa 3: dashboard web + Telegram enriquecido.

**Impacto.** Hoy plan en papel. Siguiente: Etapa 0 (no-destructiva, additiva, con tests). El
cerebro reusa `validation_gate` — no reinventa el gate.

---

## 10. Producto: tres capas de edge, cada una gateada

**Decisión.** El producto tiene 3 capas validadas por DSR, cada una en su etapa de despliegue:
- **Capa 1 (direccional):** +0.10R OOS, Deflated Sharpe ✓ (BTC 1.00 / SOL 0.97). Vivo, en clientes.
- **Capa 2 (carry):** +12.5% APY net, Sharpe 13.6 bruto. Midiendo forward (carry_paper).
- **Capa 3 (order-flow):** CVD imb≥0.50, +0.27R (SOL) / +0.34R (BTC). Cableado, midiendo forward;
  graduación si ≥30 confirmed + uplift +0.1R + DSR.

**Por qué.** No es un bot de promesas. Cada edge está en el registro: qué se probó, con qué data,
en qué horizonte, qué pasa forward.

**Evidencia.** `research/plan_evolucion_2026.md`: "Dónde estamos (validado, no prometido)" tabula
3 capas, regímenes, n, R, Sharpe. Disciplina: "Nada se despliega sin pasar el gate."

---

## 11. Híbrido data/venue: validar TradFi sobre historia REAL, ejecutar en el perp

**Decisión.** Desacoplar la **fuente de datos** del **venue de ejecución**. Para mercados
tradicionales (oro, petróleo, NASDAQ): validar el edge sobre la historia profunda y gratis de
**Dukascopy** (velas, años) y ejecutar la señal en el **perp** del exchange (MEXC). El edge es
propiedad del **activo**, no del venue.

**Por qué.** MEXC (y los perps TradFi) no tienen historia profunda (`probe_mexc_tradfi.py`: SIN
data / solo reciente). Dukascopy sí (probe #116: XAU y WTI con 5m de hace ~2 años). Sin historia
no hay cube validable. Separar data de venue da profundidad para validar + perp para ejecutar.

**Qué transfiere y qué NO (honesto).** Transfieren las features de **precio**: KL (régimen), base,
y la capa **ICT/estructura** (sweeps, OB, FVG, PD, killzones — ya NY-calibradas en `killzones_pd.py`).
**NO** transfiere el order-flow (CVD/F2): es del libro del venue y Dukascopy da solo OHLCV (sin
taker buy/sell). En TradFi la confluencia triple pierde la pata de delta hasta tener order-flow real.

**Caveat operacional — sharding en data con huecos.** El motor **DIGIERE** la OHLCV de Dukascopy
(verify: 45 eventos en XAU) pero `cosecha_shard --verify` falla: el sharding **no reproduce** el
cubo sin shardear en data con huecos (fines de semana/breaks TradFi); el buffer lookback/horizonte
está calibrado para cripto 24/7. → cosechar TradFi **UNSHARDED** (`--shards 1`, exacto por
construcción) hasta arreglar el buffer. Es plomería, no edge.

**Evidencia.**
- `tools/fetch_dukascopy.py` (PR #117/#118/#120/#122): baja OHLCV al **schema canónico** del
  pipeline (`timestamp` datetime64[ns]); alias de índices (**NQ→USATECH**, ES→USA500, YM→USA30).
- `tools/probe_dukascopy.py` + `probe_dukascopy.yml` (#116): historia profunda confirmada.
- `.github/workflows/dukascopy_cosecha.yml` (#122): cosecha UNSHARDED XAU+NQ + `cube_report`.

**Impacto.** Pipeline TradFi viable. Cosecha XAU+NQ en marcha; gate KL/POC-distance pendiente.

---

## 12. Deploy hygiene: un push de SOLO docs no re-despliega el worker

**Decisión.** En `railway.toml`, `watchPatterns` usa **blacklist** (deploya `**` salvo lo que
seguro NO toca el runtime), no whitelist. La doc/research queda fuera: `*.md`, `internal/`,
`.github/`, `tests/`, `tools/`, **`MEMORY/`, `presentaciones/`, `*.pdf`, `*.html`, `*.png`**.
`tools/funding_paper.py` se **re-incluye al final** (gana el último match) porque SÍ es runtime.

**Por qué.** Blacklist y no whitelist = **fallo seguro**: si mañana se añade un tipo de archivo
de runtime nuevo, deploya por defecto (mejor un redeploy de más que un fix que nunca sube). Y la
doc/figuras NO deben churnear el worker: cada redeploy **resetea los contadores de sesión** y
expone al bot a blips transitorios de infraestructura.

**Detonante (2026-06-30).** El bot no disparó en todo el día. NO era el motor: `watchPatterns`
solo excluía `*.md`, así que los `.pdf/.html/.png` que subimos a `MEMORY/investigacion` (review,
preprint, deck) re-desplegaban el worker en cada commit de docs. Uno de esos deploys falló
(`Heartbeat timeout / Infrastructure Error`) y dejó al bot caído con "Total: 0".

**Evidencia.** `railway.toml` (PR #138). Lección de diagnóstico registrada en `ESTADO.md`
("0 disparos puede ser DEPLOY, no el edge — revisa Railway antes de asumir 'selectivo'").

**Impacto.** Los commits de memoria de procesos (esta misma directiva de RasDG) ya **no**
reinician el bot. El diagnóstico de cadencia ahora separa "deploy caído" de "edge selectivo".

**Refinamiento (2026-07-03, PR #166).** El blanket `!**/*.html` era **demasiado ancho**: atrapaba
`cockpit.html`, que SÍ es runtime (el `cockpit_server` lo lee del disco en cada GET). Síntoma: el
rediseño del portal (#164) salió "No changes to watched files" → SKIPPED, y solo se vio en vivo
porque RasDG le dio **Redeploy a mano**; luego #165 (quitar el pie legal) volvió a saltar y quedó
sin desplegar. Fix: re-incluir `cockpit.html` al final (último match gana), igual que
`tools/funding_paper.py`. El resto de `.html` (previews de docs en `MEMORY/`) sigue excluido.
**Lección general:** una exclusión por extensión (`*.html`, `*.png`…) puede tapar un archivo de
runtime que comparte extensión con documentación — re-incluir el archivo runtime explícito, no
aflojar el patrón. Si el deploy sale **SKIPPED** cuando esperabas que subiera, el sospechoso #1 es
`watchPatterns`, no el CI.

---

## 13. Producto de 2 tiers en UN SOLO CANAL: FREE (firehose) + VIP (filtrado), mismo bot

**Decisión (RasDG 2026-06-30/07-01, refinada: "quiero UN SOLO canal").** NO hay canal de Telegram
aparte: el MISMO bot entrega **por tier de la BD**. Los usuarios **tier "free"** (los que entran al
bot sin pagar — el default de la BD) reciben TODOS los fires del motor (crudos, solo TP1, sin boosts)
etiquetados según pasen o no el filtro de calidad KL; los tiers **vip/trial/admin** siguen recibiendo
solo el subconjunto filtrado (KL-bajo) con 4 TPs + boosts CVD/POC. Envs: `FQ_FREE_TIER=1` (entrega al
tier free) y `FQ_FREE_TO_VIP=1` (descartes al VIP, etiquetados). Ambas default OFF → byte-idéntico.

**Por qué.** Jugada de MARKETING, no de señal: al prender el filtro KL el VIP se puso quieto (~18/mes)
y **un canal callado se lee como MUERTO** → nadie paga por entrar a un cuarto en silencio. El FREE es
el **escaparate ruidoso** ("el motor nunca duerme") que da prueba social y jala gente. Y cada señal
**FILTRADA** que aparece en FREE ("los VIP NO la recibieron — se ahorraron el riesgo") es un **anuncio
vivo del valor VIP** → máquina de conversión. Honesto: la señal FREE es cruda de verdad (con guía de
riesgo "dosifica chico"); el moat es el **filtro + la gestión (VIP)**, no la entrada cruda.

**El pitch de VIP es SEGURIDAD, no "gana más":** ~1/3 del drawdown (medido −12% vs −36%), no más return.
Verdad y medible = cero humo (la marca de RasDG).

**Reglas de mezcla (RasDG, asimétricas a propósito):** **VIP → FREE: PROHIBIDO** — candado
`free_leak_guard()` antes de CADA envío al canal gratis (bloquea cualquier mensaje con marcadores del
formato VIP: `Senal VIP`/TP2-4/convicción/boosts/leverage) + estructural (`_free_broadcast` nunca recibe
el msg VIP, solo el report crudo). **FREE → VIP: PERMITIDO con etiqueta** — `FQ_FREE_TO_VIP=1` manda los
DESCARTES del filtro al VIP marcados **'Señal FREE'** (informativa, sin upsell); los VIP ven todo y saben
cuál es cuál. Texto distintivo garantizado: FREE dice "Señal FREE", VIP dice "Senal VIP", y hay test de
que nunca se confunden.

**Evidencia.** `_free_broadcast` + `FREE_TIER_ENABLED`/`FREE_TO_VIP` en `fq_bot_v3_2.py` (cableado en
los 4 sitios de broadcast, additivo al path VIP; entrega vía `broadcast_to_subscribers(tiers=["free"])`,
`include_admin=False` para no duplicar al admin); `vip_format.build_free_signal` (TP1 + etiqueta +
audiencia) + `free_leak_guard`; `tests/test_free_signal.py` (5 tests, incl. "el mensaje VIP real es
bloqueado"). El diseño de canal-aparte (`FQ_FREE_CHAT_ID`) se descartó el mismo día — un solo canal.

**Impacto.** FREE y VIP son dos VISTAS del mismo motor SOL/BTC/ETH: FREE = todo etiquetado, VIP =
filtrado. Cadencia alta en FREE (visible/vivo) + calidad en VIP (premium). Reversible (quitar la env).

---

## 14. Fix: el candado VIP-pair tapaba TAMBIÉN el descarte KL hacia los VIP (2026-07-20)

**El bug.** RasDG reportó "todo el mes sin disparo" en SOL/ETH. El motor SÍ disparaba (confirmado
contra el backup `fq_motor.db`: SOL 14 opens en julio, ETH 3), pero el candado de §13
(`if pair in VIP_PAIRS: return` al inicio de `_free_broadcast`) cortaba la función ENTERA — incluida
la rama `FQ_FREE_TO_VIP` — para SOL/BTC/ETH. Resultado: cuando el filtro KL (§ arriba, `FQ_KL_FILTER`)
suprimía un fire de un par VIP, ese descarte no le llegaba a NADIE: ni al tier free (correcto, el
candado debe bloquear eso) ni al VIP etiquetado 'Señal FREE' (bug — contradice §13: "los VIP ven
todo"). Un fire real de ETH con `kl_irrev=0.98` el 8-jul quedó sin ningún rastro visible.

**El fix.** El candado ahora solo bloquea el envío al tier free (`if FREE_TIER_ENABLED and not
_is_vip_pair`); la rama `FQ_FREE_TO_VIP` corre siempre, para cualquier par. Además, `_kl_pass` ahora
manda un eco admin ("🔇 KL suprimió...") cuando tapa un fire de un par VIP — nuevo flag
`FQ_KL_SUPPRESS_NOTIFY` (default ON) — para que "silencio" (el motor no encontró setup) y "suprimida"
(el motor disparó, el filtro de calidad la tapó) se vean distintos en el chat, no idénticos.

**Evidencia.** `fq_bot_v3_2.py::_free_broadcast` y `_kl_pass`; `tests/test_free_broadcast_vip_gate.py`
(4 tests: el candado sigue tapando free para pares VIP, pero ya no tapa FREE_TO_VIP; pares no-VIP
siguen yendo a ambos tiers; el eco admin dispara solo para pares VIP suprimidos, no para la cosecha).

---

## 15. `/analisis` multi-símbolo (SOL/BTC/ETH) + fuera la tabla QTE del on-demand (2026-07-20)

**El pedido (RasDG).** Extender `/analisis` (y sus alias `/lectura /niveles /pspace /claude /ia`) a
los 3 pares VIP, y quitar "carga inútil" — la tabla cruda de probabilidades QTE que salía en cada
lectura on-demand. También se planteó (sin decidir aún — "estoy pensando") eliminar los TP forzados
de la señal disparada; **eso NO se tocó**, es un cambio de producto mayor (rompe el ledger de 4 TP,
el tracking de progreso, el motor paper) que necesita decisión explícita, no se infiere de "lo estoy
pensando".

**Multi-símbolo.** `/analisis` toma un 1er argumento opcional `SOL|BTC|ETH` (default SOL, sin
argumento = comportamiento histórico). Nueva tabla `ANALISIS_PAIRS` + `_resolve_analisis_pair(args)`
(cae a SOL ante cualquier valor no reconocido — nunca rompe el comando). Se hiló el símbolo/par
correcto a través de TODA la cadena que antes asumía SOL a fuego:
- `cmd_lectura`, `build_analisis_context`, `cmd_analisis_vip` (fetch_ohlcv, header, hashtag).
- Las 4 lecturas de Claude (`claude_followup_general/pspace/niveles/analisis_vip`): antes el prompt
  decía "SOL/USDT" en el header sin importar el par mostrado (podía confundir a Claude analizando
  BTC/ETH). Ahora leen `pair` del snapshot (`claude_integration.py`, fallback SOL/USDT si falta).
- `market_context.snapshot_for_general/pspace/niveles`: antes llamaban a
  `get_funding_rate()/get_open_interest()/get_long_short_ratio()/get_order_book()` SIN símbolo →
  SIEMPRE traían los derivados de SOL, incluso analizando BTC/ETH (bug real, no solo cosmético).
  Ahora aceptan `symbol=`/`ccy=` opcionales.
- `vip_format.build_vip_analisis/build_battle_block`: el header "Plan · {par}" y el hashtag del
  cierre (`#FQ #SOLUSDT` fijo → dinámico, mismo fix que ya tenía `build_vip_signal`) ahora usan el
  par real en vez de la constante `PAIR` (SOL) a fuego.
- Cooldown por TF en `/lectura`: solo se muestra para SOL (único símbolo cuyo
  `STATE.last_signal_ts_tf` se escribe); BTC/ETH muestran una nota en vez de un número que mezclaría
  el cooldown de SOL.

**Fuera la tabla QTE del on-demand.** `cmd_lectura` corría un Monte Carlo de 500 paths + optimizer
QAOA en el TF 15m **en cada llamada** solo para imprimir "PROBABILIDADES (sobre niveles propuestos):
Toca SL primero X%..." — cómputo pesado sin ningún consumidor real (admin no decidía con esos
números). Se quitó por completo (ni el texto ni el cálculo). El battle plan VIP de `/analisis`
(`build_analisis_context`, 2000 paths) **se dejó intacto a propósito** — ese sí alimenta una
decisión real (el veredicto que lidera el mensaje VIP). `/timelines` (deep-dive QTE explícito,
admin) tampoco se tocó — es un comando dedicado a esos números, no "carga inútil" ahí.

**Evidencia.** `fq_bot_v3_2.py` (ANALISIS_PAIRS, `_resolve_analisis_pair`, `cmd_lectura`,
`build_analisis_context`, `cmd_analisis_vip`, las 4 `claude_followup_*`); `market_context.py`
(`snapshot_for_general/pspace/niveles`); `claude_integration.py` (4 prompt builders + system prompt
genérico); `vip_format.py` (`build_vip_analisis`, `build_battle_block`). Tests: 12 en
`tests/test_analisis_multisimbolo.py` (multi-símbolo + regresión "sin tabla QTE"), 5 en
`tests/test_claude_prompts_multisimbolo.py`, 4 en `tests/test_market_context_multisimbolo.py`.

**Addendum — `/analisis_sol` / `/analisis_btc` / `/analisis_eth` dedicados (mismo día).** El
argumento (`/analisis BTC`) no era descubrible desde el menú de Telegram: BotFather solo muestra
nombres de comando + descripción, no invita a escribir un argumento después de tocar el ítem del
menú. RasDG: "un VIP no ve el comando alternativo en su menú, eso no es intuitivo". Primer intento
(`/btc` / `/eth`) descartado por el propio RasDG: Telegram no admite espacios en el nombre de un
comando (`/analisis sol` sería `/analisis` + argumento `sol`, no un comando nuevo), así que el
agrupamiento visual bajo `/analisis` se logra con guion bajo, no con espacio. Iteración final:
los 3 simétricos y explícitos — ninguno "pelón" ni default implícito — `/analisis_sol`,
`/analisis_btc`, `/analisis_eth`. Los 3 comparten el mismo bloque tier-aware que `/analisis` (mismo
cooldown, mismo gate VIP, mismo flujo admin=completo/VIP=curado) pero con el par fijo — tap-to-use
desde el menú, sin escribir nada. `/analisis <par>` se mantiene intacto para quien ya lo usa (SOL
default si no hay argumento). Cooldown compartido entre los 4 (protege la API en general, no por
símbolo). **Pendiente de RasDG:** registrar `/analisis_sol` `/analisis_btc` `/analisis_eth` en
BotFather (`/setcommands`) para que aparezcan en el menú — el código ya los sirve sin eso, pero el
menú de Telegram no se autogenera desde el bot.

---

## 16. Cerebro Etapa 0: BTC/ETH entran al ledger rico + `/lectura` sin gate (2026-07-20)

**El pedido (RasDG).** "Cerrar el gap del ledger BTC/ETH (Cerebro Etapa 0)" — las señales VIP de
BTC/ETH (motor paper, §5) se difundían pero nunca quedaban registradas en `entropy_cognition`
(el ledger rico con outcome tracking, entropía, kappa_evo). Solo SOL se medía. De paso, RasDG
encontró un bug al revisar: "`/lectura` no es tier-aware".

**El gap del ledger.** Nuevo helper `_record_vip_signal(ccy, ...)` escribe las señales BTC/ETH
que SÍ llegan al VIP (no las que el motor descarta) en `entropy_cognition.log_signal(..., symbol=ccy)`,
cableado dentro de `_btc_motor_paper_scan`/`_eth_motor_paper_scan` solo en la rama de broadcast
exitoso, más `reconcile_outcomes(..., ccy="BTC"/"ETH")` al final de cada scan. Schema `migrate_schema_v5`
(`ALTER TABLE signals ADD COLUMN symbol TEXT DEFAULT 'SOL'`) — idempotente, mismo patrón que v2-v4.

**Aislamiento por diseño, no por filtro explícito.** Las filas BTC/ETH usan el `log_signal()` simple
(no `log_signal_v2/v3`), que deja `bucket_key_v2`/`bucket_key_v3` en NULL a propósito — `NULL = valor`
nunca matchea en SQL, así que el Thompson-kappa (`_bucket_beta_counts`, sobre `bucket_key_v3`) y
`count_closed_v2_buckets` (`bucket_key_v2`) quedan aislados de BTC/ETH SIN tocar esas funciones. El
resto de lecturas (`get_open_signals`, `count_signals`, `compute_entropy_metrics`, `get_bucket_stats`,
`get_global_metrics`, `get_results_summary`, etc.) sí recibieron un parámetro `symbol="SOL"` explícito
para no mezclar poblaciones — default SOL protege el número client-facing de `/resultados`.
`get_recent_signals`/`format_ledger_telegram` quedan `symbol=None` (mezcla deliberada: es el feed
diagnóstico de admin, no una estadística agregada).

**El bug de `/lectura`.** Al investigar se encontró que `/lectura` no solo se saltaba la vista
curada VIP — no tenía NINGÚN gate. No estaba en `PREMIUM_COMMANDS` ni en `ADMIN_ONLY`, así que
cualquier usuario sin VIP ni trial podía escribirlo y recibir el dump técnico completo (multi-TF,
niveles exactos, P_master) gratis, saltándose el paywall entero de la familia `/analisis`. Fix:
`/lectura` entra a `PREMIUM_COMMANDS` y al mismo bloque tier-aware que `/analisis` (admin ve el dump
completo, VIP ve `cmd_analisis_vip` curado).

**Evidencia.** `entropy_cognition.py` (`migrate_schema_v5`, `log_signal(symbol=)`, parámetro `symbol=`
en las funciones de lectura, `reconcile_outcomes(ccy=)`); `fq_bot_v3_2.py` (`_record_vip_signal`,
cableado en `_btc_motor_paper_scan`/`_eth_motor_paper_scan`, `/lectura` en `PREMIUM_COMMANDS`).
Tests: `tests/test_cerebro_etapa0_ledger.py` (18, incl. guarda de no-contaminación de kappa_evo),
`tests/test_record_vip_signal.py` (3), `tests/test_multisimbolo_ledger_wiring.py` (5),
`tests/test_lectura_tier_aware.py` (3, inspección de fuente — `command_listener` es un loop de
polling sin arnés de test directo).

---

## 17. `/lectura` y `/analisis` on-demand: sin doble Claude, sin niveles crudos (2026-07-20)

**El bug de duplicación.** RasDG reportó (con capturas) que `/lectura` mandaba la lectura táctica
DOS VECES en mensajes separados. Causa: `cmd_lectura` ya arma su propia lectura de Claude embebida
(vía `mctx.snapshot_for_general`), pero el bloque tier-aware de `command_listener` disparaba
ADEMÁS un follow-up en background (`claude_followup_general`) para el admin — dos llamadas
independientes a la API, dos mensajes. Fix: `fu_fn = None` para la rama admin (`/lectura`); la
rama VIP conserva su follow-up porque `cmd_analisis_vip` NO trae lectura embebida propia.

**Eliminar niveles crudos (el pedido de fondo).** RasDG: "los niveles ya me parecen poco efectivos,
quiero eliminarlos por completo y quedar con la pura lectura táctica e interpretación... es mejor
esperar el precio con el análisis en lugar de forzar entrada con niveles crudos". Alcance confirmado
explícitamente: **solo `/lectura` y `/analisis` (on-demand)** — la señal automática disparada al
VIP/FREE (`build_vip_signal`, con sus 4 TP) y el RADAR de alertas tácticas (`build_battle_plan`,
`build_battle_block`) son superficies distintas y NO se tocaron.

- `cmd_lectura`: se quitó el bloque Entry/SL/TP1-4 por timeframe (venía de `calculate_levels_v2`) y
  la simulación QTE de niveles de esa vista; queda sesgo + masas-P + P_master + dirección sugerida +
  cooldown. Header "NIVELES + ESTADO POR TIMEFRAME" → "SESGO + ESTADO POR TIMEFRAME".
- `build_analisis_context`: ya no llama a `battle_planner.build_battle_plan` — `plan` queda siempre
  `None` en este camino (el battle plan en $ solo vive en el RADAR).
- `claude_followup_analisis_vip`: el snapshot que ve Claude perdió `entry/sl/sl_anchor/tp1-3/rr_tp1-3`,
  el bloque advisory del optimizer QAOA (`qte_opt_*`/`qte_vs_*`) y `battle` — queda sesgo, masas-P,
  RSI y las probabilidades QTE (cualitativas, sin niveles).
- `vip_format.build_vip_analisis`: se quitó el bloque "Detalle" con Entry/Stop/TP1-3 en $; el mensaje
  ahora se apoya en `_market_tone`/`_quality_note`/`_decision_hint` (ya existían, cero números crudos)
  más dos bullets de cierre genéricos en vez de "SL estructural"/"TPs en liquidez real".
- `claude_integration.build_analisis_vip_prompt`: reescrito — sin bloque de battle plan ni optimizer
  QAOA en el prompt; la regla "SI puedes y debes citar precios exactos" se invirtió a "NO cites
  precios exactos"; los 4 bullets pedidos pasaron de "DONDE ENTRAR: precio exacto" /
  "INVALIDACIÓN: precio exacto" a equivalentes cualitativos (contexto estructural, confirmación
  esperada, gestión sin niveles).

**Evidencia.** `fq_bot_v3_2.py` (`command_listener` bloque tier-aware, `cmd_lectura`,
`build_analisis_context`, `claude_followup_analisis_vip`); `vip_format.py` (`build_vip_analisis`);
`claude_integration.py` (`build_analisis_vip_prompt`). Tests: `tests/test_lectura_no_duplica_claude.py`
(2, inspección de fuente), `tests/test_analisis_sin_niveles.py` (4: `build_analisis_context` nunca
arma battle plan, snapshot de Claude sin niveles/battle, `build_vip_analisis` y el prompt sin
Entry/Stop/TP ni figuras de $ ajenas al precio actual), más ajuste de
`tests/test_qte_verdict.py::test_vip_analisis_sin_plan_lidera_con_accion_y_distancia`.

---

## 18. TF anchor de `/lectura` y `/analisis` on-demand: 15m → 5m (2026-07-20)

**El pedido (RasDG).** "Cambia el TF anchor 15m en las lecturas tácticas a TF anchor 5m. Más adoc
al uso real." El anchor (el TF cuyo precio/vela alimenta la lectura de Claude y el contexto de
`/analisis`) era 15m desde el rediseño multi-TF (§15 pre-refactor). El "uso real" que lo hace
menos representativo: el propio motor paper de BTC/ETH ya corre en 5m (`BTC_MOTOR_TF`/
`ETH_MOTOR_TF`, el TF de la cosecha/research), y 5m también está en `TIMEFRAMES` desde mayo
(intradía, junto a 15m). Alcance idéntico a §17: solo el chequeo manual on-demand
(`cmd_lectura`, `build_analisis_context`/`cmd_analisis_vip`); la señal automática VIP/FREE y el
RADAR (que ya usa 5m vía `FIELD_TIMEFRAMES` para sus alertas tácticas) no se tocaron.

**El cambio.** Nueva constante `ANALISIS_ANCHOR_TF = "5m"` (+ `ANALISIS_ANCHOR_CANDLE_MINUTES = 5`)
junto a `ANALISIS_PAIRS` — única fuente de verdad para mover el anchor de ambos comandos a la vez.
`build_analisis_context` pide velas de `ANALISIS_ANCHOR_TF` (antes "15m" a fuego) y pasa `tf=` a
`calculate_levels_v2` igual. `cmd_lectura` captura `anchor_price`/`anchor_df` en la iteración cuyo
`tf_id == ANALISIS_ANCHOR_TF` (antes comparaba contra `"15m"` literal); el texto visible
("LECTURA TACTICA (Claude Sonnet, TF anchor {anchor})") ahora es dinámico, no quedó hardcodeado.

**El bug que evitó (candle_minutes).** `quantum_timelines.py` calculaba `horizon_hours` con
`horizon * 15 / 60` — asumía SIEMPRE velas de 15m sin importar el TF real del `df` recibido. Si
solo se hubiera cambiado el fetch a 5m, el "Horizonte ~24h" mostrado al VIP habría sido una
mentira 3x (24h reales mostradas como si fueran 96 velas de 15m, cuando en realidad eran 96 velas
de 5m = 8h). Mismo problema en los bounds `HORIZON_MIN_CANDLES`/`HORIZON_MAX_CANDLES` (24-160,
calibrados para representar 6h-40h en velas de 15m): sin ajuste, una ventana adaptativa en 5m
quedaría 3x más corta en horas reales de lo calibrado. Fix: nuevo parámetro `candle_minutes`
(default 15 = comportamiento histórico, cero impacto en cualquier otro caller de
`quantum_analysis`/`adaptive_horizon` — RADAR, Phase E, `/timelines`, fusion_engine incluidos)
que reescala tanto `horizon_hours` como los pisos/techos del horizonte adaptativo.
`build_analisis_context` es el único caller que pasa `candle_minutes=5`.

**Evidencia.** `quantum_timelines.py` (`DEFAULT_CANDLE_MINUTES`, `adaptive_horizon`,
`quantum_analysis`); `fq_bot_v3_2.py` (`ANALISIS_ANCHOR_TF`, `ANALISIS_ANCHOR_CANDLE_MINUTES`,
`build_analisis_context`, `cmd_lectura`, `claude_followup_analisis_vip`, docstring de
`cmd_analisis_vip`). Tests: `tests/test_tp_wavelength.py` (+4: `candle_minutes` default 15 sin
cambios, escala 3x los bounds en 5m, `horizon_hours` consistente entre 15m/5m con el mismo horizon
real, comportamiento histórico intacto sin el parámetro), `tests/test_analisis_anchor_5m.py`
(5 nuevos: la constante es la fuente de verdad, `build_analisis_context` pide velas del anchor y
threadea `candle_minutes` al QTE, `cmd_lectura` ancla precio/texto al TF nuevo).

---

## 19. `/tphits`: medir qué TP se toca más seguido, por TF (2026-07-21)

**El pedido (RasDG).** Viendo una captura de `/lectura` de ETH en 5m (de antes del fix de §17-18,
con niveles crudos todavía visibles), RasDG señaló: "ese TP2 es el más verga -- simétrico y
repetible como patrón, independientemente de la dirección del mercado. En 5m." Antes de tocar
producto con esa hipótesis (reintroducir un nivel en `/lectura`, o pesar el battle planner hacia
TP2), había que verificar si el ledger la respalda con datos reales en vez de una sola captura.

**Lo que ya existía vs. lo nuevo.** El battle planner (`battle_planner.py`) YA soporta múltiples
TPs (`tps`, top 3 en `build_battle_block`) y YA usa el régimen dominante del QTE para gatear
STAND_DOWN -- las dos cosas que RasDG pidió como mejora resultaron ya construidas. Lo que faltaba
era la métrica: nada calculaba "de los TPs alcanzados, ¿cuál gana más seguido, por timeframe?".

**El comando.** `/tphits` (admin-only) desglosa outcomes (`tp1`..`tp4`/`sl`/`timeout`) por `tf_id`
desde el ledger: n, win rate, expectancy, distribución completa, y el TP más frecuente ENTRE LOS
WINS de cada TF con su proporción. `symbol=None` por default (mezcla SOL/BTC/ETH -- la muestra por
TF ya es chica, partirla más sin pedirlo explícito la deja sin señal); acepta `symbol=` para aislar
uno. `stale` se excluye (no auditable). `tf_id` NULL (señales pre-schema-v4) cae al anchor
histórico "15m", mismo criterio que `reconcile_outcomes`.

**Por qué no se tocó producto todavía.** Es un comando de medición, no una reversión del fix de
niveles crudos de §17: no reintroduce nada en `/lectura`/`/analisis`, no cambia el battle planner.
Con datos reales (¿TP2 realmente domina en 5m? ¿en qué símbolo, con qué n?) se decide después si
vale la pena una acción de producto -- la disciplina "ledger como juez" del repo (ver Disciplinas
inegociables, #5) aplica aquí antes que en cualquier otro lado.

**Evidencia.** `entropy_cognition.py` (`get_tp_distribution_by_tf`, `format_tp_distribution_telegram`);
`fq_bot_v3_2.py` (`cmd_tphits`, registrado en `COMMANDS`/`ADMIN_ONLY`). Tests:
`tests/test_tp_distribution_by_tf.py` (10: agrupación por TF, top TP entre wins, TF sin wins,
tf_id NULL cae al anchor, stale excluido, symbol None mezcla / symbol filtra, formato Telegram),
`tests/test_tphits_command.py` (5: comando + registro en COMMANDS/ADMIN_ONLY por inspección de
fuente, igual criterio que `/lectura` en §16).

---

## 20. `radar_check` en 5m simulaba solo 1/3 del horizonte real (2026-07-21)

**El pedido (RasDG).** Tras el fix de `candle_minutes` en §18 (TF anchor de `/analisis`), RasDG
pidió auditar si otros callers de `quantum_analysis` tenían el mismo bug -- puntualmente
`radar_check` cuando corre en `field_tf="5m"` (ya en producción vía `FIELD_TIMEFRAMES`, el canal de
campo por defecto desde v5.3).

**Lo que se encontró.** `radar_check` llama `qt.quantum_analysis(df, ..., adaptive=True)` -- SÍ
ejecuta `adaptive_horizon()` (a diferencia del gate QTE legado de `_evaluate_setup_v411` y del QTE
pre-fusión de `fusion_engine.py`, que corren con `adaptive=False` y por tanto no activan el bug) --
sin pasar `candle_minutes`. Auditoría completa: solo 2 call sites en todo el repo usan
`adaptive=True` -- `build_analisis_context` (ya arreglado en §18) y `radar_check`.

**La diferencia con §18.** RADAR no muestra "Horizonte ~Nh" al cliente (`build_tactical_alert`/
`build_battle_block` no referencian `horizon_hours` en absoluto) -- así que NO es un texto que
mienta al cliente. Es más serio: `HORIZON_MIN_CANDLES`/`HORIZON_MAX_CANDLES` (24-160, calibrados
para 6h-40h en velas de 15m) se aplicaban tal cual a velas de 5m, simulando solo 2h-13.3h en vez de
6h-40h reales. Esa ventana truncada alimenta directo las probabilidades (`p_sl`/`EV`) que
`battle_planner.build_battle_plan` usa para el veredicto, y que `_should_promote_tactical_to_vip`
usa para decidir si la alerta llega a clientes VIP -- afectaba la CALIDAD DE LA DECISIÓN del canal
de campo 5m en producción, no solo un número mostrado.

**El fix.** Nuevo helper genérico `_tf_candle_minutes(tf_id)` (dict `_TF_MINUTES`, fallback 15) en
`fq_bot_v3_2.py`; `radar_check` pasa `candle_minutes=_tf_candle_minutes(tf_id)` a
`quantum_analysis`. `ANALISIS_ANCHOR_CANDLE_MINUTES` (§18) se deja como estaba -- ya correcto, sin
tocar código que funciona.

**Evidencia.** `fq_bot_v3_2.py` (`_TF_MINUTES`, `_tf_candle_minutes`, `radar_check`). Tests:
`tests/test_radar_candle_minutes.py` (5: helper con TFs conocidos/desconocidos, `radar_check` en
5m/15m/1m pasa el `candle_minutes` correcto a `quantum_analysis`).

---

## 21. `/lectura`: TP1/TP2 de vuelta, SOLO en el TF anchor 5m (2026-07-21)

**El pedido (RasDG), con capturas del bot en vivo.** "Como quedó ahora no dice TPs y está muy
confuso. Regrésame TP1 y 2 en TF 5m y el nivel crudo de eso, eso te dije que sí me servía para
operar." Reversión parcial de §17 (2026-07-20, mismo día anterior): la eliminación TOTAL de
niveles crudos de `/lectura` resultó ser un sobre-corrección -- sin ningún número, el chequeo
manual on-demand que RasDG usa para decidir sus propias entradas (no el de los clientes VIP, que
ven `cmd_analisis_vip` curado) quedó "muy confuso" en la práctica real, no solo en la intención.

**Alcance exacto de la reversión (no es un rollback completo de §17).**
- Vuelven Entry, SL, TP1, TP2 (con R:R y ancla estructural) -- **SOLO** en el bloque cuyo
  `tf_id == ANALISIS_ANCHOR_TF` (5m). El pedido fue explícitamente "TF 5m", no "todos los TF".
- TP3/TP4 **NO** vuelven en ningún TF -- el pedido fue específicamente TP1/TP2, no los 4 niveles
  completos. 15m/1h se quedan en sesgo+contexto, sin ningún nivel.
- La simulación QTE (500 paths + optimizer, la "carga inútil" de §15) sigue sin volver -- eso no
  fue lo que RasDG pidió recuperar.
- `/analisis` (VIP, `cmd_analisis_vip`/`build_vip_analisis`) **NO se tocó** -- las capturas y el
  pedido fueron específicamente sobre `/lectura` (el dump admin multi-TF que RasDG usa el mismo
  para operar, distinto del mensaje curado que ven los clientes VIP). Sigue sin niveles crudos.
- La señal automática VIP/FREE (`build_vip_signal`, 4 TP) sigue sin tocarse, como en §17.

**Por qué solo 5m y no también 15m/1h.** RasDG fue explícito con el TF; además 5m es el
`ANALISIS_ANCHOR_TF` (§18) -- el TF que ya lidera la lectura táctica de Claude y el que más se
acerca al "uso real" (motor paper BTC/ETH). El condicional usa la constante, no `"5m"` a fuego, así
que si el anchor cambia en el futuro, los niveles lo siguen automáticamente (sellado por test).

**Evidencia.** `fq_bot_v3_2.py::cmd_lectura` (bloque condicional `if tf_id == ANALISIS_ANCHOR_TF`,
header y tail actualizados para reflejar que 5m sí trae niveles). Tests (4 nuevos en
`tests/test_analisis_multisimbolo.py`): el bloque 5m trae Entry/SL/TP1/TP2, NO trae TP3/TP4, 15m/1h
siguen sin ningún nivel, y los niveles siguen al `ANALISIS_ANCHOR_TF` si cambia (no hardcodeado).

---

## 22. Polymarket: se mide la CANCHA antes que la estrategia (2026-08-17)

**Contexto.** Llegó una lista de 10 repos de Polymarket con la intención explícita de
buscar rentabilidad ahí. La tentación obvia era clonar el que trae "118 estrategias
listas" y ponerlo a correr.

**Decisión.** No se evalúa ninguna estrategia. Se mide primero **la oferta capturable**
— cuántos mercados tienen volumen y horizonte para que un edge sea siquiera capturable,
y cuánto capital-tiempo cuesta cada uno — porque es el diagnóstico que puede matar la
línea entera antes de gastar en ella. Mismo criterio que ordena E7/E8 en el brief: los
diagnósticos que invalidan van primero porque cuestan poco.

**Por qué el orden importa aquí en particular.** Yo mismo abrí la conversación afirmando
que el capital de Polymarket queda bloqueado hasta la resolución (meses) y que eso mataba
la anualización. **El dato lo refutó:** el horizonte mediano es 1.44 días y en 2026 el
volumen se mudó a ≤7d ($13.6B en 1-7d vs $1.6B en >90d). Una objeción que sonaba
estructural era un prior sin medir. Ese es exactamente el costo de opinar antes de medir,
y quedó registrado a propósito.

**Qué se construyó.** `tools/polymarket_supply.py` — sondeo sobre `markets.parquet`
(281 MB de un dataset de 53 GB: el paso barato a propósito). La identidad que gobierna:

```
retorno_anual = 365·(edge − spread/2) / (precio · h_pond)
```

con `h_pond` = horizonte ponderado por VOLUMEN. La participación **se cancela del
retorno**: solo fija cuánto capital cabe. De ahí el hallazgo de forma: donde el retorno
es espectacular el capital que cabe es ridículo ($0.2M a ≤1d), y donde cabe capital serio
($48M a ≤90d) el retorno es terrenal.

**Qué NO se decidió.** Nada sobre operar. El spread —único coste real del venue— no se
mide en `markets.parquet`, y con ~113 vueltas al año **una horquilla de 4pp anula un edge
de 2pp**. El apalancamiento temporal no distingue entre edge y coste. Veredicto abierto.

**Evidencia.** `internal/POLYMARKET_OFERTA_2026-08.md` (radiografía completa),
`tools/polymarket_supply.py`, `tests/test_polymarket_supply.py` (13 tests). Cero código en
el path del motor, cero flags nuevos, cero capital. `MEMORY/CEMENTERIO.md` §Polymarket
guarda el triaje de los 10 repos para no re-proponerlos.

**La invariante que deja.** El reporte **falla** (`ValueError`) si se le pide un agregado
sin desglose por año — criterio de aceptación de E9, cableado en el único sitio que hoy
imprime números de Polymarket. La n<30 se marca en el impreso, las filas excluidas se
cuentan encima de los números, y las columnas constantes se delatan (cazó `active` y
`archived`, constantes en las 1.84M filas: la lección `vp_basis` en dataset ajeno).

### 22-bis · El paso 2: la horquilla, y el estimador elegido por adversidad

**Resultado.** 1.13pp (rebote) a 1.90pp (Roll corregido) sobre 14.68M trades leídos por
rangos HTTP (sin bajar los 37.5 GB). Contra el breakeven de 4pp, **margen 2.1x**: el coste
NO se come el edge, al contrario que en perps. El veredicto cambia de "quizá" a **"el venue
es viable, la señal no existe"** — que es un problema distinto, no un permiso.

**Dos decisiones de método que valen más que el número.**

1. **El veredicto usa el estimador MÁS ADVERSO, no el promedio ni el favorable.** Está
   cableado en `verdict()` y fijado por test. Promediar dos estimadores que discrepan 68%
   esconde el desacuerdo; elegir el favorable es selección por resultado.
2. **El sesgo de Roll se mide, no se supone.** Roll asume signo del taker iid; en
   Polymarket ρ₁=+0.295. La corrección `√(1+ρ₂−2ρ₁)` = 0.825 mueve 1.57 → 1.90. Sin
   medir ρ, el veredicto habría viajado con un sesgo desconocido a su favor.

**Dos correcciones honestas a lo que yo mismo escribí en este mismo encargo.**

- Afirmé que sin colapsar por `transaction_hash` el rebote se sesgaba hacia cero. **Falso:
  el efecto medido es −0.0%** (los fills del mismo lado nunca cambian de lado, ya salían
  solos). El colapso se mantiene por definición correcta del precio del taker, no por sesgo.
- El paso 1 señalaba el corte de ≤1d como el mejor (494 vueltas/año). **La horquilla ahí
  es el doble** (3.29pp): margen 1.2x y $0.2M de capacidad. La optimización ingenua elegía
  la esquina frágil, y solo se vio al medir el coste por corte.

**Lo que sigue estando prohibido.** Operar. No hay edge medido; el único intento propio
que sí está medido falla (3.29pp vs vara 2pp, `marea/vault/MODEL.md`). El siguiente paso
es Brier advantage contra el precio del venue, por el gate como todo lo demás.

**Evidencia.** `internal/POLYMARKET_HORQUILLA_2026-08.md`, `tools/polymarket_spread.py`,
`tests/test_polymarket_spread.py` (19 tests, incluidos los que verifican que cada estimador
recupera una horquilla SINTÉTICA conocida — un estimador sin esa verificación es una
opinión con decimales).

---

## Resumen

| Decisión | Razonamiento core | Archivos / commits clave | Estado |
|---|---|---|---|
| Measure-first gate | multi-testing mata falsos positivos | `tools/validation_gate.py`, `3f0f497` | VIVO |
| CVD (order-flow) | gratis, replicado, ortogonal; mide forward primero | `29f3836`, `fbce1e9` | Midiendo forward |
| F1/F2 (física) | deep-research 107 agentes; F2 ganador ortho | `4176dd6`, `7197ede`, `c355d25` | F2 dormido (OFF); F1 redundante |
| Carry neutral | Sharpe 13.6 > 0.8; sobrevive bear | `carry_regime.md`, `4bae27c`, `c6a2c89` | Midiendo forward (basket CLEAN) |
| ETH 3er símbolo | coefs Y/memoria por activo | `plan_evolucion_2026.md` §1.3, `30f8ad0` | Cableado, falta cube + DSR |
| Colectores no-críticos | desacoplamiento (cae colector, motor sigue) | `launcher.py`, `12abc00`, `c79a6fb` | VIVO |
| Taker + maker | fill-rate real es el juez; neto fees+slippage | `motor_paper.py` | VIVO |
| Cerebro | registro asimétrico (SOL≠BTC/ETH) | `cerebro_arquitectura.md`, `f0cce80` | Etapa 0 planificada |
| Producto 3 capas | cada edge documentado y gateado | `plan_evolucion_2026.md` | Cap.1 vivo; 2/3 midiendo |
| Híbrido data/venue | TradFi: validar en Dukascopy, ejecutar en perp | `fetch_dukascopy.py`, #116/#122 | Cosecha XAU+NQ en marcha |
| Deploy hygiene | docs no re-despliegan; blacklist = fallo seguro | `railway.toml`, #138 | VIVO |
| Producto 2 tiers | UN SOLO canal: tier "free" de la BD recibe el firehose etiquetado; VIP el filtrado; candado VIP→FREE | `_free_broadcast`, `build_free_signal`, `free_leak_guard` | Cableado (dormido: `FQ_FREE_TIER` + `FQ_FREE_TO_VIP`) |
| Polymarket: cancha antes que estrategia | el diagnóstico que invalida va primero; oferta ✓, horquilla ✓ (1.13–1.90pp, margen 2.1x) | `tools/polymarket_supply.py`, `tools/polymarket_spread.py`, `internal/POLYMARKET_*_2026-08.md` | Lead abierto (0 capital; **venue viable, sin señal medida**) |

---

## Disciplinas inegociables

1. **Sin data especulativa**: OFI se paga solo si el CVD gratis lo justifica.
2. **Forward siempre**: la capa 3 (CVD) mide forward antes de client-facing.
3. **Ortogonalidad**: features nuevos suman DENTRO del CVD validado o van al cementerio.
4. **Símbolo-específico**: coefs Y, memoria, basket, veto — se recalibran por símbolo.
5. **Ledger como juez**: `/data/*.jsonl` es la fuente de verdad (fill-rate, R neto, regímenes).
6. **No hay veto sin dato**: `FQ_CVD_FILTER`, `FQ_PERSIST_BOOST`, etc. son flags con criterio de
   ON/OFF documentado en el plan.

_Actualizado: 2026-06-30. Fuente de verdad: `git log`, `research/*.md`, `tools/validation_gate.py`,
`motor_paper.py`, `launcher.py`, `tools/fetch_dukascopy.py`, `volume_profile.py`, `railway.toml`, `tests/`._
