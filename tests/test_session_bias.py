# -*- coding: utf-8 -*-
"""Tests del modulo session_bias (London/NY/Asia condicionado al sesgo diario).

Cubre la tesis: London es fake cuando barre CONTRA el sesgo y real cuando corre
CON el; NY resuelve hacia el sesgo; Asia es rango; y la regla de la 4H de London
con volumen alto manda la continuacion de NY. El peso siempre es suave y acotado.
"""
import session_bias as sb


# --------------------------------------------------------------------------
# Helpers de direccion
# --------------------------------------------------------------------------
def test_dir_helpers():
    assert sb.dir_from_signal("long") == 1
    assert sb.dir_from_signal("SHORT") == -1
    assert sb.dir_from_signal("flat") == 0
    assert sb.dir_from_bias("alcista debil") == 1
    assert sb.dir_from_bias("bajista") == -1
    assert sb.dir_from_bias("rango") == 0
    assert sb.thrust_from_sweep({"direction": "high"}) == 1
    assert sb.thrust_from_sweep({"direction": "low"}) == -1
    assert sb.thrust_from_sweep(None) == 0


# --------------------------------------------------------------------------
# Clasificacion del dia
# --------------------------------------------------------------------------
def test_trending_day_ny_resolves_toward_bias():
    # London corre con el sesgo -> movimiento real, NY extiende.
    d = sb.classify_day(+1, london_thrust_dir=+1)
    assert d["day_type"] == "trending"
    assert d["resolution_dir"] == +1
    assert d["london_real"] is True
    # London barre contra el sesgo -> fake, pero NY igual revierte hacia el sesgo.
    d2 = sb.classify_day(+1, london_thrust_dir=-1)
    assert d2["resolution_dir"] == +1
    assert d2["london_real"] is False


def test_balanced_day_ny_continues_from_london_sweep():
    # Sin sesgo: NY continua fadeando el empuje de London.
    d = sb.classify_day(0, london_thrust_dir=+1)
    assert d["day_type"] == "balanced"
    assert d["resolution_dir"] == -1
    d2 = sb.classify_day(0, london_thrust_dir=-1)
    assert d2["resolution_dir"] == +1


# --------------------------------------------------------------------------
# London
# --------------------------------------------------------------------------
def test_london_real_move_boosted_fake_penalized():
    bias = +1  # diario alcista
    w_with, lbl_with, _ = sb.session_bias_weight(+1, "london", bias,
                                                 london_thrust_dir=+1)
    w_against, _, _ = sb.session_bias_weight(-1, "london", bias,
                                             london_thrust_dir=+1)
    assert w_with > 1.0
    assert w_against < 1.0
    assert "real" in lbl_with


def test_london_sweep_against_bias_is_the_fake():
    # Diario alcista, London empuja ABAJO (engineering liquidity = fake).
    # Perseguir ese empuje (short) debe pesar menos que alinearse al sesgo (long).
    bias = +1
    w_chase, _, _ = sb.session_bias_weight(-1, "london", bias,
                                           london_thrust_dir=-1)
    w_aligned, _, _ = sb.session_bias_weight(+1, "london", bias,
                                             london_thrust_dir=-1)
    assert w_aligned > w_chase


def test_london_balanced_low_conviction():
    w, lbl, detail = sb.session_bias_weight(+1, "london", 0, london_thrust_dir=0)
    assert w < 1.0
    assert detail["day_type"] == "balanced"


# --------------------------------------------------------------------------
# New York
# --------------------------------------------------------------------------
def test_ny_continuation_follows_bias():
    w_short, lbl, _ = sb.session_bias_weight(-1, "ny", -1)  # bias bajista
    w_long, _, _ = sb.session_bias_weight(+1, "ny", -1)
    assert w_short > 1.0 > w_long
    assert "continuacion" in lbl


def test_ny_london_4h_high_volume_rule_drives_direction():
    # Sin sesgo y sin empuje: neutral.
    w_base, _, _ = sb.session_bias_weight(+1, "ny", 0)
    assert abs(w_base - sb.NEUTRAL) < 1e-9
    # 4H de London cierra ALCISTA con volumen alto -> NY sigue arriba.
    w_follow, lbl, _ = sb.session_bias_weight(+1, "ny", 0, london_close_dir=+1,
                                              london_high_volume=True)
    w_counter, _, _ = sb.session_bias_weight(-1, "ny", 0, london_close_dir=+1,
                                             london_high_volume=True)
    assert w_follow > 1.0 > w_counter
    assert "4H" in lbl
    # Volumen NO alto -> la regla no aplica (vuelve a neutral).
    w_lowvol, _, _ = sb.session_bias_weight(+1, "ny", 0, london_close_dir=+1,
                                            london_high_volume=False)
    assert abs(w_lowvol - sb.NEUTRAL) < 1e-9


# --------------------------------------------------------------------------
# Asia
# --------------------------------------------------------------------------
def test_asia_is_range_damped():
    w_long, lbl, _ = sb.session_bias_weight(+1, "asia", +1)
    w_short, _, _ = sb.session_bias_weight(-1, "asia", -1)
    assert w_long < 1.0 and w_short < 1.0
    assert "rango" in lbl.lower()


# --------------------------------------------------------------------------
# Zona PD
# --------------------------------------------------------------------------
def test_pd_zone_modulation():
    # long en discount (barato) pesa mas que long en premium (estirado).
    w_disc, _, _ = sb.session_bias_weight(+1, "ny", +1, pd_zone="discount")
    w_prem, _, _ = sb.session_bias_weight(+1, "ny", +1, pd_zone="premium")
    assert w_disc > w_prem


# --------------------------------------------------------------------------
# Invariantes
# --------------------------------------------------------------------------
def test_weight_always_clamped():
    for sd in (+1, -1, 0):
        for bd in (+1, -1, 0):
            for sess in ("london", "ny", "asia", "overlap", "fuera"):
                for thrust in (+1, -1, 0):
                    w, lbl, detail = sb.session_bias_weight(
                        sd, sess, bd, london_thrust_dir=thrust,
                        pd_zone="discount", london_close_dir=sd,
                        london_high_volume=True)
                    assert sb.W_MIN <= w <= sb.W_MAX
                    assert isinstance(lbl, str)


def test_signal_dir_zero_is_neutral():
    w, lbl, _ = sb.session_bias_weight(0, "london", +1, london_thrust_dir=+1)
    assert abs(w - sb.NEUTRAL) < 1e-9


def test_session_mapping():
    assert sb.session_from_killzone("silver_bullet_lo") == "london"
    assert sb.session_from_killzone("london_open_kz") == "london"
    assert sb.session_from_killzone("ny_am_kz") == "ny"
    assert sb.session_from_killzone("london_close_kz") == "ny"  # horario NY-AM
    assert sb.session_from_killzone("asia_kz") == "asia"
    assert sb.normalize_session("overlap") == "ny"
    assert sb.normalize_session("LONDON") == "london"


# --------------------------------------------------------------------------
# Integracion con FieldState
# --------------------------------------------------------------------------
def test_from_field_extracts_inputs():
    class _Field:
        bias_4h = "alcista"
        recent_sweep = {"direction": "low"}  # empuje abajo (barrio minimos)
        pd_zone = "discount"
        killzone = "london_open_kz"

    f = _Field()
    # Diario alcista + London empuja abajo (fake) -> long alineado al sesgo
    # debe pesar > 1.0.
    w, lbl, detail = sb.session_bias_weight_from_field(f, "long")
    assert detail["session"] == "london"
    assert detail["day_type"] == "trending"
    assert w > 1.0


def test_from_field_degrades_gracefully_without_sweep():
    class _Field:
        bias_4h = "rango"
        recent_sweep = None
        pd_zone = "equilibrium"
        killzone = "fuera"

    f = _Field()
    w, lbl, detail = sb.session_bias_weight_from_field(f, "long")
    assert sb.W_MIN <= w <= sb.W_MAX
