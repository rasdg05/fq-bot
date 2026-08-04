# -*- coding: utf-8 -*-
"""
E7 — la geometria juzgada sobre las 13.429 senales del cube, no sobre 90 cierres.

Dos regresiones que este archivo fija para siempre:

1. EL RECORRIDO DEL CUBE NO ES EL DEL LEDGER. El cube acumula MFE/MAE hasta el
   final del horizonte de la etiqueta, incluso DESPUES de que la barrera mato el
   trade (bt_labeler.label_event_grid). El ledger para al cerrar. Promediarlos, o
   leer "el TP esta lejos" desde el del cube, es la misma forma exacta del
   fantasma de julio: credito por un recorrido posterior a la muerte de la senal.

2. LA LECTURA DE SEPARACION CLASICA ES TAUTOLOGICA. "Ganador" quiere decir que
   el precio toco el TP, luego su MFE es >= la distancia al TP por construccion:
   esa comparacion separa siempre, mida lo que mida. El juez honesto es contra la
   senal INVERTIDA (mfe' = -mae), o sea el signo de mfe_r + mae_r.
"""
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("pyarrow")

from tools import geometry_report as gr


# --- fixture: un cube minimo con la misma forma que cosecha_cubes/ -----------

def _cube_rows():
    """2 eventos x 2 tps x 2 horizontes = 8 filas, como el cube real (largo)."""
    rows = []
    for ev, (ts, direction, pnl) in enumerate([
            ("2024-01-01T00:00:00", 1, -1.0),
            ("2024-01-02T00:00:00", -1, 2.0)]):
        for tp in ("tp1", "tp4"):
            for h, mfe, mae in ((96, 1.5, -1.0), (288, 6.0, -4.0)):
                rows.append({
                    "entry_index": ev, "entry_ts": ts, "direction": direction,
                    "bars_held": 3, "pnl_r": pnl if tp == "tp4" else pnl / 2.0,
                    "outcome": "loss" if pnl < 0 else "win",
                    "tp": tp, "horizon": h, "mfe_r": mfe, "mae_r": mae,
                })
    return rows


@pytest.fixture
def cube_dir(tmp_path):
    df = pd.DataFrame(_cube_rows())
    df.to_parquet(tmp_path / "tp_cube_SOL_USDT.parquet")
    df.to_parquet(tmp_path / "tp_cube_BTC_USDT.parquet")
    return str(tmp_path)


# --- 1. cargar una CELDA, no el cubo entero ---------------------------------

def test_carga_una_celda_y_no_cuenta_la_senal_doce_veces(cube_dir):
    """El cube es largo: sumar filas contaria cada senal una vez por celda."""
    closes = gr.load_cube_closes(cube_dir, tp="tp4", horizon=288)
    assert len(closes) == 4                      # 2 eventos x 2 simbolos
    assert {c["symbol"] for c in closes} == {"SOL_USDT", "BTC_USDT"}
    assert all(c["mfe_r"] == 6.0 for c in closes)


def test_filtra_por_simbolo(cube_dir):
    closes = gr.load_cube_closes(cube_dir, tp="tp4", horizon=288, symbol="SOL_USDT")
    assert len(closes) == 2


def test_el_cube_no_trae_orden_de_barra(cube_dir):
    """Si algun dia lo trajera, el contrafactual dejaria de ser cota inferior;
    hasta entonces la ausencia es un hecho que el informe debe declarar."""
    closes = gr.load_cube_closes(cube_dir, tp="tp4", horizon=288)
    assert all(c.get("mfe_bar") is None and c.get("mae_bar") is None
               for c in closes)


# --- 2. la invariante: los dos recorridos NO se mezclan ----------------------

def test_el_cube_se_marca_como_scope_horizonte(cube_dir):
    closes = gr.load_cube_closes(cube_dir, tp="tp4", horizon=288)
    assert gr.excursion_scope(closes) == gr.SCOPE_HORIZON


def test_el_ledger_se_marca_como_scope_vida(tmp_path):
    import json
    p = tmp_path / "l.jsonl"
    p.write_text(json.dumps({"payload": {
        "event": "CLOSE", "pnl_r": 1.0, "mfe_r": 1.2, "mae_r": -0.3}}) + "\n")
    closes = gr.load_closes(jsonl_path=str(p))
    assert gr.excursion_scope(closes) == gr.SCOPE_LIFE


def test_mezclar_cube_y_ledger_levanta(cube_dir):
    """LA invariante de E7. Sin esto, alguien promedia el MFE +6.66R del cube con
    el del ledger y publica un numero que no mide nada."""
    closes = gr.load_cube_closes(cube_dir, tp="tp4", horizon=288)
    closes.append({"event": "CLOSE", "pnl_r": 1.0, "mfe_r": 1.0, "mae_r": -0.5,
                   gr.SCOPE_KEY: gr.SCOPE_LIFE})
    with pytest.raises(gr.MixedScopeError):
        gr.excursion_scope(closes)


# --- 3. no acreditar recorrido posterior a la muerte de la senal -------------

def _h(pnl_r, mfe_r, mae_r, direction=1):
    return {"event": "CLOSE", "pnl_r": pnl_r, "mfe_r": mfe_r, "mae_r": mae_r,
            "direction": direction, gr.SCOPE_KEY: gr.SCOPE_HORIZON}


def test_scope_horizonte_no_concluye_que_el_tp_esta_lejos(capsys):
    """Con el ledger esto dispara 'Recoger antes'. Con el cube NO puede: ese MFE
    pudo ocurrir despues del stop. Es el fantasma otra vez."""
    closes = [_h(-1.0, 1.8, -1.0) for _ in range(40)]
    gr.report_tp_too_far(closes)
    out = capsys.readouterr().out
    assert "COTA SUPERIOR" in out
    assert "Recoger antes" not in out


def test_scope_vida_si_concluye(capsys):
    """La lectura del ledger no se degrada por soportar el cube."""
    closes = [{"event": "CLOSE", "pnl_r": -1.0, "mfe_r": 1.8, "mae_r": -1.0}
              for _ in range(40)]
    gr.report_tp_too_far(closes)
    assert "Recoger antes" in capsys.readouterr().out


def test_scope_horizonte_no_concluye_que_el_sl_esta_cerca(capsys):
    closes = [_h(+2.0, 3.0, -1.5) for _ in range(40)]
    gr.report_sl_too_tight(closes)
    out = capsys.readouterr().out
    assert "COTA SUPERIOR" in out
    assert "Ensancharlo los salvaria" not in out


def test_el_banner_declara_el_scope(capsys):
    gr.scope_banner([_h(-1.0, 1.0, -1.0)])
    assert "scope=horizonte" in capsys.readouterr().out


# --- 4. separacion honesta: contra la senal invertida, no contra el desenlace -

def test_la_lectura_clasica_se_deja_enganar_pero_la_nueva_no(capsys):
    """Ganadores con MFE alto y perdedores con MAE alto: la comparacion clasica
    canta 'separan' por pura construccion, mientras la asimetria (MFE+MAE) es
    exactamente cero -> invertir la senal daba lo mismo. Un volado."""
    closes = [_h(+2.0, 4.0, -1.0) for _ in range(50)]
    closes += [_h(-1.0, 1.0, -4.0) for _ in range(50)]

    gr.report_distribution(closes)
    assert "Separan" in capsys.readouterr().out          # la tautologica pica

    gr.report_separation(closes, reps=200)
    out = capsys.readouterr().out
    assert "NO separa" in out                            # la honesta no
    assert "volado" in out


def test_detecta_separacion_real(capsys):
    """Recorrido asimetrico a favor: el IC95% de MFE+MAE por encima de cero."""
    closes = [_h(+2.0, 3.0, -0.5) for _ in range(60)]
    closes += [_h(-1.0, 2.0, -1.0) for _ in range(60)]
    gr.report_separation(closes, reps=200)
    out = capsys.readouterr().out
    assert ">> SEPARA." in out


def test_la_separacion_se_desglosa_por_lado(capsys):
    """Un solo lado positivo puede ser deriva del mercado, no senal (H1)."""
    closes = [_h(+1.0, 2.0, -0.5, direction=1) for _ in range(40)]
    closes += [_h(-1.0, 2.0, -0.5, direction=-1) for _ in range(40)]
    gr.report_separation(closes, reps=200)
    out = capsys.readouterr().out
    assert "long    n=   40" in out
    assert "short   n=   40" in out


def test_separacion_con_muestra_chica_no_concluye(capsys):
    closes = [_h(+1.0, 2.0, -0.5) for _ in range(5)]
    gr.report_separation(closes, reps=100)
    out = capsys.readouterr().out
    assert "NO concluir" in out
    assert ">> SEPARA." not in out


# --- 5. el contrafactual sobre el cube es una cota inferior, y lo dice -------

def test_el_contrafactual_declara_la_cota_cuando_casi_todo_es_ambiguo(capsys):
    """Sin orden de barra y con horizontes largos casi toda senal cruza ambos
    umbrales -> toda celda colapsa a -SL. La tabla no puede juzgar geometrias y
    el informe tiene que decirlo en vez de dejar leer '-0.4R' como veredicto."""
    closes = [_h(-1.0, 3.0, -3.0) for _ in range(100)]
    gr.counterfactual(closes, tps=[1.0], sls=[1.0])
    out = capsys.readouterr().out
    assert "COTA INFERIOR VACIA" in out
    assert "Ambiguedad maxima de la tabla: 100%" in out


def test_sin_ambiguedad_no_grita_cota(capsys):
    closes = [_h(+1.0, 3.0, -0.2) for _ in range(100)]
    gr.counterfactual(closes, tps=[1.0], sls=[1.0])
    out = capsys.readouterr().out
    assert "COTA INFERIOR VACIA" not in out
