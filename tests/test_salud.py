# -*- coding: utf-8 -*-
"""
E3 — /salud: el instrumento VISIBLE.

`_ledger_health`, `n_excluded`, `MOTOR_FILL_REJECTED`, `cvd_staleness_min`,
`bars_held`: todo escrito, nada visible. Cinco arreglos invisibles no son
producto — son cinco cosas que hay que acordarse de ir a mirar, y acordarse es
exactamente lo que falló en julio.

Este archivo fija que el panel:
  1. contesta las cinco preguntas del brief,
  2. da el veredicto PEOR, nunca el promedio (un solo chequeo roto rompe el
     conjunto: promediar salud es como promediar regímenes),
  3. dice QUÉ HACER cuando algo está mal,
  4. no se cae cuando el sistema se cae — que es justo cuando se consulta.
"""
import pytest

import salud


# --- 1. ¿el track record es fiable? -----------------------------------------

def test_track_record_suspendido_es_roto():
    c = salud.check_track_record({"ok": False, "reasons": ["cierres no auditables"]})
    assert c["estado"] == salud.BROKEN
    assert "SUSPENDIDO" in c["titulo"]
    assert "NO publiques" in c["accion"]


def test_track_record_sano():
    assert salud.check_track_record({"ok": True, "n": 12})["estado"] == salud.OK


def test_track_record_con_deriva_avisa_sin_romper():
    """Integridad OK + aviso de drift no es lo mismo que ledger roto. Confundirlos
    llevaría a suspender el track record por una señal de mercado."""
    c = salud.check_track_record({"ok": True, "reasons": ["DRIFT a la baja"], "n": 40})
    assert c["estado"] == salud.WARN


def test_sin_audit_no_se_afirma_que_es_fiable():
    """'Nadie ha mirado' no es 'está bien'."""
    assert salud.check_track_record({})["estado"] == salud.UNKNOWN


# --- 2. ¿cuántas filas se excluyen y por qué? -------------------------------

def test_muchas_exclusiones_avisan():
    c = salud.check_exclusiones(100, 25)
    assert c["estado"] == salud.WARN
    assert "25 de 100" in c["detalle"]


def test_pocas_exclusiones_estan_ok():
    c = salud.check_exclusiones(100, 2)
    assert c["estado"] == salud.OK
    assert "2 de 100" in c["detalle"]         # el número se ve igual


def test_las_exclusiones_siempre_se_reportan():
    """No se borran nunca: son la prueba de que el número es explicable."""
    assert "de" in salud.check_exclusiones(100, 0)["detalle"]


# --- 3. ¿el CVD está fresco? ------------------------------------------------

def test_cvd_rancio_es_roto():
    c = salud.check_cvd(240.0)
    assert c["estado"] == salud.BROKEN
    assert "RANCIO" in c["titulo"]


def test_cvd_fresco():
    assert salud.check_cvd(5.0)["estado"] == salud.OK


def test_cvd_apagado_no_es_un_problema():
    """Si el filtro está off no hay nada que envejecer: marcarlo en rojo
    entrenaría a ignorar el rojo."""
    assert salud.check_cvd(None, activo=False)["estado"] == salud.OK


def test_cvd_sin_datos_no_es_lo_mismo_que_fresco():
    assert salud.check_cvd(None, activo=True)["estado"] == salud.WARN


# --- 4. ¿cuántos fills se rechazaron? ---------------------------------------

def test_rechazo_masivo_de_fills_avisa():
    c = salud.check_fills(80, 20)
    assert c["estado"] == salud.WARN
    assert "80 rechazados de 100" in c["detalle"]


def test_rechazo_normal_de_fills():
    assert salud.check_fills(5, 95)["estado"] == salud.OK


# --- 5. ¿cuándo corrió el último audit? -------------------------------------

def test_audit_que_nunca_corrio_avisa():
    c = salud.check_audit({})
    assert c["estado"] == salud.WARN
    assert "/audit" in c["accion"]


def test_audit_viejo_avisa():
    """Un audit de anteayer describe un sistema que ya no existe."""
    c = salud.check_audit({"ok": True, "ts": "2026-08-01T10:00:00"},
                          ahora_iso="2026-08-04T03:00:00")
    assert c["estado"] == salud.WARN


def test_audit_de_hoy_esta_al_dia():
    c = salud.check_audit({"ok": True, "ts": "2026-08-04T01:00:00"},
                          ahora_iso="2026-08-04T03:00:00")
    assert c["estado"] == salud.OK
    assert "sin hallazgos" in c["detalle"]


# --- el veredicto: el peor manda, nunca el promedio -------------------------

def test_el_veredicto_es_el_peor_no_el_promedio():
    """Cuatro verdes y un rojo NO es 'casi todo bien'. Promediar salud es el
    mismo error que promediar regímenes."""
    checks = [salud._check("a", salud.OK, "x"), salud._check("b", salud.OK, "x"),
              salud._check("c", salud.OK, "x"), salud._check("d", salud.BROKEN, "x")]
    assert salud.veredicto(checks) == salud.BROKEN


def test_desconocido_no_cuenta_como_bueno():
    checks = [salud._check("a", salud.OK, "x"), salud._check("b", salud.UNKNOWN, "x")]
    assert salud.veredicto(checks) == salud.UNKNOWN


def test_aviso_pesa_mas_que_desconocido():
    checks = [salud._check("a", salud.UNKNOWN, "x"), salud._check("b", salud.WARN, "x")]
    assert salud.veredicto(checks) == salud.WARN


# --- se entiende a las 3am --------------------------------------------------

def test_el_veredicto_va_primero():
    """Si todo está bien no hay que leer nada más.

    V4: "todo bien" incluye ahora el sizing. Sin `gstats` el panel dice
    DESCONOCIDO a proposito — no saber si arriesgas de mas no es estar bien."""
    import growth
    sano = growth.growth_stats([3.0, -1.0, -1.0] * 40, 0.005)
    txt = salud.render(salud.gather(health={"ok": True, "n": 5, "ts": "2026-08-04T01:00"},
                                    n_total=10, n_excluded=0, cvd_activo=False,
                                    n_rejected=1, n_opened=9, gstats=sano,
                                    ahora_iso="2026-08-04T03:00"))
    assert "TODO EN ORDEN" in txt.split("\n")[2]


def test_sin_saber_el_sizing_el_panel_no_dice_que_todo_esta_bien():
    """No saber si arriesgas de mas no es estar bien: es no saberlo."""
    txt = salud.render(salud.gather(health={"ok": True, "n": 5, "ts": "2026-08-04T01:00"},
                                    n_total=10, n_excluded=0, cvd_activo=False,
                                    n_rejected=1, n_opened=9,
                                    ahora_iso="2026-08-04T03:00"))
    assert "TODO EN ORDEN" not in txt


def test_lo_roto_dice_que_hacer():
    txt = salud.render(salud.gather(health={"ok": False, "reasons": ["tracker roto"]},
                                    n_total=10, n_excluded=0))
    assert "→" in txt
    assert "no publiques" in txt.lower()


def test_lo_verde_no_gasta_lineas_en_acciones():
    """Una acción en verde es ruido, y el ruido entrena a no leer."""
    txt = salud.render([salud._check("a", salud.OK, "todo bien", accion="haz algo")])
    assert "haz algo" not in txt


def test_las_cinco_preguntas_del_brief_estan():
    claves = {c["clave"] for c in salud.gather()}
    assert {"track_record", "audit", "exclusiones", "cvd", "fills"} <= claves


def test_y_la_sexta_que_ninguna_otra_metrica_contesta():
    """El sizing: E[R], IC95% y DSR son invariantes a la fraccion arriesgada, asi
    que sin este chequeo una sobre-apuesta no deja huella en ningun sitio."""
    assert "sobreapuesta" in {c["clave"] for c in salud.gather()}


# --- E4: el panel dice QUE SE CAE con cada fuente rota ----------------------

def test_una_fuente_rota_dice_que_afirmaciones_se_caen():
    """En julio nadie hizo esta pregunta. 'El colector está caído' no basta:
    hay que saber qué deja de sostenerse, y que salga solo."""
    c = salud.check_procedencia(
        {"tracker.outcomes": "cierres imposibles"},
        [("track_record.publico", False), ("audit.veredicto", False)])
    assert c["estado"] == salud.BROKEN
    assert "track_record.publico" in c["accion"]


def test_sin_fuentes_rotas_esta_verde():
    assert salud.check_procedencia({})["estado"] == salud.OK


# --- no se cae cuando el sistema se cae -------------------------------------

def test_una_lectura_rota_no_tumba_el_panel(monkeypatch):
    """Se consulta JUSTO cuando algo va mal: si se cayera con el sistema, no
    serviría exactamente el día que hace falta."""
    def _boom():
        raise RuntimeError("colector caido")
    assert salud._safe(_boom, default="fallback") == "fallback"


def test_gather_live_nunca_lanza(monkeypatch):
    monkeypatch.setenv("FQ_CVD_FILTER", "1")
    monkeypatch.setenv("FQ_CVD_COLLECT", "/no/existe.parquet")
    monkeypatch.setenv("FQ_MOTOR_PAPER_LEDGER_PATH", "/no/existe.jsonl")
    checks = salud.gather_live(ahora_iso="2026-08-04T03:00:00")
    assert len(checks) == 7
    salud.render(checks)                       # tampoco al pintar


def test_el_comando_esta_registrado_como_admin():
    """Si no está en ADMIN_ONLY, un cliente ve las tripas del sistema."""
    import re
    src = open("fq_bot_v3_2.py", encoding="utf-8").read()
    admin = re.search(r"ADMIN_ONLY = \{(.*?)\}", src, re.S).group(1)
    assert '"/salud"' in admin
    assert '"/salud":' in src                  # y despachado


# --- el contador de fills rechazados existe de verdad -----------------------

def test_el_ledger_report_cuenta_los_fills_rechazados(tmp_path):
    """Estaba sellado en el ledger y no lo contaba nadie: invisible."""
    import motor_paper
    from execution import DurableHashLedger
    p = tmp_path / "l.jsonl"
    led = DurableHashLedger(str(p))
    led.append({"event": "MOTOR_FILL_REJECTED", "ts": 1, "why": "rapido"})
    led.append({"event": "MOTOR_VETOED", "ts": 2, "killzone": "london_open_kz",
                "stage": "segmento"})
    led.append({"event": "MOTOR_VETOED", "ts": 3, "killzone": None,
                "stage": "gobernador"})
    rep = motor_paper.ledger_report(str(p))
    assert rep["n_fill_rejected"] == 1
    assert rep["vetoed_by_stage"] == {"segmento": 1, "gobernador": 1}
