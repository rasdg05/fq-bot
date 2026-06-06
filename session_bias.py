# -*- coding: utf-8 -*-
"""
================================================================================
  SESSION BIAS MODULE - FQ v5.4
  Clasificacion London / NY / Asia condicionada al sesgo diario (HTF)
================================================================================

  Tesis operativa (RasDG):

    "London es un fake move. New York es una continuacion. Asia es un rango."

  ...pero esas tres etiquetas SOLO se sostienen en un dia balanceado. La
  clave es DONDE esta el precio en el diario (sesgo HTF), no el reloj:

    - London es el FAKE cuando barre liquidez CONTRA el sesgo diario
      (engineering liquidity); NY revierte ese barrido hacia el sesgo.
    - London es el MOVIMIENTO REAL cuando corre CON el sesgo HTF; entonces
      NY solo EXTIENDE lo que London empezo.
    - En cualquiera de los dos casos, en un dia con sesgo, NY resuelve hacia
      la direccion del sesgo diario.
    - El rango de Asia es la liquidez que London corre. El barrido de London
      es desde donde NY continua.
    - Regla de volumen 4H: si la vela 4H de London cierra con volumen alto en
      una direccion, NY tiende a seguir esa direccion.

  Este modulo es PURO (sin I/O, sin red, sin reloj): recibe direcciones ya
  resueltas (+1 long / -1 short / 0 nulo) y devuelve un multiplicador SUAVE
  (acotado, estilo volume_modulator) + una etiqueta humana para reportes.
  No veta: solo pondera. Todo constante de tuning es override-able por env.
================================================================================
"""
import os

# ============================================================
# CONSTANTES DE TUNING (override-able por env)
# ============================================================
def _envf(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)

# Boost cuando la senal corre con el movimiento real / la continuacion NY.
W_ALIGN          = _envf("FQ_SB_W_ALIGN",        1.15)
# Castigo cuando la senal pelea contra el movimiento real / la continuacion.
W_FIGHT          = _envf("FQ_SB_W_FIGHT",        0.87)
# London balanceado: fade del barrido hacia la continuacion NY (leve favor).
W_LONDON_FADE    = _envf("FQ_SB_W_LONDON_FADE",  1.05)
# London balanceado sin barrido claro: baja conviccion (es el fake).
W_LONDON_FAKE    = _envf("FQ_SB_W_LONDON_FAKE",  0.95)
# Asia: rango pequeno -> conviccion direccional reducida.
W_ASIA_RANGE     = _envf("FQ_SB_W_ASIA_RANGE",   0.95)
# Modulacion por zona PD (premium/discount) en sesiones direccionales.
W_PD_BONUS       = _envf("FQ_SB_W_PD_BONUS",     1.04)
W_PD_PENALTY     = _envf("FQ_SB_W_PD_PENALTY",   0.97)
# Bonus extra cuando la 4H de London cerro con volumen alto a favor (NY sigue).
W_4H_VOL_BONUS   = _envf("FQ_SB_W_4H_VOL_BONUS", 1.08)

# Clamp final del multiplicador (suave, estilo vol_modulator [0.75,1.20]).
W_MIN            = _envf("FQ_SB_W_MIN",           0.80)
W_MAX            = _envf("FQ_SB_W_MAX",           1.25)

NEUTRAL = 1.0


# ============================================================
# HELPERS DE DIRECCION
# ============================================================
def dir_from_signal(direction):
    """'long' -> +1, 'short' -> -1, otro -> 0."""
    d = str(direction).lower()
    if d == "long":
        return 1
    if d == "short":
        return -1
    return 0


def dir_from_bias(bias_str):
    """Sesgo textual (bias_4h) -> direccion. 'alcista[ debil]' -> +1,
    'bajista[ debil]' -> -1, 'rango'/'lateral'/None -> 0."""
    b = str(bias_str).lower()
    if "alcista" in b:
        return 1
    if "bajista" in b:
        return -1
    return 0


def thrust_from_sweep(recent_sweep):
    """recent_sweep['direction'] -> direccion del EMPUJE de London.

    'high' = barrio los maximos (precio empujo hacia ARRIBA) -> +1
    'low'  = barrio los minimos (precio empujo hacia ABAJO)  -> -1
    None / sin info -> 0
    """
    if not recent_sweep:
        return 0
    side = str(recent_sweep.get("direction", "")).lower()
    if side == "high":
        return 1
    if side == "low":
        return -1
    return 0


def session_from_killzone(killzone_name):
    """Mapea el nombre de killzone (killzones_pd) a sesion macro.

    Devuelve 'london' / 'ny' / 'asia' / 'other'. 'london_close_kz' cae en
    horario NY-AM (CDMX) y es ventana de continuacion -> 'ny'. El overlap
    (handoff London->NY) tambien se trata como continuacion -> 'ny'.
    """
    kz = str(killzone_name).lower()
    if kz in ("silver_bullet_lo", "london_open_kz", "eu_pre_open"):
        return "london"
    if kz in ("asia_kz", "asia_open"):
        return "asia"
    if kz in ("silver_bullet_ny_am", "silver_bullet_ny_pm", "ny_am_kz",
              "ny_pm_kz", "ny_close_hour", "london_close_kz", "overlap"):
        return "ny"
    return "other"


def normalize_session(session):
    """Acepta etiquetas legacy (asia/london/ny/overlap) o nombres de killzone."""
    s = str(session).lower()
    if s in ("london", "ny", "asia", "other"):
        return s
    if s == "overlap":
        return "ny"
    return session_from_killzone(s)


# ============================================================
# CLASIFICACION DEL DIA
# ============================================================
def classify_day(bias_dir, london_thrust_dir=0):
    """Clasifica el dia y resuelve la direccion hacia la que NY tiende.

    Args:
        bias_dir:          sesgo diario/HTF (+1/-1/0).
        london_thrust_dir: empuje direccional de London (+1/-1/0).

    Returns dict:
        day_type:       'trending' | 'balanced'
        resolution_dir: direccion esperada de resolucion NY (+1/-1/0)
        london_real:    True si London corre CON el sesgo (movimiento real);
                        False si barre contra el sesgo (fake); None si N/A.
    """
    if bias_dir != 0:
        # Dia con sesgo: NY resuelve hacia el sesgo, corra o fakee London.
        london_real = None
        if london_thrust_dir != 0:
            london_real = (london_thrust_dir == bias_dir)
        return {"day_type": "trending",
                "resolution_dir": bias_dir,
                "london_real": london_real}
    # Dia balanceado: las etiquetas clasicas se sostienen. NY continua DESDE el
    # barrido de London (fade del empuje = reversion del fake).
    return {"day_type": "balanced",
            "resolution_dir": -london_thrust_dir,
            "london_real": None}


# ============================================================
# PESO PRINCIPAL
# ============================================================
def session_bias_weight(signal_dir, session, bias_dir, london_thrust_dir=0,
                        pd_zone="equilibrium", london_close_dir=0,
                        london_high_volume=False):
    """Multiplicador suave + etiqueta para una senal segun la tesis de sesiones.

    Args:
        signal_dir:        +1 long / -1 short (0 -> no-op neutral).
        session:           'london'/'ny'/'asia'/'overlap' o nombre de killzone.
        bias_dir:          sesgo diario/HTF (+1/-1/0).
        london_thrust_dir: empuje de London (+1/-1/0), de recent_sweep.
        pd_zone:           'premium'/'discount'/'equilibrium'.
        london_close_dir:  direccion del cierre 4H de London (+1/-1/0).
        london_high_volume:True si esa 4H cerro con volumen alto.

    Returns:
        (weight: float, label: str, detail: dict)
    """
    sess = normalize_session(session)
    day = classify_day(bias_dir, london_thrust_dir)
    res_dir = day["resolution_dir"]

    if signal_dir == 0:
        return NEUTRAL, "sin direccion", _detail(sess, day, NEUTRAL)

    w = NEUTRAL
    label = ""

    if sess == "asia":
        # "Asia es un rango pequeno": conviccion direccional reducida.
        w = W_ASIA_RANGE
        label = "Asia: rango (liquidez que London correra)"

    elif sess == "london":
        if day["day_type"] == "trending":
            # Movimiento real = sesgo. Pelear contra el = perseguir el fake.
            if signal_dir == bias_dir:
                w = W_ALIGN
                label = "London corre CON el sesgo (movimiento real)"
            else:
                w = W_FIGHT
                label = "London contra el sesgo (probable fake)"
        else:
            # Dia balanceado: London es el fake. Perseguir el empuje = castigo;
            # fadearlo hacia la continuacion NY = leve favor.
            if london_thrust_dir != 0 and signal_dir == london_thrust_dir:
                w = W_FIGHT
                label = "London fake: persiguiendo el barrido"
            elif london_thrust_dir != 0 and signal_dir == -london_thrust_dir:
                w = W_LONDON_FADE
                label = "London fake: fade hacia continuacion NY"
            else:
                w = W_LONDON_FAKE
                label = "London: dia balanceado, baja conviccion"

    elif sess == "ny":
        # Regla 4H: cierre de London con volumen alto manda la continuacion.
        edir = res_dir
        rule_4h = False
        if london_high_volume and london_close_dir != 0:
            edir = london_close_dir
            rule_4h = True
        if edir != 0 and signal_dir == edir:
            w = W_ALIGN
            label = ("NY continuacion (4H London alto vol)" if rule_4h
                     else "NY continuacion del barrido London")
        elif edir != 0 and signal_dir == -edir:
            w = W_FIGHT
            label = "NY contra la continuacion"
        else:
            w = NEUTRAL
            label = "NY sin direccion de continuacion clara"

    else:
        return NEUTRAL, "fuera de sesion macro", _detail(sess, day, NEUTRAL)

    # --- Modulacion PD (premium/discount) en sesiones direccionales ---
    if sess in ("london", "ny"):
        w *= _pd_factor(signal_dir, pd_zone)

    # --- Bonus por 4H de London con volumen alto a favor en NY ---
    if sess == "ny" and london_high_volume and london_close_dir == signal_dir \
            and signal_dir != 0:
        w *= W_4H_VOL_BONUS

    w = max(W_MIN, min(W_MAX, w))
    return w, label, _detail(sess, day, w, pd_zone=pd_zone)


def _pd_factor(signal_dir, pd_zone):
    """Longs favorecidos en discount, shorts en premium (ICT). Neutral en eq."""
    z = str(pd_zone).lower()
    if z == "discount":
        return W_PD_BONUS if signal_dir == 1 else W_PD_PENALTY
    if z == "premium":
        return W_PD_BONUS if signal_dir == -1 else W_PD_PENALTY
    return 1.0


def _detail(sess, day, w, pd_zone=None):
    d = {
        "session":        sess,
        "day_type":       day["day_type"],
        "resolution_dir": day["resolution_dir"],
        "london_real":    day["london_real"],
        "weight":         round(w, 4),
    }
    if pd_zone is not None:
        d["pd_zone"] = pd_zone
    return d


# ============================================================
# INTEGRACION CON FieldState (lee atributos, sin I/O)
# ============================================================
def session_bias_weight_from_field(field, direction,
                                   london_close_dir=0, london_high_volume=False):
    """Extrae los inputs del FieldState y devuelve (weight, label, detail).

    Degrada con gracia: si falta recent_sweep o bias_4h, esos inputs caen a 0
    y el peso tiende a neutral. La regla 4H solo se aplica si el caller pasa
    london_close_dir/london_high_volume (el field no los carga).
    """
    signal_dir = dir_from_signal(direction)
    bias_dir = dir_from_bias(getattr(field, "bias_4h", "rango"))
    thrust = thrust_from_sweep(getattr(field, "recent_sweep", None))
    pd_zone = getattr(field, "pd_zone", "equilibrium")
    session = getattr(field, "killzone", "fuera")
    return session_bias_weight(
        signal_dir, session, bias_dir,
        london_thrust_dir=thrust, pd_zone=pd_zone,
        london_close_dir=london_close_dir, london_high_volume=london_high_volume)


# ============================================================
# SELF-TESTS  -  python session_bias.py
# ============================================================
def _run_self_tests():
    print("Running session_bias self-tests...\n")

    # --- classify_day ---
    d = classify_day(+1, london_thrust_dir=+1)
    assert d["day_type"] == "trending" and d["resolution_dir"] == +1
    assert d["london_real"] is True, "London corre con sesgo -> real"
    d = classify_day(+1, london_thrust_dir=-1)
    assert d["resolution_dir"] == +1 and d["london_real"] is False, \
        "London contra sesgo -> fake, NY revierte hacia el sesgo"
    d = classify_day(0, london_thrust_dir=+1)
    assert d["day_type"] == "balanced" and d["resolution_dir"] == -1, \
        "Balanceado: NY continua fadeando el empuje de London"
    print("  [OK] classify_day")

    # --- London en dia con sesgo alcista ---
    # long CON el sesgo -> boost
    w_long, lbl, _ = session_bias_weight(+1, "london", +1, london_thrust_dir=+1)
    # short CONTRA el sesgo (persiguiendo el fake) -> castigo
    w_short, _, _ = session_bias_weight(-1, "london", +1, london_thrust_dir=+1)
    assert w_long > 1.0 >= w_short, (w_long, w_short)
    assert w_long > w_short
    print("  [OK] london trending boost/penalty")

    # --- London barriendo CONTRA el sesgo (fake) ---
    # bias alcista, London empuja abajo (fake). Un short que persigue el empuje
    # baja; un long alineado al sesgo sube.
    w_chase, _, _ = session_bias_weight(-1, "london", +1, london_thrust_dir=-1)
    w_with, _, _ = session_bias_weight(+1, "london", +1, london_thrust_dir=-1)
    assert w_with > w_chase
    print("  [OK] london fake-against-bias")

    # --- NY continuacion ---
    # dia con sesgo bajista -> NY resuelve short
    w_ny_short, lbl_s, _ = session_bias_weight(-1, "ny", -1)
    w_ny_long, _, _ = session_bias_weight(+1, "ny", -1)
    assert w_ny_short > 1.0 > w_ny_long
    assert "continuacion" in lbl_s
    print("  [OK] ny continuation")

    # --- Regla 4H volumen alto manda en NY (dia balanceado) ---
    # sin sesgo, sin la regla -> neutral si no hay thrust
    w_base, _, _ = session_bias_weight(+1, "ny", 0, london_thrust_dir=0)
    assert abs(w_base - NEUTRAL) < 1e-9
    # con cierre 4H London alto vol al alza -> NY sigue al alza (boost)
    w_4h, lbl4, _ = session_bias_weight(+1, "ny", 0, london_close_dir=+1,
                                        london_high_volume=True)
    w_4h_against, _, _ = session_bias_weight(-1, "ny", 0, london_close_dir=+1,
                                             london_high_volume=True)
    assert w_4h > 1.0 > w_4h_against
    assert "4H" in lbl4
    print("  [OK] london 4H high-volume rule drives NY")

    # --- Asia: rango, conviccion reducida ---
    w_asia, lbl_a, _ = session_bias_weight(+1, "asia", +1)
    assert w_asia < 1.0 and "rango" in lbl_a.lower()
    print("  [OK] asia range damp")

    # --- PD modulation ---
    w_disc, _, _ = session_bias_weight(+1, "ny", +1, pd_zone="discount")
    w_prem, _, _ = session_bias_weight(+1, "ny", +1, pd_zone="premium")
    assert w_disc > w_prem, "long en discount > long en premium"
    print("  [OK] pd modulation")

    # --- Clamp ---
    for sd in (+1, -1):
        for bd in (+1, -1, 0):
            for sess in ("london", "ny", "asia", "overlap", "fuera"):
                w, _, _ = session_bias_weight(sd, sess, bd, london_thrust_dir=bd,
                                              pd_zone="discount",
                                              london_close_dir=sd,
                                              london_high_volume=True)
                assert W_MIN <= w <= W_MAX, (sd, bd, sess, w)
    print("  [OK] weight always clamped to [{}, {}]".format(W_MIN, W_MAX))

    # --- session mapping ---
    assert session_from_killzone("silver_bullet_lo") == "london"
    assert session_from_killzone("ny_am_kz") == "ny"
    assert session_from_killzone("london_close_kz") == "ny"  # horario NY-AM
    assert session_from_killzone("asia_open") == "asia"
    assert normalize_session("overlap") == "ny"
    print("  [OK] session mapping")

    print("\nAll session_bias self-tests passed.")


if __name__ == "__main__":
    _run_self_tests()
