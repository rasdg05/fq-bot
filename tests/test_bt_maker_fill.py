# -*- coding: utf-8 -*-
"""Fill-model de la entrada maker en backtest (bt_engine.maker_entry_fill_mask):
una limite pasiva en `entry_price` se llena SOLO si una vela SIGUIENTE penetra el
nivel mas alla de eps (touch NO llena). Verifica geometria long/short, ventana
TTL (excluye la vela de firing), y que coincide con la regla VIVA por-vela de
gold_paper.process_maker_pending. Sin red ni datos: arrays sinteticos.

Segunda mitad (V2): el fill deja de ser binario. `maker_fill_probability` mete la
COLA en la ecuacion — dos senales con la misma penetracion y flujo distinto no se
llenan igual — y `maker_expectancy`/`require_fill_modeled` impiden que una cifra
maker salga publicada con el fill asumido al 100%. Ese supuesto ya volteo un
signo en agosto (+0.060R -> -0.0350R), y esta vez levanta en vez de imprimirse."""
import numpy as np
import pandas as pd
import pytest

import bt_engine as eng

EPS = 1e-4   # 1 bps
TTL = 6


def _trades(rows):
    return pd.DataFrame([{"entry_index": ei, "entry_price": e, "direction": d}
                         for ei, e, d in rows])


def test_long_fills_on_penetration():
    low = np.array([100, 99.98, 100, 100, 100, 100, 100, 100.0])  # bar1 < 99.99
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is True


def test_long_misses_on_no_touch():
    low = np.full(8, 100.0)        # nunca penetra por debajo de 99.99
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


def test_short_fills_on_penetration():
    high = np.array([100, 100.02, 100, 100, 100, 100, 100, 100.0])  # bar1 > 100.01
    low = np.full(8, 99.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.SHORT)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is True


def test_firing_bar_is_excluded():
    # la penetracion ocurre SOLO en la vela de entrada (idx0); la ventana arranca
    # en idx1 -> NO debe contar como fill (modela una limite recien puesta).
    low = np.array([90, 100, 100, 100, 100, 100, 100, 100.0])
    high = np.full(8, 101.0)
    m = eng.maker_entry_fill_mask(_trades([(0, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


def test_ttl_window_respected():
    low = np.array([100, 100, 100, 100, 100, 100, 100, 90.0])   # penetra en idx7
    high = np.full(8, 101.0)
    t = _trades([(0, 100.0, eng.LONG)])
    assert bool(eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=6)[0]) is False  # ventana [1..6]
    assert bool(eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=7)[0]) is True   # ventana [1..7]


def test_no_evaluable_bars_is_miss():
    # entrada en la ULTIMA vela: no hay velas siguientes -> MISS (conservador)
    low = np.array([100, 99.0])
    high = np.array([101, 101.0])
    m = eng.maker_entry_fill_mask(_trades([(1, 100.0, eng.LONG)]), high, low,
                                  eps=EPS, ttl_bars=TTL)
    assert bool(m[0]) is False


# --- V2: la cola -----------------------------------------------------------

def _mercado(low_seq, *, vol=100.0, taker_buy=None, n_bars=None):
    """Velas sinteticas: low a medida, high fijo arriba, volumen plano."""
    low = np.asarray(low_seq, dtype=float)
    n = n_bars or len(low)
    high = np.full(n, 101.0)
    volume = np.full(n, float(vol))
    tb = None if taker_buy is None else np.full(n, float(taker_buy))
    return high, low, volume, tb


def test_la_cola_cero_reproduce_la_binaria():
    """El modelo COLAPSA en `maker_entry_fill_mask` cuando la cola tiende a cero.

    Es la afirmacion que hace legible toda la curva del informe: la regla que el
    repo uso hasta agosto no es "otra cosa", es la ESQUINA mas optimista de este
    modelo — la de estar siempre el primero. Si dejara de cumplirse, la tabla de
    `fill_quality` compararia peras con manzanas sin avisar.
    """
    high, low, vol, tb = _mercado([100, 99.0, 100, 100, 100, 100, 100, 100])
    t = _trades([(0, 100.0, eng.LONG)])
    mask = eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=TTL)
    p = eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL,
                                   queue_frac=1e-9, volume=vol, taker_buy=tb)
    assert p[0] == pytest.approx(float(mask[0]))


def test_la_probabilidad_nunca_supera_la_binaria():
    """p <= mask elementwise, SIEMPRE. El refinamiento no puede inventar fills.

    El flujo se cuenta solo mas alla de eps, asi que donde la binaria dice MISS
    esto tiene que decir 0 exacto. Sin esta cota, "modelar la cola" podria acabar
    siendo una forma elegante de subir el fill rate.
    """
    rng = np.random.default_rng(11)
    n = 40
    low = 100.0 - rng.random(n) * 0.5
    high = 100.0 + rng.random(n) * 0.5
    vol = rng.random(n) * 1000 + 1
    t = _trades([(i, 100.0, eng.LONG if i % 2 else eng.SHORT) for i in range(n - TTL)])
    mask = eng.maker_entry_fill_mask(t, high, low, eps=EPS, ttl_bars=TTL)
    for q in (0.01, 0.5, 5.0):
        p = eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL,
                                       queue_frac=q, volume=vol)
        assert np.all(p <= mask.astype(float) + 1e-12)
        assert np.all(p[~mask] == 0.0)
        assert np.all((p >= 0) & (p <= 1))


def test_mas_cola_nunca_llena_mas():
    """Monotonia: la P(fill) no sube al meter mas gente por delante."""
    high, low, vol, _ = _mercado([100, 99.995, 99.99, 100, 100, 100, 100, 100])
    t = _trades([(0, 100.0, eng.LONG)])
    ps = [eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL,
                                     queue_frac=q, volume=vol)[0]
          for q in (0.1, 0.5, 1.0, 4.0)]
    assert all(a >= b for a, b in zip(ps, ps[1:]))


def test_el_flujo_firmado_es_el_del_lado_que_te_consume():
    """A una BID la consume el taker SELL; el taker BUY se cruza contra el ask y
    no toca tu cola. Con el mismo volumen total, mas compras agresivas => menos
    P(fill) para un LONG. Contar el volumen total seria contar el doble."""
    high, low, vol, _ = _mercado([100, 99.9, 100, 100, 100, 100, 100, 100])
    t = _trades([(0, 100.0, eng.LONG)])
    kw = dict(eps=EPS, ttl_bars=TTL, queue_frac=1.0, volume=vol)
    p_vendedores = eng.maker_fill_probability(t, high, low, taker_buy=vol * 0.1, **kw)
    p_compradores = eng.maker_fill_probability(t, high, low, taker_buy=vol * 0.9, **kw)
    assert p_vendedores[0] > p_compradores[0]


def test_sin_cola_declarada_no_hay_modelo():
    """Cola cero o negativa ES asumir fill del 100%: se dice, no se acepta."""
    high, low, vol, _ = _mercado([100, 99.0, 100, 100, 100, 100, 100, 100])
    t = _trades([(0, 100.0, eng.LONG)])
    with pytest.raises(ValueError):
        eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL,
                                   queue_frac=0.0, volume=vol)
    with pytest.raises(ValueError):      # ni las dos, ni ninguna
        eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL)
    with pytest.raises(ValueError):      # queue_frac mide cola en volumen
        eng.maker_fill_probability(t, high, low, eps=EPS, ttl_bars=TTL,
                                   queue_frac=1.0)


# --- V2: la invariante de publicacion --------------------------------------

def _simulado(cost, **extra):
    t = pd.DataFrame({"entry_price": [100.0] * 4, "stop_price": [99.0] * 4,
                      "exit_price": [101.0, 99.0, 101.0, 99.0],
                      "direction": [eng.LONG] * 4, "bars_held": [5] * 4,
                      "outcome": ["win", "loss", "win", "loss"]})
    for k, v in extra.items():
        t[k] = v
    return eng.simulate(t, cost=cost, stop_on_ruin=False)["trades"]


def test_simulate_marca_la_procedencia_del_fill():
    """Cada fila sale diciendo COMO se decidio que la limite se llenaba."""
    taker = _simulado(eng.CostModel(maker_entry=False))
    assert set(taker["fill_model"]) == {eng.FILL_TAKER}
    techo = _simulado(eng.CostModel(maker_entry=True))
    assert set(techo["fill_model"]) == {eng.FILL_ASSUMED}
    modelado = _simulado(eng.CostModel(maker_entry=True), fill_p=[0.5, 0.5, 1.0, 0.0])
    assert set(modelado["fill_model"]) == {eng.FILL_MODELED}


def test_no_se_publica_un_maker_con_fill_asumido():
    """LA invariante de V2. El techo de E8 (+0.060R) era exactamente esto y el
    fill real lo dejo en -0.0350R: el error del supuesto era MAS GRANDE que el
    margen entero. Ahora levanta en vez de imprimirse."""
    techo = _simulado(eng.CostModel(maker_entry=True))
    with pytest.raises(eng.MakerFillAssumedError):
        eng.maker_expectancy(techo)
    # y tampoco cuela por la puerta de atras: sin procedencia, tampoco sale
    with pytest.raises(eng.MakerFillAssumedError):
        eng.maker_expectancy(techo.drop(columns=["fill_model"]))
    with pytest.raises(eng.MakerFillAssumedError):
        eng.require_fill_modeled({"expectancy": 0.06})
    with pytest.raises(eng.MakerFillAssumedError):
        eng.require_fill_modeled({"fill_model": [eng.FILL_ASSUMED]})


def test_la_expectancy_pesa_por_probabilidad_de_fill():
    """E[R|fill] = sum(p*r)/sum(p): una senal que casi nunca llena no puede
    aportar su R entero al numero que se publica."""
    r = np.array([1.0, -1.0, 1.0, -1.0])
    p = np.array([1.0, 0.0, 1.0, 0.0])
    t = pd.DataFrame({"net_pnl_r": r, "fill_p": p,
                      "fill_model": [eng.FILL_MODELED] * 4})
    res = eng.require_fill_modeled(eng.maker_expectancy(t, reps=200))
    assert res["expectancy"] == pytest.approx(1.0)
    assert res["fill_rate"] == pytest.approx(0.5)
    assert res["n_esperada"] == pytest.approx(2.0)


def test_el_ic_incluye_la_incertidumbre_del_fill():
    """El fill es una moneda, no un dato: con p=0.5 el IC tiene que ser MAS ancho
    que con el mismo R y fill seguro. Si no, el numero publicado presume de una
    precision que no tiene."""
    rng = np.random.default_rng(3)
    r = rng.normal(0.1, 1.0, 400)
    seguro = pd.DataFrame({"net_pnl_r": r, "fill_p": 1.0,
                           "fill_model": [eng.FILL_MODELED] * len(r)})
    moneda = seguro.assign(fill_p=0.5)
    a = eng.maker_expectancy(seguro, reps=400)
    b = eng.maker_expectancy(moneda, reps=400)
    assert (b["hi"] - b["lo"]) > (a["hi"] - a["lo"])


@pytest.mark.parametrize("low_seq,expected", [
    ([100, 100, 100, 99.0, 100, 100, 100, 100], True),    # fill en idx3
    ([100, 100, 100, 100, 100, 100, 100, 100], False),    # nunca penetra
])
def test_agrees_with_gold_paper_live_rule(low_seq, expected):
    """La mascara vectorizada (backtest) debe dar el MISMO veredicto que la regla
    viva por-vela gold_paper.process_maker_pending alimentada vela a vela."""
    gp = pytest.importorskip("gold_paper")
    low = np.array(low_seq, dtype=float)
    high = np.full(len(low), 101.0)
    E, d = 100.0, eng.LONG
    # regla viva: arma la pendiente y la alimenta desde la vela SIGUIENTE
    pend = [{"pid": 1, "direction": d, "limit": E, "waited": 0}]
    led = []
    for j in range(1, len(low)):
        pend = gp.process_maker_pending(pend, led, float(high[j]), float(low[j]),
                                        j, eps=EPS, ttl_bars=TTL)
        if not pend:
            break
    live_filled = any(e["event"] == "MAKER_FILL" for e in led)
    mask = eng.maker_entry_fill_mask(_trades([(0, E, d)]), high, low,
                                     eps=EPS, ttl_bars=TTL)
    assert bool(mask[0]) == live_filled == expected
