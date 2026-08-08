# -*- coding: utf-8 -*-
"""
La frontera deja de ser una constante, y un tier deja de contarse sin su puerta.

`internal/BRIEF_FRONTERA_2026-08.md` escribió dos cosas que la medición corrige,
y las dos son de la misma familia que el fantasma de julio: no eran errores de
conocimiento, eran cifras apoyadas en un supuesto que nadie hacía cumplir.

1. **"La frontera son +0.07R"** — no es una constante. Es `-IC_lo`, y el IC
   depende de la n. Toda palanca que FILTRA señales sube la media y **aleja la
   vara** a la vez. Medido en el cube: cortar el tercil bajo de convicción sube
   el neto de tp4 en +0.022R y encarece la vara en +0.017R — o sea que **el 78%
   de lo que aparenta ganar se lo come el ensanchamiento del IC**. Comparar una
   config filtrada contra la vara de la config sin filtrar es un avance de
   mentira, y es barato de cometer.

2. **"Bajar comisiones: +0.06 a +0.09R, no depende de que ningún research salga
   bien"** — la aritmética del coste sí; que la cuenta ALCANCE el tier, no. El
   primer escalón de Binance que pide volumen (VIP1) pide $15M en 30 días. La
   estrategia emite ~45 señales/mes en el universo VIP; a la capacidad NETA que
   midió V3 ($22k) eso son ~$0.97M/mes, **15x por debajo**. La cuenta no puede
   ser lo bastante grande para ganarse el tier que abarataría el edge, porque el
   edge no sostiene una cuenta tan grande. Es la pared de V3 vista por el otro
   lado.

Es la tercera vez que el repo publica una cifra apoyada en un supuesto más
grande que el margen entero (fill al 100% en V2, liquidez de catálogo en V3,
tier de comisiones aquí). Por eso `FeeTierUnreachableError` falla CERRADO: una
puerta que no se puede evaluar no se cuenta como cruzada.
"""
import numpy as np
import pytest

pd = pytest.importorskip("pandas")

from tools.frontier_report import (                                # noqa: E402
    MAX_CAPITAL_LOCK_FRAC, TIERS, FeeTierUnreachableError,
    FrontierBarMovedError, conviction_cut, frontier_gap,
    monthly_volume_usd, require_own_bar, require_reachable)

T0 = pd.Timestamp("2020-01-01")


def _tier(clase, magnitud, bps=4.0):
    return ("tier de prueba", bps, (clase, magnitud), "nota")


# --------------------------------------------------------------------------
#  1) La vara se calcula sobre la n de cada configuración
# --------------------------------------------------------------------------

def test_brecha_es_menos_el_limite_inferior_del_ic():
    """La identidad que hace barato recalcular la vara en cada fila.

    Si `lo = media - h`, cruzar pide `media > h`, o sea que falta `-lo`. Que sea
    una identidad y no una aproximación es lo que permite exigirla en TODAS las
    filas sin coste — y una vara que cuesta cara es una vara que se omite.
    """
    rng = np.random.default_rng(11)
    x = rng.normal(0.05, 1.0, 800)
    brecha, media, n = frontier_gap(x)
    from tools.cube_report import _boot_ci
    lo, _hi, _p = _boot_ci(x)
    assert n == 800
    assert media == pytest.approx(float(x.mean()))
    assert brecha == pytest.approx(-lo)


def test_perder_muestra_encarece_la_vara():
    """Menos n -> IC más ancho -> hace falta MÁS media para cruzar.

    La vara es el semiancho `h = brecha + media`; separarla de la media es lo
    que permite ver el peaje. (Comparar brechas a secas no vale: la submuestra
    también mueve la media, y entonces se están midiendo dos cosas a la vez.)
    """
    rng = np.random.default_rng(3)
    grande = rng.normal(0.05, 1.0, 4000)
    chico = grande[:1333]
    b_g, m_g, n_g = frontier_gap(grande)
    b_c, m_c, n_c = frontier_gap(chico)
    assert n_c < n_g
    assert (b_c + m_c) > (b_g + m_g), "menos muestra tiene que ENCARECER la vara"


def test_el_peaje_del_filtrado_se_cuenta_aparte():
    """La regresión central: un filtro que sube la media NO cierra la brecha en
    la misma cantidad, y la diferencia hay que nombrarla o el avance es aparente.

    Réplica sintética de lo medido en el cube (tp4, corte del tercil bajo):
    la media sube y la vara se encarece a la vez.
    """
    rng = np.random.default_rng(5)
    base = rng.normal(0.01, 1.0, 3774)
    # el "filtro": se queda con 2/3 y de verdad rinde más
    filtrado = rng.normal(0.033, 1.0, 2510)

    b_base, m_base, _ = frontier_gap(base)
    b_filt, m_filt, _ = frontier_gap(filtrado)

    subida = m_filt - m_base
    cerrado = b_base - b_filt
    assert subida > 0, "el filtro tiene que subir la media para que el test diga algo"
    assert cerrado < subida, (
        "la brecha no puede cerrarse tanto como sube la media: la diferencia "
        "es el peaje de la muestra perdida y es lo que hay que reportar aparte")


def test_una_fila_sin_su_propia_vara_no_se_publica():
    require_own_bar({"brecha": 0.02, "n": 100})           # ok
    with pytest.raises(FrontierBarMovedError):
        require_own_bar({"neto": 0.09})                   # subió la media y ya
    with pytest.raises(FrontierBarMovedError):
        require_own_bar({"brecha": 0.02})                 # sin la n no hay vara
    with pytest.raises(FrontierBarMovedError):
        require_own_bar("tp4 mejoró un montón")


# --------------------------------------------------------------------------
#  2) Un tier no se cuenta sin su puerta
# --------------------------------------------------------------------------

def test_vip1_no_se_alcanza_con_el_volumen_que_genera_la_cuenta():
    """La regresión que le pone número a la palanca #1 del brief.

    $15M/30d contra los ~$0.97M que genera la estrategia a la capacidad neta de
    V3. No es "todavía no": es 15x, y la distancia crece si la cuenta encoge.
    """
    ok, motivo = require_reachable(_tier("volumen", 15_000_000.0), 970_973.0)
    assert ok is False
    assert "15,000,000" in motivo and "970,973" in motivo

    ok, _ = require_reachable(_tier("volumen", 500_000.0), 970_973.0)
    assert ok is True


def test_puerta_de_capital_sin_precio_falla_cerrado():
    """Sin precio no se evalúa, y no evaluarla NO es alcanzarla.

    Esta versión del módulo nació con el bug: trataba la puerta de capital como
    "sin requisito" y marcaba ALCANZABLE el tier que pide 500.000 HYPE
    inmovilizados. El espejismo, cometido dentro del módulo escrito para
    impedirlo.
    """
    with pytest.raises(FeeTierUnreachableError):
        require_reachable(_tier("capital", 500_000.0), 1e9, equity=22_000)
    with pytest.raises(FeeTierUnreachableError):
        require_reachable(_tier("capital", 10.0), 1e9, hype_price=40.0)


def test_puerta_de_capital_con_precio_se_juzga_contra_la_cuenta():
    # 10 HYPE a $40 = $400 sobre una cuenta de $22k -> 1.8%, dentro del tope
    ok, motivo = require_reachable(_tier("capital", 10.0), 1e9,
                                   equity=22_000, hype_price=40.0)
    assert ok is True
    assert "DIRECCIONAL" in motivo, "la exposición ajena a la estrategia se dice"

    # 500.000 HYPE a $40 = $20M sobre la misma cuenta -> imposible
    ok, motivo = require_reachable(_tier("capital", 500_000.0), 1e9,
                                   equity=22_000, hype_price=40.0)
    assert ok is False
    assert "20,000,000" in motivo


def test_puerta_desconocida_no_se_cuenta_como_ganada():
    with pytest.raises(FeeTierUnreachableError):
        require_reachable(_tier("desconocida", 0.0), 1e12, equity=1e9,
                          hype_price=40.0)


def test_el_tier_base_del_repo_es_el_coste_con_el_que_todo_esta_medido():
    """Si alguien baja este número, cambia en silencio TODAS las cifras netas
    del repo. Que esté fijado obliga a que sea una decisión, no un ajuste."""
    base = TIERS[0]
    assert base[1] == 5.00
    assert base[2] == ("ninguna", 0.0)


def test_ninguna_puerta_de_volumen_de_la_tabla_la_cruza_la_cuenta_medida():
    """~$0.97M/mes es la foto a la capacidad NETA de V3. Ningún escalón
    gateado por volumen entra ahí."""
    vol = 970_973.0
    for tier in TIERS:
        if tier[2][0] != "volumen":
            continue
        ok, _ = require_reachable(tier, vol)
        assert ok is False, "%s no debería alcanzarse con $%s/30d" % (tier[0], vol)


# --------------------------------------------------------------------------
#  3) El volumen sale de las señales, no de un catálogo
# --------------------------------------------------------------------------

def test_volumen_mensual_sale_del_stop_medido_y_cuenta_las_dos_piernas():
    """`notional = risk/stop_frac`, y cada trade cruza el book dos veces.

    El `stop_frac` sale de las propias señales. Es la lección de V3: su default
    de liquidez estaba 8x fuera del BTC real y por eso el tool contestaba con
    parámetros de catálogo durante meses.
    """
    n = 30
    t = pd.DataFrame({
        "entry_ts": [T0 + pd.Timedelta(days=i) for i in range(n)],
        "entry_price": [100.0] * n,
        "stop_price": [99.0] * n,           # stop_frac = 1%
    })
    vol, por_mes, stop_frac = monthly_volume_usd(t, equity=100_000,
                                                 risk_frac=0.01)
    assert stop_frac == pytest.approx(0.01)
    # 30 señales en ~29 días -> ~31.5/mes; notional = 1000/0.01 = 100_000
    assert por_mes == pytest.approx(30 / (29 / 30.44), rel=1e-6)
    assert vol == pytest.approx(por_mes * 2.0 * 100_000.0)


def test_encoger_la_cuenta_aleja_el_tier():
    """Corolario incómodo y medido: bajar el capital NO abarata nada, aleja el
    tier. El coste fijo por trade no escala; el volumen que compra el descuento,
    sí."""
    n = 30
    t = pd.DataFrame({
        "entry_ts": [T0 + pd.Timedelta(days=i) for i in range(n)],
        "entry_price": [100.0] * n,
        "stop_price": [99.5] * n,
    })
    grande, _, _ = monthly_volume_usd(t, equity=500_000, risk_frac=0.0025)
    chica, _, _ = monthly_volume_usd(t, equity=10_000, risk_frac=0.0025)
    assert chica < grande
    assert require_reachable(_tier("volumen", 15e6), chica)[0] is False


# --------------------------------------------------------------------------
#  4) El corte de convicción es un umbral pre-registrado, no un barrido
# --------------------------------------------------------------------------

def test_corte_de_conviccion_tira_un_tercio_y_solo_el_tercio_bajo():
    t = pd.DataFrame({"p_master": np.linspace(0.0, 1.0, 900),
                      "net_r": np.zeros(900)})
    d = conviction_cut(t)
    assert len(d) == pytest.approx(600, abs=2)
    assert d["p_master"].min() > t["p_master"].quantile(1 / 3) - 1e-9
    # `drop=None` es el control: sin corte no se toca nada
    assert len(conviction_cut(t, drop=None)) == 900


def test_el_tope_de_capital_inmovilizado_es_una_decision_visible():
    """No es una constante de mercado. Si algún día sube, que se vea en el diff:
    inmovilizar token para abaratar fees es exposición direccional ajena a la
    estrategia, y su varianza es mucho mayor que los +0.04R que compra."""
    assert 0.0 < MAX_CAPITAL_LOCK_FRAC <= 0.25
