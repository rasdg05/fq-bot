# -*- coding: utf-8 -*-
"""Los 4 experimentos de mejora-longs (funding/breadth/cvd_ortho/onchain): el harness
corre end-to-end en sintético (sin red) y el gate reporta sin reventar."""
import subprocess
import sys


def test_self_test_offline():
    r = subprocess.run([sys.executable, "tools/validate_long_gates.py", "--self-test"],
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "self-test OK" in r.stdout
