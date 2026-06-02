# -*- coding: utf-8 -*-
"""
Guardian anti-fugas. Renderiza TODAS las superficies de cara al cliente y
verifica que no reaparezcan versiones, jerga interna del motor ni formulas
crudas. Blinda el trabajo de pulido: si alguien reintroduce "v5.1" o
"P_master" en una vista de cliente, este test lo caza.

La vista admin (build_about_admin, build_help_admin) queda EXCLUIDA a
proposito: ahi la matematica es bienvenida.
"""
import re
import pytest

import branding
import vip_format
import public_format
import legal

# Tokens prohibidos en cualquier superficie de cliente.
BANNED = [
    "v5.1", "v5.0", "v4.2", "v4.3",
    "Mistral", "Emergent Time", "TauPostulate", "FQv5",
    "Quantum Timelines", "QTE", "Phase E", "tau(t)", "postulado",
    "Thompson", "kappa_evo", "kappa(p)", "P_master", "Theta(D)",
    "Opus 4", "Sonnet 4", "Claude",
    "Silver Bullet", "OTE 70", "Power of 3", "Inducement",
    "bucket_key", "Monte Carlo", "QAOA", "f_confluencia",
    "phi^", "w_clock", "W_eff",
]

# Patrones de formula cruda que no deben verse (P(SL) 22%, EV +1.4R, etc.)
FORMULA_PATTERNS = [
    re.compile(r"P\(SL\)"),
    re.compile(r"P\(TP\d?\)"),
    re.compile(r"EV\s*[+-]?\d"),         # "EV +1.4" / "EV 1.4"
    re.compile(r"Coherencia\s+\d"),
    re.compile(r"\bphi\b"),
    re.compile(r"sync_score"),
]


def _fake_field():
    class F:
        bias_aligned = True
        pd_zone = "discount"
        has_fuel = True
        recent_sweep = True
        pool_low = True
        pool_high = False
        confluence_count = 4
        node_type = "colapso"
    return F()


def _fake_decision():
    return {
        "direction": "long",
        "p_master_data": {"p_master": 3.0},
        "levels": {
            "entry": 145.0, "sl": 142.0, "risk": 3.0,
            "tp1": 148.0, "rr_tp1": 1.0, "tp2": 151.0, "rr_tp2": 2.0,
            "tp3": 154.0, "rr_tp3": 3.0, "tp4": 157.0, "rr_tp4": 4.0,
        },
    }


def _fake_qa():
    return {
        "n_paths": 500,
        "coherence": 0.78,
        "probabilities": {
            "p_reach_tp1": 0.62, "p_reach_tp2": 0.41, "p_tp1": 0.62,
            "p_tp2": 0.41, "p_sl": 0.22, "expected_R": 1.4,
        },
        "regimes": {"bull_continuation": 0.47, "bear_reversal": 0.21,
                    "sweep_and_reverse": 0.12},
    }


def _client_surfaces():
    """Lista de (nombre, texto) de todas las vistas de cliente."""
    field = _fake_field()
    decision = _fake_decision()
    qa = _fake_qa()
    levels = decision["levels"]
    levels["sl_anchor"] = "OB_bullish"
    last = {"close": 145.0}

    summary = {
        "w30": {"n": 3, "win_rate": 0.66, "expectancy": 0.5,
                "profit_factor": 2.0, "best_pnl": 1.8},
        "w90": {"n": 5, "win_rate": 0.8, "expectancy": 1.1,
                "profit_factor": 4.0, "best_pnl": 2.5},
        "total": {"n": 7, "win_rate": 0.7, "expectancy": 0.7,
                  "profit_factor": 3.0, "best_pnl": 2.5},
        "longest_streak": 3,
    }

    surfaces = [
        # VIP
        ("vip.signal", vip_format.build_vip_signal(field, decision)),
        ("vip.analisis", vip_format.build_vip_analisis("long", levels, "alcista", 3.0, last, qa=qa)),
        ("vip.about", vip_format.build_about_vip()),
        ("vip.welcome", vip_format.build_welcome()),
        ("vip.welcome_tier", vip_format.build_welcome_for_tier("vip")),
        ("vip.help", vip_format.build_help_vip()),
        ("vip.help_free", vip_format.build_help_free()),
        ("vip.resultados", vip_format.build_resultados(summary)),
        # Publico
        ("pub.info", public_format.build_info()),
        ("pub.pricing", public_format.build_pricing()),
        ("pub.welcome", public_format.build_welcome()),
        ("pub.resultados", public_format.build_resultados(summary)),
        ("pub.closure", public_format.build_closure_announcement(
            {"direction": "long", "outcome": "tp3", "pnl_r": 1.8,
             "minutes_open": 90, "ts_emitted": "2026-06-01T13:00:00Z",
             "ts_closed": "2026-06-01T14:30:00Z"},
            {"n_closed_7d": 4, "win_rate_7d": 0.75, "expectancy_7d": 1.1})),
        ("pub.teaser", public_format.build_new_signal_teaser(
            {"direction": "short", "session": "ny", "p_master_final": 3.0,
             "ts_emitted": "2026-06-01T16:00:00Z"})),
        ("pub.tp3", public_format.build_tp3_celebration(
            {"direction": "long", "ts_emitted": "2026-06-01T13:00:00Z",
             "hit_price": 152.30, "tp3": 152.30})),
        ("pub.weekly", public_format.build_weekly_stats(
            {"n_closed_7d": 4, "win_rate": 0.75, "expectancy": 1.1,
             "profit_factor": 3.0, "best_pnl": 2.5})),
        # CTAs y mantras (todas las variantes)
    ] + [
        ("pub.cta.%d" % i, public_format.build_cta(i))
        for i in range(len(public_format.CTA_VARIANTS))
    ] + [
        ("pub.mantra.%d" % i, public_format.build_mantra(i))
        for i in range(len(public_format.MANTRAS))
    ] + [
        # Legal
        ("legal.disclaimer", legal.build_disclaimer()),
        ("legal.terms", legal.build_terms()),
        ("legal.privacy", legal.build_privacy()),
        ("legal.menu", legal.build_legal_menu()),
    ]
    return surfaces


@pytest.mark.parametrize("name,text", _client_surfaces())
def test_no_banned_tokens(name, text):
    lower = text.lower()
    hits = [tok for tok in BANNED if tok.lower() in lower]
    assert not hits, "{}: tokens prohibidos {}".format(name, hits)


@pytest.mark.parametrize("name,text", _client_surfaces())
def test_no_raw_formulas(name, text):
    hits = [p.pattern for p in FORMULA_PATTERNS if p.search(text)]
    assert not hits, "{}: formulas crudas {}".format(name, hits)


@pytest.mark.parametrize("name,text", _client_surfaces())
def test_no_version_numbers(name, text):
    # Cualquier "v5", "v4.x" suelto es fuga de versionado.
    assert not re.search(r"\bv\d+\.\d+\b", text), "{}: numero de version visible".format(name)
