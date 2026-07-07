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


# --------- motor base (paper) -> tier free (pares cosecha) ---------

def _sig(d=1):
    return {"direction": d, "entry": 6.8050, "stop": 6.8537, "tp": 6.6530}


def test_motor_free_cosecha_va_a_free(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "FREE_ADMIN_ECHO", False)
    monkeypatch.setattr(bot, "broadcast_to_subscribers",
                        lambda msg, **kw: sent.append((msg, kw)) or (1, 0))
    bot._motor_free_broadcast(_sig(-1), {"symbol": "AVAX/USDT", "tf": "5m"})
    assert len(sent) == 1
    assert sent[0][1].get("tiers") == ["free"]
    assert "AVAX" in sent[0][0]


def test_motor_free_vip_bloqueado(monkeypatch):
    sent = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "FREE_ADMIN_ECHO", False)
    monkeypatch.setattr(bot, "broadcast_to_subscribers",
                        lambda msg, **kw: sent.append((msg, kw)) or (1, 0))
    for pair in ("SOL/USDT", "BTC/USDT", "ETH/USDT"):
        bot._motor_free_broadcast(_sig(1), {"symbol": pair, "tf": "5m"})
    assert sent == []


def test_motor_free_kl_honesto_del_fire(monkeypatch):
    capt = {}
    monkeypatch.setattr(bot, "_free_broadcast",
                        lambda rep, pair, kl: capt.update(pair=pair, kl=kl, rep=rep))
    bot._motor_free_broadcast(_sig(1), {"symbol": "XRP/USDT",
                                        "regime_tags": {"kl_low": False}})
    assert capt["kl"] is False                      # respeta el kl_low del fire
    bot._motor_free_broadcast(_sig(1), {"symbol": "XRP/USDT"})
    assert capt["kl"] is True                       # sin tag -> semántica sin-filtro
    assert capt["rep"]["direction"] == "long"
    assert capt["rep"]["levels"]["entry"] == 6.8050


def test_free_echo_admin_con_conteo(monkeypatch):
    echos = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "FREE_ADMIN_ECHO", True)
    monkeypatch.setattr(bot, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(bot, "broadcast_to_subscribers", lambda msg, **kw: (3, 0))
    monkeypatch.setattr(bot, "telegram_send",
                        lambda msg, cid=None, **kw: echos.append((msg, cid)) or True)
    bot._free_broadcast(_report(), "XRP/USDT", True)
    assert len(echos) == 1
    assert "3 entregada(s)" in echos[0][0] and "XRP/USDT" in echos[0][0]
    assert echos[0][1] == "123"


def test_flota_digest_individual_off_y_agregado(monkeypatch):
    import types
    fake_rt = types.SimpleNamespace(digest_every=288, counts={"fire": 2, "opened": 1, "vetoed": 1},
                                    account=types.SimpleNamespace(open=[]))
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_PAIRS_TF", "5m")
    monkeypatch.setattr(bot, "FREE_FLEET_DIGEST_EVERY", 2)
    monkeypatch.setattr(bot, "_FREE_FLEET_TICKS", {"n": 0})
    monkeypatch.setattr(bot, "_xsym_motor_runtime", lambda pair, lp: fake_rt)
    monkeypatch.setattr(bot, "_xsym_motor_paper_scan", lambda exchange, **kw: None)
    digests = []
    monkeypatch.setattr(bot, "broadcast_to_subscribers",
                        lambda msg, **kw: digests.append((msg, kw)) or (1, 0))
    monkeypatch.setattr(bot, "_XSYM_MOTOR", {"XRP/USDT": fake_rt})
    bot._free_pairs_scan(None, {"5m"})          # tick 1: sin digest
    assert fake_rt.digest_every == 0            # individual apagado
    assert digests == []
    bot._free_pairs_scan(None, {"5m"})          # tick 2: digest agregado
    assert len(digests) == 1
    assert "Flota free" in digests[0][0]
    assert digests[0][1].get("tiers") == ["admin"]


def test_free_echo_apagable(monkeypatch):
    echos = []
    monkeypatch.setattr(bot, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(bot, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(bot, "FREE_ADMIN_ECHO", False)
    monkeypatch.setattr(bot, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(bot, "broadcast_to_subscribers", lambda msg, **kw: (3, 0))
    monkeypatch.setattr(bot, "telegram_send",
                        lambda msg, cid=None, **kw: echos.append((msg, cid)) or True)
    bot._free_broadcast(_report(), "XRP/USDT", True)
    assert echos == []
