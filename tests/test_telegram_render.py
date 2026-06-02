# -*- coding: utf-8 -*-
"""
Render seguro de mensajes Telegram HTML. Regresion: al activar la ALERTA
TACTICA, el 'reason' del gate (p.ej. "vol_score=0.78<0.85") incrustaba '<' en
un mensaje HTML, Telegram fallaba el parse y el RADAR admin salia con los tags
crudos (<b>...). Estos tests blindan el escape y el strip de fallback.
"""
import fq_bot_v3_2 as b


def test_html_escape_neutralizes_reason_chars():
    # reasons reales del gate de promocion / conviccion
    assert b._html_escape("vol_score=0.78<0.85") == "vol_score=0.78&lt;0.85"
    assert b._html_escape("market.p_sl>0.55") == "market.p_sl&gt;0.55"
    assert b._html_escape("a & b") == "a &amp; b"
    # idempotencia del orden: el & se escapa primero (no doble-escape de &lt;)
    assert "&lt;" in b._html_escape("x<y") and "&amp;lt;" not in b._html_escape("x<y")


def test_escaped_reason_has_no_raw_angle_brackets():
    reason = "vol_score=0.78<0.85"
    suffix = "<i>(no promovida: {})</i>".format(b._html_escape(reason))
    # el unico '<'/'>' restante es el de los tags <i>...</i>, no el del reason
    inner = suffix.replace("<i>", "").replace("</i>", "")
    assert "<" not in inner and ">" not in inner


def test_strip_html_tags_keeps_numeric_comparisons():
    src = "<b>RADAR FQ [5m]</b>\n<i>vol_score=0.78<0.85</i>"
    out = b._strip_html_tags(src)
    assert "<b>" not in out and "</b>" not in out
    assert "<i>" not in out and "</i>" not in out
    # NO debe comerse el "<0.85" (no es un tag: empieza con digito)
    assert "0.78<0.85" in out


def test_strip_html_tags_handles_attributes():
    assert b._strip_html_tags('<a href="x">link</a>') == "link"
