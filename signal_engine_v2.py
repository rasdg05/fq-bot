# -*- coding: utf-8 -*-
"""
================================================================================
  SIGNAL ENGINE v2 - FQ v5.1 Mistral Emergent Time Edition
  Disparo de senales arreglado con macro deslizante y eval continuo
================================================================================

  PROBLEMA RESUELTO (v3.1.x y v3.2.x):
    - Macro test era punto-a-punto (iloc[-1] vs iloc[-4])
      -> fallaba si BTC corregia entre velas
    - Eval solo en cierre de vela o min 12
      -> 13 oportunidades desperdiciadas por vela
    - Threshold 0.08% muy estricto en mercado lateral
    - Sin diagnostico granular de "cerca de disparar"

  SOLUCION v2:
    - Macro con ventana deslizante (max move en 4 velas, no punto-a-punto)
    - Threshold 0.05% (calibrado mas permisivo)
    - Eval cada minuto cuando hay setup en formacion
    - Diagnostico continuo en STATE para mostrar via /status
    - Logs estructurados para que veas exactamente por que no dispara
    - Cooldown reducido a 1h
    - Heartbeat con resumen cada hora

  El gate Theta(D) sigue siendo veto absoluto. Solo afinamos:
    - QUE constituye "macro decoherente"
    - CUANDO evaluamos el gate
    - COMO reportamos el resultado
================================================================================
"""
import logging
import traceback
import pandas as pd
from datetime import datetime, timezone, timedelta

log = logging.getLogger("fq_signal_v2")

# ============================================================
# CONFIG NUEVO (override del bot)
# ============================================================
# Estos valores reemplazan los del bot principal cuando se importa este modulo
MACRO_THRESHOLD_PCT_V2  = 0.0005    # 0.05% (vs 0.08% antes)
INTRA_CANDLE_MINUTES_V2 = 7         # eval temprano (vs 12)
EVAL_EVERY_N_MINUTES    = 2         # eval cada 2 min cuando hay momentum
SIGNAL_COOLDOWN_HOURS_V2 = 1        # cooldown reducido (vs 2h)
HEARTBEAT_INTERVAL_MIN  = 60        # log resumen cada hora

# ============================================================
# MACRO TEST CALIBRADO - VENTANA DESLIZANTE
# ============================================================
def test_macro_v2(fetch_ohlcv_fn, exchange, symbol_btc, symbol_eth):
    """
    Macro test con ventana deslizante:
    - Toma el rango de las ultimas 4 velas (1h en 15m)
    - Compara precio actual vs ese rango
    - Direccion bull si precio > min reciente con momentum >= threshold
    - Direccion bear si precio < max reciente con momentum >= threshold
    """
    out = {
        "passed":     False,
        "direction":  None,
        "btc_change": 0.0,
        "eth_change": 0.0,
        "btc_bull":   0.0,
        "btc_bear":   0.0,
        "eth_bull":   0.0,
        "eth_bear":   0.0,
        "diagnostic": "",
    }
    try:
        btc = fetch_ohlcv_fn(exchange, symbol_btc, "15m", limit=20)
        eth = fetch_ohlcv_fn(exchange, symbol_eth, "15m", limit=20)

        # Ventana 4 velas anteriores como base, vela actual como punto
        btc_base_low  = float(btc["close"].iloc[-6:-2].min())
        btc_base_high = float(btc["close"].iloc[-6:-2].max())
        btc_now       = float(btc["close"].iloc[-1])

        eth_base_low  = float(eth["close"].iloc[-6:-2].min())
        eth_base_high = float(eth["close"].iloc[-6:-2].max())
        eth_now       = float(eth["close"].iloc[-1])

        # Momentum bull: cuanto subio desde el minimo reciente
        btc_bull = (btc_now - btc_base_low) / btc_base_low if btc_base_low > 0 else 0
        eth_bull = (eth_now - eth_base_low) / eth_base_low if eth_base_low > 0 else 0

        # Momentum bear: cuanto bajo desde el maximo reciente
        btc_bear = (btc_base_high - btc_now) / btc_base_high if btc_base_high > 0 else 0
        eth_bear = (eth_base_high - eth_now) / eth_base_high if eth_base_high > 0 else 0

        out["btc_bull"] = btc_bull * 100
        out["btc_bear"] = btc_bear * 100
        out["eth_bull"] = eth_bull * 100
        out["eth_bear"] = eth_bear * 100

        # Reportar el movimiento dominante (display)
        if btc_now >= btc_base_low + (btc_base_high - btc_base_low) / 2:
            btc_display = btc_bull * 100
        else:
            btc_display = -btc_bear * 100
        if eth_now >= eth_base_low + (eth_base_high - eth_base_low) / 2:
            eth_display = eth_bull * 100
        else:
            eth_display = -eth_bear * 100
        out["btc_change"] = btc_display
        out["eth_change"] = eth_display

        # Decision
        if btc_bull >= MACRO_THRESHOLD_PCT_V2 and eth_bull >= MACRO_THRESHOLD_PCT_V2:
            out["passed"] = True
            out["direction"] = "long"
            out["diagnostic"] = "BULL: BTC+{:.3f}% ETH+{:.3f}%".format(btc_bull*100, eth_bull*100)
        elif btc_bear >= MACRO_THRESHOLD_PCT_V2 and eth_bear >= MACRO_THRESHOLD_PCT_V2:
            out["passed"] = True
            out["direction"] = "short"
            out["diagnostic"] = "BEAR: BTC-{:.3f}% ETH-{:.3f}%".format(btc_bear*100, eth_bear*100)
        else:
            # No pasa, pero diagnostico de que tan cerca esta
            best_bull = min(btc_bull, eth_bull) * 100
            best_bear = min(btc_bear, eth_bear) * 100
            need = MACRO_THRESHOLD_PCT_V2 * 100
            if best_bull > best_bear:
                gap = need - best_bull
                out["diagnostic"] = "MACRO bull falta {:.3f}% (have BTC+{:.3f}% ETH+{:.3f}%)".format(
                    gap, btc_bull*100, eth_bull*100)
            else:
                gap = need - best_bear
                out["diagnostic"] = "MACRO bear falta {:.3f}% (have BTC-{:.3f}% ETH-{:.3f}%)".format(
                    gap, btc_bear*100, eth_bear*100)

    except Exception as e:
        log.error("test_macro_v2 error: {}".format(e))
        out["diagnostic"] = "ERROR: " + str(e)[:80]
    return out

# ============================================================
# EVALUATE WITH FULL DIAGNOSTICS
# ============================================================
def evaluate_setup_diagnostic(
    exchange, symbol, timeframe, fetch_ohlcv_fn, add_indicators_fn,
    test_technical_fn, test_liquidity_fn, detect_pspace_fn, laplacian_check_fn,
    calculate_levels_fn, build_signal_msg_fn, telegram_send_fn,
    get_session_fn, kappa_evo_fn, log_signal_fn,
    state, config_const, intra=False
):
    """
    Evaluate completo con diagnostico granular en cada gate.

    config_const dict contiene:
        SYMBOL_BTC, SYMBOL_ETH, PHI, PMASTER_MIN, RR_MIN_TP_DIVINO,
        TECH_MIN_ALIGNED, PSPACE_MIN_MASSES, MACRO_THRESHOLD_PCT
    """
    diagnostic = {
        "stage":       "init",
        "macro":       None,
        "tecnica":     None,
        "liquidez":    None,
        "pspace":      None,
        "lap":         None,
        "p_master":    None,
        "p_master_raw": None,
        "kappa_evo":   None,
        "rr_tp3":      None,
        "passed":      False,
        "direction":   None,
        "reason":      "",
    }

    try:
        df = fetch_ohlcv_fn(exchange, symbol, timeframe, limit=200)
        df = add_indicators_fn(df)
        if len(df) < 50:
            diagnostic["reason"] = "Datos insuficientes ({})".format(len(df))
            return False, diagnostic

        price = float(df["close"].iloc[-1])
        diagnostic["price"] = price

        with state.lock:
            state.last_sol_price = price
            state.last_eval_ts   = datetime.now(timezone.utc)

        session, w_clock, _, _ = get_session_fn()
        diagnostic["session"] = session
        diagnostic["w_clock"] = w_clock

        # ===== GATE 1: MACRO =====
        diagnostic["stage"] = "macro"
        macro = test_macro_v2(
            fetch_ohlcv_fn, exchange,
            config_const["SYMBOL_BTC"], config_const["SYMBOL_ETH"]
        )
        diagnostic["macro"] = macro

        with state.lock:
            state.last_btc_chg = macro["btc_change"]
            state.last_eth_chg = macro["eth_change"]

        if not macro["passed"]:
            diagnostic["reason"] = macro["diagnostic"]
            return False, diagnostic

        direction = macro["direction"]
        diagnostic["direction"] = direction

        # ===== GATE 2: TECNICA =====
        diagnostic["stage"] = "tecnica"
        tecnica = test_technical_fn(df, direction)
        diagnostic["tecnica"] = tecnica

        if not tecnica["passed"]:
            diagnostic["reason"] = "TEC FAIL {}/{} (need>={})  dir={}".format(
                tecnica["aligned"], tecnica["total"],
                config_const["TECH_MIN_ALIGNED"], direction)
            return False, diagnostic

        # ===== GATE 3: LIQUIDEZ =====
        diagnostic["stage"] = "liquidez"
        liquidez = test_liquidity_fn(df, direction)
        diagnostic["liquidez"] = liquidez

        if not liquidez["passed"]:
            diagnostic["reason"] = "LIQ FAIL RSI {:.0f}/{:.0f}/{:.0f} dir={}".format(
                liquidez["rsi6"], liquidez["rsi12"], liquidez["rsi24"], direction)
            return False, diagnostic

        # ===== GATE 4: P-SPACE =====
        diagnostic["stage"] = "pspace"
        masses = detect_pspace_fn(df)
        diagnostic["pspace"] = {"count": masses["count"]}

        if not masses["passed"]:
            diagnostic["reason"] = "PSPACE FAIL {} masas (need>={})".format(
                masses["count"], config_const["PSPACE_MIN_MASSES"])
            return False, diagnostic

        # ===== MODULADORES =====
        diagnostic["stage"] = "moduladores"
        lap = laplacian_check_fn(df)
        h_factor = 1.0 if lap["active"] else 0.7
        diagnostic["lap"] = {"active": lap["active"], "ratio": lap["ratio"]}

        # P_master raw (formula original)
        p_master_raw = config_const["PHI"] * w_clock * h_factor
        p_master_raw *= 1 + (masses["count"] - 2) * 0.15
        diagnostic["p_master_raw"] = p_master_raw

        # kappa_evo
        kappa_evo = 1.0
        if kappa_evo_fn:
            try:
                kappa_evo, bucket_stats = kappa_evo_fn(
                    session, p_master_raw, direction, masses
                )
                diagnostic["kappa_evo"] = kappa_evo
                diagnostic["bucket_stats"] = bucket_stats
            except Exception as e:
                log.warning("kappa_evo error: {}".format(e))

        p_master = p_master_raw * kappa_evo
        diagnostic["p_master"] = p_master

        if p_master < config_const["PMASTER_MIN"]:
            diagnostic["reason"] = (
                "P_master {:.2f} < {:.2f} (raw={:.2f} k={:.3f} W={:.2f})".format(
                    p_master, config_const["PMASTER_MIN"],
                    p_master_raw, kappa_evo, w_clock)
            )
            return False, diagnostic

        # ===== R:R CHECK =====
        diagnostic["stage"] = "rr"
        levels = calculate_levels_fn(df, direction)
        diagnostic["rr_tp3"] = levels["rr_tp3"]
        diagnostic["levels"] = levels

        if levels["rr_tp3"] < config_const["RR_MIN_TP_DIVINO"]:
            diagnostic["reason"] = "RR FAIL tp3={:.2f} < {:.2f}".format(
                levels["rr_tp3"], config_const["RR_MIN_TP_DIVINO"])
            return False, diagnostic

        # ===== TODOS LOS GATES PASADOS - DISPARAR =====
        diagnostic["stage"] = "fired"
        diagnostic["passed"] = True
        diagnostic["reason"] = "SENAL DISPARADA"

        decoh = {"macro": macro, "tecnica": tecnica, "liquidez": liquidez}
        msg = build_signal_msg_fn(direction, levels, decoh, masses,
                                  session, w_clock, p_master, lap, intra)
        if telegram_send_fn(msg):
            with state.lock:
                state.last_signal_ts     = datetime.now(timezone.utc)
                state.last_signal_dir    = direction
                state.last_signal_price  = levels["entry"]
                state.last_signal_levels = levels
                state.signals_today     += 1
                state.signals_total     += 1
                state.last_eval_result   = "SENAL: {} @ ${:.2f} P={:.2f}".format(
                    direction.upper(), levels["entry"], p_master)

            # Log al ledger evolutivo
            if log_signal_fn:
                try:
                    log_signal_fn(
                        direction, levels, p_master_raw, p_master,
                        kappa_evo, session, w_clock, masses,
                        macro, liquidez, tecnica, lap, intra
                    )
                except Exception as e:
                    log.error("Ledger log error: {}".format(e))

            return True, diagnostic
        else:
            diagnostic["reason"] = "Telegram send failed"
            return False, diagnostic

    except Exception as e:
        log.error("evaluate_setup_diagnostic: {}\n{}".format(e, traceback.format_exc()))
        diagnostic["reason"] = "EXCEPTION: " + str(e)[:120]
        return False, diagnostic

# ============================================================
# DIAGNOSTIC FORMATTERS
# ============================================================
def format_diagnostic_short(d):
    """Una linea para log"""
    if d.get("passed"):
        return "FIRED ${:.2f} {} P={:.2f}".format(
            d.get("price", 0), d.get("direction", "?").upper(), d.get("p_master", 0))

    stage = d.get("stage", "?")
    reason = d.get("reason", "")
    return "EVAL ${:.2f} W={:.2f} stage={} | {}".format(
        d.get("price", 0), d.get("w_clock", 0), stage, reason)

def format_diagnostic_telegram(d):
    """Para mostrar en /status detallado"""
    if d.get("passed"):
        return "Ultima eval: SENAL DISPARADA"

    lines = ["<b>ULTIMA EVALUACION</b>"]
    lines.append("Stage alcanzado: <b>{}</b>".format(d.get("stage", "?").upper()))
    lines.append("Precio: ${:.2f}  Sesion: {} W={:.2f}".format(
        d.get("price", 0), d.get("session", "?"),
        d.get("w_clock", 0)))
    lines.append("Razon: {}".format(d.get("reason", "")))

    if d.get("macro"):
        m = d["macro"]
        lines.append("")
        lines.append("Macro:")
        lines.append("  BTC bull: {:.3f}% / bear: {:.3f}%".format(
            m.get("btc_bull", 0), m.get("btc_bear", 0)))
        lines.append("  ETH bull: {:.3f}% / bear: {:.3f}%".format(
            m.get("eth_bull", 0), m.get("eth_bear", 0)))
        lines.append("  Need: {:.3f}% en ambos, misma direccion".format(
            MACRO_THRESHOLD_PCT_V2 * 100))

    if d.get("p_master") is not None:
        lines.append("")
        lines.append("P_master: {:.3f}  (raw {:.3f} * k_evo {:.3f})".format(
            d.get("p_master", 0), d.get("p_master_raw", 0), d.get("kappa_evo", 1)))

    return "\n".join(lines)

# ============================================================
# CONTINUOUS EVAL LOOP HELPER
# ============================================================
class ContinuousEvalState:
    """
    Mantiene estado del loop de evaluacion continuo.
    Decide si toca evaluar en este tick basado en:
    - Vela nueva (siempre eval)
    - Min 7 intra-vela (eval temprano)
    - Cada N min si hubo casi-disparo en la previa (eval continuo)
    """
    def __init__(self):
        self.last_candle_ts        = None
        self.last_intra_ts         = None
        self.last_continuous_ts    = None
        self.last_signal_ts        = None
        self.last_diagnostic       = None
        self.near_miss_streak      = 0
        self.last_heartbeat_ts     = None

    def should_eval(self, current_candle_ts, elapsed_minutes):
        """Devuelve (eval: bool, reason: str, intra: bool)"""
        # Vela nueva
        if self.last_candle_ts is None or current_candle_ts > self.last_candle_ts:
            return True, "new_candle", False

        # Intra-vela temprana (min 7)
        if (elapsed_minutes >= INTRA_CANDLE_MINUTES_V2 and
            self.last_intra_ts != current_candle_ts):
            return True, "intra_min7", True

        # Eval continuo si hubo casi-disparo
        if self.near_miss_streak > 0:
            now_utc = datetime.now(timezone.utc)
            if (self.last_continuous_ts is None or
                (now_utc - self.last_continuous_ts).total_seconds() >= EVAL_EVERY_N_MINUTES * 60):
                return True, "continuous_near_miss", True

        return False, "wait", False

    def update_post_eval(self, current_candle_ts, reason, diagnostic, fired):
        now_utc = datetime.now(timezone.utc)
        if reason == "new_candle":
            self.last_candle_ts = current_candle_ts
            self.last_intra_ts  = None
        elif reason == "intra_min7":
            self.last_intra_ts = current_candle_ts
        elif reason == "continuous_near_miss":
            self.last_continuous_ts = now_utc

        self.last_diagnostic = diagnostic

        # Track near-miss: si paso macro pero fallo despues, sigue intentando
        if fired:
            self.last_signal_ts = now_utc
            self.near_miss_streak = 0
        elif diagnostic and diagnostic.get("stage") in ("p_master", "rr", "moduladores"):
            self.near_miss_streak = min(5, self.near_miss_streak + 1)
        elif diagnostic and diagnostic.get("stage") == "macro":
            self.near_miss_streak = max(0, self.near_miss_streak - 1)

    def in_cooldown(self):
        if self.last_signal_ts is None:
            return False, 0
        delta = datetime.now(timezone.utc) - self.last_signal_ts
        cooldown = timedelta(hours=SIGNAL_COOLDOWN_HOURS_V2)
        if delta < cooldown:
            rem = cooldown - delta
            return True, int(rem.total_seconds() / 60)
        return False, 0

    def should_heartbeat(self):
        now_utc = datetime.now(timezone.utc)
        if (self.last_heartbeat_ts is None or
            (now_utc - self.last_heartbeat_ts).total_seconds() >= HEARTBEAT_INTERVAL_MIN * 60):
            self.last_heartbeat_ts = now_utc
            return True
        return False
