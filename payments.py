# -*- coding: utf-8 -*-
"""
================================================================================
  PAYMENTS MODULE - FQ v4.1 Mistral Edition
  Stripe Checkout + Crypto USDT (TRC20/ERC20) verification
================================================================================

  Stripe:
    - Crea sesion de Checkout con metadata chat_id
    - Webhook handler en landing/server.py confirma pago
    - On confirmation: confirm_payment() en vip_system

  Crypto:
    - Genera referencia unica y muestra wallet RasDG
    - Polling al explorer (Tronscan TRC20 / Etherscan ERC20)
    - Verifica monto + memo/refid + tx confirmaciones
    - On match: confirm_payment()

  Variables de entorno requeridas:
    STRIPE_SECRET_KEY=sk_test_... o sk_live_...
    STRIPE_WEBHOOK_SECRET=whsec_...
    CRYPTO_USDT_TRC20_ADDRESS=Txxxx...    (tu wallet TRON)
    CRYPTO_USDT_ERC20_ADDRESS=0xxxx...    (tu wallet ETH)
    LANDING_URL=https://rasdg-quantum.up.railway.app

================================================================================
"""
import os
import logging
import time
import requests
import secrets
from datetime import datetime, timezone, timedelta

import vip_system as vip

log = logging.getLogger("fq_payments")

# ============================================================
# CONFIG
# ============================================================
STRIPE_SECRET_KEY     = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()

USDT_TRC20_ADDRESS = os.environ.get("CRYPTO_USDT_TRC20_ADDRESS", "").strip()
USDT_ERC20_ADDRESS = os.environ.get("CRYPTO_USDT_ERC20_ADDRESS", "").strip()

LANDING_URL = os.environ.get("LANDING_URL", "https://rasdg-quantum.up.railway.app").strip()

# Tronscan API (free, no key required for basic)
TRONSCAN_BASE = "https://apilist.tronscanapi.com/api"
ETHERSCAN_BASE = "https://api.etherscan.io/api"
ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "").strip()

# USDT contract addresses
USDT_TRC20_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_ERC20_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"

CRYPTO_TOLERANCE = 0.50    # tolerancia +-0.50 USDT en monto exacto
CRYPTO_MIN_CONFIRMATIONS = 1
CRYPTO_MAX_AGE_HOURS = 72

# ============================================================
# STRIPE
# ============================================================
def stripe_available():
    return bool(STRIPE_SECRET_KEY)

def create_stripe_checkout(chat_id, plan_id):
    """
    Crea sesion de Stripe Checkout. Devuelve URL de pago.
    """
    if not stripe_available():
        return None, "Stripe no configurado."
    plan_info = vip.PLAN_PRICES.get(plan_id)
    if not plan_info:
        return None, "Plan invalido."
    if plan_info["price_usd"] == 0:
        return None, "Plan gratis no requiere pago."

    chat_id = str(chat_id)

    # Crear pago pendiente en BD
    payment_id = vip.record_payment(
        chat_id=chat_id,
        plan=plan_id,
        amount_usd=plan_info["price_usd"],
        method="stripe",
        status="pending",
        metadata={"plan_label": plan_info["label"]}
    )

    # Llamar Stripe API
    try:
        r = requests.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(STRIPE_SECRET_KEY, ""),
            data={
                "mode": "payment",
                "payment_method_types[]": "card",
                "line_items[0][price_data][currency]": "usd",
                "line_items[0][price_data][product_data][name]": "FQ v4.1 - " + plan_info["label"],
                "line_items[0][price_data][product_data][description]":
                    "Acceso VIP por {} dias al sistema FQ v4.1".format(plan_info["days"]),
                "line_items[0][price_data][unit_amount]": int(plan_info["price_usd"] * 100),
                "line_items[0][quantity]": "1",
                "success_url": LANDING_URL + "/success?session_id={CHECKOUT_SESSION_ID}",
                "cancel_url": LANDING_URL + "/cancel",
                "metadata[chat_id]": chat_id,
                "metadata[plan_id]": plan_id,
                "metadata[payment_id]": str(payment_id),
                "client_reference_id": "fq_{}_{}".format(chat_id, payment_id),
            },
            timeout=20,
        )
        if r.status_code != 200:
            log.error("Stripe checkout error {}: {}".format(r.status_code, r.text[:300]))
            return None, "Error al crear checkout."
        data = r.json()
        checkout_url = data.get("url")
        session_id = data.get("id")
        if not checkout_url:
            return None, "Stripe no devolvio URL."

        # Guardar session_id en payment
        import sqlite3
        c = sqlite3.connect(vip.VIP_DB_PATH, timeout=20)
        c.execute("UPDATE payments SET stripe_id = ? WHERE id = ?",
                  (session_id, payment_id))
        c.commit()
        c.close()

        return checkout_url, None
    except Exception as e:
        log.error("create_stripe_checkout exception: {}".format(e))
        return None, "Error inesperado: {}".format(str(e)[:100])

def stripe_handle_webhook_event(event):
    """
    Procesa evento de webhook de Stripe.
    Solo nos interesa 'checkout.session.completed' por ahora.
    """
    event_type = event.get("type")
    if event_type != "checkout.session.completed":
        return False, "ignored"

    session = event.get("data", {}).get("object", {})
    metadata = session.get("metadata", {})
    payment_id = metadata.get("payment_id")
    chat_id = metadata.get("chat_id")
    plan_id = metadata.get("plan_id")

    if not payment_id:
        log.warning("Stripe webhook without payment_id")
        return False, "no payment_id"

    # Confirmar pago
    success = vip.confirm_payment(int(payment_id))
    if success:
        log.info("Stripe payment confirmed: {} chat={} plan={}".format(
            payment_id, chat_id, plan_id))
        return True, "confirmed"
    return False, "already_processed"

# ============================================================
# CRYPTO USDT
# ============================================================
def crypto_available():
    return bool(USDT_TRC20_ADDRESS or USDT_ERC20_ADDRESS)

def create_crypto_payment(chat_id, plan_id, network="trc20"):
    """
    Genera instruccion de pago crypto.
    Devuelve dict con {wallet, amount, ref_id, payment_id, qr_data}
    """
    plan_info = vip.PLAN_PRICES.get(plan_id)
    if not plan_info:
        return None, "Plan invalido."
    if plan_info["price_usd"] == 0:
        return None, "Plan gratis no requiere pago."

    chat_id = str(chat_id)
    network = network.lower()

    if network == "trc20":
        wallet = USDT_TRC20_ADDRESS
        if not wallet:
            return None, "TRC20 no configurado."
    elif network == "erc20":
        wallet = USDT_ERC20_ADDRESS
        if not wallet:
            return None, "ERC20 no configurado."
    else:
        return None, "Red invalida (usa trc20 o erc20)."

    # Monto unico para identificar pago: precio + cents distintivos
    # Ej: $49 -> $49.{XX} donde XX es 4 digitos del chat_id
    cents_id = int(str(chat_id)[-4:]) if str(chat_id)[-4:].isdigit() else \
               int(secrets.token_hex(2), 16) % 10000
    amount_unique = round(plan_info["price_usd"] + cents_id / 10000.0, 4)
    ref_id = "FQ-" + secrets.token_hex(3).upper()

    payment_id = vip.record_payment(
        chat_id=chat_id,
        plan=plan_id,
        amount_usd=amount_unique,
        method="crypto_" + network,
        status="pending",
        metadata={
            "wallet": wallet,
            "network": network,
            "ref_id": ref_id,
            "plan_label": plan_info["label"],
        }
    )

    qr_data = "{}?amount={}".format(wallet, amount_unique) if network == "trc20" else \
              "ethereum:{}?value={}".format(wallet, int(amount_unique * 1e6))

    return {
        "payment_id": payment_id,
        "wallet": wallet,
        "amount":  amount_unique,
        "ref_id":  ref_id,
        "network": network,
        "qr_data": qr_data,
        "expires_in_hours": CRYPTO_MAX_AGE_HOURS,
    }, None

def verify_trc20_payment(payment):
    """
    Verifica un pago TRC20 contra Tronscan.
    payment es dict de la BD.
    Devuelve True si encuentra match.
    """
    metadata = payment.get("metadata") or "{}"
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    expected_amount = float(payment["amount_usd"])
    wallet = metadata.get("wallet") or USDT_TRC20_ADDRESS

    try:
        # Get recent USDT transfers to wallet
        r = requests.get(
            TRONSCAN_BASE + "/token_trc20/transfers",
            params={
                "limit": 50,
                "toAddress": wallet,
                "contract_address": USDT_TRC20_CONTRACT,
            },
            timeout=15
        )
        if r.status_code != 200:
            log.warning("Tronscan API {} {}".format(r.status_code, r.text[:200]))
            return False

        data = r.json()
        transfers = data.get("token_transfers", []) or data.get("data", [])

        # Buscar tx con monto ~= expected_amount
        payment_created = datetime.fromisoformat(payment["created_at"])
        for tx in transfers:
            tx_amount_raw = tx.get("quant") or tx.get("amount_str") or 0
            try:
                # USDT tiene 6 decimales en TRC20
                tx_amount = float(tx_amount_raw) / 1_000_000
            except Exception:
                continue

            tx_ts = tx.get("block_ts") or tx.get("timestamp")
            if tx_ts:
                try:
                    tx_dt = datetime.fromtimestamp(int(tx_ts) / 1000, tz=timezone.utc)
                    if tx_dt < payment_created - timedelta(minutes=10):
                        continue  # tx muy vieja
                except Exception:
                    pass

            if abs(tx_amount - expected_amount) <= CRYPTO_TOLERANCE:
                # Match!
                tx_hash = tx.get("transaction_id") or tx.get("hash")
                confs = tx.get("confirmed", 1)
                if confs >= CRYPTO_MIN_CONFIRMATIONS:
                    log.info("TRC20 match found: payment={} tx={} amount={}".format(
                        payment["id"], tx_hash, tx_amount))
                    # Update tx_hash
                    import sqlite3
                    c = sqlite3.connect(vip.VIP_DB_PATH, timeout=20)
                    c.execute("UPDATE payments SET tx_hash = ? WHERE id = ?",
                              (tx_hash, payment["id"]))
                    c.commit()
                    c.close()
                    # Confirm
                    return vip.confirm_payment(payment["id"])
        return False
    except Exception as e:
        log.error("verify_trc20_payment: {}".format(e))
        return False

def verify_erc20_payment(payment):
    """Verifica pago USDT ERC20 via Etherscan"""
    if not ETHERSCAN_KEY:
        log.warning("Etherscan key not set, skipping ERC20 verification")
        return False

    metadata = payment.get("metadata") or "{}"
    if isinstance(metadata, str):
        import json
        try:
            metadata = json.loads(metadata)
        except Exception:
            metadata = {}

    expected_amount = float(payment["amount_usd"])
    wallet = metadata.get("wallet") or USDT_ERC20_ADDRESS

    try:
        r = requests.get(
            ETHERSCAN_BASE,
            params={
                "module": "account",
                "action": "tokentx",
                "contractaddress": USDT_ERC20_CONTRACT,
                "address": wallet,
                "startblock": 0,
                "endblock": 99999999,
                "sort": "desc",
                "apikey": ETHERSCAN_KEY,
            },
            timeout=20
        )
        if r.status_code != 200:
            return False
        data = r.json()
        if data.get("status") != "1":
            return False
        txs = data.get("result", [])

        payment_created = datetime.fromisoformat(payment["created_at"])
        for tx in txs:
            try:
                tx_amount = int(tx["value"]) / 1_000_000  # USDT 6 decimals
                tx_ts = int(tx["timeStamp"])
                tx_dt = datetime.fromtimestamp(tx_ts, tz=timezone.utc)
                if tx_dt < payment_created - timedelta(minutes=10):
                    continue
                if tx["to"].lower() != wallet.lower():
                    continue
                if abs(tx_amount - expected_amount) <= CRYPTO_TOLERANCE:
                    tx_hash = tx["hash"]
                    confs = int(tx.get("confirmations", 0))
                    if confs >= CRYPTO_MIN_CONFIRMATIONS:
                        log.info("ERC20 match: payment={} tx={}".format(
                            payment["id"], tx_hash))
                        import sqlite3
                        c = sqlite3.connect(vip.VIP_DB_PATH, timeout=20)
                        c.execute("UPDATE payments SET tx_hash = ? WHERE id = ?",
                                  (tx_hash, payment["id"]))
                        c.commit()
                        c.close()
                        return vip.confirm_payment(payment["id"])
            except Exception:
                continue
        return False
    except Exception as e:
        log.error("verify_erc20_payment: {}".format(e))
        return False

def crypto_polling_check():
    """
    Llamar periodicamente desde el bot. Verifica pagos crypto pendientes.
    Devuelve lista de payment_ids confirmados en esta corrida.
    """
    confirmed = []

    pending_trc20 = vip.get_pending_payments(method="crypto_trc20", max_age_hours=CRYPTO_MAX_AGE_HOURS)
    pending_erc20 = vip.get_pending_payments(method="crypto_erc20", max_age_hours=CRYPTO_MAX_AGE_HOURS)

    for p in pending_trc20:
        if verify_trc20_payment(p):
            confirmed.append(p["id"])

    for p in pending_erc20:
        if verify_erc20_payment(p):
            confirmed.append(p["id"])

    return confirmed
