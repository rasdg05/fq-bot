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

---

## Disciplinas inegociables

1. **Sin data especulativa**: OFI se paga solo si el CVD gratis lo justifica.
2. **Forward siempre**: la capa 3 (CVD) mide forward antes de client-facing.
3. **Ortogonalidad**: features nuevos suman DENTRO del CVD validado o van al cementerio.
4. **Símbolo-específico**: coefs Y, memoria, basket, veto — se recalibran por símbolo.
5. **Ledger como juez**: `/data/*.jsonl` es la fuente de verdad (fill-rate, R neto, regímenes).
6. **No hay veto sin dato**: `FQ_CVD_FILTER`, `FQ_PERSIST_BOOST`, etc. son flags con criterio de
   ON/OFF documentado en el plan.

_Actualizado: 2026-06-29. Fuente de verdad: `git log`, `research/*.md`, `tools/validation_gate.py`,
`motor_paper.py`, `launcher.py`, `tools/fetch_dukascopy.py`, `volume_profile.py`, `tests/`._
