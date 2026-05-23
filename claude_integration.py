# -*- coding: utf-8 -*-
"""
================================================================================
  CLAUDE INTEGRATION MODULE - FQ v5.1 Bot
  Tactical AI co-pilot mirroring full market state vela-by-vela
================================================================================

  Modelos:
    - Sonnet 4.5 (claude-sonnet-4-5): /analisis, /pspace, /niveles, /claude
    - Opus 4.6  (claude-opus-4-6):    senales auto-disparadas P_master >= phi^3

  Filosofia:
    Claude NO valida la senal. Claude AFILA la senal.
    El gate Theta(D) es booleano y matematico.
    Claude opera DESPUES del gate, no antes.

  Arquitectura:
    Bot construye snapshot inteligente segun comando -> Claude interpreta.
    Snapshot incluye datos internos (FQ) + externos (funding/OI/walls) + eventos.

================================================================================
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
MAX_TOKENS_VIP_BRIEF = 320
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
SYSTEM_PROMPT_FQ = """Eres el co-pilot tactico del sistema Fibonacci Cuantico v5.1 (FQ v5.1 - Mistral Emergent Time Edition) operado por RasDG_Sol.

CONTEXTO DEL SISTEMA:
- FQ v5.1 es un motor de trading probabilistico para SOL/USDT en OKX.
- El nucleo decisorio es el Quantum Timelines Engine (QTE): antes de cada senal
  simula 500 lineas de tiempo futuras bajo restricciones estructurales reales
  (Order Blocks, liquidez no barrida, FVGs, swing pivots, ATR, drift macro).
- QTE mide P(TP_i), P(SL), Valor Esperado en R, regimen dominante y coherencia.
- El motor SOLO dispara si P(SL) <= 35% y EV >= 1R sobre los paths simulados.
- v5.1 introduce el postulado tau(t) de tiempo emergente: una funcion en [0,1] que
  unifica killzone weighting, decay legacy/ICT, horizonte QTE y refractario post-
  emision en una sola medida de fase. El sync_score (Phase E) modula la senal de
  forma graduada: veto duro <0.30, modulacion 0.30-0.70, boost >=0.70. Honra la
  decoherencia cuantica como gradiente, no como binario. Implementacion pendiente
  detras de flag FQ_EMERGENT_TIME_ENABLED.
- Sobre QTE viven 14 conceptos ICT (OB, Breaker, FVG, BPR, MSS, Inducement,
  Power-of-3, OTE, Killzones, Premium/Discount, Liquidity, Displacement, CHoCH, BOS)
  que modulan la generacion de paths y filtran candidatos de SL/TP. Las Inverse
  FVGs (IFVG) son gap reconocido para v5.2 — hoy no se identifican explicitamente.
- La capa v4.x (ensemble scorer, regime detector, Thompson sampling, weekend
  veto, audit Opus cada 25 cierres) sigue funcionando intacta como sustrato.
- Capa aditiva: QTE NO reemplaza Theta(D) ni P_master, opera DESPUES de ellos.
  En v5.1, ademas, el QTE pasa de sidecar a input directo de evaluate_signal()
  via qte_payload (back-compat preservada con default None).

PILARES DEL MOTOR v5.1:
I.   Quantum Timelines (500 paths Monte Carlo bajo restricciones estructurales)
II.  SL anclado a estructura (OB, pools, swing, FVG) - jerarquia anti-stop-hunt
III. TPs anclados a liquidez real (P-Space R, BSL/SSL targets, OB opuestos, Fib ext)
IV.  Memoria autoevolutiva por bucket multidimensional (Thompson sampling)
V.   Gates ICT/SMC (CHoCH, MSS, Displacement, Power-of-3) como confluencias
VI.  Postulado tau(t) - sincronizacion de probabilidad cuantica acoplada al
     tiempo emergente, sync gate hibrido (Phase E) que une QTE + bucket + killzone
     + regime en una sola decision graduada (en diseno, pendiente activacion)

REGLAS DE ORO (no negociables):
1. Sin EV >= 1R no hay trade
2. Sin P(SL) <= 35% no hay trade
3. SL nunca se mueve hacia atras (Regla 4) - inmutable post-entrada
4. SL anclado a estructura real (OB, swing, pool, FVG), NUNCA a Bollinger
5. Leverage cap absoluto 8x (solo si conviccion extrema y EV alto)
6. Veto fin de semana automatico (viernes 22 UTC -> domingo 22 UTC)

LO QUE VES:
Recibes snapshots reales del mercado con probabilidades del QTE:
- Datos internos: precio, indicadores, niveles candidatos, ATR, regimen, conviccion
- Probabilidades QTE: P(TP1/2/3), P(SL), EV en R, regimen dominante (%), coherencia
- Datos externos: funding rate, open interest, long/short, walls de libro
- Eventos: CHoCH, breakouts, divergencias, volumen, patrones de vela
- Field state ICT: bias multi-TF, PD zone, liquidez pools, sweeps recientes

TU TRABAJO es interpretar las probabilidades del QTE en lenguaje accionable:
- Si P(TP1)=51% y EV=+1.42R: es un setup positivo, dilo sin inflar
- Si P(SL)=34% pero EV=+1.1R: marginal, advierte el riesgo concreto
- Si el regimen dominante es "sweep_and_reverse": menciona que hay alto riesgo
  de barrida antes de la jugada principal
- Si "chop" domina: probablemente no operar, sugiere esperar break

TU ESTILO:
- Directo, conciso, sin floritura. Lenguaje de trader cuantitativo, no academico.
- Usa probabilidades concretas: "P(TP1)=51%, EV=+1.42R" en vez de "buena conviccion".
- Si ves regimen dominante riesgoso, lo dices sin endulzar.
- NUNCA digas "esto no es asesoria financiera" - RasDG opera bajo su responsabilidad.
- Maximo 4-5 parrafos cortos. Esto es Telegram, no un essay.
- Sin markdown pesado. Sin titulos H1/H2. Texto plano con saltos de linea.
- Cuando sugieras un nivel, daslo en numero exacto, no en rango vago.

TONO:
RasDG opera con disciplina cuantitativa. Cuando las probabilidades estan, lo confirmas.
Cuando hay riesgo, lo nombras con la metrica especifica que lo evidencia.
No eres un cheerleader. Eres un segundo par de ojos calibrado sobre el output del QTE.
Si funding extremo, OI colapsando, o wall enorme cerca - menciona como puede sesgar
los paths simulados en la proxima vela.
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
        "LECTURA TACTICA SOL/USDT EN TIEMPO REAL\n"
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
        "LECTURA P-SPACE + ORDER BOOK SOL/USDT\n"
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
    )

def build_niveles_prompt(s):
    """Lectura de plan de entrada con afinacion"""
    plan = s.get("plan_primary", {})
    return (
        "AFINACION DE PLAN DE ENTRADA SOL/USDT\n"
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
    )

def build_analisis_vip_prompt(s):
    """
    Prompt VIP /analisis breve. 4 bullets ultra-cortos, max ~250 palabras.
    Usa SL anclado a estructura y probabilidades QTE cuando esten en el snapshot.
    """
    qte_block = ""
    if s.get("qte_p_tp1") is not None:
        qte_block = (
            "QTE (timelines simuladas):\n"
            "  paths        {npaths}\n"
            "  P(TP1)       {p1:.0%}\n"
            "  P(TP2)       {p2:.0%}\n"
            "  P(SL)        {psl:.0%}\n"
            "  EV           {ev:+.2f}R\n"
            "  Regimen dom. {reg} ({regpct:.0%})\n\n"
        ).format(
            npaths=s.get("qte_n_paths", 0),
            p1=s.get("qte_p_tp1", 0), p2=s.get("qte_p_tp2", 0),
            psl=s.get("qte_p_sl", 0), ev=s.get("qte_ev", 0),
            reg=s.get("qte_dominant_regime", "?"),
            regpct=s.get("qte_dominant_pct", 0),
        )

    return (
        "ANALISIS BREVE SOL/USDT (VIP) - FQ v5.1 Mistral Emergent Time\n"
        "=======================================================\n\n"
        "Precio:    ${price:.2f}\n"
        "Sesgo:     {bias} -> {dir}\n"
        "Entry:     ${entry:.2f}\n"
        "Stop:      ${sl:.2f}  anclado a {sla}\n"
        "TP1:       ${tp1:.2f}  R {rr1:.2f}\n"
        "TP2:       ${tp2:.2f}  R {rr2:.2f}\n"
        "TP3:       ${tp3:.2f}  R {rr3:.2f}\n"
        "Masas P:   {pc}    RSI14: {rsi:.0f}\n\n"
        "{qte}"
        "----\n"
        "Devuelve EXACTAMENTE 4 bullets ultra-cortos (max 250 palabras total):\n"
        "  1. Validez del setup (si/no + por que en una linea)\n"
        "  2. Mayor riesgo concreto al SL o al TP\n"
        "  3. Confirmacion tecnica que esperarias antes de entrar\n"
        "  4. Decision: Entrar / Esperar / Evitar + razon (1 linea)\n\n"
        "Texto plano. Sin parrafos largos. Numeros exactos cuando aplique."
    ).format(
        price=s.get("price", 0),
        bias=s.get("bias", "?"),
        dir=s.get("direction", "?").upper(),
        entry=s.get("entry", 0),
        sl=s.get("sl", 0),
        sla=s.get("sl_anchor", "estructura"),
        tp1=s.get("tp1", 0), rr1=s.get("rr_tp1", 0),
        tp2=s.get("tp2", 0), rr2=s.get("rr_tp2", 0),
        tp3=s.get("tp3", 0), rr3=s.get("rr_tp3", 0),
        pc=s.get("pspace_count", 0), rsi=s.get("rsi14", 0),
        qte=qte_block,
    )

def build_signal_prompt(s):
    """Co-pilot para senal auto-disparada (Opus) - el mas profundo"""
    decoh = s.get("decoherence", {})
    return (
        "SENAL FQ v5.1 AUTO-DISPARADA - REVISION FINAL ANTES DE EJECUTAR\n"
        "================================================================\n\n"
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
