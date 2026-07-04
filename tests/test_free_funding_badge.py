# -*- coding: utf-8 -*-
"""Badge de FUNDING para el tier FREE (FQ_FREE_FUNDING): cuando el funding acompaña a la
dirección, la señal cruda gana 'FUNDING A FAVOR — probabilidad reforzada' (el "poquito
mejor de probabilidad" que pidió RasDG 2026-07-03). OFF (funding_favorable=False) -> señal
BYTE-IDÉNTICA. El badge NO es marcador VIP: pasa el candado free_leak_guard (una FREE con
badge sigue siendo FREE, jamás se confunde con producto premium). El sesgo direccional lo
decide el bot con _funding_favorable (mismo umbral validado que el boost VIP)."""
import motor_paper

import fq_bot_v3_2 as bot
import vip_format


def _long():
    return {"direction": "long",
            "levels": {"entry": 145.0, "sl": 142.0, "tp1": 148.0, "rr_tp1": 1.0}}


def _short():
    return {"direction": "short",
            "levels": {"entry": 145.0, "sl": 148.0, "tp1": 142.0, "rr_tp1": 1.0}}


# --------- render del badge (vip_format.build_free_signal) ---------

def test_off_es_byte_identica():
    base = vip_format.build_free_signal(_long(), pair="SOL/USDT")
    off = vip_format.build_free_signal(_long(), pair="SOL/USDT", funding_favorable=False)
    assert base == off
    assert "FUNDING A FAVOR" not in base


def test_favorable_agrega_badge():
    base = vip_format.build_free_signal(_long(), pair="SOL/USDT")
    boosted = vip_format.build_free_signal(_long(), pair="SOL/USDT", funding_favorable=True)
    assert "FUNDING A FAVOR" not in base
    assert "FUNDING A FAVOR" in boosted
    assert "probabilidad reforzada" in boosted


def test_short_tambien_recibe_badge():
    msg = vip_format.build_free_signal(_short(), pair="SOL/USDT", funding_favorable=True)
    assert "▼ SHORT" in msg and "FUNDING A FAVOR" in msg


def test_badge_pasa_el_candado_anti_fuga():
    """El badge FREE JAMÁS debe tripear el guard anti-fuga: no es marcador VIP. Se prueba en
    las 4 combinaciones (kl_passed x audience) porque _free_broadcast lo exige antes de enviar."""
    for kl in (True, False):
        for aud in ("free", "vip"):
            msg = vip_format.build_free_signal(_long(), pair="SOL/USDT",
                                               kl_passed=kl, audience=aud,
                                               funding_favorable=True)
            assert vip_format.free_leak_guard(msg), \
                "badge FREE bloqueado por el guard (kl=%s aud=%s)" % (kl, aud)
            assert "FUNDING A FAVOR" in msg


# --------- predicado direccional (bot._funding_favorable) ---------

def test_predicado_direccional(monkeypatch):
    # funding FRÍO (pctl 0.3): a favor del LONG, no del SHORT
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.3))
    assert bot._funding_favorable(_long(), "SOL/USDT") is True
    assert bot._funding_favorable(_short(), "SOL/USDT") is False
    # funding CALIENTE (pctl 0.8): a favor del SHORT, no del LONG
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.8))
    assert bot._funding_favorable(_short(), "SOL/USDT") is True
    assert bot._funding_favorable(_long(), "SOL/USDT") is False
    # zona NEUTRA (0.6): nadie
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.6))
    assert bot._funding_favorable(_long(), "SOL/USDT") is False
    assert bot._funding_favorable(_short(), "SOL/USDT") is False


def test_predicado_defensivo(monkeypatch):
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (None, None))
    assert bot._funding_favorable(_long(), "SOL/USDT") is False        # sin dato
    assert bot._funding_favorable({"direction": "x"}, "SOL/USDT") is False  # dirección rara
    assert bot._funding_favorable(None, "SOL/USDT") is False           # report None
