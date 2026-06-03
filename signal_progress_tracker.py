# -*- coding: utf-8 -*-
"""
================================================================================
  SIGNAL PROGRESS TRACKER - alertas proactivas durante una senal activa
  by RasDG_Sol + Claude

  Sistema PARALELO al outcome tracker:
  - NO modifica el ledger (no cierra senales)
  - Solo detecta eventos intermedios (TP1/TP2/TP3 tocados) y manda alertas
  - Idempotente via UNIQUE(signal_id, event) en tabla signal_progress

  Eventos emitidos:
    tp1_hit            -> precio alcanzo TP1 (sugiere mover SL a BE)
    tp2_hit            -> precio alcanzo TP2 (sugiere parcial)
    tp3_hit            -> precio alcanzo TP3 (sugiere trailing)
    be_suggested       -> 1+ vela despues de tp1_hit y precio aun cerca
    partial_suggested  -> emitido junto con tp2_hit
================================================================================
"""
import logging
import sqlite3
from datetime import datetime, timezone

import entropy_cognition as ev

log = logging.getLogger("fq_progress")

try:
    import pandas as pd
except ImportError:
    pd = None

# Orden de eventos por TP. Si en una vela hi cruza TP3, tambien implica TP1+TP2.
_LONG_TP_FIELDS  = [("tp1_hit", "tp1"), ("tp2_hit", "tp2"), ("tp3_hit", "tp3")]
_SHORT_TP_FIELDS = [("tp1_hit", "tp1"), ("tp2_hit", "tp2"), ("tp3_hit", "tp3")]

# ============================================================
# QUERIES A signal_progress
# ============================================================
def _connect():
    conn = sqlite3.connect(ev.DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def get_sent_events(signal_id):
    """Retorna set de eventos ya enviados para esta senal."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT event FROM signal_progress WHERE signal_id=?",
            (int(signal_id),)
        ).fetchall()
        return set(r["event"] for r in rows)
    finally:
        conn.close()

def mark_progress_event(signal_id, event, price):
    """INSERT OR IGNORE - idempotente. Devuelve True si se inserto, False si ya existia."""
    conn = _connect()
    try:
        cur = conn.execute("""
            INSERT OR IGNORE INTO signal_progress
                (signal_id, event, ts_event, price)
            VALUES (?, ?, ?, ?)
        """, (int(signal_id), event,
              datetime.now(timezone.utc).isoformat(),
              float(price) if price is not None else None))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()

# ============================================================
# DETECCION DE EVENTOS CONTRA VELAS
# ============================================================
def post_emission_candles(df, ts_emitted_str):
    """Subset de velas posteriores a la emision de la senal.

    Robusto a zona horaria: fetch_ohlcv produce timestamps NAIVE (UTC), pero
    ts_emitted suele venir con offset (+00:00). Comparar naive vs tz-aware lanza
    TypeError en pandas 2.x (y el aviso de progreso se perdia en silencio). Aqui
    alineamos la tz del corte a la de la columna antes de filtrar.
    """
    if pd is None or df is None or len(df) == 0:
        return None
    try:
        ts_em = datetime.fromisoformat(ts_emitted_str)
    except Exception:
        return None
    ts_ts = pd.Timestamp(ts_em)
    col = df["timestamp"]
    col_tz = getattr(col.dtype, "tz", None)
    if col_tz is not None:
        # Columna tz-aware -> corte tz-aware en UTC.
        ts_ts = (ts_ts.tz_localize("UTC") if ts_ts.tzinfo is None
                 else ts_ts.tz_convert("UTC"))
    else:
        # Columna naive (UTC) -> corte naive (descartar tz tras normalizar a UTC).
        if ts_ts.tzinfo is not None:
            ts_ts = ts_ts.tz_convert("UTC").tz_localize(None)
    return df[col > ts_ts]


def check_progress_events(signal_row, df, sent=None):
    """
    Dado una senal abierta y df reciente, devuelve lista de eventos NUEVOS no enviados.
    Cada evento: (kind, price).

    No modifica el ledger ni cierra la senal - eso lo hace reconcile_outcomes.
    Solo TPs intermedios (no TP4, que ya implica cierre via outcome tracker).

    ``sent``: conjunto de eventos ya emitidos. Si es None se consulta la tabla
    signal_progress por signal_id (comportamiento clasico del ledger). El
    tactical_tracker pasa su propio set para reusar esta deteccion sin tocar
    la tabla del ledger.
    """
    df_post = post_emission_candles(df, signal_row["ts_emitted"])
    if df_post is None or len(df_post) == 0:
        return []

    direction = signal_row["direction"]
    tp1 = signal_row["tp1"]
    tp2 = signal_row["tp2"]
    tp3 = signal_row["tp3"]

    if sent is None:
        sent = get_sent_events(signal_row["id"])
    events = []

    # Buscamos en TODAS las velas post-emision el primer toque de cada TP
    hit = {"tp1_hit": None, "tp2_hit": None, "tp3_hit": None}
    for _, row in df_post.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if direction == "long":
            if hit["tp1_hit"] is None and hi >= tp1: hit["tp1_hit"] = tp1
            if hit["tp2_hit"] is None and hi >= tp2: hit["tp2_hit"] = tp2
            if hit["tp3_hit"] is None and hi >= tp3: hit["tp3_hit"] = tp3
        else:
            if hit["tp1_hit"] is None and lo <= tp1: hit["tp1_hit"] = tp1
            if hit["tp2_hit"] is None and lo <= tp2: hit["tp2_hit"] = tp2
            if hit["tp3_hit"] is None and lo <= tp3: hit["tp3_hit"] = tp3
        if all(v is not None for v in hit.values()):
            break

    for kind, price in hit.items():
        if price is not None and kind not in sent:
            events.append((kind, price))

    # be_suggested: si tp1_hit ya esta marcado en la BD (o lo acabamos de detectar)
    # y han pasado >=1 vela desde el primer touch, sugerir BE.
    tp1_already_sent = "tp1_hit" in sent
    tp1_just_detected = hit["tp1_hit"] is not None
    if (tp1_already_sent or tp1_just_detected) and "be_suggested" not in sent:
        if len(df_post) >= 2:
            events.append(("be_suggested", float(df_post["close"].iloc[-1])))

    # partial_suggested: junto con tp2_hit (mismo precio TP2)
    if hit["tp2_hit"] is not None and "partial_suggested" not in sent:
        events.append(("partial_suggested", hit["tp2_hit"]))

    return events

# ============================================================
# FORMATO DE ALERTAS
# ============================================================
_G = {
    "rule": "━" * 30,
    "title": "◆",
    "event": "▰",
    "act":   "▸",
    "chk":   "▪",
    "long":  "▴",
    "short": "▾",
}

def _side(direction):
    d = (direction or "").lower()
    return (_G["long"] if d == "long" else _G["short"]) + " " + d.upper()

def build_progress_alert(sig, event, price, label="Senal"):
    sid = sig["id"]
    side = _side(sig.get("direction"))

    if event == "tp1_hit":
        return "\n".join([
            _G["rule"],
            "  {} {} #{} · TP1 alcanzado".format(_G["event"], label, sid),
            _G["rule"],
            "  {} Direccion   {}".format(_G["act"], side),
            "  {} Precio      ${:.4f}".format(_G["act"], price),
            "  {} PnL parcial +1.00R".format(_G["act"]),
            "",
            "  Sugerencia operativa:",
            "  {} Mueve SL a entry (break-even)".format(_G["chk"]),
            "  {} Deja correr a TP2 / TP3".format(_G["chk"]),
            _G["rule"],
        ])

    if event == "tp2_hit":
        return "\n".join([
            _G["rule"],
            "  {} {} #{} · TP2 alcanzado".format(_G["event"], label, sid),
            _G["rule"],
            "  {} Direccion   {}".format(_G["act"], side),
            "  {} Precio      ${:.4f}".format(_G["act"], price),
            "  {} PnL parcial +2.00R aprox".format(_G["act"]),
            "",
            "  Sugerencia operativa:",
            "  {} Toma parcial 30-50%".format(_G["chk"]),
            "  {} Trailing SL bajo ultima estructura".format(_G["chk"]),
            _G["rule"],
        ])

    if event == "tp3_hit":
        return "\n".join([
            _G["rule"],
            "  {} {} #{} · TP3 alcanzado".format(_G["event"], label, sid),
            _G["rule"],
            "  {} Direccion   {}".format(_G["act"], side),
            "  {} Precio      ${:.4f}".format(_G["act"], price),
            "  {} PnL parcial +3.00R aprox".format(_G["act"]),
            "",
            "  Sugerencia operativa:",
            "  {} Trailing agresivo al swing previo".format(_G["chk"]),
            "  {} Resto corre a TP4 o se cierra al toque".format(_G["chk"]),
            _G["rule"],
        ])

    if event == "tp3_celebration":
        return build_tp3_celebration(sig, price)

    if event == "be_suggested":
        return "\n".join([
            _G["rule"],
            "  {} {} #{} · SL a break-even".format(_G["event"], label, sid),
            _G["rule"],
            "  {} Direccion   {}".format(_G["act"], side),
            "  TP1 confirmado.",
            "",
            "  El SL ya no deberia estar",
            "  donde lo pusiste en la entrada.",
            "  Muevelo a entry y duerme tranquilo.",
            _G["rule"],
        ])

    if event == "partial_suggested":
        return "\n".join([
            _G["rule"],
            "  {} {} #{} · Tomar parcial".format(_G["event"], label, sid),
            _G["rule"],
            "  {} Direccion   {}".format(_G["act"], side),
            "  TP2 tocado. Recomendacion:",
            "  cerrar 30-50% de la posicion.",
            "",
            "  Lo que queda corre a TP3/TP4",
            "  con SL ya en zona de profit.",
            _G["rule"],
        ])

    return "Progress event #{}: {} @ ${:.4f}".format(sid, event, price)


def build_tp3_celebration(sig, price):
    """Mensaje CELEBRATORIO de TP3, con fines de animo para los usuarios.

    Distinto del progress alert operativo (build_progress_alert tp3_hit, que
    sugiere trailing): aqui el tono es de festejo. Se difunde a TODOS los
    suscriptores cuando una senal real corre sus tres objetivos.
    """
    sid = sig["id"]
    side = _side(sig.get("direction"))
    price_str = "${:.4f}".format(price) if price is not None else "-"
    return "\n".join([
        _G["rule"],
        "  \U0001F973 TP3 ALCANZADO · Senal #{}".format(sid),
        _G["rule"],
        "  {} Direccion   {}".format(_G["act"], side),
        "  {} Precio      {}".format(_G["act"], price_str),
        "  {} Corrida     +3.00R confirmados \U0001F3AF".format(_G["act"]),
        "",
        "  Tercer objetivo tocado. Disciplina",
        "  sistematica, no suerte. \U0001F64C",
        "  Felicidades a quienes la tomaron.",
        _G["rule"],
    ])
