# -*- coding: utf-8 -*-
"""Ruteo de tiers (RasDG 2026-07-06): los pares VIP (BTC/ETH/SOL — los que pasaron el
gate) JAMÁS van al tier free; la flota FREE (los 10 pares cosecha) dispara SOLO al tier
free (broadcast_enabled=False, sin carril VIP) y salta pares con carril legacy dedicado
(LINK/BNB/BCH) para no doblar el scan."""
import fq_bot_v3_2 as bot


def _report():
    return {"direction": "long",
            "levels": {"entry": 100.0, "sl": 98.0, "tp1": 102.0, "rr_tp1": 1.0}}


# --------- configuración por default ---------

def test_vip_pairs_default():
    assert bot.VIP_PAIRS == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}


def test_flota_free_default_es_la_cosecha():
    assert bot.FREE_SCAN_PAIRS == ["ADA", "AVAX", "BCH", "BNB", "DOGE",
                                   "DOT", "LINK", "LTC", "TRX", "XRP"]
    for c in bot.FREE_SCAN_PAIRS:
        assert "{}/USDT".format(c) not in bot.VIP_PAIRS


def test_free_tier_default_on():
    assert bot.FREE_TIER_ENABLED is True


# --------- candado: pares VIP jamás al tier free ---------

def test_free_broadcast_bloquea_pares_vip(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "broadcast_to_subscribers",
                        lambda msg, **kw: sent.append((msg, kw)) or (1, 0))
    for pair in ("BTC/USDT", "ETH/USDT", "SOL/USDT"):
        bot._free_broadcast(_report(), pair, True)
    assert sent == []


def test_free_broadcast_deja_pasar_cosecha(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "broadcast_to_subscribers",
                        lambda msg, **kw: sent.append((msg, kw)) or (1, 0))
    bot._free_broadcast(_report(), "XRP/USDT", True)
    assert len(sent) == 1
    assert sent[0][1].get("tiers") == ["free"]
    assert sent[0][1].get("include_admin") is False


# --------- flota free: dedupe legacy + jamás VIP ---------

def test_flota_free_salta_vip_y_legacy(monkeypatch):
    llamadas = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_PAIRS_TF", "5m")
    monkeypatch.setattr(bot, "LINK_MOTOR_PAPER_ENABLED", True)   # carril legacy activo
    monkeypatch.setattr(bot, "BNB_MOTOR_PAPER_ENABLED", False)
    monkeypatch.setattr(bot, "BCH_MOTOR_PAPER_ENABLED", False)
    monkeypatch.setattr(bot, "_xsym_motor_paper_scan",
                        lambda exchange, **kw: llamadas.append(kw))
    bot._free_pairs_scan(None, {"5m"})
    pares = [k["pair"] for k in llamadas]
    assert "LINK/USDT" not in pares                 # legacy dedupe
    assert "BTC/USDT" not in pares                  # VIP jamás por el carril free
    assert "XRP/USDT" in pares and "ADA/USDT" in pares
    assert all(k["broadcast_enabled"] is False for k in llamadas)   # sin gate -> sin VIP
    assert all(k["kl_gated"] is True for k in llamadas)             # etiqueta KL honesta
    assert len(pares) == 9                          # 10 cosecha - LINK (legacy)


def test_flota_free_no_op_sin_free_tier(monkeypatch):
    llamadas = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", False)
    monkeypatch.setattr(bot, "_xsym_motor_paper_scan",
                        lambda exchange, **kw: llamadas.append(kw))
    bot._free_pairs_scan(None, {"5m"})
    assert llamadas == []


def test_flota_free_no_op_fuera_de_tf(monkeypatch):
    llamadas = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_PAIRS_TF", "5m")
    monkeypatch.setattr(bot, "_xsym_motor_paper_scan",
                        lambda exchange, **kw: llamadas.append(kw))
    bot._free_pairs_scan(None, {"15m"})
    assert llamadas == []
