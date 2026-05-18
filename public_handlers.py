# -*- coding: utf-8 -*-
"""
================================================================================
  PUBLIC HANDLERS - comandos del bot publico (limitados, sin LLM por usuario)
  by RasDG_Sol + Claude

  Comandos publicos:
    /start /info /precio /unirme /stripe /crypto /codigo

  CUALQUIER otro comando -> build_unknown (redirige al VIP).
  El bot publico NO conversa - solo emite y redirige.
================================================================================
"""
import os
import re
import logging

import public_format as fmt
import public_outcome_announcer as poa

log = logging.getLogger("fq_public_handlers")

# ============================================================
# CONFIG
# ============================================================
VIP_BOT_USERNAME = os.environ.get("FQ_VIP_BOT_USERNAME", "").strip().lstrip("@")
STRIPE_LINK      = os.environ.get("FQ_STRIPE_LINK", "").strip()
USDT_ADDRESS     = os.environ.get("FQ_USDT_ADDRESS", "").strip()
USDT_NETWORK     = os.environ.get("FQ_USDT_NETWORK", "TRC20").strip()

# Regex codigo: alfanumerico + guiones, 4-32 chars
CODIGO_RX = re.compile(r"^[A-Za-z0-9\-_]{4,32}$")

# ============================================================
# COMMAND HANDLERS - cada uno recibe (chat_id, args_str, msg_obj) -> str
# ============================================================
def cmd_start(chat_id, args, msg_obj=None):
    """Suscribe automaticamente al chat al canal publico"""
    username = ""
    first_name = ""
    if msg_obj and isinstance(msg_obj, dict):
        from_user = msg_obj.get("from", {})
        username = from_user.get("username", "") or ""
        first_name = from_user.get("first_name", "") or ""
    try:
        poa.add_subscriber(chat_id, username=username, first_name=first_name)
        log.info("Nuevo subscriber publico: chat_id={} @{}".format(chat_id, username))
    except Exception as e:
        log.error("add_subscriber error: {}".format(e))
    return fmt.build_welcome()

def cmd_info(chat_id=None, args=None, msg_obj=None):
    return fmt.build_info()

def cmd_precio(chat_id=None, args=None, msg_obj=None):
    return fmt.build_pricing()

def cmd_unirme(chat_id=None, args=None, msg_obj=None):
    return fmt.build_unirme(VIP_BOT_USERNAME)

def cmd_stripe(chat_id=None, args=None, msg_obj=None):
    return fmt.build_stripe(STRIPE_LINK)

def cmd_crypto(chat_id=None, args=None, msg_obj=None):
    return fmt.build_crypto(USDT_ADDRESS, USDT_NETWORK)

def cmd_codigo(chat_id=None, args=None, msg_obj=None):
    if not args:
        return fmt.build_codigo_response(None, VIP_BOT_USERNAME)
    codigo = (args or "").strip().split()[0] if args else ""
    if not CODIGO_RX.match(codigo or ""):
        return fmt.build_codigo_response(None, VIP_BOT_USERNAME)
    return fmt.build_codigo_response(codigo, VIP_BOT_USERNAME)

def cmd_desuscribir(chat_id, args=None, msg_obj=None):
    try:
        poa.remove_subscriber(chat_id)
        return "Ya no recibiras mas reportes. Para volver: /start"
    except Exception as e:
        log.error("remove_subscriber: {}".format(e))
        return "Hubo un error. Intenta de nuevo en un momento."

def cmd_unknown(chat_id=None, args=None, msg_obj=None):
    return fmt.build_unknown()

# ============================================================
# DISPATCHER
# ============================================================
COMMANDS = {
    "/start":        cmd_start,
    "/info":         cmd_info,
    "/precio":       cmd_precio,
    "/precios":      cmd_precio,      # alias
    "/unirme":       cmd_unirme,
    "/vip":          cmd_unirme,       # alias
    "/stripe":       cmd_stripe,
    "/crypto":       cmd_crypto,
    "/usdt":         cmd_crypto,       # alias
    "/codigo":       cmd_codigo,
    "/desuscribir":  cmd_desuscribir,
    "/stop":         cmd_desuscribir,  # alias
    "/help":         cmd_info,         # /help redirige a info
}

def dispatch(text, chat_id, msg_obj=None):
    """
    Entry point del listener. text es el mensaje completo recibido.
    Devuelve string a enviar (o None si no aplica).
    """
    if not text or not text.startswith("/"):
        return None  # no responder a mensajes que no sean comandos

    parts = text.strip().split(None, 1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    # Strip bot username si esta presente (/cmd@BotName)
    if "@" in cmd:
        cmd = cmd.split("@")[0]

    handler = COMMANDS.get(cmd)
    if handler is None:
        return cmd_unknown(chat_id, args, msg_obj)
    try:
        return handler(chat_id, args, msg_obj)
    except Exception as e:
        log.error("handler {} error: {}".format(cmd, e))
        return fmt.build_unknown()
