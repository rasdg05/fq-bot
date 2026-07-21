# -*- coding: utf-8 -*-
"""
LLM tactical co-pilot. Sonnet para lecturas VIP, Opus para revision de
senales auto-disparadas.

El LLM recibe payloads ricos (precio, QTE, niveles, eventos, walls,
derivados) y devuelve lecturas tacticas. En vistas de cara al cliente
el output es cualitativo (probabilidad alta / edge claro), no formulas.
"""
import os
import json
import logging
import traceback

try:
    from anthropic import Anthropic
    from anthropic import APIError, APITimeoutError, RateLimitError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    Anthropic = None

log = logging.getLogger("fq_claude")

# ============================================================
# CONFIG
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()

MODEL_SONNET = "claude-sonnet-4-5"
MODEL_OPUS   = "claude-opus-4-6"

MAX_TOKENS_TACTICAL  = 700
MAX_TOKENS_SIGNAL    = 900
MAX_TOKENS_VIP_BRIEF = 560   # FQ v5.x: +140 para el bullet de eleccion de niveles (QTE optimizer advisory)
TIMEOUT_SECONDS      = 35

_client = None

def is_available():
    return ANTHROPIC_AVAILABLE and bool(ANTHROPIC_API_KEY)

def get_client():
    global _client
    if not ANTHROPIC_AVAILABLE:
        raise RuntimeError("anthropic SDK no instalado (pip install anthropic)")
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY no configurada")
    if _client is None:
        _client = Anthropic(api_key=ANTHROPIC_API_KEY, timeout=TIMEOUT_SECONDS)
    return _client

# ============================================================
# SYSTEM PROMPT
# ============================================================
SYSTEM_PROMPT_FQ = """Eres el copiloto tactico del sistema FQ (senales SOL/BTC/ETH en OKX).

CONTEXTO TECNICO:
Recibes snapshots cuantitativos por vela: precio, sesgo, niveles candidatos
(entry/SL/TPs), simulacion Monte Carlo con probabilidades de toque por TP y SL,
EV en multiplos de R, regimen dominante, coherencia entre paths, sincronizacion
temporal, datos externos (funding, OI, long/short, walls), eventos estructurales
(displacements, sweeps, breakouts) y bias multi-timeframe.

DECISION:
El motor ya filtra setups con EV negativo o probabilidad de SL alta. Tu trabajo
es interpretar lo que el motor ya decidio: confirmar, corregir o vetar con
postura clara, anclando a niveles reales (Order Blocks, liquidez, swings).

REGLAS DE ORO:
1. SL inmutable una vez entrada.
2. SL anclado a estructura real, nunca a indicadores volatiles.
3. Leverage maximo 8x solo en conviccion extrema.
4. Veto fin de semana (viernes 22 UTC a domingo 22 UTC).

ESTILO DE OUTPUT:
- Directo, conciso, lenguaje de trader. Sin floritura.
- En vistas de cara al cliente (VIP /analisis): cualitativo. Di "probabilidad
  alta", "edge claro", "campo neutro", "trampa probable" en lugar de citar
  porcentajes crudos o multiplos de R en el cuerpo. Puedes mencionar precios
  exactos cuando son niveles operativos (entry, SL, invalida, gatillo).
- Solo usa probabilidades o EV crudos si el prompt del usuario te lo pide
  explicitamente (vistas admin).
- Cuando hay riesgo, lo nombras sin endulzar.
- Sin markdown pesado. Texto plano con saltos de linea.
- Niveles en numeros exactos, nunca rangos vagos.
- No digas "esto no es asesoria financiera".
- No menciones versiones del producto, modelos de IA, frameworks, ni jerga
  interna del motor en el texto que el cliente lee.

TONO:
Segundo par de ojos calibrado. No eres cheerleader. Si funding extremo, OI
colapsando o wall hostil cerca, mencionalo en lenguaje operativo, no academico.
"""

# ============================================================
# HELPERS DE FORMATEO PARA SNAPSHOTS
# ============================================================
def fmt_events(events):
    """Formatea eventos detectados para el prompt"""
    if not events:
        return "  Sin eventos detectados en este momento."
    lines = []
    for e in events:
        line = "  - {}".format(e["type"])
        if "level" in e:    line += " en ${:.2f}".format(e["level"])
        if "strength" in e: line += " ({:.2f}% mas alla)".format(e["strength"])
        if "vol_x" in e:    line += " volumen {:.1f}x".format(e["vol_x"])
        if "body_pct" in e: line += " cuerpo {:.0f}%".format(e["body_pct"])
        if "context" in e:  line += " - {}".format(e["context"])
        if "rsi_change" in e: line += " RSI delta {:+.1f}".format(e["rsi_change"])
        lines.append(line)
    return "\n".join(lines)

def fmt_candles(candles):
    """Formatea evolucion de velas"""
    if not candles:
        return "  N/A"
    lines = []
    for c in candles:
        line = "  {} O:{} H:{} L:{} C:{} ({} {}%) RSI:{} Vol:{}".format(
            c["ts"], c["o"], c["h"], c["l"], c["c"],
            c["color"], c["body_pct"], c["rsi"], int(c["vol"])
        )
        if "delta_close_pct" in c:
            line += " [d:{:+.2f}%]".format(c["delta_close_pct"])
        lines.append(line)
    return "\n".join(lines)

def fmt_walls(walls, label):
    """Formatea walls de libro de ordenes"""
    if not walls:
        return "  Sin {} significativos".format(label)
    lines = []
    for w in walls:
        lines.append("  ${:.2f} - {:.0f} contratos ({:.2f}% del precio)".format(
            w["price"], w["size"], w["dist_pct"]))
    return "\n".join(lines)

def _fmt_num(v, fmt):
    """Formatea valor numerico, o devuelve texto crudo si es string/None."""
    if v is None:
        return "N/A"
    if isinstance(v, str):
        return v  # "UNAVAILABLE" pasa derecho
    try:
        return fmt.format(v)
    except (TypeError, ValueError):
        return str(v)

def fmt_external(s):
    """Formatea bloque de datos externos. Defensivo: tolera UNAVAILABLE."""
    parts = []
    if "funding_pct" in s:
        f = _fmt_num(s["funding_pct"], "{:+.4f}%")
        parts.append("Funding: {} - {}".format(f, s.get("funding_interp", "")))
    if "oi_millions" in s:
        oi_val = _fmt_num(s["oi_millions"], "${:.2f}M")
        oi_line = "Open Interest: {}".format(oi_val)
        if "oi_change_pct" in s:
            delta = _fmt_num(s["oi_change_pct"], "{:+.2f}%")
            oi_line += " (delta {}) - {}".format(delta, s.get("oi_trend", ""))
        parts.append(oi_line)
    if "ls_ratio" in s:
        ls_val = _fmt_num(s["ls_ratio"], "{:.2f}")
        parts.append("L/S Ratio: {} - {}".format(ls_val, s.get("ls_interp", "")))
    if "ob_pressure_interp" in s:
        parts.append("Presion libro 0.5%: {}".format(s["ob_pressure_interp"]))
    if not parts:
        return "  Datos externos no disponibles."
    return "\n".join("  - " + p for p in parts)

# ============================================================
# PROMPT BUILDERS
# ============================================================
def build_general_prompt(s):
    """Lectura tactica general - comando /claude"""
    return (
        "LECTURA TACTICA {pair} EN TIEMPO REAL\n"
        "========================================\n\n"
        "ESTADO INTERNO (FQ):\n"
        "  Precio: ${:.2f}\n"
        "  Sesion: {} (W_clock={:.2f})\n"
        "  Sesgo estructural: {} (score {:+d})\n"
        "  Momentum 5v: {:+.2f}% | 20v: {:+.2f}%\n\n"
        "GATE Theta(D):\n"
        "  Macro: BTC {:+.2f}% / ETH {:+.2f}%\n"
        "  Tecnica: {}/{} indicadores\n"
        "  Liquidez RSI 6/12/24: {:.0f}/{:.0f}/{:.0f}\n"
        "  P-Space: {} masas\n"
        "  Theta(D) = {}\n\n"
        "INDICADORES:\n"
        "  EMA50: ${:.2f} | EMA200: ${:.2f}\n"
        "  RSI14: {:.1f} | MACD: {:.3f}\n\n"
        "EVOLUCION ULTIMAS 5 VELAS 15m:\n{}\n\n"
        "EVENTOS DETECTADOS:\n{}\n\n"
        "ESTADO EXTERNO (DERIVADOS):\n{}\n\n"
        "----\n"
        "Dame tu lectura tactica:\n"
        "1. Que esta pasando aqui realmente (que ven los datos por dentro Y por fuera)\n"
        "2. Riesgos no obvios o trampas que el gate matematico podria no estar viendo\n"
        "3. Que esperarias para entrar con conviccion - dame triggers concretos con niveles\n\n"
        "Maximo 4 parrafos cortos."
    ).format(
        s.get("price", 0), s.get("session", "?"), s.get("w_clock", 0),
        s.get("bias", "?"), s.get("bias_score", 0),
        s.get("mom_5", 0), s.get("mom_20", 0),
        s.get("btc_chg", 0), s.get("eth_chg", 0),
        s.get("tec_aligned", 0), s.get("tec_total", 0),
        s.get("rsi6", 0), s.get("rsi12", 0), s.get("rsi24", 0),
        s.get("pspace_count", 0),
        "1 DECOHERENTE" if s.get("theta_d") else "0 SUPERPOSICION",
        s.get("ema50", 0), s.get("ema200", 0),
        s.get("rsi14", 0), s.get("macd", 0),
        fmt_candles(s.get("candle_evolution", [])),
        fmt_events(s.get("events", [])),
        fmt_external(s),
        pair=s.get("pair", "SOL/USDT"),
    )

def build_pspace_prompt(s):
    """Lectura de P-Space con foco en walls y libro"""
    masses = s.get("pspace_full", {}).get("masses", [])
    masses_lines = []
    for m in masses[:8]:
        dist_pct = abs(s.get("price", 0) - m["price"]) / s.get("price", 1) * 100
        masses_lines.append("  {} ${:.2f} ({:.2f}% lejos, w={:.1f}, tipo={})".format(
            m["name"], m["price"], dist_pct, m["weight"], m.get("type", "?")))
    masses_text = "\n".join(masses_lines) if masses_lines else "  Sin masas detectadas"

    return (
        "LECTURA P-SPACE + ORDER BOOK {pair}\n"
        "=====================================\n\n"
        "ESTADO ACTUAL:\n"
        "  Precio: ${:.2f}\n"
        "  Sesgo: {} (score {:+d})\n\n"
        "MASAS P-SPACE DETECTADAS:\n{}\n\n"
        "Curvatura kappa(p):\n"
        "  Peso soportes: {:.2f}\n"
        "  Peso resistencias: {:.2f}\n"
        "  Balance: {:+.2f} (-1 bajista / +1 alcista)\n\n"
        "ORDER BOOK WALLS:\n"
        "BID walls (compradores apilados):\n{}\n\n"
        "ASK walls (vendedores apilados):\n{}\n\n"
        "Presion 0.5%: {}\n\n"
        "EVENTOS DETECTADOS:\n{}\n\n"
        "----\n"
        "Tu lectura:\n"
        "1. Donde esta la verdadera batalla (P-Space teorico vs walls reales)\n"
        "2. Si las masas FQ coinciden con walls - confirmacion. Si no - cual mandara?\n"
        "3. Que escenario tactico ves (rebote, ruptura, trampa de liquidez)\n\n"
        "Maximo 4 parrafos cortos."
    ).format(
        s.get("price", 0), s.get("bias", "?"), s.get("bias_score", 0),
        masses_text,
        s.get("pspace_full", {}).get("support_weight", 0),
        s.get("pspace_full", {}).get("resistance_weight", 0),
        s.get("curvature_balance", 0),
        fmt_walls(s.get("bid_walls", []), "BID walls"),
        fmt_walls(s.get("ask_walls", []), "ASK walls"),
        s.get("ob_pressure_interp", "N/A"),
        fmt_events(s.get("events", [])),
        pair=s.get("pair", "SOL/USDT"),
    )

def build_niveles_prompt(s):
    """Lectura de plan de entrada con afinacion"""
    plan = s.get("plan_primary", {})
    return (
        "AFINACION DE PLAN DE ENTRADA {pair}\n"
        "=====================================\n\n"
        "ESTADO:\n"
        "  Precio: ${:.2f}\n"
        "  Sesion: {} (W={:.2f})\n"
        "  Sesgo: {} (score {:+d})\n\n"
        "PLAN PRIMARIO PROPUESTO POR EL BOT:\n"
        "  Modo: {}\n"
        "  Zona: {}\n"
        "  Trigger: {}\n"
        "  SL: ${:.2f} | TP3 divino: ${:.2f}\n\n"
        "EVENTOS DETECTADOS:\n{}\n\n"
        "EVOLUCION ULTIMAS 3 VELAS:\n{}\n\n"
        "WALLS RELEVANTES:\n"
        "BIDs:\n{}\n"
        "ASKs:\n{}\n\n"
        "DERIVADOS:\n{}\n\n"
        "----\n"
        "Tu trabajo:\n"
        "1. Confirma o cuestiona el plan - que ves bien, que afinarias\n"
        "2. Sugerencia concreta de SL alternativo si la estructura lo justifica (con razon)\n"
        "3. Riesgos contextuales (funding extremo? wall hostil cerca? evento adverso?)\n"
        "4. Si entrarias TU con este setup - si o no, breve justificacion\n\n"
        "Maximo 4 parrafos cortos."
    ).format(
        s.get("price", 0), s.get("session", "?"), s.get("w_clock", 0),
        s.get("bias", "?"), s.get("bias_score", 0),
        plan.get("mode", "?"), plan.get("zone", "?"), plan.get("trigger", "?"),
        s.get("plan_sl", 0), s.get("plan_tp3", 0),
        fmt_events(s.get("events", [])),
        fmt_candles(s.get("candle_evolution", [])),
        fmt_walls(s.get("bid_walls", []), "BIDs"),
        fmt_walls(s.get("ask_walls", []), "ASKs"),
        fmt_external(s),
        pair=s.get("pair", "SOL/USDT"),
    )

def build_analisis_vip_prompt(s):
    """
    Prompt VIP /analisis. El LLM recibe payload del motor y emite lectura
    cualitativa de 4 bullets. Sin formulas crudas ni precios exactos en el
    output (2026-07-20, RasDG: "los niveles ya me parecen poco efectivos,
    es mejor esperar el precio con el analisis en lugar de forzar entrada
    con niveles crudos") -- el snapshot de este on-demand ya no trae
    entry/SL/TP ni battle plan (esos siguen vivos solo en la senal
    automatica VIP/FREE y en el RADAR, otras superficies que no se tocan).
    """
    qte_block = ""
    if s.get("qte_p_tp1") is not None:
        # Distribucion de regimenes (top 3) en formato corto
        reg_lbl = {"bull_continuation": "bull", "bear_reversal": "bear",
                   "chop": "chop", "sweep_and_reverse": "sweep", "range": "range"}
        reg_top3 = s.get("qte_regimes_top3") or []
        reg_dist = " / ".join(
            "{} {:.0%}".format(reg_lbl.get(k, k), v) for k, v in reg_top3
        ) or "{} ({:.0%})".format(
            s.get("qte_dominant_regime", "?"), s.get("qte_dominant_pct", 0) or 0)
        # P(tocar TPk antes que SL) - medida util; fallback a p_tp* legacy
        r1 = s.get("qte_p_reach_tp1") if s.get("qte_p_reach_tp1") is not None else s.get("qte_p_tp1", 0)
        r2 = s.get("qte_p_reach_tp2") if s.get("qte_p_reach_tp2") is not None else s.get("qte_p_tp2", 0)
        r3 = s.get("qte_p_reach_tp3") or 0
        qte_block = (
            "QTE ({npaths} timelines simuladas, niveles del bot):\n"
            "  P(SL)            {psl:.0%}      P(timeout) {pto:.0%}\n"
            "  P(toca TP1<SL)   {r1:.0%}\n"
            "  P(toca TP2<SL)   {r2:.0%}\n"
            "  P(toca TP3<SL)   {r3:.0%}\n"
            "  EV               {ev:+.2f}R     Coherencia {coh:.0%}\n"
            "  Regimenes:       {regdist}\n\n"
        ).format(
            npaths=s.get("qte_n_paths", 0),
            psl=s.get("qte_p_sl", 0) or 0,
            pto=s.get("qte_p_timeout", 0) or 0,
            r1=r1 or 0, r2=r2 or 0, r3=r3 or 0,
            ev=s.get("qte_ev", 0) or 0,
            coh=s.get("qte_coherence", 0) or 0,
            regdist=reg_dist,
        )
        # Veredicto canonico del motor (misma fuente que VIP/admin). Es input
        # para que tu lectura no contradiga la del motor; confirmalo o corrigelo.
        if s.get("qte_verdict_label"):
            qte_block += "  Veredicto del motor: {}\n\n".format(s["qte_verdict_label"])

    # Sync emergente: payload tecnico para que el LLM module su lectura.
    # Es input, no debe ser citado en el output.
    phase_e_block = ""
    if s.get("phase_e_sync_score") is not None:
        pm = s.get("phase_e_phi_memory")
        pm_str = "{:.2f} (informativo, sin bucket)".format(pm) if pm is not None else "N/A"
        delta = s.get("phase_e_delta_min")
        delta_str = "{:.0f}min desde ultima senal".format(delta) if delta is not None else "sin senal previa"
        phase_e_block = (
            "SYNC EMERGENTE (uso interno, no citar en el output):\n"
            "  sync_score   {sync:.2f}     tier  {tier}\n"
            "  tau          {tau:.3f}\n"
            "  phi_clock    {pc:.2f}     (sesion / killzone weight)\n"
            "  phi_memory   {pm}\n"
            "  phi_horizon  {ph:.2f}     (1-P_SL * EV/2 * coherence)\n"
            "  phi_refract  {pr:.2f}     ({dt})\n"
            "  coherence    {coh}\n\n"
        ).format(
            sync=s.get("phase_e_sync_score"), tier=s.get("phase_e_tier", "?"),
            tau=s.get("phase_e_tau", 0),
            pc=s.get("phase_e_phi_clock", 0),
            pm=pm_str,
            ph=s.get("phase_e_phi_horizon", 0),
            pr=s.get("phase_e_phi_refractory", 0),
            dt=delta_str,
            coh="{:.2f}".format(s["phase_e_coherence"]) if s.get("phase_e_coherence") is not None else "N/A",
        )

    return (
        "ANALISIS {pair} (vista VIP)\n"
        "=============================\n\n"
        "Precio:    ${price:.2f}\n"
        "Sesgo:     {bias} -> {dir}\n"
        "Masas P:   {pc}    RSI14: {rsi:.0f}\n\n"
        "{qte}"
        "{phase_e}"
        "----\n"
        "TU ROL: copiloto de lectura intradia. NO hay plan de entrada numerico\n"
        "para este chequeo -- el cliente pidio dejar de forzar entradas con\n"
        "niveles crudos y esperar que el precio confirme. Tu trabajo es\n"
        "interpretar sesgo + probabilidades, no fijar precios.\n"
        "\n"
        "REGLAS DE OUTPUT (lo lee un cliente VIP):\n"
        "- No cites porcentajes crudos ni multiplos de R en el texto. Usa lenguaje\n"
        "  cualitativo: probabilidad alta/media/baja, edge claro/marginal, campo\n"
        "  neutro, trampa probable, regimen ranging, etc.\n"
        "- NO cites precios exactos de entry, SL, TP, zonas de acumulacion ni\n"
        "  gatillos numericos -- no los tienes en este payload y el cliente no\n"
        "  los quiere aqui. Habla de estructura (Order Blocks, liquidez, barridas)\n"
        "  en terminos relativos, no de niveles.\n"
        "- No menciones nombres de version, modelos, frameworks ni jerga interna.\n"
        "\n"
        "ENTREGA EXACTAMENTE 4 BULLETS (max 280 palabras):\n"
        "  1. VEREDICTO: 'A favor / selectivo / sin edge / stand down'. Sin\n"
        "     tibieza -- di que tan convencido estas y por que.\n"
        "  2. CONTEXTO ESTRUCTURAL: que esta haciendo el precio ahora (liquidez,\n"
        "     Order Blocks, barridas) sin dar coordenadas exactas.\n"
        "  3. QUE ESPERAR ANTES DE ACTUAR: la confirmacion de precio que\n"
        "     validaria o mataria la idea, descrita cualitativamente.\n"
        "  4. GESTION: como pensar el riesgo/tamano en este escenario, sin\n"
        "     numeros de nivel.\n"
        "\n"
        "Cero relleno. Si coincides con stand down, dilo directo y describe el\n"
        "unico evento (barrida + confirmacion) que te haria reenganchar."
    ).format(
        price=s.get("price", 0),
        bias=s.get("bias", "?"),
        dir=s.get("direction", "?").upper(),
        pc=s.get("pspace_count", 0), rsi=s.get("rsi14", 0),
        qte=qte_block,
        phase_e=phase_e_block,
        pair=s.get("pair", "SOL/USDT"),
    )

def build_signal_prompt(s):
    """Co-pilot para senal auto-disparada (Opus) - el mas profundo"""
    decoh = s.get("decoherence", {})
    return (
        "SENAL AUTO-DISPARADA - REVISION FINAL ANTES DE EJECUTAR\n"
        "========================================================\n\n"
        "DIRECCION: {}\n"
        "P_master: {:.2f}\n"
        "Sesion: {} (W={:.2f})\n\n"
        "NIVELES PROPUESTOS:\n"
        "  Entry: ${:.2f}\n"
        "  SL:    ${:.2f} (riesgo {:.2f}%)\n"
        "  TP1:   ${:.2f} (R:R {:.2f})\n"
        "  TP2:   ${:.2f} (R:R {:.2f})\n"
        "  TP3 *DIVINO*: ${:.2f} (R:R {:.2f})\n"
        "  TP4:   ${:.2f} (R:R {:.2f})\n\n"
        "GATE THETA(D) PASADO:\n"
        "  Macro: BTC {:+.2f}% / ETH {:+.2f}%\n"
        "  Tecnica: {}/{} alineados\n"
        "  Liquidez: RSI 6/12/24 = {:.0f}/{:.0f}/{:.0f}\n"
        "  P-Space: {} masas\n\n"
        "EVOLUCION 5 VELAS:\n{}\n\n"
        "EVENTOS ACTIVOS:\n{}\n\n"
        "DERIVADOS EN VIVO:\n{}\n\n"
        "WALLS:\n"
        "BIDs:\n{}\n"
        "ASKs:\n{}\n\n"
        "----\n"
        "Esta senal pasa el gate matematico. Tu trabajo:\n\n"
        "1. AFINA el SL: el SL propuesto esta anclado a estructura real? Si no, dame nivel mejor con razon.\n"
        "2. AFINA los TPs: los walls de orden book afectan algun TP? Hay liquidez que tomar antes?\n"
        "3. RIESGO CONTEXTUAL: funding/OI/L-S extremos? Evento adverso en horizonte?\n"
        "4. CONVICCION FINAL: del 1-10, que tan limpio te parece este setup, y por que.\n\n"
        "Esta lectura ira directo al usuario junto a la senal automatica. Se conciso, accionable, profesional.\n"
        "Maximo 5 parrafos cortos."
    ).format(
        s.get("direction", "?").upper(), s.get("p_master", 0),
        s.get("session", "?"), s.get("w_clock", 0),
        s.get("entry", 0), s.get("sl", 0), s.get("risk_pct", 0),
        s.get("tp1", 0), s.get("rr_tp1", 0),
        s.get("tp2", 0), s.get("rr_tp2", 0),
        s.get("tp3", 0), s.get("rr_tp3", 0),
        s.get("tp4", 0), s.get("rr_tp4", 0),
        decoh.get("macro", {}).get("btc_change", 0),
        decoh.get("macro", {}).get("eth_change", 0),
        decoh.get("tecnica", {}).get("aligned", 0),
        decoh.get("tecnica", {}).get("total", 0),
        decoh.get("liquidez", {}).get("rsi6", 0),
        decoh.get("liquidez", {}).get("rsi12", 0),
        decoh.get("liquidez", {}).get("rsi24", 0),
        s.get("pspace_count", 0),
        fmt_candles(s.get("candle_evolution", [])),
        fmt_events(s.get("events", [])),
        fmt_external(s),
        fmt_walls(s.get("bid_walls", []), "BIDs"),
        fmt_walls(s.get("ask_walls", []), "ASKs"),
    )

# ============================================================
# API CALLS
# ============================================================
def _call_anthropic(model, prompt, max_tokens):
    """Helper interno con manejo robusto de errores"""
    try:
        client = get_client()
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=SYSTEM_PROMPT_FQ,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join([blk.text for blk in resp.content if hasattr(blk, "text")])
        log.info("Claude [{}] OK - in:{} out:{}".format(
            model, resp.usage.input_tokens, resp.usage.output_tokens))
        return text.strip()
    except RateLimitError:
        log.warning("Anthropic rate limit on {}".format(model))
        return "[Claude] Rate limit alcanzado. Reintenta en 1 minuto."
    except APITimeoutError:
        log.warning("Anthropic timeout on {}".format(model))
        return "[Claude] Timeout - red lenta. Reintenta."
    except APIError as e:
        log.error("Anthropic API error on {}: {}".format(model, e))
        return "[Claude] Error API: {}".format(str(e)[:120])
    except Exception as e:
        log.error("Claude unexpected error: {}\n{}".format(e, traceback.format_exc()))
        return "[Claude] Error inesperado: {}".format(str(e)[:120])

def tactical_general(snapshot):
    """Lectura tactica general - Sonnet"""
    return _call_anthropic(MODEL_SONNET, build_general_prompt(snapshot), MAX_TOKENS_TACTICAL)

def tactical_pspace(snapshot):
    """Lectura P-Space con order book - Sonnet"""
    return _call_anthropic(MODEL_SONNET, build_pspace_prompt(snapshot), MAX_TOKENS_TACTICAL)

def tactical_niveles(snapshot):
    """Afinacion de plan de entrada - Sonnet"""
    return _call_anthropic(MODEL_SONNET, build_niveles_prompt(snapshot), MAX_TOKENS_TACTICAL)

def tactical_analisis_vip(snapshot):
    """Lectura VIP breve para /analisis - Sonnet, 320 tokens, 4 bullets"""
    return _call_anthropic(MODEL_SONNET, build_analisis_vip_prompt(snapshot), MAX_TOKENS_VIP_BRIEF)

def signal_copilot(snapshot):
    """Co-pilot para senal auto-disparada de alta conviccion - Opus"""
    return _call_anthropic(MODEL_OPUS, build_signal_prompt(snapshot), MAX_TOKENS_SIGNAL)

def is_high_conviction(p_master, phi_cubed=4.236):
    """Determina si la senal es de alta conviccion (P_master >= phi^3)"""
    return p_master >= phi_cubed
