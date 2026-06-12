# -*- coding: utf-8 -*-
"""
================================================================================
  RETRIEVAL GATE (F2) - señal VIP ORO por expectancy del vecindario
  by RasDG_Sol + Claude

  F1 (bt_retrieval) demostró OOS, leakage-clean, que la expectancy del VECINDARIO
  (k-NN de estados análogos) concentra el edge en el top percentil:
    BTC top5%: exp +1.51R calmar 1.74   |   SOL top5%: exp +1.23R calmar 1.81
  (causal >> placebo, sin necesitar el oracle). Esta pieza convierte ese
  diagnóstico en una DECISIÓN: clasifica un estado nuevo como

    ORO     -> vecindario denso Y expectancy >= umbral del top percentil
    BASE    -> vecindario denso pero por debajo del umbral oro
    ABSTAIN -> vecindario ralo (la capa NO opina; no se arriesga capital)

  y, si es ORO, arma una señal {symbol,direction,entry,stop,tp} con TP1 al
  horizonte ganador del cubo (consumible TAL CUAL por execution.PaperBroker /
  live_driver -> paper primero, 0% real).

  Disciplina (deck §F2): nada decide hasta que F1 es positivo y pasa leakage; el
  umbral oro se CALIBRA offline con el OOS del research (no se inventa). Pieza
  pura: numpy/pandas, reusa bt_retrieval. Sin red, sin monolito, sin fusion_engine.
================================================================================
"""
import os
import json
import logging

import numpy as np
import pandas as pd

import bt_retrieval as btr

log = logging.getLogger("retrieval_gate")

GOLD, BASE, ABSTAIN = "gold", "base", "abstain"
LONG, SHORT = 1, -1

# top percentil que define "oro" (5% por defecto = lo que validamos en F1).
GOLD_TOP_PCT = float(os.environ.get("FQ_RETRIEVAL_GOLD_TOP_PCT", "0.05"))


def calibrate_gold_threshold(expectancies, top_pct=None):
    """Umbral ORO = percentil (1 - top_pct) de la expectancy del vecindario sobre
    estados CONFIDENT (no abstenidos) del OOS de research. Espeja el subset
    top5% del runner: oro = retr_expectancy_r por encima de ese percentil.

    expectancies: iterable de retr_expectancy_r (de retrieval_oos, confident).
    Devuelve el umbral (float) o None si no hay datos.
    """
    top_pct = GOLD_TOP_PCT if top_pct is None else float(top_pct)
    x = np.asarray([v for v in expectancies if v is not None and np.isfinite(v)],
                   dtype="float64")
    if x.size == 0:
        return None
    return float(np.quantile(x, 1.0 - top_pct))


def _one_row_df(state):
    """Normaliza un estado (dict/Series/df 1 fila) a DataFrame de 1 fila para el
    StateVectorizer."""
    if isinstance(state, pd.DataFrame):
        return state.iloc[[0]] if len(state) else state
    if isinstance(state, pd.Series):
        return state.to_frame().T
    return pd.DataFrame([dict(state)])


class StateIndex:
    """Índice vivo de analogía: StateVectorizer (fit causal) + backend k-NN +
    side-table id->pnl_r/entry_index. Envuelve bt_retrieval para consultar el
    vecindario de un estado NUEVO (no presente en el índice)."""

    def __init__(self, vectorizer, backend, id2pnl, id2entry=None):
        self.vec = vectorizer
        self.be = backend
        self.id2pnl = {int(k): float(v) for k, v in id2pnl.items()}
        self.id2entry = {int(k): float(v) for k, v in (id2entry or {}).items()}

    @classmethod
    def build(cls, past_df, *, backend="exact", bit_width=4, vectorizer=None):
        """Construye el índice desde estados PASADOS ya resueltos (pnl_r no NaN).
        El vectorizer se ajusta SOLO con ese pasado (sin leakage de escalado)."""
        df = past_df[past_df["pnl_r"].notna()].reset_index(drop=True)
        if len(df) == 0:
            raise ValueError("past_df sin estados resueltos (pnl_r)")
        vec = (vectorizer or btr.StateVectorizer()).fit(df)
        V = vec.transform(df)
        ids = df["entry_index"].to_numpy(dtype=np.uint64)
        be = btr.make_backend(backend, dim=vec.dim, bit_width=bit_width)
        be.add_with_ids(V, ids)
        ent = df["entry_index"].astype("int64")
        id2pnl = dict(zip(ent, df["pnl_r"].astype(float)))
        id2entry = dict(zip(ent, df["entry_index"].astype(float)))
        return cls(vec, be, id2pnl, id2entry)

    # ---- persistencia (artefacto de produccion por simbolo) ----
    INDEX_EXACT, INDEX_TURBO = "index.pkl", "index.turbo"

    def save(self, out_dir, *, backend="exact"):
        """Persiste scaler + indice + side-table en out_dir (retrieval/<ex>/<sym>/)."""
        os.makedirs(out_dir, exist_ok=True)
        self.vec.save(os.path.join(out_dir, "scaler.pkl"))
        fname = self.INDEX_EXACT if backend == "exact" else self.INDEX_TURBO
        self.be.write(os.path.join(out_dir, fname))
        ids = list(self.id2pnl.keys())
        pd.DataFrame({"id": ids, "pnl_r": [self.id2pnl[i] for i in ids],
                      "entry_index": [self.id2entry.get(i) for i in ids]}
                     ).to_parquet(os.path.join(out_dir, "outcomes.parquet"))

    @classmethod
    def load(cls, out_dir, *, backend="exact", bit_width=4):
        vec = btr.StateVectorizer.load(os.path.join(out_dir, "scaler.pkl"))
        if backend == "exact":
            be = btr.ExactBackend.load(os.path.join(out_dir, cls.INDEX_EXACT))
        else:
            be = btr.TurbovecBackend.load(os.path.join(out_dir, cls.INDEX_TURBO),
                                          dim=vec.dim, bit_width=bit_width)
        out = pd.read_parquet(os.path.join(out_dir, "outcomes.parquet"))
        id2pnl = dict(zip(out["id"].astype("int64"), out["pnl_r"].astype(float)))
        id2entry = dict(zip(out["id"].astype("int64"), out["entry_index"].astype(float)))
        return cls(vec, be, id2pnl, id2entry)

    def query(self, state, *, k=50, sim_floor=0.5, n_floor=None,
              decay_bars=None, max_age_bars=None):
        """Recupera el vecindario del estado y devuelve neighborhood_stats."""
        n_floor = (k // 2) if n_floor is None else n_floor
        q = self.vec.transform(_one_row_df(state))
        kk = min(k, len(self.id2pnl))
        scores, ids = self.be.search(q, kk)
        sc, nb = scores[0], ids[0]
        pnl = np.array([self.id2pnl[int(i)] for i in nb], dtype="float64")
        ages = None
        cur = state.get("entry_index") if hasattr(state, "get") else None
        if cur is not None and self.id2entry:
            ages = np.array([float(cur) - self.id2entry.get(int(i), float(cur))
                             for i in nb], dtype="float64")
        return btr.neighborhood_stats(sc, pnl, ages=ages, sim_floor=sim_floor,
                                      n_floor=n_floor, decay_bars=decay_bars,
                                      max_age_bars=max_age_bars)


class GoldGate:
    """Clasifica un estado en ORO / BASE / ABSTAIN según la expectancy de su
    vecindario contra el umbral oro calibrado. Es el GATE del F2 (deck §4)."""

    def __init__(self, index, gold_threshold, *, k=50, sim_floor=0.5,
                 n_floor=None, decay_bars=None, max_age_bars=None):
        self.index = index
        self.gold_threshold = gold_threshold
        self.k = k
        self.sim_floor = sim_floor
        self.n_floor = n_floor
        self.decay_bars = decay_bars
        self.max_age_bars = max_age_bars

    def classify(self, state):
        st = self.index.query(state, k=self.k, sim_floor=self.sim_floor,
                              n_floor=self.n_floor, decay_bars=self.decay_bars,
                              max_age_bars=self.max_age_bars)
        if st["abstain"]:
            tier = ABSTAIN
        elif (self.gold_threshold is not None
              and np.isfinite(st["expectancy_r"])
              and st["expectancy_r"] >= self.gold_threshold):
            tier = GOLD
        else:
            tier = BASE
        return {"tier": tier, **st}

    # ---- persistencia del gate completo (indice + umbral + params) ----
    def save(self, out_dir, *, backend="exact", meta_extra=None):
        """Persiste el indice y un meta.json con umbral oro + params del gate.
        El artefacto resultante lo reconstruye GoldGate.from_dir en el live."""
        self.index.save(out_dir, backend=backend)
        meta = {"backend": backend, "gold_threshold": self.gold_threshold,
                "k": self.k, "sim_floor": self.sim_floor, "n_floor": self.n_floor,
                "decay_bars": self.decay_bars, "max_age_bars": self.max_age_bars,
                "dim": self.index.vec.dim, "n_states": len(self.index.id2pnl)}
        if meta_extra:
            meta.update(meta_extra)
        with open(os.path.join(out_dir, "meta.json"), "w") as fh:
            json.dump(meta, fh, indent=2, default=float)

    @classmethod
    def from_dir(cls, out_dir, **overrides):
        """Reconstruye el gate desde el artefacto persistido (para el live)."""
        with open(os.path.join(out_dir, "meta.json")) as fh:
            meta = json.load(fh)
        backend = overrides.pop("backend", meta.get("backend", "exact"))
        idx = StateIndex.load(out_dir, backend=backend,
                              bit_width=int(meta.get("bit_width", 4)))
        params = {"k": int(meta.get("k", 50)), "sim_floor": meta.get("sim_floor", 0.5),
                  "n_floor": meta.get("n_floor"), "decay_bars": meta.get("decay_bars"),
                  "max_age_bars": meta.get("max_age_bars")}
        params.update(overrides)
        return cls(idx, meta.get("gold_threshold"), **params)


def classify_live(gate, field, report):
    """Clasifica una señal VIVA (field + report del motor) reusando EXACTAMENTE
    el mismo esquema de features con el que se construyó el índice
    (bt_features.extract_features). Así la consulta al vecindario ve lo mismo que
    el research: sin esto, los nombres de columna no cuadrarían con el scaler.

    Devuelve el verdict dict del gate ({"tier": gold/base/abstain, ...}) o None
    si no hay gate. Pieza puente para la entrega: el monolito la llama en el
    disparo para decidir la marca "VIP Gold". Import perezoso de bt_features para
    no arrastrar pandas si nadie clasifica en vivo."""
    if gate is None:
        return None
    import bt_features
    state = bt_features.extract_features(field, report)
    # `direction` es categórica del vectorizer y vive en el report, no en el field.
    state["direction"] = report.get("direction")
    return gate.classify(state)


def build_gold_signal(symbol, direction, entry, stop, *, tp_r=1.0):
    """Arma la señal {symbol,direction,entry,stop,tp} con TP1 a tp_r veces el
    riesgo (ganador del cubo: TP1 / horizonte ~8h). direction: LONG(+1)/SHORT(-1).
    Devuelve None si el riesgo es nulo. Formato idéntico al que consume
    execution.PaperBroker / live_driver (paper primero)."""
    direction = int(direction)
    entry, stop = float(entry), float(stop)
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    tp = entry + direction * float(tp_r) * risk
    return {"symbol": symbol, "direction": direction, "entry": entry,
            "stop": stop, "tp": tp}


def gold_signal_source(gate, state_feed, *, level_fn, tp_r=1.0):
    """Adapta el GoldGate a un signal_source para live_driver (paper primero).

    state_feed : callable() -> estado nuevo (dict) o None.
    level_fn   : callable(state) -> (symbol, direction, entry, stop) con la
                 lectura del campo en ese estado (en prod: field/calculate_levels;
                 en tests: un doble). Solo se llama si el estado es ORO.
    Devuelve un callable() -> signal dict (solo si ORO y niveles válidos) o None.
    """
    def _src():
        state = state_feed()
        if state is None:
            return None
        verdict = gate.classify(state)
        if verdict["tier"] != GOLD:
            return None
        symbol, direction, entry, stop = level_fn(state)
        return build_gold_signal(symbol, direction, entry, stop, tp_r=tp_r)
    return _src
