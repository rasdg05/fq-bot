# -*- coding: utf-8 -*-
"""
================================================================================
  GOLD LIVE (F2 etapa 2b) - adaptador de produccion del gate ORO al loop en vivo
  by RasDG_Sol + Claude

  El puente fino entre el motor en vivo y el gate de retrieval, para emitir
  senales VIP ORO en PAPEL (0% real). En cada vela, con el (field, report) que ya
  computa fusion_engine.evaluate_signal:

    1) arma el state-row IDENTICO al del indice denso (bt_features.extract_features
       -> mismas features, mismo vector) -> sin drift entre research y live.
    2) GoldGate.classify -> ORO / BASE / ABSTAIN.
    3) si ORO: direccion = field.propose_direction() (LECTURA DE CAMPO) y SL via
       calculate_levels; arma la senal con TP1 (ganador del cubo).

  La senal sale en el formato del PaperBroker / live_driver -> se enchufa al
  driver paper que ya audita el Reconciler. Pieza pura (gate y calculate_levels
  inyectables): se testea sin red ni monolito. El monolito solo llama a evaluate()
  por vela y rutea la senal por el governor -> broker (paper).
================================================================================
"""
import logging

import retrieval_gate as rg
from execution import LONG, SHORT
from live_driver import DIR_MAP

log = logging.getLogger("gold_live")


def live_state_row(field, report):
    """State-row para la query del gate, IDENTICO a las filas del indice denso:
    direction=LONG (convencion del replay denso) + extract_features(field, report).
    Asi el vector vivo se construye con las MISMAS features que el indice."""
    import bt_features as bf
    row = {"direction": LONG}
    row.update(bf.extract_features(field, report))
    return row


class GoldLiveEngine:
    """Evalua cada vela contra el gate ORO y, si dispara, arma la senal con la
    lectura de campo (direccion + niveles). gate y calculate_levels_fn son
    inyectables -> testeable sin monolito."""

    def __init__(self, gate, symbol, *, calculate_levels_fn, tp_r=1.0):
        self.gate = gate
        self.symbol = symbol
        self.calculate_levels_fn = calculate_levels_fn
        self.tp_r = tp_r

    @classmethod
    def from_dir(cls, gate_dir, symbol, *, calculate_levels_fn, tp_r=1.0,
                 **gate_overrides):
        """Carga el gate persistido (artefacto del build) y arma el engine."""
        gate = rg.GoldGate.from_dir(gate_dir, **gate_overrides)
        return cls(gate, symbol, calculate_levels_fn=calculate_levels_fn, tp_r=tp_r)

    def evaluate(self, field, report, df_primary, price):
        """Devuelve (signal|None, verdict). signal solo si el estado es ORO y el
        campo da direccion y niveles validos. verdict trae el tier y los stats del
        vecindario (para logging/telemetria)."""
        state = live_state_row(field, report)
        verdict = self.gate.classify(state)
        if verdict.get("tier") != rg.GOLD:
            return None, verdict
        draw = field.propose_direction() if hasattr(field, "propose_direction") else None
        direction = DIR_MAP.get(str(draw).lower()) if draw is not None else None
        if direction is None:
            verdict = {**verdict, "skip": "campo sin direccion"}
            return None, verdict
        try:
            levels = self.calculate_levels_fn(df_primary, draw)
            stop = float(levels["sl"])
        except Exception as e:
            verdict = {**verdict, "skip": f"niveles no disponibles: {e}"}
            return None, verdict
        sig = rg.build_gold_signal(self.symbol, direction, float(price), stop,
                                   tp_r=self.tp_r)
        if sig is None:
            verdict = {**verdict, "skip": "riesgo nulo"}
        return sig, verdict

    def signal_source(self, bar_feed):
        """Adapta el engine a un signal_source para live_driver (paper). bar_feed
        es callable() -> (field, report, df_primary, price) o None."""
        def _src():
            bar = bar_feed()
            if bar is None:
                return None
            field, report, df_primary, price = bar
            sig, _verdict = self.evaluate(field, report, df_primary, price)
            return sig
        return _src
