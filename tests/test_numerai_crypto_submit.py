# -*- coding: utf-8 -*-
"""Runner diario de Numerai Crypto: universo -> mapeo Binance -> submission. Camino offline."""
import sys

sys.path.insert(0, "tools")
import numerai_crypto_submit as ncs


def test_self_test():
    assert ncs._self_test() == 0          # end-to-end offline, sin red ni credenciales


def test_universe_file_and_mapping(tmp_path):
    uf = tmp_path / "u.txt"
    uf.write_text("btc\nETH\n# comentario\nsol\nbtc\n")     # minúsculas, comentario, duplicado
    toks = ncs.live_universe(universe_file=str(uf), data_dir=str(tmp_path))
    assert toks == ["BTC", "ETH", "SOL"]                     # upper, sin dups, sin comentario
    m = ncs.to_binance(toks)
    assert m["BTC"] == "BTCUSDT" and m["SOL"] == "SOLUSDT"
