#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FQ PUBLIC BOT - entrypoint
  by RasDG_Sol + Claude

  Bot publico de propaganda/marketing del sistema FQ.

  Caracteristicas:
   - Comandos limitados: /start /info /precio /unirme /stripe /crypto /codigo
   - NUNCA expone Claude por usuario (cero consumo de API por comandos publicos)
   - Lee ledger VIP en read-only para anunciar cierres +1R
   - Scheduler interno: lecturas Sonnet 2/dia, CTAs 2/dia, stats domingo
   - Suscripcion automatica con /start, opt-out con /desuscribir

  ENV vars criticas:
   - TELEGRAM_TOKEN_PUBLIC    token del @RasDG_FQ_publico_bot (o como lo llames)
   - FQ_VIP_BOT_USERNAME       username del bot VIP para deep links (/codigo, /unirme)
   - FQ_PUBLIC_DB_PATH         path del .db local (default /data/fq_public.db)
   - FQ_VIP_LEDGER_PATH        path del .db VIP (default /data/fq_ledger.db, RO)
   - ANTHROPIC_API_KEY         para generar lecturas Sonnet
   - FQ_STRIPE_LINK            link de pago Stripe (opcional)
   - FQ_USDT_ADDRESS           address USDT (opcional)
================================================================================
"""
import os
import sys
import json
import time
import logging
import threading
import traceback
from datetime import datetime, timezone

import requests

import public_format as fmt
import public_handlers as ph
import public_outcome_announcer as poa
import public_scheduler as ps
from ops import heartbeat as hb

# ============================================================
# CONFIG
# ============================================================
def _resolve_public_token(env=None):
    """Token del bot publico -> (token, source).

    REGLA: bajo el launcher (FQ_LAUNCHER=1, VIP + public en el MISMO container)
    NO hay fallback al token VIP: el VIP ya hace getUpdates ahi mismo y
    compartir token = dos pollers compitiendo -> HTTP 409 en loop y comandos
    repartidos al azar entre ambos bots. Standalone (legacy, un solo bot) el
    fallback se conserva.

    source: 'public' | 'vip_fallback' | None.
    """
    env = os.environ if env is None else env
    pub = (env.get("TELEGRAM_TOKEN_PUBLIC") or "").strip()
    if pub:
        return pub, "public"
    vip = (env.get("TELEGRAM_TOKEN") or "").strip()
    if vip and (env.get("FQ_LAUNCHER") or "").strip() != "1":
        return vip, "vip_fallback"
    return "", None


TELEGRAM_TOKEN, TOKEN_SOURCE = _resolve_public_token()

POLL_INTERVAL_SEC      = 3        # short poll cada 3 seg
SCHEDULER_TICK_SECONDS = 60       # tick cada minuto

# getUpdates HTTP 409 = Conflict: OTRO consumidor esta usando el MISMO token
# (segunda instancia del bot -- p.ej. servicio Railway duplicado -- o un
# webhook activo). Reintentar cada 5s fijos solo spamea el log: backoff
# exponencial + UNA alerta al admin por racha con el diagnostico.
CONFLICT_BACKOFF_BASE_SEC = 5
CONFLICT_BACKOFF_MAX_SEC  = 300
CONFLICT_ALERT_AFTER      = 5     # alertar al admin tras N 409 consecutivos


def _conflict_backoff(consecutive):
    """Segundos de espera tras `consecutive` HTTP 409 seguidos (>= 1)."""
    if consecutive <= 0:
        return 0
    return min(CONFLICT_BACKOFF_BASE_SEC * (2 ** (consecutive - 1)),
               CONFLICT_BACKOFF_MAX_SEC)

# ============================================================
# LOGGING
# ============================================================
import fq_logging
fq_logging.setup()
log = logging.getLogger("fq_public_bot")

# ============================================================
# TELEGRAM
# ============================================================
def telegram_send(chat_id, text, parse_mode=None):
    if not TELEGRAM_TOKEN:
        return False
    url = "https://api.telegram.org/bot{}/sendMessage".format(TELEGRAM_TOKEN)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
    try:
        r = requests.post(url, data=payload, timeout=20)
        if r.status_code == 200:
            return True
        # Codes 403/400 = bloqueado o user borrado - desactivar suscripcion
        if r.status_code in (400, 403):
            try:
                resp = r.json()
                desc = (resp.get("description") or "").lower()
                if "blocked" in desc or "deactivated" in desc or "chat not found" in desc:
                    log.info("Desactivando subscriber bloqueado: {}".format(chat_id))
                    poa.remove_subscriber(chat_id)
            except Exception:
                pass
        log.warning("telegram_send {} HTTP {}: {}".format(chat_id, r.status_code, r.text[:100]))
    except Exception as e:
        log.error("telegram_send {} exception: {}".format(chat_id, e))
    return False

def broadcast(text, kind="generic", title="", parse_mode=None):
    """Envia text a TODOS los subscribers activos. Devuelve numero de envios exitosos."""
    subs = poa.get_active_subscribers()
    if not subs:
        log.info("Broadcast {}: cero subscribers - skipping".format(kind))
        return 0
    sent = failed = 0
    for cid in subs:
        if telegram_send(cid, text, parse_mode=parse_mode):
            sent += 1
        else:
            failed += 1
    poa.log_content_sent(kind, title, sent, failed)
    log.info("Broadcast {} '{}' enviado a {}/{} chats".format(kind, title, sent, len(subs)))
    return sent

# ============================================================
# COMMAND LISTENER (long-poll Telegram)
# ============================================================
class ListenerState:
    def __init__(self):
        self.offset = 0
        self.lock = threading.Lock()

def _alert_admin_conflict():
    """Aviso unico (por racha) al admin: hay un conflicto de token."""
    admin_cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not admin_cid:
        return
    try:
        telegram_send(
            int(admin_cid),
            "FQ Public Bot: HTTP 409 persistente en getUpdates.\n"
            "Causa tipica: OTRA instancia esta haciendo polling con el MISMO "
            "token (revisa en Railway si hay un servicio duplicado ademas del "
            "worker) o hay un webhook activo (getWebhookInfo).\n"
            "Este proceso entra en backoff (hasta {}s) hasta que el conflicto "
            "desaparezca.".format(CONFLICT_BACKOFF_MAX_SEC))
    except Exception:
        pass


def command_listener(state):
    if not TELEGRAM_TOKEN:
        log.error("No TELEGRAM_TOKEN_PUBLIC - listener disabled")
        return
    url = "https://api.telegram.org/bot{}/getUpdates".format(TELEGRAM_TOKEN)
    log.info("Command listener iniciado")
    conflicts = 0
    while True:
        try:
            params = {"timeout": 30, "offset": state.offset or 0}
            r = requests.get(url, params=params, timeout=40)
            if r.status_code == 409:
                conflicts += 1
                wait = _conflict_backoff(conflicts)
                log.warning(
                    "getUpdates HTTP 409 (#%d consecutivo): otra instancia "
                    "con el mismo token (servicio duplicado?) o webhook "
                    "activo. Backoff %ds.", conflicts, wait)
                if conflicts == CONFLICT_ALERT_AFTER:
                    _alert_admin_conflict()
                time.sleep(wait)
                continue
            if r.status_code != 200:
                log.warning("getUpdates HTTP {}".format(r.status_code))
                time.sleep(5)
                continue
            conflicts = 0
            data = r.json()
            if not data.get("ok"):
                log.warning("getUpdates not ok: {}".format(data))
                time.sleep(5)
                continue
            updates = data.get("result", [])
            for u in updates:
                with state.lock:
                    state.offset = u["update_id"] + 1
                _handle_update(u)
        except Exception as e:
            log.error("listener loop: {}\n{}".format(e, traceback.format_exc()))
            time.sleep(POLL_INTERVAL_SEC)

def _handle_update(update):
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    text = msg.get("text", "")
    if not chat_id or not text:
        return
    # Dispatch
    response = ph.dispatch(text, chat_id, msg_obj=msg)
    if response:
        telegram_send(chat_id, response)

# ============================================================
# MAIN
# ============================================================
def main():
    log.info("=" * 70)
    log.info("  FQ PUBLIC BOT")
    log.info("  VIP ledger (RO): {}".format(poa.VIP_DB_PATH))
    log.info("  Public DB:       {}".format(poa.PUBLIC_DB_PATH))
    log.info("  VIP bot @:       {}".format(ph.VIP_BOT_USERNAME or "(no configurado)"))
    log.info("=" * 70)

    if not TELEGRAM_TOKEN:
        if (os.environ.get("FQ_LAUNCHER") or "").strip() == "1":
            # Bajo el launcher NO robamos el token VIP ni salimos con rc!=0
            # (el launcher tumbaria el container completo -> restart loop y
            # se llevaria al VIP por delante). El publico queda PARQUEADO y
            # VIP + maintenance siguen vivos.
            log.critical(
                "TELEGRAM_TOKEN_PUBLIC vacio: bot publico PARQUEADO (sin "
                "fallback al token VIP bajo launcher; setea la env en el "
                "servicio Railway y redeploya).")
            while True:
                time.sleep(600)
                log.critical("Bot publico sigue parqueado: falta TELEGRAM_TOKEN_PUBLIC")
        log.error("FATAL: TELEGRAM_TOKEN_PUBLIC vacio (o TELEGRAM_TOKEN como fallback)")
        sys.exit(1)

    if TOKEN_SOURCE == "vip_fallback":
        log.warning(
            "Usando TELEGRAM_TOKEN (VIP) como fallback: modo standalone "
            "legacy. Si el bot VIP corre en paralelo con este token habra "
            "HTTP 409 en getUpdates.")

    # Inicializar BD publica
    try:
        poa.init_public_db()
    except Exception as e:
        log.error("init_public_db error: {}".format(e))
        sys.exit(1)

    # Anuncio interno (a admin si configurado) - opcional
    admin_cid = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if admin_cid:
        try:
            telegram_send(int(admin_cid),
                "FQ Public Bot ONLINE\n"
                "Subscribers: {}\n"
                "VIP ledger: {}".format(
                    poa.count_subscribers(),
                    "OK" if os.path.isfile(poa.VIP_DB_PATH) else "no encontrado"
                ))
        except Exception:
            pass

    # Thread: listener de comandos
    listener_state = ListenerState()
    t_listener = threading.Thread(target=command_listener,
                                   args=(listener_state,), daemon=True)
    t_listener.start()

    # Thread: scheduler de contenido (cierres, lecturas, CTAs, stats)
    sched_state = ps.SchedulerState()
    def send_cb(text, kind="generic", title=""):
        return broadcast(text, kind=kind, title=title)
    t_sched = threading.Thread(
        target=ps.run_scheduler_loop,
        args=(sched_state, send_cb, SCHEDULER_TICK_SECONDS),
        daemon=True
    )
    t_sched.start()

    # Loop principal: heartbeat / keep alive
    log.info("Main loop iniciado (heartbeat 5min)")
    while True:
        try:
            time.sleep(300)
            try:
                hb.beat("public")
            except Exception:
                pass
            log.info("Heartbeat | subs={} VIP_db_exists={}".format(
                poa.count_subscribers(),
                os.path.isfile(poa.VIP_DB_PATH)
            ))
        except KeyboardInterrupt:
            log.info("Interrupcion - cerrando bot publico")
            break
        except Exception as e:
            log.error("main heartbeat: {}".format(e))
            time.sleep(10)

if __name__ == "__main__":
    main()
