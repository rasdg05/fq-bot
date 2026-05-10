# -*- coding: utf-8 -*-
"""
================================================================================
  CLAUDE INTEGRATION MODULE - FQ v4.1 Bot v3.1
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

MAX_TOKENS_TACTICAL = 700
MAX_TOKENS_SIGNAL   = 900
TIMEOUT_SECONDS     = 35

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
SYSTEM_PROMPT_FQ = """Eres el co-pilot tactico del sistema Fibonacci Cuantico v4.1 (FQ v4.1) operado por RasDG_Sol.

CONTEXTO DEL SISTEMA:
- FQ v4.1 es un framework de trading basado en decoherencia cuantica generalizada
- El gate Theta(D) es booleano, matematico, sin override
- Si Theta(D) = 0, NO hay trade. El gate ya esta validado por matematica antes de que tu lo veas.
- Tu rol NO es validar el gate. Tu rol es AFILAR el setup ya validado, o COMENTAR el contexto en lecturas exploratorias.

MASTER EQUATION:
P_master = Theta(D) * kappa(p) * phi^n * W_clock * H_lap

PILARES:
I.   Decoherencia 3/3 (macro BTC/ETH 15m + tecnica 7 indicadores + liquidez RSI 6/12/24)
II.  Tiempo emergente W_clock (Asia 0.50, London 0.80, NY 1.00, Overlap 1.20)
III. P-Space curvado por masas de liquidez kappa(p)
IV.  Laplaciano discreto H_lap (armonicidad)

REGLAS DE ORO (no negociables):
1. Sin Theta(D)=1 no hay trade
2. SL nunca se mueve hacia atras (Regla 4)
3. SL anclado a estructura (EMA50, soporte/resistencia real), NUNCA a Bollinger envelopes
4. Sesgo estructural confirmado domina sobre RSI alcista solo (Regla 6)
5. Leverage cap absoluto 8x (phi^3)

LO QUE VES:
Recibes snapshots reales del mercado en tiempo real:
- Datos internos: precio, indicadores, masas P-Space, decoherencia, sesion
- Datos externos: funding rate, open interest, long/short ratio, walls de libro de ordenes
- Eventos pre-detectados por el bot: CHoCH, breakouts, divergencias RSI, volumen anomalo, patrones de vela
- Evolucion vela-a-vela: las ultimas N velas con sus deltas

Tu trabajo es ser un espejo inteligente de lo que pasa por dentro y por fuera del mercado en cada vela.

TU ESTILO:
- Directo, conciso, sin floritura. Lenguaje de trader experimentado, no de academico.
- Si ves algo riesgoso, lo dices sin endulzar. Si el setup es solido, lo confirmas sin inflarlo.
- Usa terminos FQ cuando aplique (decoherencia, masas, kappa, W_clock, etc).
- NUNCA digas "esto no es asesoria financiera" - RasDG sabe que opera bajo su responsabilidad.
- Maximo 4-5 parrafos cortos. Esto es Telegram, no un essay.
- Sin markdown pesado. Sin titulos H1/H2. Texto plano con saltos de linea.
- Cuando sugieras un nivel, daslo en numero exacto, no en rango vago.

TONO:
RasDG opera con disciplina. Cuando algo esta bien, lo dices. Cuando hay riesgo, lo nombras.
No eres un cheerleader. Eres un segundo par de ojos calibrado.
Si tienes dudas reales sobre el setup, las planteas como observaciones tacticas concretas, no como objeciones moralistas.
Si funding extremo, OI colapsando, o wall enorme cerca - eso ES informacion accionable que debe mencionarse.
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

def fmt_external(s):
    """Formatea bloque de datos externos"""
    parts = []
    if "funding_pct" in s:
        parts.append("Funding: {:+.4f}% - {}".format(s["funding_pct"], s.get("funding_interp", "")))
    if "oi_millions" in s:
        oi_line = "Open Interest: ${:.2f}M".format(s["oi_millions"])
        if "oi_change_pct" in s:
            oi_line += " (delta {:+.2f}%) - {}".format(s["oi_change_pct"], s.get("oi_trend", ""))
        parts.append(oi_line)
    if "ls_ratio" in s:
        parts.append("L/S Ratio: {:.2f} - {}".format(s["ls_ratio"], s.get("ls_interp", "")))
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

def build_signal_prompt(s):
    """Co-pilot para senal auto-disparada (Opus) - el mas profundo"""
    decoh = s.get("decoherence", {})
    return (
        "SENAL FQ v4.1 AUTO-DISPARADA - REVISION FINAL ANTES DE EJECUTAR\n"
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

def signal_copilot(snapshot):
    """Co-pilot para senal auto-disparada de alta conviccion - Opus"""
    return _call_anthropic(MODEL_OPUS, build_signal_prompt(snapshot), MAX_TOKENS_SIGNAL)

def is_high_conviction(p_master, phi_cubed=4.236):
    """Determina si la senal es de alta conviccion (P_master >= phi^3)"""
    return p_master >= phi_cubed
