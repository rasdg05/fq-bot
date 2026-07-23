"""forward_measure: reconstrucción de trades por pid, buckets base/+flujo/+KL,
verificación de cadena hash y honestidad de muestra (kl sin tag => vacío)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
import forward_measure as fm


def _write_ledger(tmp_path, sym, events):
    p = tmp_path / ("motor_paper_%s_USDT.jsonl" % sym)
    with open(p, "w", encoding="utf-8") as fh:
        for e in events:
            fh.write(json.dumps(e) + "\n")
    return str(p)


def _ev(seq, payload):
    return {"seq": seq, "payload": payload}


def test_reconstruye_trades_y_buckets(tmp_path):
    # dos trades cerrados: pid1 (flujo✓, kl_low✓, +2R), pid2 (flujo✗, kl_low✗, -1R)
    evs = [
        _ev(0, {"event": "OPEN", "pid": 1, "direction": 1, "ts": "t0"}),
        _ev(1, {"event": "MOTOR_OPEN_META", "pid": 1, "regime": "stable",
                "cvd_confirmed": True, "kl_low": True}),
        _ev(2, {"event": "CLOSE", "pid": 1, "pnl_r": 2.0, "reason": "tp"}),
        _ev(3, {"event": "OPEN", "pid": 2, "direction": -1, "ts": "t1"}),
        _ev(4, {"event": "MOTOR_OPEN_META", "pid": 2, "regime": "deriva",
                "cvd_confirmed": False, "kl_low": False}),
        _ev(5, {"event": "CLOSE", "pid": 2, "pnl_r": -1.0, "reason": "stop"}),
    ]
    path = _write_ledger(tmp_path, "SOL", evs)
    closed, chain_ok, breaks, still_open = fm.load_trades(path)
    assert len(closed) == 2 and still_open == 0
    s = fm.summarize(closed)
    assert s["base"]["n"] == 2 and abs(s["base"]["mean_r"] - 0.5) < 1e-9
    assert s["flujo"]["n"] == 1 and s["flujo"]["mean_r"] == 2.0     # solo el cvd_confirmed
    assert s["kl"]["n"] == 1 and s["kl"]["mean_r"] == 2.0           # solo el kl_low
    assert s["kl_tagged"] is True


def test_pid_reuse_entre_reinicios(tmp_path):
    # pid=1 se reusa: dos trades distintos con el mismo pid deben contarse ambos
    evs = [
        _ev(0, {"event": "OPEN", "pid": 1, "direction": 1, "ts": "t0"}),
        _ev(1, {"event": "CLOSE", "pid": 1, "pnl_r": 1.0, "reason": "tp"}),
        _ev(2, {"event": "OPEN", "pid": 1, "direction": 1, "ts": "t1"}),
        _ev(3, {"event": "CLOSE", "pid": 1, "pnl_r": -1.0, "reason": "stop"}),
    ]
    path = _write_ledger(tmp_path, "BTC", evs)
    closed, *_ = fm.load_trades(path)
    assert len(closed) == 2


def test_kl_bucket_vacio_sin_tag(tmp_path):
    # sin kl_low en ningún trade -> bucket kl vacío y kl_tagged False (no inventa)
    evs = [
        _ev(0, {"event": "OPEN", "pid": 1, "direction": 1, "ts": "t0"}),
        _ev(1, {"event": "MOTOR_OPEN_META", "pid": 1, "regime": "stable",
                "cvd_confirmed": True}),
        _ev(2, {"event": "CLOSE", "pid": 1, "pnl_r": 1.5, "reason": "tp"}),
    ]
    path = _write_ledger(tmp_path, "ETH", evs)
    closed, *_ = fm.load_trades(path)
    s = fm.summarize(closed)
    assert s["kl_tagged"] is False and s["kl"]["n"] == 0
    assert s["flujo"]["n"] == 1


def test_cadena_hash_detecta_ruptura(tmp_path):
    good = [
        {"seq": 0, "prev": "genesis", "hash": "a", "payload": {"event": "OPEN", "pid": 1}},
        {"seq": 1, "prev": "a", "hash": "b", "payload": {"event": "CLOSE", "pid": 1, "pnl_r": 1.0}},
    ]
    p = tmp_path / "motor_paper_SOL_USDT.jsonl"
    with open(p, "w") as fh:
        for e in good:
            fh.write(json.dumps(e) + "\n")
    _closed, ok, breaks, _open = fm.load_trades(str(p))
    assert ok is True and breaks == 0
    # rompe el enlace
    good[1]["prev"] = "WRONG"
    with open(p, "w") as fh:
        for e in good:
            fh.write(json.dumps(e) + "\n")
    _closed, ok, breaks, _open = fm.load_trades(str(p))
    assert ok is False and breaks == 1


def test_open_sin_cierre_no_cuenta(tmp_path):
    evs = [
        _ev(0, {"event": "OPEN", "pid": 1, "direction": 1, "ts": "t0"}),
        _ev(1, {"event": "MOTOR_OPEN_META", "pid": 1, "regime": "stable"}),
    ]
    path = _write_ledger(tmp_path, "BNB", evs)
    closed, _ok, _b, still_open = fm.load_trades(path)
    assert len(closed) == 0 and still_open == 1
