# -*- coding: utf-8 -*-
"""Regresion del bug reportado por RasDG (2026-07-20): SOL y ETH "sin disparo en
todo el mes". La causa real: el candado de pares VIP en `_free_broadcast` cortaba
con un `return` temprano ANTES de la rama FQ_FREE_TO_VIP, asi que un descarte KL
de un par VIP (SOL/BTC/ETH) no le llegaba a NADIE -- ni al tier free (correcto,
el candado debe bloquear eso) ni al VIP etiquetado 'Senal FREE' (bug: DECISIONES.md
Sec.13 dice "los VIP ven todo"). Resultado en el chat: silencio total,
indistinguible de "el motor no encontro setup".

Estos tests sellan: (1) el candado sigue bloqueando el tier free para pares VIP,
(2) pero YA NO bloquea FQ_FREE_TO_VIP, (3) pares no-VIP siguen yendo a ambos, y
(4) el eco admin de supresion KL (_kl_pass) distingue "suprimida" de "silencio"."""
import fq_bot_v3_2 as b


def _report():
    return {"direction": "short", "p_master_data": {"p_master": 2.5},
            "levels": {"entry": 199.20, "sl": 199.70, "risk": 0.50,
                       "tp1": 196.72, "rr_tp1": 4.98, "tp2": 195.18, "rr_tp2": 8.06,
                       "tp3": 193.94, "rr_tp3": 10.55, "tp4": 192.70, "rr_tp4": 13.04}}


def _wire(monkeypatch):
    monkeypatch.setattr(b, "VIP_FORMAT_AVAILABLE", True)
    monkeypatch.setattr(b, "FREE_TIER_ENABLED", True)
    monkeypatch.setattr(b, "FREE_TO_VIP", True)
    monkeypatch.setattr(b, "FREE_FUNDING_ENABLED", False)
    monkeypatch.setattr(b, "FREE_ADMIN_ECHO", False)
    monkeypatch.setattr(b, "VIP_PAIRS", {"BTC/USDT", "ETH/USDT", "SOL/USDT"})
    sent = []
    monkeypatch.setattr(b, "broadcast_to_subscribers",
                         lambda msg, **kw: (sent.append((msg, kw.get("tiers"))), (1, 0))[1])
    return sent


def test_vip_pair_kl_discard_reaches_vip_not_free(monkeypatch):
    """SOL/USDT descartada por KL (kl_passed=False): el candado sigue tapando el
    tier free, pero la rama FREE_TO_VIP debe seguir entregando a VIP/trial -- antes
    del fix, el `return` temprano mataba ambos envios."""
    sent = _wire(monkeypatch)
    b._free_broadcast(_report(), "SOL/USDT", False)
    tiers_sent = [t for _, t in sent]
    assert ["free"] not in tiers_sent          # candado VIP-pair: sigue sin ir a free
    assert ["vip", "trial"] in tiers_sent      # pero SI llega a VIP etiquetado 'Senal FREE'


def test_non_vip_pair_reaches_both_tiers(monkeypatch):
    """Un par de cosecha (AVAX, no esta en VIP_PAIRS) sigue yendo a ambos: free Y
    vip->free, comportamiento sin cambios por este fix."""
    sent = _wire(monkeypatch)
    b._free_broadcast(_report(), "AVAX/USDT", False)
    tiers_sent = [t for _, t in sent]
    assert ["free"] in tiers_sent
    assert ["vip", "trial"] in tiers_sent


def test_kl_suppress_admin_echo_fires_for_vip_pair(monkeypatch):
    """Cuando el KL suprime un fire de un par VIP, el admin recibe un eco que dice
    'suprimida' -- distinto de simplemente no ver nada (silencio)."""
    import pandas as pd
    monkeypatch.setattr(b, "KL_FILTER", {"SOL"})
    monkeypatch.setattr(b, "KL_SUPPRESS_NOTIFY", True)
    monkeypatch.setattr(b, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(b, "VIP_PAIRS", {"BTC/USDT", "ETH/USDT", "SOL/USDT"})

    class _FakeMotorPaper:
        @staticmethod
        def kl_regime_live(closes):
            return {"low": False, "irrev": 0.67}

    import sys
    monkeypatch.setitem(sys.modules, "motor_paper", _FakeMotorPaper)
    echoes = []
    monkeypatch.setattr(b, "telegram_send", lambda text, chat_id=None: echoes.append(text))

    df = pd.DataFrame({"close": [100.0] * 40})
    result = b._kl_pass(df, "SOL/USDT")

    assert result is False
    assert len(echoes) == 1
    assert "suprim" in echoes[0].lower() and "SOL/USDT" in echoes[0]


def test_kl_suppress_admin_echo_silent_for_non_vip_pair(monkeypatch):
    """La flota cosecha NO dispara el eco admin (ya se ve en el stream FREE->VIP);
    solo los pares VIP (SOL/BTC/ETH) lo necesitan."""
    import pandas as pd
    monkeypatch.setattr(b, "KL_FILTER", {"AVAX"})
    monkeypatch.setattr(b, "KL_SUPPRESS_NOTIFY", True)
    monkeypatch.setattr(b, "TELEGRAM_CHAT_ID", "123")
    monkeypatch.setattr(b, "VIP_PAIRS", {"BTC/USDT", "ETH/USDT", "SOL/USDT"})

    class _FakeMotorPaper:
        @staticmethod
        def kl_regime_live(closes):
            return {"low": False, "irrev": 0.67}

    import sys
    monkeypatch.setitem(sys.modules, "motor_paper", _FakeMotorPaper)
    echoes = []
    monkeypatch.setattr(b, "telegram_send", lambda text, chat_id=None: echoes.append(text))

    df = pd.DataFrame({"close": [100.0] * 40})
    result = b._kl_pass(df, "AVAX/USDT")

    assert result is False
    assert echoes == []
