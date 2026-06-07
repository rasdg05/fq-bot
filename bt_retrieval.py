# -*- coding: utf-8 -*-
"""
================================================================================
  BT RETRIEVAL - capa de expectancy por analogia (k-NN) sobre el harness bt_*
  by RasDG_Sol + Claude

  Estimador LOCAL no-parametrico que COMPLEMENTA al lightgbm global. Codifica
  cada estado de mercado (features del motor en la vela de senal) como vector,
  indexa el historico con su desenlace forward (pnl_r) adjunto, y en cada senal
  nueva recupera los k analogos mas cercanos -> expectancy empirica + WR +
  dispersion + confianza del vecindario.

  DISENO (lo que hace de fiar esta pieza):
    - CAUSALIDAD por construccion: el indice de un evento de test es el TRAIN de
      su fold walk-forward (ya purgado + embargado por bt_walkforward). Ningun
      vecino "vio el futuro" del query. El test de leakage (causal vs oracle vs
      placebo) lo demuestra o FALSA la tesis.
    - SYMBOL-AGNOSTICA: las mismas features/escalado se computan igual en SOL y
      BTC. La separacion es de DATOS (indice/escalador por simbolo), no de codigo.
    - BACKEND ENCHUFABLE: ExactBackend (numpy, fuente de verdad para validar) y
      TurbovecBackend (IdMapIndex 2/4-bit, aceleracion de produccion) detras del
      MISMO contrato. El test de aproximacion compara ambos.
    - ESCALADO causal: el StateVectorizer ajusta center/scale SOLO con el train
      (pasado); nunca con el test. L2-normaliza -> producto interno = coseno.

  Pieza pura: numpy/pandas. turbovec es import perezoso/opcional. No toca red,
  no toca el monolito, no toca fusion_engine. Se enchufa tras bt_labeler.
================================================================================
"""
import logging
import pickle

import numpy as np
import pandas as pd

log = logging.getLogger("bt_retrieval")

LONG = 1
SHORT = -1
WIN = "win"


# ============================================================
# BACKENDS (contrato comun, espejo de turbovec.IdMapIndex)
# ============================================================
class ExactBackend:
    """k-NN exacto por producto interno (numpy). Fuente de verdad.

    Mantiene una matriz de vectores L2-normalizados + sus ids uint64. La busqueda
    es matmul + top-k: O(n*dim) por query, microsegundos para los ~10k-50k
    eventos de un backtest. Espeja el contrato de turbovec para que el resto del
    codigo sea agnostico del backend.
    """

    def __init__(self, dim, bit_width=None):
        self.dim = int(dim)
        self.bit_width = bit_width  # ignorado (exacto); presente por simetria
        self._vecs = np.empty((0, self.dim), dtype=np.float32)
        self._ids = np.empty((0,), dtype=np.uint64)
        self._pos = {}  # id -> fila

    def add_with_ids(self, vectors, ids):
        vectors = np.ascontiguousarray(vectors, dtype=np.float32)
        ids = np.asarray(ids, dtype=np.uint64)
        if vectors.shape[0] != ids.shape[0]:
            raise ValueError("vectors e ids deben tener la misma longitud")
        if vectors.shape[1] != self.dim:
            raise ValueError(f"dim {vectors.shape[1]} != {self.dim}")
        for j, i in enumerate(ids):
            if int(i) in self._pos:
                raise ValueError(f"id {int(i)} ya presente")
            self._pos[int(i)] = self._vecs.shape[0] + j
        self._vecs = np.vstack([self._vecs, vectors]) if len(self._vecs) else vectors.copy()
        self._ids = np.concatenate([self._ids, ids])

    def contains(self, id):
        return int(id) in self._pos

    def remove(self, id):
        i = int(id)
        if i not in self._pos:
            return False
        row = self._pos.pop(i)
        keep = np.ones(self._vecs.shape[0], dtype=bool)
        keep[row] = False
        self._vecs = self._vecs[keep]
        self._ids = self._ids[keep]
        # reindexar
        self._pos = {int(v): p for p, v in enumerate(self._ids)}
        return True

    def search(self, queries, k, allowlist=None):
        """queries: (nq, dim). Devuelve (scores, ids) shape (nq, eff_k) uint64.

        allowlist (opcional): uint64 de ids candidatos. Empty -> ValueError
        (espeja turbovec; el llamador debe abstenerse antes). Ids ausentes se
        ignoran (a diferencia de turbovec, que lanza KeyError -> lo maneja el
        wrapper causal interseccion-antes).
        """
        Q = np.ascontiguousarray(queries, dtype=np.float32)
        if Q.ndim == 1:
            Q = Q[None, :]
        if self._vecs.shape[0] == 0:
            raise ValueError("indice vacio")
        if allowlist is not None:
            allow = np.asarray(allowlist, dtype=np.uint64)
            if allow.size == 0:
                raise ValueError("allowlist vacia")
            rows = np.array([self._pos[int(a)] for a in allow if int(a) in self._pos],
                            dtype=np.int64)
            if rows.size == 0:
                raise ValueError("allowlist sin ids presentes")
            sub = self._vecs[rows]
            sub_ids = self._ids[rows]
        else:
            sub = self._vecs
            sub_ids = self._ids
        sims = Q @ sub.T  # (nq, m)  producto interno = coseno (todo L2-norm)
        eff_k = min(k, sub.shape[0])
        # top-k por fila (sin ordenar, luego ordenamos el subconjunto)
        idx = np.argpartition(-sims, eff_k - 1, axis=1)[:, :eff_k]
        part = np.take_along_axis(sims, idx, axis=1)
        order = np.argsort(-part, axis=1)
        idx = np.take_along_axis(idx, order, axis=1)
        scores = np.take_along_axis(sims, idx, axis=1).astype(np.float32)
        ids = sub_ids[idx]
        return scores, ids

    def write(self, path):
        with open(path, "wb") as fh:
            pickle.dump({"dim": self.dim, "vecs": self._vecs, "ids": self._ids}, fh)

    @classmethod
    def load(cls, path):
        with open(path, "rb") as fh:
            d = pickle.load(fh)
        obj = cls(d["dim"])
        if len(d["ids"]):
            obj.add_with_ids(d["vecs"], d["ids"])
        return obj


class TurbovecBackend:
    """Envuelve turbovec.IdMapIndex (2/4-bit, SIMD). Import perezoso.

    Mismo contrato que ExactBackend. Gestiona los dos gotchas de causalidad de
    turbovec: allowlist vacia -> ValueError, e ids ausentes -> KeyError (aqui se
    intersecta con los presentes ANTES de buscar). Aproximado: el test #5 valida
    que el recall no degrada la expectancy estimada frente al exacto.
    """

    def __init__(self, dim, bit_width=4):
        import turbovec  # perezoso: solo si se pide este backend
        self._tv = turbovec
        self.dim = int(dim)
        # turbovec exige dim multiplo de 8: padding con ceros (no altera el
        # producto interno ni la norma L2; las dims extra aportan 0).
        self._pad = (-self.dim) % 8
        self._tdim = self.dim + self._pad
        self.bit_width = int(bit_width)
        self._idx = turbovec.IdMapIndex(self._tdim, self.bit_width)
        self._present = set()

    def _fit_pad(self, V):
        V = np.ascontiguousarray(V, dtype=np.float32)
        if V.ndim == 1:
            V = V[None, :]
        if self._pad:
            V = np.hstack([V, np.zeros((V.shape[0], self._pad), dtype=np.float32)])
        return np.ascontiguousarray(V, dtype=np.float32)

    def add_with_ids(self, vectors, ids):
        ids = np.asarray(ids, dtype=np.uint64)
        self._idx.add_with_ids(self._fit_pad(vectors), ids)
        self._present.update(int(i) for i in ids)

    def contains(self, id):
        return int(id) in self._present

    def remove(self, id):
        ok = self._idx.remove(np.uint64(int(id)))
        self._present.discard(int(id))
        return bool(ok)

    def search(self, queries, k, allowlist=None):
        Q = self._fit_pad(queries)
        try:
            self._idx.prepare()
        except Exception:
            pass
        if allowlist is not None:
            allow = np.asarray([int(a) for a in allowlist if int(a) in self._present],
                               dtype=np.uint64)
            if allow.size == 0:
                raise ValueError("allowlist sin ids presentes")
            scores, ids = self._idx.search(Q, k, allowlist=allow)
        else:
            scores, ids = self._idx.search(Q, k)
        return np.asarray(scores, dtype=np.float32), np.asarray(ids, dtype=np.uint64)

    def write(self, path):
        self._idx.write(path)

    @classmethod
    def load(cls, path, dim, bit_width=4):
        import turbovec
        obj = cls.__new__(cls)
        obj._tv = turbovec
        obj.dim = int(dim)
        obj.bit_width = int(bit_width)
        obj._idx = turbovec.IdMapIndex.load(path)
        obj._present = set()
        return obj


def make_backend(kind="exact", *, dim, bit_width=4):
    """Fabrica de backend. kind: 'exact' (default, fuente de verdad) | 'turbovec'."""
    if kind == "exact":
        return ExactBackend(dim)
    if kind == "turbovec":
        return TurbovecBackend(dim, bit_width)
    raise ValueError(f"backend desconocido: {kind}")


# ============================================================
# VECTOR DE ESTADO (symbol-agnostico, escalado causal)
# ============================================================
# Continuas: convicción del motor + scorer + regimen/volumen + estructura.
DEFAULT_NUMERIC = [
    "p_master", "p_master_raw", "p_master_pre_vol",
    "scorer_total", "scorer_volume", "scorer_structure",
    "scorer_liquidity", "scorer_concept_stack", "scorer_history",
    "regime_score",
    "field_confluence_count", "field_pd_pct", "field_w_effective",
]
# Categoricas: contexto/regimen. One-hot a ESCALA FIJA pequena (no dominan el
# producto interno frente a las continuas estandarizadas).
DEFAULT_CATEGORICAL = [
    "direction", "field_killzone", "field_bias_4h", "field_bias_1h",
    "regime_state", "field_node_type",
]


class StateVectorizer:
    """Construye el vector de estado L2-normalizado para producto interno.

    fit(): center=mediana, scale=IQR (robusto a colas de cripto) SOLO con datos
    pasados (train del fold). Aprende el vocabulario categorico del train.
    transform(): estandariza continuas, one-hot fijo de categoricas, concatena y
    L2-normaliza -> coseno. Imputa NaN con 0 (= mediana tras centrar).

    LEAKAGE: ajustar SIEMPRE con el train; transformar train y test con el MISMO
    fit. Nunca refit sobre el test.
    """

    def __init__(self, numeric=None, categorical=None, cat_scale=0.5):
        self.numeric = list(numeric if numeric is not None else DEFAULT_NUMERIC)
        self.categorical = list(categorical if categorical is not None else DEFAULT_CATEGORICAL)
        self.cat_scale = float(cat_scale)
        self.center_ = None
        self.scale_ = None
        self.vocab_ = None
        self.dim = None

    def _num_matrix(self, df):
        cols = []
        for c in self.numeric:
            s = pd.to_numeric(df[c], errors="coerce") if c in df.columns else pd.Series(
                np.nan, index=df.index)
            cols.append(s.to_numpy(dtype="float64"))
        return np.vstack(cols).T if cols else np.empty((len(df), 0))

    def fit(self, df):
        X = self._num_matrix(df)
        self.center_ = np.nanmedian(X, axis=0)
        q75, q25 = np.nanpercentile(X, [75, 25], axis=0)
        iqr = q75 - q25
        iqr[~np.isfinite(iqr) | (iqr <= 0)] = 1.0  # evita /0; columnas constantes
        self.scale_ = iqr
        self.vocab_ = {}
        for c in self.categorical:
            vals = sorted(set(df[c].dropna().astype(str))) if c in df.columns else []
            self.vocab_[c] = vals
        n_oh = sum(len(v) for v in self.vocab_.values())
        self.dim = len(self.numeric) + n_oh
        return self

    def transform(self, df):
        if self.center_ is None:
            raise RuntimeError("StateVectorizer no ajustado (llama a fit)")
        X = self._num_matrix(df)
        Z = (X - self.center_) / self.scale_
        Z = np.nan_to_num(Z, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32)
        blocks = [Z]
        for c in self.categorical:
            vocab = self.vocab_.get(c, [])
            if not vocab:
                continue
            col = df[c].astype(str).to_numpy() if c in df.columns else np.array([""] * len(df))
            oh = np.zeros((len(df), len(vocab)), dtype=np.float32)
            for j, v in enumerate(vocab):
                oh[col == v, j] = self.cat_scale
            blocks.append(oh)
        V = np.hstack(blocks).astype(np.float32) if len(blocks) > 1 else blocks[0]
        norms = np.linalg.norm(V, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return (V / norms).astype(np.float32)

    def save(self, path):
        with open(path, "wb") as fh:
            pickle.dump(self.__dict__, fh)

    @classmethod
    def load(cls, path):
        obj = cls()
        with open(path, "rb") as fh:
            obj.__dict__.update(pickle.load(fh))
        return obj


# ============================================================
# ESTIMADOR DEL VECINDARIO
# ============================================================
def neighborhood_stats(scores, pnl_r, ages=None, *, sim_floor=0.5, n_floor=1,
                       decay_bars=None, max_age_bars=None):
    """Reduce un vecindario (scores + pnl_r) a estadisticos de decision.

    scores : coseno de cada vecino (mayor = mas similar).
    pnl_r  : desenlace forward (en R) de cada vecino.
    ages   : antiguedad en velas del vecino respecto al query (para recencia).
    sim_floor : umbral de coseno para contar un vecino "en radio".
    n_floor   : minimo de vecinos en radio; por debajo -> abstain=True.
    decay_bars: half-life de recencia (exp). None = sin decaimiento.
    max_age_bars: descarta vecinos mas viejos que esto (eviccion blanda). None=off.

    Devuelve: expectancy_r, wr, dispersion, n_in_radius, confidence, abstain.
    """
    scores = np.asarray(scores, dtype="float64").ravel()
    pnl = np.asarray(pnl_r, dtype="float64").ravel()
    m = np.isfinite(scores) & np.isfinite(pnl)
    if ages is not None:
        ages = np.asarray(ages, dtype="float64").ravel()
        if max_age_bars is not None:
            m &= ages <= max_age_bars
    scores, pnl = scores[m], pnl[m]
    ages = ages[m] if ages is not None else None

    in_radius = scores >= sim_floor
    n_in_radius = int(in_radius.sum())
    if n_in_radius < max(1, n_floor):
        return {"expectancy_r": np.nan, "wr": np.nan, "dispersion": np.nan,
                "n_in_radius": n_in_radius, "confidence": 0.0, "abstain": True}

    s, p = scores[in_radius], pnl[in_radius]
    w = np.clip(s, 1e-6, None)  # peso por similitud
    if decay_bars is not None and ages is not None:
        a = ages[in_radius]
        w = w * np.exp(-np.log(2.0) * a / float(decay_bars))
    wsum = w.sum()
    exp_r = float((w * p).sum() / wsum)
    wr = float((w * (p > 0)).sum() / wsum)
    var = float((w * (p - exp_r) ** 2).sum() / wsum)
    disp = float(np.sqrt(max(var, 0.0)))
    # confianza: crece con n y baja con dispersion (acotada [0,1]).
    conf = float(n_in_radius / (n_in_radius + 1.0) / (1.0 + disp))
    return {"expectancy_r": exp_r, "wr": wr, "dispersion": disp,
            "n_in_radius": n_in_radius, "confidence": conf, "abstain": False}


# ============================================================
# DIAGNOSTICO OOS (read-only) SOBRE FOLDS WALK-FORWARD
# ============================================================
def retrieval_oos(labeled, folds, valid_index, *, backend="exact", bit_width=4,
                  k=50, vectorizer=None, sim_floor=0.5, n_floor=None,
                  decay_bars=None, max_age_bars=None, mode="causal", seed=42):
    """Calcula los estadisticos de retrieval para cada evento de TEST de cada fold.

    Para cada fold (train_idx, test_idx) -> filas reales via valid_index:
      mode='causal' : indice = TRAIN del fold (purgado+embargado por
                      bt_walkforward). Estrictamente sin futuro. <- el de fiar.
      mode='oracle' : indice = TODOS los eventos (incluye test y futuro). Cota
                      superior LEAKY: si causal colapsa frente a esto, la tesis
                      depende de fuga.
      mode='placebo': indice = train con pnl_r BARAJADO. La expectancy estimada
                      debe volverse no informativa (colapsa a ~0). Si no, hay bug.

    Devuelve un DataFrame (solo filas de test) con las columnas originales +
    retr_expectancy_r, retr_wr, retr_dispersion, retr_n, retr_confidence,
    retr_abstain, fold.
    """
    rng = np.random.default_rng(seed)
    n_floor = (k // 2) if n_floor is None else n_floor
    lab = labeled.reset_index(drop=True)
    # mapeo posicion-en-valid -> fila real (0..len(lab)-1 dentro de 'valid')
    valid_pos = {int(orig): p for p, orig in enumerate(valid_index)}
    pos_to_orig = {p: int(orig) for p, orig in enumerate(valid_index)}

    out_rows = []
    for fi, (train_idx, test_idx) in enumerate(folds):
        tr_orig = [pos_to_orig[int(p)] for p in train_idx]
        te_orig = [pos_to_orig[int(p)] for p in test_idx]
        tr = lab.iloc[tr_orig]
        te = lab.iloc[te_orig]
        tr = tr[tr["pnl_r"].notna()]
        if len(tr) == 0:
            continue

        vec = vectorizer if vectorizer is not None else StateVectorizer()
        vec = vec.fit(tr)  # SOLO con train (pasado) -> sin leakage de escalado

        # indice segun modo
        if mode == "oracle":
            idx_src = lab[lab["pnl_r"].notna()]
        else:
            idx_src = tr
        Vidx = vec.transform(idx_src)
        ids = idx_src["entry_index"].to_numpy(dtype=np.uint64)
        pnl_idx = idx_src["pnl_r"].to_numpy(dtype="float64")
        if mode == "placebo":
            pnl_idx = rng.permutation(pnl_idx)
        entry_idx_idx = idx_src["entry_index"].to_numpy(dtype="float64")

        be = make_backend(backend, dim=vec.dim, bit_width=bit_width)
        be.add_with_ids(Vidx, ids)
        id2pnl = {int(i): float(p) for i, p in zip(ids, pnl_idx)}
        id2entry = {int(i): float(e) for i, e in zip(ids, entry_idx_idx)}

        Qte = vec.transform(te)
        te_entry = te["entry_index"].to_numpy(dtype="float64")
        kk = min(k, len(idx_src))
        scores, nbr_ids = be.search(Qte, kk)

        for r in range(len(te)):
            nb = nbr_ids[r]
            sc = scores[r]
            # en causal/placebo, excluir el propio evento si colisiona (no en train)
            p = np.array([id2pnl[int(i)] for i in nb], dtype="float64")
            a = np.array([te_entry[r] - id2entry[int(i)] for i in nb], dtype="float64")
            st = neighborhood_stats(sc, p, ages=a, sim_floor=sim_floor,
                                    n_floor=n_floor, decay_bars=decay_bars,
                                    max_age_bars=max_age_bars)
            row = dict(te.iloc[r])
            row.update({"retr_expectancy_r": st["expectancy_r"],
                        "retr_wr": st["wr"], "retr_dispersion": st["dispersion"],
                        "retr_n": st["n_in_radius"], "retr_confidence": st["confidence"],
                        "retr_abstain": st["abstain"], "fold": fi})
            out_rows.append(row)
    return pd.DataFrame(out_rows)


# ============================================================
# ABLACION READ-ONLY: ¿anade edge OOS?
# ============================================================
def retrieval_ablation(oos_df, gate_threshold=0.0):
    """Compara expectancy OOS realizada de subconjuntos (read-only, no decide).

    Responde la pregunta de F1: condicionar por la expectancy del vecindario,
    ¿mejora la expectancy realizada frente a tomar TODAS las senales?

    Devuelve dict con:
      base        : todas las senales resueltas (sin retrieval).
      confident   : senales NO abstenidas (vecindario denso).
      gate_pass   : confident con retr_expectancy_r >= gate_threshold (lo que el
                    GATE dejaria pasar).
      gate_block  : confident con retr_expectancy_r <  gate_threshold (vetadas).
      abstained   : senales raras (la capa no opina).
    El edge de retrieval = expectancy_r(gate_pass) - expectancy_r(base).
    """
    df = oos_df[oos_df["pnl_r"].notna()].copy()

    def _stats(sub):
        if len(sub) == 0:
            return {"n": 0, "expectancy_r": np.nan, "wr": np.nan,
                    "total_r": np.nan, "pf": np.nan}
        p = sub["pnl_r"].astype(float).to_numpy()
        gains = p[p > 0].sum()
        losses = -p[p < 0].sum()
        pf = float(gains / losses) if losses > 0 else float("inf")
        return {"n": int(len(sub)), "expectancy_r": float(p.mean()),
                "wr": float((p > 0).mean()), "total_r": float(p.sum()), "pf": pf}

    confident = df[~df["retr_abstain"].astype(bool)]
    gate_pass = confident[confident["retr_expectancy_r"] >= gate_threshold]
    gate_block = confident[confident["retr_expectancy_r"] < gate_threshold]
    abstained = df[df["retr_abstain"].astype(bool)]

    base = _stats(df)
    res = {
        "base": base,
        "confident": _stats(confident),
        "gate_pass": _stats(gate_pass),
        "gate_block": _stats(gate_block),
        "abstained": _stats(abstained),
    }
    gp = res["gate_pass"]["expectancy_r"]
    res["edge_vs_base_r"] = (gp - base["expectancy_r"]) if base["n"] and gate_pass.shape[0] else np.nan
    return res
