# -*- coding: utf-8 -*-
"""
Guardian anti-ruptura de HTML en Telegram.

Todos los mensajes se envian con parse_mode=HTML. Un '<' que NO forme un tag
valido rompe el parse de Telegram ("can't parse entities"); el bot reenvia sin
parse_mode y _strip_html_tags borra TODO el formato, o (peor) se traga el texto
hasta el siguiente '>'. Esa fue la causa de que /lectura y /analisis se vieran
rotos:
  - 'P(TP2<SL)' en el bloque QTE admin (quantum_timelines)
  - 'P(SL) <= 0.35' en build_about_admin (vip_format)
  - 'RSI >45' en el texto libre de Claude, incrustado sin escapar

Este test caza la reintroduccion de esa clase de bug.
"""
import re
import pytest

import quantum_timelines as qt
import vip_format


# Tags que Telegram acepta en parse_mode=HTML.
_TG_TAGS = "b|strong|i|em|u|ins|s|strike|del|a|code|pre|tg-spoiler|blockquote|span"
_VALID_TAG = re.compile(r"</?(?:%s)(?:\s[^<>]*)?>" % _TG_TAGS, re.IGNORECASE)


def dangerous_lt(text):
    """Fragmentos con un '<' que Telegram no podria parsear: cualquier '<' que
    no inicie un tag valido y no este escapado como &lt;. Devuelve lista de
    contextos (20 chars) para que el assert sea legible."""
    stripped = _VALID_TAG.sub("", text)
    stripped = (stripped.replace("&lt;", "").replace("&gt;", "")
                        .replace("&amp;", ""))
    return [stripped[m.start():m.start() + 20] for m in re.finditer(r"<", stripped)]


def _qa(p_sl, ev, coh=0.5, with_baseline=False):
    """qa minimo para alimentar build_qte_block_admin."""
    qa = {
        "n_paths": 500, "horizon_candles": 96, "horizon_hours": 24.0,
        "elapsed_ms": 70.0, "coherence": coh,
        "probabilities": {
            "p_sl": p_sl, "p_tp1": max(0.0, 1 - p_sl), "p_tp2": 0.0, "p_tp3": 0.0,
            "p_reach_tp1": max(0.0, 1 - p_sl), "p_reach_tp2": 0.0, "p_reach_tp3": 0.0,
            "p_timeout": 0.0, "expected_R": ev, "win_rate": max(0.0, 1 - p_sl),
        },
        "regimes": {"bear_reversal": 0.6, "sweep_and_reverse": 0.25, "chop": 0.15},
        "dominant_regime": "bear_reversal", "dominant_regime_pct": 0.6,
        "vs_baseline": None,
    }
    if with_baseline:
        qa["vs_baseline"] = {
            "baseline_p_sl": p_sl, "optimized_p_sl": max(0.0, p_sl - 0.3),
            "baseline_ev_R": ev, "optimized_ev_R": ev + 1.0, "delta_R": 1.0,
        }
    return qa


# Casos que cubren las 4 ramas del veredicto + con/sin optimizer.
_QTE_CASES = [
    ("adverso", _qa(1.0, -1.0, coh=0.45)),
    ("favorable", _qa(0.28, 1.35, coh=0.72)),
    ("moderado", _qa(0.50, 0.6, coh=0.55)),
    ("sin_edge", _qa(0.62, 0.1, coh=0.30)),
    ("con_optimizer", _qa(1.0, -1.0, with_baseline=True)),
]


@pytest.mark.parametrize("name,qa", _QTE_CASES)
def test_qte_admin_block_sin_lt_crudo(name, qa):
    """El bloque QTE admin es texto plano: no debe contener NINGUN '<'
    (regresion directa de 'P(TP2<SL)'). Un '>' suelto (p.ej. el arrow '->'
    del optimizer) es inofensivo en HTML de Telegram; solo '<' rompe el parse."""
    block = qt.build_qte_block_admin(qa)
    assert "<" not in block, "{}: el bloque QTE emite '<' crudo".format(name)
    assert not dangerous_lt(block), "{}: '<' peligroso en el bloque".format(name)


@pytest.mark.parametrize("name,qa", _QTE_CASES)
def test_qte_admin_block_tiene_veredicto(name, qa):
    """El bloque debe incluir el veredicto accionable (no solo numeros)."""
    block = qt.build_qte_block_admin(qa)
    assert "VEREDICTO QTE" in block, "{}: falta el veredicto".format(name)


def test_about_admin_sin_lt_peligroso():
    """build_about_admin usa simbolos unicode (<= -> ≤) para no romper HTML."""
    text = vip_format.build_about_admin()
    bad = dangerous_lt(text)
    assert not bad, "build_about_admin tiene '<' peligroso: {}".format(bad)


# ----------------------------------------------------------------------------
# Escapado del texto libre de Claude. Vive en fq_bot_v3_2, que importa
# pandas_ta/ccxt; si no estan (entorno sin deps) solo se omiten ESTOS tests
# (los de quantum_timelines/vip_format de arriba siguen corriendo). En CI con
# Python 3.12 + deps, corren todos.
# ----------------------------------------------------------------------------
try:
    import fq_bot_v3_2 as fq
except Exception:  # ModuleNotFoundError de pandas_ta/ccxt, etc.
    fq = None

_needs_fq = pytest.mark.skipif(
    fq is None, reason="requiere pandas_ta/ccxt (Python 3.12 en CI)")


@_needs_fq
@pytest.mark.parametrize("raw", [
    "Stop bajo 77.8 con RSI >45 y BTC estable.",
    "P(SL) < 0.3 indica edge claro.",
    "Zona <relevante> con R&D, target 75.5.",
    "1 < 2 > 0 & verdadero",
])
def test_escape_claude_neutraliza_lt(raw):
    """El texto plano de Claude no debe poder romper el parse HTML."""
    out = fq._escape_claude(raw)
    assert not dangerous_lt(out), "queda '<' peligroso tras escapar: {!r}".format(out)
    assert "<" not in out and ">" not in out, "quedan '<'/'>' sin escapar"


@_needs_fq
@pytest.mark.parametrize("falsy", [None, ""])
def test_escape_claude_falsy_preserva_guards(falsy):
    """None/'' -> '' (falsy) para que los guards 'if reading:' sigan igual."""
    assert fq._escape_claude(falsy) == ""


@_needs_fq
def test_escape_claude_dentro_de_template_preserva_formato():
    """Los tags <b> del template no pasan por _escape_claude: el mensaje final
    conserva el formato y no tiene '<' peligroso."""
    reading = fq._escape_claude("Reclaim sobre 77.3, RSI >45. P(SL) < 0.3.")
    msg = "<b>LECTURA</b>\n\n{}\n\n#FQ".format(reading)
    assert not dangerous_lt(msg)
    assert "<b>" in msg  # el formato del template sobrevive
