# -*- coding: utf-8 -*-
"""
E2 — un fire suprimido tiene que dejar rastro REPRECIABLE.

Se medía lo que se abrió. `MOTOR_VETOED` se sellaba con killzone y motivo, pero
sin geometría: no había forma de saber qué R habría hecho la señal que no se
tomó, así que "¿el veto de londres salva o cuesta?" no tenía respuesta ni con un
año de ledger. El contrafactual sencillamente no existía.

Y había tres formas de suprimir un fire que ni siquiera se sellaban:
  · el gobernador lo rechaza (halt por drawdown, riesgo cero) -> solo un log
  · el report no se puede normalizar (sin niveles) -> caída silenciosa
  · el fill se rechaza por selección adversa -> sellado, pero sin geometría

Las regresiones que fija este archivo: cada camino por el que un fire NO se
convierte en posición queda sellado, con quién lo suprimió (`stage`) y con lo
necesario para repreciarlo.
"""
import pytest

import motor_paper
import feature_snapshot as fs
import segment_veto as sv
from execution import Account, HashLedger, PaperBroker, RiskGovernor


class _Field:
    def __init__(self, killzone="ny_am_kz"):
        self.killzone = killzone


def _report(direction="long", entry=100.0, sl=99.0, tp1=103.0):
    levels = {"entry": entry, "sl": sl}
    if tp1 is not None:
        levels["tp1"] = tp1
    return {"decision": "fire", "direction": direction, "levels": levels}


def _runtime(veto=None, governor=None):
    ledger = HashLedger()
    return motor_paper.MotorPaperRuntime(
        "SOL/USDT", account=Account("t", 10_000.0),
        broker=PaperBroker(ledger=ledger), governor=governor,
        veto=veto if veto is not None else sv.SegmentVeto())


def _events(rt, name):
    return [r["payload"] for r in rt.broker.ledger.records
            if r["payload"].get("event") == name]


# --- 1. el veto de segmento ahora es repreciable ----------------------------

def test_el_veto_sella_la_geometria():
    """Sin dirección/entry/stop/tp no se puede calcular el R de lo que no pasó."""
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    ev = _events(rt, "MOTOR_VETOED")[0]
    assert ev["direction"] == 1
    assert (ev["entry"], ev["stop"], ev["tp"]) == (100.0, 99.0, 103.0)


def test_el_veto_dice_quien_lo_suprimio():
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    assert _events(rt, "MOTOR_VETOED")[0]["stage"] == "segmento"


def test_el_veto_conserva_motivo_y_killzone():
    """No se pierde nada de lo que ya se sellaba (compatibilidad hacia atrás)."""
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    ev = _events(rt, "MOTOR_VETOED")[0]
    assert ev["killzone"] == "london_open_kz"
    assert "killzone=london_open_kz" in ev["why"]


# --- 2. los caminos que antes se perdían en silencio ------------------------

def test_el_rechazo_del_gobernador_queda_sellado():
    """Solo se logueaba. Sin sellarlo no hay forma de medir cuánto R cuesta el
    halt por drawdown — que es justo lo que hay que saber para calibrarlo."""
    class _Halt(RiskGovernor):
        def decide(self, account, requested_risk=None):
            return {"approved": False, "reason": "halt por drawdown"}

    rt = _runtime(governor=_Halt())
    rt.on_bar(True, _Field(), _report(), None, 100.0)
    ev = _events(rt, "MOTOR_VETOED")
    assert len(ev) == 1
    assert ev[0]["stage"] == "gobernador"
    assert "halt por drawdown" in ev[0]["why"]
    assert ev[0]["entry"] == 100.0            # repreciable


def test_el_fire_no_normalizable_queda_sellado():
    """Un fire sin tp1 se caía sin contarse. Un fire que no llega a señal ES un
    fire perdido: si son muchos, el motor está mudo por una razón arreglable."""
    rt = _runtime()
    rt.on_bar(True, _Field(), _report(tp1=None), None, 100.0)
    ev = _events(rt, "MOTOR_VETOED")
    assert len(ev) == 1 and ev[0]["stage"] == "normalize"


def test_cada_stage_lleva_su_contador():
    """Para /salud: 'el motor está mudo' se responde repartiendo entre culpables,
    no con un número agregado."""
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    rt.on_bar(True, _Field(), _report(tp1=None), None, 100.0)
    assert rt.counts["veto_segmento"] == 1
    assert rt.counts["veto_normalize"] == 1


def test_el_veto_de_segmento_sigue_contando_como_vetoed():
    """El contador histórico no cambia de significado por añadir los nuevos."""
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    assert rt.counts["vetoed"] == 1


def test_un_fire_que_abre_no_sella_veto():
    rt = _runtime()
    rt.on_bar(True, _Field(), _report(), None, 100.0)
    assert _events(rt, "MOTOR_VETOED") == []


# --- 3. el vector de E1 viaja con el veto -----------------------------------

def test_el_veto_lleva_el_vector_de_E1(monkeypatch):
    """Mismo vector que el OPEN: si no, los vetados no son comparables con los
    abiertos y el contrafactual compara peras con manzanas."""
    monkeypatch.setenv("FQ_FEATURE_SNAPSHOT", "1")
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    ev = _events(rt, "MOTOR_VETOED")[0]
    assert ev[fs.SCHEMA_KEY] == fs.SCHEMA_VERSION
    assert "p_master" in ev[fs.FEATURES_KEY]


def test_sin_el_flag_el_veto_no_lleva_claves_nuevas(monkeypatch):
    monkeypatch.delenv("FQ_FEATURE_SNAPSHOT", raising=False)
    rt = _runtime(veto=sv.parse(killzones="london_open_kz"))
    rt.on_bar(True, _Field("london_open_kz"), _report(), None, 100.0)
    assert fs.SCHEMA_KEY not in _events(rt, "MOTOR_VETOED")[0]


# --- 4. el informe: repreciar con la regla pesimista -------------------------

def test_reprecia_pesimista_el_empate():
    """Si TP y SL caen en la misma vela cuenta como stop. Misma convención que
    resolve_on_bar: sin esa regla el contrafactual se premia a sí mismo con un R
    que el motor vivo no habría cobrado."""
    from tools.veto_cost import outcome_r
    v = {"direction": 1, "entry": 100.0, "stop": 99.0, "tp": 103.0}
    assert outcome_r(v, highs=[103.5], lows=[98.5]) == -1.0


def test_reprecia_un_ganador():
    from tools.veto_cost import outcome_r
    v = {"direction": 1, "entry": 100.0, "stop": 99.0, "tp": 103.0}
    assert outcome_r(v, highs=[101.0, 103.5], lows=[100.0, 102.0]) == pytest.approx(3.0)


def test_reprecia_un_short():
    from tools.veto_cost import outcome_r
    v = {"direction": -1, "entry": 100.0, "stop": 101.0, "tp": 97.0}
    assert outcome_r(v, highs=[100.5], lows=[96.5]) == pytest.approx(3.0)


def test_sin_resolver_dentro_de_la_ventana_es_None():
    """None, no cero: 'no se resolvió' no es 'no ganó nada'."""
    from tools.veto_cost import outcome_r
    v = {"direction": 1, "entry": 100.0, "stop": 99.0, "tp": 103.0}
    assert outcome_r(v, highs=[100.5], lows=[99.5]) is None


def test_las_filas_previas_a_E2_no_cuentan_como_cero():
    """Un veto viejo sin geometría no se puede repreciar. Contarlo como 0R
    diluiría el resultado hacia 'los vetos no hacen nada' — que es exactamente la
    conclusión que un dato ausente NO puede sostener."""
    from tools.veto_cost import repriceable
    viejos = [{"event": "MOTOR_VETOED", "why": "killzone", "killzone": "london_open_kz"}]
    nuevos = [{"event": "MOTOR_VETOED", "direction": 1, "entry": 100.0,
               "stop": 99.0, "tp": 103.0}]
    assert repriceable(viejos + nuevos) == nuevos


def test_el_informe_reparte_por_stage(capsys):
    from tools.veto_cost import report
    report([{"event": "MOTOR_VETOED", "stage": "segmento"},
            {"event": "MOTOR_VETOED", "stage": "gobernador"},
            {"event": "MOTOR_VETOED", "stage": "segmento"}])
    out = capsys.readouterr().out
    assert "segmento" in out and "gobernador" in out
    assert "QUIÉN suprime" in out


def test_el_informe_marca_la_muestra_chica(capsys):
    """n<30 no concluye, ni a favor ni en contra del veto."""
    from tools.veto_cost import report
    vs = [{"event": "MOTOR_VETOED", "stage": "segmento", "direction": 1,
           "entry": 100.0, "stop": 99.0, "tp": 103.0} for _ in range(5)]
    report(vs, r_by_index={id(v): 1.0 for v in vs})
    assert "NO concluir" in capsys.readouterr().out
