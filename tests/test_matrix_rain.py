# -*- coding: utf-8 -*-
"""Lluvia digital FQ (piezas de SHOW). Ambas versiones traen --self-test que valida
la física (φ en la caída dorada, Fibonacci deletreado, castas presentes). La curses
es stdlib puro y corre siempre; la Pygame se salta si no está pygame (jamás es
dependencia del bot — es vanidad para clips)."""
import subprocess
import sys

import pytest


def test_matrix_rain_curses_self_test():
    r = subprocess.run([sys.executable, "tools/matrix_rain.py", "--self-test"],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "self-test OK" in r.stdout


def test_matrix_rain_pygame_self_test():
    pytest.importorskip("pygame")           # show-only; nunca en requirements del bot
    r = subprocess.run([sys.executable, "tools/matrix_rain_gl.py", "--self-test"],
                       capture_output=True, text=True, timeout=90,
                       env={"SDL_VIDEODRIVER": "dummy", "SDL_AUDIODRIVER": "dummy",
                            "PATH": __import__("os").environ.get("PATH", "")})
    assert r.returncode == 0, r.stderr
    assert "self-test OK" in r.stdout


def test_fibonacci_stream_is_actually_fibonacci():
    """El río dorado deletrea la sucesión (no dígitos al azar): candado de identidad."""
    import tools.matrix_rain as mr
    fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610, 987]
    stream = "".join(str(n) for n in fib)
    assert stream in mr.FIB, "la constante FIB dejó de ser Fibonacci"
    assert abs(mr.PHI - 0.6180339887) < 1e-9, "φ-1 corrompido"
