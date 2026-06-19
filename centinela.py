# -*- coding: utf-8 -*-
"""
================================================================================
  CENTINELA — el despertar por sesion de "La Lectura"
  by RasDG_Sol + Claude
================================================================================
No es un autopiloto. Es el companero que te toca el hombro SOLO cuando abren las
sesiones que VOS operas (NY AM + Asia open por default; la apertura de Londres se
saltea a proposito) y te deja servida la lectura para que decidas. Fuera de esas
ventanas, calla.

  · Compone La Lectura (lectura.py) sobre los simbolos que le pidas.
  · Entrega SIEMPRE a stdout + a un diario por fecha (lecturas/AAAA-MM-DD.md).
  · Entrega a tu Telegram si hay TELEGRAM_TOKEN + TELEGRAM_CHAT_ID (las MISMAS
    del bot; no importa el monolito, manda con urllib). Sin esas vars: lo omite.
  · Es TZ-agnostico: calcula la hora CDMX el mismo (no depende del reloj del
    server) y deduplica con un archivo de estado -> un cron simple no repite.

Horarios (de killzones_pd.KILLZONES_CDMX, fuente unica de verdad):
  ny_am_kz   -> 08:00 CDMX   (apertura NY manana)
  asia_open  -> 17:00 CDMX   (apertura de Asia, la franja de las 6 PM)
  [london_open_kz 01:00 — EXCLUIDO por default, vos no operas la apertura EU]

Uso:
  python centinela.py --once            # lo llama el cron; entrega solo si estamos
                                        #   en la ventana de una apertura (TZ-agnostico)
  python centinela.py --once --force    # probar ya, sin esperar la apertura
  python centinela.py --watch           # loop propio: duerme hasta la proxima apertura
  python centinela.py --symbols SOL-USDT-SWAP,BTC-USDT-SWAP --once
  python centinela.py --sessions ny_am_kz,asia_open,london_open_kz --once  # sumar Londres

Cron (TZ-agnostico: corre seguido, el centinela decide y deduplica):
  */15 * * * * cd /opt/fq-bot && /usr/bin/python3 centinela.py --once >> /var/log/centinela.log 2>&1

systemd timer (alternativa a cron):
  # /etc/systemd/system/centinela.service
  [Service]
  Type=oneshot
  WorkingDirectory=/opt/fq-bot
  EnvironmentFile=/opt/fq-bot/.env
  ExecStart=/usr/bin/python3 centinela.py --once
  # /etc/systemd/system/centinela.timer
  [Timer]
  OnCalendar=*:0/15
  Persistent=true
  [Install]
  WantedBy=timers.target
================================================================================
"""
import argparse
import html
import json
import os
import sys
import time
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import killzones_pd as kz
import lectura

DEFAULT_SYMBOLS = ["SOL-USDT-SWAP"]
DEFAULT_OPENS = ["ny_am_kz", "asia_open"]      # NY AM + Asia; Londres excluido a proposito
WINDOW_MIN = 20                                # ancho de la ventana de apertura

SESSION_LABELS = {
    "ny_am_kz":            "Apertura NY (manana)",
    "asia_open":           "Apertura de Asia",
    "london_open_kz":      "Apertura de Londres",
    "silver_bullet_ny_am": "Silver Bullet NY AM",
    "ny_pm_kz":            "Apertura NY (tarde)",
    "prueba":              "prueba (forzado)",
}

LECTURAS_DIR = os.path.join(_HERE, "lecturas")
STATE_FILE = os.path.join(LECTURAS_DIR, ".centinela_state.json")


# ============================================================
# HORARIOS DE SESION (PURO — testeable sin reloj real)
# ============================================================
def _kz_start(name):
    """Hora de inicio (decimal CDMX) de una killzone por nombre."""
    for row in kz.KILLZONES_CDMX:
        if row[0] == name:
            return float(row[1])
    raise KeyError("killzone desconocida: %s" % name)


def _hours(dt):
    return dt.hour + dt.minute / 60.0


def session_now(now_cdmx, opens=DEFAULT_OPENS, window_min=WINDOW_MIN):
    """Nombre de la apertura si `now` cae en su ventana [start, start+window); si no, None."""
    h = _hours(now_cdmx)
    w = window_min / 60.0
    for name in opens:
        s = _kz_start(name)
        if s <= h < s + w:
            return name
    return None


def next_session_open(now_cdmx, opens=DEFAULT_OPENS):
    """(datetime, name) de la proxima apertura configurada (hoy o manana)."""
    best = None
    for name in opens:
        s = _kz_start(name)
        hh, mm = int(s), int(round((s - int(s)) * 60))
        cand = now_cdmx.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if cand <= now_cdmx:
            cand = cand + timedelta(days=1)
        if best is None or cand < best[0]:
            best = (cand, name)
    return best


# ============================================================
# DIGEST (compone La Lectura por simbolo; dfs inyectable -> testeable)
# ============================================================
def build_session_digest(symbols, session_name, now_cdmx, dfs_by_symbol=None):
    label = SESSION_LABELS.get(session_name, session_name)
    blocks = []
    for sym in symbols:
        d = dfs_by_symbol[sym] if dfs_by_symbol is not None else lectura.fetch_dfs(sym)
        L = lectura.build_lectura(sym, d["15m"], d["1h"], d["4h"], d.get("1m"), now_cdmx=now_cdmx)
        blocks.append(lectura.render(L))
    header = "[ DESPERTAR · %s · %s CDMX ]" % (label, now_cdmx.strftime("%Y-%m-%d %H:%M"))
    return {
        "session": session_name, "label": label, "now": now_cdmx,
        "symbols": list(symbols), "header": header, "blocks": blocks,
        "text": header + "\n\n" + "\n\n".join(blocks),
    }


# ============================================================
# ENTREGA
# ============================================================
def _telegram_send(text):
    """Manda al chat admin reusando TELEGRAM_TOKEN/TELEGRAM_CHAT_ID del bot.
    <pre> + escape -> el reporte llega monoespaciado y alineado al celular."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False, "sin TELEGRAM_TOKEN/TELEGRAM_CHAT_ID"
    import urllib.parse
    import urllib.request
    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": "<pre>" + html.escape(text) + "</pre>",
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    url = "https://api.telegram.org/bot%s/sendMessage" % token
    try:
        req = urllib.request.Request(url, data=data, headers={"User-Agent": "centinela"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return (r.status == 200), ("ok" if r.status == 200 else "http %s" % r.status)
    except Exception as e:
        return False, str(e)[:120]


def _append_file(digest):
    os.makedirs(LECTURAS_DIR, exist_ok=True)
    path = os.path.join(LECTURAS_DIR, digest["now"].strftime("%Y-%m-%d") + ".md")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\n\n" + digest["text"] + "\n")
    return path


def deliver(digest, to_telegram=True):
    """stdout + diario por fecha SIEMPRE; Telegram opt-in (1 mensaje por simbolo,
    para no chocar el limite de 4096 chars)."""
    results = []
    print(digest["text"])
    results.append(("file", _append_file(digest)))
    if to_telegram:
        oks, infos = [], []
        for msg in [digest["header"]] + digest["blocks"]:
            ok, info = _telegram_send(msg)
            oks.append(ok)
            infos.append(info)
        results.append(("telegram", "ok" if all(oks) else ";".join(sorted(set(infos)))))
    return results


# ============================================================
# ESTADO (dedupe: no repetir la misma apertura el mismo dia)
# ============================================================
def _fire_key(now_cdmx, session):
    return "%s|%s" % (now_cdmx.strftime("%Y-%m-%d"), session)


def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_state(st):
    os.makedirs(LECTURAS_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(st, fh)


# ============================================================
# MODOS
# ============================================================
def run_once(symbols, opens, *, force=False, window_min=WINDOW_MIN, to_telegram=True):
    now = datetime.now(kz.CDMX_TZ)
    if kz.is_weekend_closed() and not force:
        print("[centinela] fin de semana — mercado cerrado, no despierto.", file=sys.stderr)
        return 0

    session = session_now(now, opens, window_min)
    if session is None and not force:
        nxt, nname = next_session_open(now, opens)
        print("[centinela] fuera de apertura. Proxima: %s a las %s CDMX." % (
            SESSION_LABELS.get(nname, nname), nxt.strftime("%H:%M")), file=sys.stderr)
        return 0
    session = session or "prueba"

    key = _fire_key(now, session)
    if not force:
        if _load_state().get("last") == key:
            print("[centinela] ya despertado para %s — no repito." % key, file=sys.stderr)
            return 0

    digest = build_session_digest(symbols, session, now)
    res = deliver(digest, to_telegram=to_telegram)
    if not force:
        st = _load_state()
        st["last"] = key
        _save_state(st)
    print("[centinela] entregado: %s" % ", ".join("%s=%s" % (k, v) for k, v in res),
          file=sys.stderr)
    return 0


def run_watch(symbols, opens, *, window_min=WINDOW_MIN, to_telegram=True):
    print("[centinela] watch on. Sesiones: %s. Ctrl-C para salir." % ", ".join(opens),
          file=sys.stderr)
    while True:
        now = datetime.now(kz.CDMX_TZ)
        nxt, nname = next_session_open(now, opens)
        print("[centinela] proxima %s en %.1f h (%s CDMX)" % (
            SESSION_LABELS.get(nname, nname), (nxt - now).total_seconds() / 3600.0,
            nxt.strftime("%H:%M")), file=sys.stderr)
        while (nxt - datetime.now(kz.CDMX_TZ)).total_seconds() > 0:
            time.sleep(min((nxt - datetime.now(kz.CDMX_TZ)).total_seconds(), 300))
        now = datetime.now(kz.CDMX_TZ)
        if kz.is_weekend_closed():
            print("[centinela] %s cae en finde — salteo." % nname, file=sys.stderr)
            time.sleep(90)
            continue
        deliver(build_session_digest(symbols, nname, now), to_telegram=to_telegram)
        time.sleep(max(window_min * 60, 90))   # pasar la ventana para no re-disparar


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Centinela — despertar por sesion de La Lectura (no autopiloto).")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true",
                      help="entrega ahora si estamos en ventana de apertura (cron-friendly)")
    mode.add_argument("--watch", action="store_true",
                      help="loop propio: duerme hasta la proxima apertura")
    ap.add_argument("--force", action="store_true", help="entrega aunque no sea horario (probar)")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    ap.add_argument("--sessions", default=",".join(DEFAULT_OPENS))
    ap.add_argument("--window", type=int, default=WINDOW_MIN, help="ancho ventana apertura (min)")
    ap.add_argument("--no-telegram", action="store_true", help="omitir entrega a Telegram")
    args = ap.parse_args(argv)

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    opens = [s.strip() for s in args.sessions.split(",") if s.strip()]
    to_tg = not args.no_telegram

    if args.watch:
        return run_watch(symbols, opens, window_min=args.window, to_telegram=to_tg)
    return run_once(symbols, opens, force=args.force, window_min=args.window, to_telegram=to_tg)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
