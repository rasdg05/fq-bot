# -*- coding: utf-8 -*-
"""
================================================================================
  LA LECTURA — co-piloto de lectura de mercado por sesion
  by RasDG_Sol + Claude
================================================================================
Compone los motores PUROS del taller en UNA lectura, para que VOS decidas:

  · DONDE va la liquidez   -> ict_smc (estructura/PD) + liquidity_magnet (imanes)
  · CUANDO estas parado    -> killzones_pd (killzone) + session_bias (sesion macro)
  · si el movimiento es REAL-> volume_quality (volumen + franjas muertas)
  · DONDE sentarte a esperar-> battle_planner (zonas candidatas: OB / FVG / pool)

NO dispara, NO ejecuta, NO predice el futuro. Lee el presente y lo ORDENA.
Es instrumento, no autopiloto — lo unico que sobrevivio a los tests honestos.

  build_lectura(...)  es PURO (inyecta `now_cdmx`) -> testeable sin red.
  fetch_dfs(...)      es el unico I/O (OKX publico, sin API key).

Uso:
    python lectura.py [SYMBOL]          # default SOL-USDT-SWAP
================================================================================
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools"))

from datetime import datetime

import pandas as pd

import ict_smc
import liquidity_magnet as lm
import killzones_pd as kz
import session_bias as sb
import volume_quality as vq
import battle_planner as bp

DEFAULT_SYMBOL = "SOL-USDT-SWAP"
# OKX bar codes por timeframe (minutos minuscula, horas mayuscula)
TIMEFRAMES = {"1m": ("1m", 200), "15m": ("15m", 300), "1h": ("1H", 300), "4h": ("4H", 200)}


# ============================================================
# INDICADORES (atr14 + ema50 sin pandas_ta — robusto en cualquier entorno)
# ============================================================
def _ensure_indicators(df):
    if df is None or df.empty:
        return df
    df = df.copy()
    h, l, c = df["high"].astype(float), df["low"].astype(float), df["close"].astype(float)
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=1).mean()
    df["ema50"] = c.ewm(span=50, adjust=False).mean()
    df["vol_ma20"] = df["volume"].rolling(20, min_periods=1).mean()
    return df


def _fetch_recent(symbol, bar, limit=300):
    """Velas recientes CERRADAS (OKX /market/candles, hasta 300 en 1 llamada).
    Descarta la vela en formacion para que los indicadores usen barras cerradas."""
    import json
    import urllib.request
    url = ("https://www.okx.com/api/v5/market/candles?instId=%s&bar=%s&limit=%d"
           % (symbol, bar, limit))
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read()).get("data", [])
    rows = []
    for c in data:                       # [ts,o,h,l,c,vol,...,confirm]
        if len(c) > 8 and c[8] == "0":   # vela en formacion -> fuera
            continue
        rows.append((int(c[0]), float(c[1]), float(c[2]), float(c[3]),
                     float(c[4]), float(c[5])))
    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def fetch_dfs(symbol):
    """I/O: baja 1m/15m/1h/4h de OKX (publico) y agrega indicadores."""
    out = {}
    for key, (bar, _n) in TIMEFRAMES.items():
        out[key] = _ensure_indicators(_fetch_recent(symbol, bar, 300))
    return out


# ============================================================
# COMPOSER (PURO)
# ============================================================
def build_lectura(symbol, df_15m, df_1h, df_4h, df_1m=None, now_cdmx=None):
    """Compone la lectura completa. PURO salvo `now_cdmx` (inyectable)."""
    now_cdmx = now_cdmx or datetime.now(kz.CDMX_TZ)
    if df_15m is None or len(df_15m) < 30:
        return {"symbol": symbol, "error": "datos insuficientes (15m)", "now_cdmx": now_cdmx}

    price = float(df_15m["close"].iloc[-1])

    # --- 1) SESION / TIEMPO ---
    weekend = kz.weekend_status()
    killzone = kz.current_killzone(now_cdmx)
    legacy_sess, legacy_w = kz.get_legacy_session(now_cdmx)
    macro_sess = sb.session_from_killzone(killzone["name"])
    dead = vq.is_dead_window(now_cdmx)
    dead_label = vq.dead_window_label(now_cdmx)

    # --- 2) ESTRUCTURA (field ICT/SMC) ---
    field = ict_smc.read_field(df_15m, df_1h, df_4h, df_1m, {}, None)
    field.killzone = killzone["name"]                 # read_field no llena el timing
    field.killzone_priority = killzone["priority"]
    field.w_killzone = killzone["w_kz"]
    field.minutes_in_kz = killzone["minutes_in_kz"]
    field.minutes_to_next_kz = killzone["minutes_to_next_kz"]
    proposed = field.propose_direction()
    actionable, why_not = field.is_actionable()

    # --- 3) IMANES (hacia que liquidez va el precio) ---
    cloud = lm.ma_cloud(df_15m)
    mode, mode_dir = lm.context_mode(cloud)
    vwap = lm.daily_vwap(df_15m)
    magnets = sorted(lm.enumerate_magnets(df_15m, field, price),
                     key=lambda m: abs(m.price - price))

    # --- 4) CONTEXTO (volumen real?) ---
    vol = vq.volume_score(df_15m)
    vol_label = vq.volume_quality_label(vol["score"])

    # --- 5) SESION x DIRECCION (la tesis de sesiones aplicada) ---
    dir_used = proposed or mode_dir
    session_weight = session_label = None
    if dir_used:
        session_weight, session_label, _ = sb.session_bias_weight_from_field(field, dir_used)

    # --- 6) ZONAS CANDIDATAS (donde sentarse a esperar) ---
    atr_val = df_15m["atr14"].iloc[-1]
    atr = float(atr_val) if pd.notna(atr_val) else price * 0.005
    field_data = {
        "ob_bullish": field.order_blocks.get("bullish"),
        "ob_bearish": field.order_blocks.get("bearish"),
        "pool_high": field.pool_high,
        "pool_low": field.pool_low,
        "fvgs": field.fvgs,
        "ema50": float(df_15m["ema50"].iloc[-1]) if "ema50" in df_15m.columns else None,
    }
    zones = []
    if dir_used:
        zones = sorted(bp.extract_candidate_zones(dir_used, price, field_data, atr),
                       key=lambda z: abs(z["ref"] - price))

    return {
        "symbol": symbol, "price": price, "now_cdmx": now_cdmx, "error": None,
        "weekend": weekend, "killzone": killzone, "macro_session": macro_sess,
        "legacy_session": legacy_sess, "legacy_weight": legacy_w,
        "dead": dead, "dead_label": dead_label,
        "field": field, "proposed_dir": proposed, "actionable": actionable, "why_not": why_not,
        "cloud": cloud, "mode": mode, "mode_dir": mode_dir, "vwap": vwap, "magnets": magnets,
        "tension": bool(proposed and mode_dir and proposed != mode_dir),
        "vol": vol, "vol_label": vol_label,
        "session_weight": session_weight, "session_label": session_label,
        "dir_used": dir_used, "zones": zones, "atr": atr,
    }


# ============================================================
# VEREDICTO (lenguaje natural, honesto — NO una orden)
# ============================================================
def _verdict(L):
    f, price = L["field"], L["price"]
    if L["weekend"]["closed"]:
        return "Mercado cerrado (fin de semana). Descansá — esto vuelve el domingo."
    parts = []

    if f.bias_4h == "rango":
        parts.append("Sesgo macro 4H en RANGO: sin direccion estructural. Terreno de barridos "
                     "a ambos lados — el bot calla, no le impongas direccion.")
    elif L["dir_used"]:
        d = "LONG" if L["dir_used"] == "long" else "SHORT"
        side = "above" if L["dir_used"] == "long" else "below"
        nxt = next((m for m in L["magnets"] if m.side == side), None)
        nxt_s = ("proximo iman %s en %.4f (%+.2f%%)" % (nxt.note, nxt.price, (nxt.price / price - 1) * 100)
                 if nxt else "sin iman claro en esa direccion")
        z = L["zones"][0] if L["zones"] else None
        z_s = ("zona candidata: %s @ %.4f%s" % (z["label"], z["ref"],
               " (espera barrido+reclamo)" if z["needs_sweep"] else "")
               if z else "sin zona candidata limpia todavia")
        align = "alineado 4H+1H" if f.bias_aligned else "1H aun no confirma"
        parts.append("El campo se inclina %s: sesgo %s (%s), PD %s. %s. %s." % (
            d, f.bias_4h, align, f.pd_zone, nxt_s, z_s))
    else:
        parts.append("Sesgo %s pero PD en %s (sin discount/premium claro). Paciencia: "
                     "espera a que el precio busque la zona correcta." % (f.bias_4h, f.pd_zone))

    if not L["actionable"] and L["why_not"]:
        parts.append("Aviso: %s." % L["why_not"])

    if L.get("tension"):
        parts.append("Tension: el cloud de MAs lee continuacion %s (precio del otro lado de "
                     "las medias) mientras la estructura macro pide %s — espera a que una gane, "
                     "no fuerces el lado." % (L["mode_dir"], L["proposed_dir"]))

    kzn = L["killzone"]["name"]
    if kzn == "fuera":
        parts.append("Fuera de killzone (%s en ~%d'). Sin prisa: observa, no persigas." % (
            L["killzone"].get("next_kz_name", "?"), L["killzone"]["minutes_to_next_kz"]))
    else:
        parts.append("Killzone %s (prioridad %s) activa — ventana de atencion." % (
            kzn, L["killzone"]["priority"]))

    if L["dead"]:
        parts.append("Franja muerta (%s): desconfia de los movimientos, suelen ser manipulacion." %
                     (L["dead_label"] or "horario flojo"))
    elif L["vol"]["score"] < 0.8:
        parts.append("Volumen %s (%.2fx): poca conviccion detras del precio." % (
            L["vol_label"], L["vol"]["score"]))
    elif L["vol"].get("is_climax"):
        parts.append("Vela climax (vol %.2fx + cuerpo grande): ojo a exhaustion/reversion." %
                     L["vol"]["score"])

    return " ".join(parts)


# ============================================================
# RENDER (texto para CLI — puro)
# ============================================================
def _arrow(side):
    return "↑" if side == "above" else "↓"


def render(L):
    if L.get("error"):
        return "LA LECTURA · %s — %s" % (L["symbol"], L["error"])
    f = L["field"]
    price = L["price"]
    t = L["now_cdmx"]
    dow = ["lun", "mar", "mie", "jue", "vie", "sab", "dom"][t.weekday()]
    W = 60
    out = []
    out.append("=" * W)
    out.append("  LA LECTURA · %s · %.4f · %02d:%02d CDMX (%s)" % (
        L["symbol"], price, t.hour, t.minute, dow))
    out.append("=" * W)

    # SESION
    out.append("")
    out.append("[ SESION ]")
    kzd = L["killzone"]
    if kzd["name"] == "fuera":
        out.append("   Killzone : fuera · proxima (%s) en ~%d'" % (
            kzd.get("next_kz_name", "?"), kzd["minutes_to_next_kz"]))
    else:
        out.append("   Killzone : %s (prioridad %s) · %d' dentro · termina en ~%d'" % (
            kzd["name"], kzd["priority"], kzd["minutes_in_kz"], kzd["minutes_to_next_kz"]))
    out.append("   Macro    : %s   ·   legacy: %s (%.2f)" % (
        L["macro_session"], L["legacy_session"], L["legacy_weight"]))
    out.append("   Estado   : %s" % L["weekend"]["reason"])

    # ESTRUCTURA
    out.append("")
    out.append("[ ESTRUCTURA ]")
    out.append("   Sesgo    : 4H %s · 1H %s · %s" % (
        f.bias_4h, f.bias_1h, "ALINEADO" if f.bias_aligned else "desalineado"))
    out.append("   PD zone  : %s (%.0f%%) · rango %.4f – %.4f (eq %.4f)" % (
        f.pd_zone, f.pd_pct * 100, f.range_low, f.range_high, f.equilibrium))
    out.append("   Campo    : propone %s · confluencias %d · jerarquia %s" % (
        (L["proposed_dir"] or "—").upper(), f.confluence_count, f.pd_hierarchy))
    if not L["actionable"] and L["why_not"]:
        out.append("   Aviso    : %s" % L["why_not"])

    # IMANES
    out.append("")
    out.append("[ IMANES · hacia donde va la liquidez ]")
    tens = "   ⚠ TENSION con la estructura" if L.get("tension") else ""
    out.append("   Cloud    : %s%s%s" % (
        L["mode"], (" -> " + L["mode_dir"]) if L["mode_dir"] else "", tens))
    out.append("   VWAP dia : %s" % ("%.4f" % L["vwap"] if L["vwap"] else "—"))
    if L["magnets"]:
        out.append("   Cercanos :")
        for m in L["magnets"][:6]:
            out.append("     %s %.4f  (%+.2f%%)  %s" % (
                _arrow(m.side), m.price, (m.price / price - 1) * 100, m.note))
    else:
        out.append("   Cercanos : sin imanes identificables")

    # CONTEXTO
    out.append("")
    out.append("[ CONTEXTO ]")
    climax = " · CLIMAX" if L["vol"].get("is_climax") else ""
    out.append("   Volumen  : %s (%.2fx)%s" % (L["vol_label"], L["vol"]["score"], climax))
    if L["dead"]:
        out.append("   Franja   : MUERTA (%s)" % (L["dead_label"] or "horario flojo"))
    if L["session_weight"] is not None:
        out.append("   Sesion×dir: peso %.2f — \"%s\"" % (L["session_weight"], L["session_label"]))

    # ZONAS
    if L["dir_used"]:
        out.append("")
        out.append("[ ZONAS CANDIDATAS · donde sentarte a esperar · %s ]" % L["dir_used"].upper())
        if L["zones"]:
            for z in L["zones"][:4]:
                sweep = "  (barrido+reclamo)" if z["needs_sweep"] else ""
                out.append("     • %-22s @ %.4f   SL %.4f%s" % (
                    z["label"], z["ref"], z["sl"], sweep))
        else:
            out.append("     (ninguna zona limpia en el lado favorable todavia)")

    # VEREDICTO
    out.append("")
    out.append("[ LA LECTURA ]")
    verdict = _verdict(L)
    for line in _wrap(verdict, W - 6):
        out.append("   " + line)
    out.append("")
    out.append("   — Vos decidis. Esto es lectura, no orden.")
    out.append("=" * W)
    return "\n".join(out)


def _wrap(text, width):
    words, line, lines = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(line)
            line = w
        else:
            line = (line + " " + w) if line else w
    if line:
        lines.append(line)
    return lines


# ============================================================
# CLI
# ============================================================
def main(argv):
    symbol = argv[1] if len(argv) > 1 else DEFAULT_SYMBOL
    print("[lectura] bajando datos de %s (OKX)..." % symbol, file=sys.stderr)
    dfs = fetch_dfs(symbol)
    L = build_lectura(symbol, dfs["15m"], dfs["1h"], dfs["4h"], dfs["1m"])
    print(render(L))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
