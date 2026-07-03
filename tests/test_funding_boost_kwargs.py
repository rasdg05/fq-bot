# -*- coding: utf-8 -*-
"""Boost de funding DIRECCIONAL (_funding_vip_kwargs): long con funding frío (pctl<=0.5)
o short con funding caliente (pctl>=0.7) — ambos lados validados in-cube. Zona neutra o
flag off -> {} (señal byte-idéntica). Defensivo ante fallo del fetch."""
import motor_paper

import fq_bot_v3_2 as bot


def test_boost_direccional(monkeypatch):
    monkeypatch.setattr(bot, "FUNDING_BOOST_ENABLED", True)
    # funding FRÍO (pctl 0.3): boost al LONG, nada al SHORT
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.3))
    assert bot._funding_vip_kwargs({"direction": "long"}, "SOL/USDT") == {"funding_boost": True}
    assert bot._funding_vip_kwargs({"direction": "short"}, "SOL/USDT") == {}
    # funding CALIENTE (pctl 0.8): boost al SHORT, nada al LONG
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.8))
    assert bot._funding_vip_kwargs({"direction": "short"}, "SOL/USDT") == {"funding_boost": True}
    assert bot._funding_vip_kwargs({"direction": "long"}, "SOL/USDT") == {}
    # zona NEUTRA (0.6): nadie
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (1e-4, 0.6))
    assert bot._funding_vip_kwargs({"direction": "long"}, "SOL/USDT") == {}
    assert bot._funding_vip_kwargs({"direction": "short"}, "SOL/USDT") == {}


def test_flag_off_y_fallos_defensivos(monkeypatch):
    monkeypatch.setattr(bot, "FUNDING_BOOST_ENABLED", False)
    assert bot._funding_vip_kwargs({"direction": "long"}, "SOL/USDT") == {}
    monkeypatch.setattr(bot, "FUNDING_BOOST_ENABLED", True)
    monkeypatch.setattr(motor_paper, "funding_pctl_live", lambda p, **k: (None, None))
    assert bot._funding_vip_kwargs({"direction": "long"}, "SOL/USDT") == {}   # sin dato
    assert bot._funding_vip_kwargs({"direction": "otra"}, "SOL/USDT") == {}   # dirección rara
    assert bot._funding_vip_kwargs(None, "SOL/USDT") == {}                    # report None
