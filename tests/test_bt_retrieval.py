# -*- coding: utf-8 -*-
"""
Tests de bt_retrieval: backend, vectorizador causal, estimador de vecindario y
-- lo critico -- el TEST DE LEAKAGE que falsea (o sostiene) la tesis de retrieval.

Sin red, sin monolito: datos sinteticos con una SENAL inyectada (un cluster de
estados cuya region del espacio paga, otra que pierde) para que un k-NN causal
tenga algo real que recuperar. Si el k-NN no separa esto, no separara nada.
"""
import numpy as np
import pandas as pd
import pytest

import bt_retrieval as R
import bt_walkforward as W


# ------------------------------------------------------------
# Generador sintetico con SENAL local recuperable
# ------------------------------------------------------------
def _make_events(n=1200, seed=7, signal=True):
    """Eventos con entry_index creciente (orden temporal), 2 features que definen
    un estado, y un pnl_r que -- si signal=True -- depende de la REGION del estado
    (la mitad 'buena' del espacio paga +0.6R, la 'mala' -0.6R, con ruido). Asi un
    vecino cercano predice el desenlace. Con signal=False el pnl_r es ruido puro.
    """
    rng = np.random.default_rng(seed)
    f1 = rng.standard_normal(n)
    f2 = rng.standard_normal(n)
    region = (f1 + f2) > 0  # frontera lineal en el espacio de estado
    if signal:
        base = np.where(region, 0.6, -0.6)
    else:
        base = np.zeros(n)
    pnl = base + rng.standard_normal(n) * 0.5
    entry_index = np.arange(n) * 3  # velas espaciadas; orden temporal estricto
    bars_held = rng.integers(2, 8, n)  # horizonte variable -> exit_index variable
    df = pd.DataFrame({
        "entry_index": entry_index,
        "bars_held": bars_held,
        "direction": rng.choice([R.LONG, R.SHORT], n),
        "p_master": f1,                 # feature continua 1
        "scorer_total": f2,             # feature continua 2
        "p_master_raw": f1 * 0.5,
        "p_master_pre_vol": f1,
        "scorer_volume": rng.standard_normal(n),
        "scorer_structure": rng.standard_normal(n),
        "scorer_liquidity": rng.standard_normal(n),
        "scorer_concept_stack": rng.standard_normal(n),
        "scorer_history": rng.standard_normal(n),
        "regime_score": rng.standard_normal(n),
        "field_confluence_count": rng.integers(3, 6, n),
        "field_pd_pct": rng.random(n),
        "field_w_effective": rng.random(n),
        "field_killzone": rng.choice(["london", "ny", "asia"], n),
        "field_bias_4h": rng.choice(["alcista", "bajista", "rango"], n),
        "field_bias_1h": rng.choice(["alcista", "bajista", "rango"], n),
        "regime_state": rng.choice(["drift", "stable", "shift_moderate"], n),
        "field_node_type": rng.choice(["colapso", "superposicion"], n),
        "outcome": np.where(pnl > 0, "win", "loss"),
        "pnl_r": pnl,
    })
    return df


# ------------------------------------------------------------
# Backend exacto
# ------------------------------------------------------------
def test_exact_backend_basico():
    be = R.ExactBackend(4)
    v = np.eye(4, dtype=np.float32)
    be.add_with_ids(v, np.arange(4, dtype=np.uint64))
    s, ids = be.search(np.array([[1, 0, 0, 0]], np.float32), 2)
    assert int(ids[0, 0]) == 0           # el mas similar es el propio eje
    assert s[0, 0] == pytest.approx(1.0)
    assert be.contains(0) and be.remove(0) and not be.contains(0)


def test_exact_backend_allowlist_y_vacia():
    be = R.ExactBackend(4)
    be.add_with_ids(np.eye(4, dtype=np.float32), np.arange(4, dtype=np.uint64))
    s, ids = be.search(np.array([[1, 0, 0, 0]], np.float32), 4,
                       allowlist=np.array([1, 2], np.uint64))
    assert set(int(i) for i in ids[0]) <= {1, 2}      # restringe a la allowlist
    with pytest.raises(ValueError):
        be.search(np.array([[1, 0, 0, 0]], np.float32), 2,
                  allowlist=np.array([], np.uint64))


def test_exact_write_load(tmp_path):
    be = R.ExactBackend(3)
    be.add_with_ids(np.eye(3, dtype=np.float32), np.arange(3, dtype=np.uint64))
    p = tmp_path / "i.pkl"
    be.write(str(p))
    be2 = R.ExactBackend.load(str(p))
    s, ids = be2.search(np.array([[0, 1, 0]], np.float32), 1)
    assert int(ids[0, 0]) == 1


# ------------------------------------------------------------
# Vectorizador causal
# ------------------------------------------------------------
def test_vectorizer_l2_norm_y_fit_solo_pasado():
    df = _make_events(200)
    vz = R.StateVectorizer().fit(df.iloc[:100])     # fit con pasado
    V = vz.transform(df.iloc[100:])                 # transform del "futuro"
    norms = np.linalg.norm(V, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-5)       # L2-normalizado -> coseno
    assert V.shape[1] == vz.dim
    # robusto a NaN: una feature toda-NaN no rompe
    d2 = df.iloc[100:].copy()
    d2["p_master"] = np.nan
    V2 = vz.transform(d2)
    assert np.isfinite(V2).all()


def test_vectorizer_categoricas_no_dominan():
    """Una categorica a escala fija no debe acaparar la norma frente a continuas."""
    df = _make_events(300)
    vz = R.StateVectorizer().fit(df)
    V = vz.transform(df)
    # la energia de las primeras columnas (continuas) no es despreciable
    n_num = len(vz.numeric)
    cont_energy = (V[:, :n_num] ** 2).sum(axis=1).mean()
    assert cont_energy > 0.1


# ------------------------------------------------------------
# Estimador de vecindario
# ------------------------------------------------------------
def test_neighborhood_abstain_por_esparsidad():
    st = R.neighborhood_stats(scores=[0.1, 0.2], pnl_r=[1.0, -1.0],
                              sim_floor=0.5, n_floor=2)
    assert st["abstain"] is True               # nadie supera el radio -> abstain

    st2 = R.neighborhood_stats(scores=[0.9, 0.8, 0.7], pnl_r=[1.0, 1.0, -1.0],
                               sim_floor=0.5, n_floor=2)
    assert st2["abstain"] is False
    assert st2["n_in_radius"] == 3
    assert st2["expectancy_r"] > 0


def test_neighborhood_recencia_pondera_recientes():
    # vecino reciente gana (+1), viejo pierde (-1); el decaimiento debe inclinar +
    st = R.neighborhood_stats(scores=[0.9, 0.9], pnl_r=[1.0, -1.0],
                              ages=[1.0, 1000.0], sim_floor=0.5, n_floor=1,
                              decay_bars=50)
    assert st["expectancy_r"] > 0


# ------------------------------------------------------------
# *** TEST DE LEAKAGE (la puerta de F0) ***
# ------------------------------------------------------------
def _run_modes(df, embargo=8, k=50, n_splits=6):
    folds, valid_index = W.folds_from_labeled(df, n_splits=n_splits, embargo=embargo)
    assert len(folds) > 0
    res = {}
    for mode in ("causal", "oracle", "placebo"):
        oos = R.retrieval_oos(df, folds, valid_index, k=k, mode=mode,
                              sim_floor=0.3, n_floor=5, seed=1)
        res[mode] = R.retrieval_ablation(oos, gate_threshold=0.0)
    return res


def test_leakage_causal_recupera_senal_real():
    """Con SENAL real, el k-NN CAUSAL debe dar edge>0: las senales que el
    vecindario marca positivas pagan mas que la base. Es la tesis sosteniendose."""
    df = _make_events(n=1500, signal=True)
    res = _run_modes(df)
    base = res["causal"]["base"]["expectancy_r"]
    gate = res["causal"]["gate_pass"]["expectancy_r"]
    assert res["causal"]["gate_pass"]["n"] > 30
    assert gate > base                      # condicionar mejora la expectancy
    assert res["causal"]["edge_vs_base_r"] > 0.05


def test_leakage_placebo_colapsa():
    """Barajar el desenlace en el indice debe DESTRUIR el edge (vuelve ~0). Si el
    placebo conserva edge, hay fuga o bug -> no fiarse de los numeros."""
    df = _make_events(n=1500, signal=True)
    res = _run_modes(df)
    edge_real = res["causal"]["edge_vs_base_r"]
    edge_placebo = res["placebo"]["edge_vs_base_r"]
    assert abs(edge_placebo) < 0.5 * edge_real + 0.05   # colapsa frente al real


def test_leakage_sin_senal_no_inventa_edge():
    """Sin senal (pnl puro ruido), el causal NO debe fabricar edge. Si lo hace,
    el estimador esta sobreajustando -> alarma."""
    df = _make_events(n=1500, signal=False)
    res = _run_modes(df)
    edge = res["causal"]["edge_vs_base_r"]
    assert abs(edge) < 0.12                  # banda de ruido, sin edge espurio


def test_leakage_embargo_estable():
    """Barrido de embargo: la expectancy del gate causal debe ser ESTABLE, no
    decreciente al subir el embargo. Un decaimiento delataria fuga por solape."""
    df = _make_events(n=1600, signal=True)
    gates = []
    for emb in (0, 8, 24, 48):
        folds, vi = W.folds_from_labeled(df, n_splits=6, embargo=emb)
        oos = R.retrieval_oos(df, folds, vi, k=50, mode="causal",
                              sim_floor=0.3, n_floor=5, seed=1)
        gates.append(R.retrieval_ablation(oos)["gate_pass"]["expectancy_r"])
    gates = np.array(gates)
    assert np.all(np.isfinite(gates))
    # estable: el rango no se desploma al subir embargo (no es monotono a la baja)
    assert gates.min() > 0.5 * gates.max()


# ------------------------------------------------------------
# *** TEST DE APROXIMACION (#5): exacto vs turbovec ***
# ------------------------------------------------------------
def test_denso_turbovec_query_step():
    """Pivot DENSO: muchos estados (no solo los que disparan), indice grande con
    turbovec y queries subsampleadas (query_step). El leakage gate debe aguantar:
    causal recupera edge, placebo colapsa."""
    pytest.importorskip("turbovec")
    df = _make_events(n=5000, signal=True)        # 5k estados (denso)
    folds, vi = W.folds_from_labeled(df, n_splits=6, embargo=8)
    common = dict(k=50, sim_floor=0.3, n_floor=5, seed=1,
                  backend="turbovec", bit_width=4, query_step=5)
    oos_c = R.retrieval_oos(df, folds, vi, mode="causal", **common)
    oos_p = R.retrieval_oos(df, folds, vi, mode="placebo", **common)
    edge_c = R.retrieval_ablation(oos_c)["edge_vs_base_r"]
    edge_p = R.retrieval_ablation(oos_p)["edge_vs_base_r"]
    assert R.retrieval_ablation(oos_c)["gate_pass"]["n"] > 30
    assert edge_c > 0.05                          # densidad -> recupera la senal
    assert abs(edge_p) < 0.5 * edge_c + 0.05      # placebo colapsa


def test_replay_states_denso_sintetico():
    """replay_states emite un estado por vela con label forward en ATR."""
    import bt_features as bf
    rng = np.random.default_rng(3)
    n = 1500
    close = 100 + np.cumsum(rng.standard_normal(n))
    ts = pd.date_range("2024-01-01", periods=n, freq="5min")
    dfp = pd.DataFrame({"timestamp": ts, "open": close, "high": close + 1,
                        "low": close - 1, "close": close, "volume": 1.0})

    def fake_eval(dp, dm, dh, ds, *a, **k):
        # field/report minimos; nunca dispara (decision != fire)
        class F: pass
        f = F()
        for at in ("confluence_count", "pd_pct", "w_effective", "node_type",
                   "killzone", "killzone_priority", "bias_4h", "bias_1h",
                   "choch", "has_fuel"):
            setattr(f, at, 0.5 if at in ("pd_pct", "w_effective") else "x")
        return False, f, {"decision": "field_only", "p_master_data": {}, "score": {}}

    out = bf.replay_states(dfp, None, None, None, fake_eval, None, None, None, {},
                           min_lookback=50, step=1, horizon_bars=100)
    assert len(out) > 1000
    assert {"entry_index", "pnl_r", "bars_held", "fired", "outcome"} <= set(out.columns)
    assert out["bars_held"].iloc[0] == 100
    assert out["pnl_r"].notna().all()
    assert not out["fired"].any()   # fake_eval nunca dispara (decision != fire)


def test_replay_states_enriquece_filas_fired():
    """UNIFICADO: las filas fired=True cargan dir/entry/sl/targets reales del motor
    -> ese subset es el track record de senales (alimenta label_events + frontera)."""
    import bt_features as bf
    rng = np.random.default_rng(5)
    n = 900
    close = 100 + np.cumsum(rng.standard_normal(n))
    ts = pd.date_range("2024-01-01", periods=n, freq="5min")
    dfp = pd.DataFrame({"timestamp": ts, "open": close, "high": close + 1,
                        "low": close - 1, "close": close, "volume": 1.0})

    class F:
        def __init__(self, c):
            for at in ("confluence_count", "node_type", "killzone", "bias_4h"):
                setattr(self, at, 1.0)

    def fake_eval(dp, dm, dh, ds, *a, **k):
        i = len(dp) - 1
        c = float(dp["close"].iloc[-1])
        f = F(c)
        if i % 60 == 0:        # dispara periodicamente con niveles completos
            rep = {"decision": "fire", "direction": "long",
                   "levels": {"entry": c, "sl": c - 2, "tp1": c + 2, "tp2": c + 3,
                              "tp3": c + 3, "tp4": c + 5, "rr_tp3": 1.5}}
            return True, f, rep
        return False, f, {"decision": "field_only", "levels": {}}

    out = bf.replay_states(dfp, None, None, None, fake_eval, None, None, None, {},
                           min_lookback=100, step=1, horizon_bars=50)
    fired = out[out["fired"]]
    assert len(fired) >= 5
    # las filas fired llevan los niveles reales del motor y la direccion correcta
    assert fired["stop_price"].notna().all()
    assert fired["px_tp4"].notna().all()
    assert set(fired["direction"].unique()) <= {bf.LONG, bf.SHORT}
    assert (fired["direction"] == bf.LONG).all()
    assert (fired["entry_price"] == fired["target_price"] - 2).all()  # entry = motor, no close[i]
    # las no-fired no tienen niveles (NaN) pero si label denso
    nonf = out[~out["fired"]]
    assert nonf["stop_price"].isna().all()
    assert out["pnl_r"].notna().all()


def test_aproximacion_turbovec_vs_exacto():
    turbovec = pytest.importorskip("turbovec")
    df = _make_events(n=1500, signal=True)
    folds, vi = W.folds_from_labeled(df, n_splits=6, embargo=8)
    common = dict(k=50, mode="causal", sim_floor=0.3, n_floor=5, seed=1)
    oos_exact = R.retrieval_oos(df, folds, vi, backend="exact", **common)
    oos_turbo = R.retrieval_oos(df, folds, vi, backend="turbovec", bit_width=4, **common)
    e_exact = R.retrieval_ablation(oos_exact)["gate_pass"]["expectancy_r"]
    e_turbo = R.retrieval_ablation(oos_turbo)["gate_pass"]["expectancy_r"]
    # la aproximacion 4-bit no debe degradar la expectancy estimada fuera del ruido
    assert abs(e_turbo - e_exact) < 0.12


# --------------------------------------------------------------------------
# Eje A — variantes de vector (base vs +bloque quantum)
# --------------------------------------------------------------------------
def test_vector_variants_quantum_adds_block_dims():
    import pandas as pd
    cols = {c: [0.1, 0.2, 0.3] for c in R.DEFAULT_NUMERIC + R.QUANTUM_BLOCK}
    df = pd.DataFrame(cols)
    v = R.vector_variants()
    v["base"].fit(df)
    v["quantum"].fit(df)
    # mismas categóricas (ausentes aquí) -> la diferencia de dim es el bloque quantum
    assert v["quantum"].dim - v["base"].dim == len(R.QUANTUM_BLOCK)
    assert v["quantum"].dim > v["base"].dim


def test_quantum_block_is_disjoint_from_base():
    assert not (set(R.QUANTUM_BLOCK) & set(R.DEFAULT_NUMERIC))
