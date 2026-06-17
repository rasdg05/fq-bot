# -*- coding: utf-8 -*-
"""
Contrato del cableado de notificaciones SIN importar el monolito (que necesita
ccxt/pandas). Parsea el codigo fuente con ast y verifica que las firmas y los
call-sites del boton "Abrir app" siguen en su lugar. Asi un refactor que rompa
la integracion lo caza el CI ligero, no produccion.
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _params(path, func_name):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return {a.arg for a in node.args.args} | {a.arg for a in node.args.kwonlyargs}
    raise AssertionError("{} no define {}".format(path, func_name))


def _src(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


# ---- firmas ----
def test_telegram_send_accepts_reply_markup():
    assert "reply_markup" in _params("fq_bot_v3_2.py", "telegram_send")


def test_broadcast_accepts_reply_markup():
    assert "reply_markup" in _params("fq_bot_v3_2.py", "broadcast_to_subscribers")


def test_app_button_helper_defined():
    assert "view" in _params("fq_bot_v3_2.py", "_app_button")


def test_dm_admin_accepts_view():
    assert "view" in _params("ops/maintenance.py", "_dm_admin")


# ---- call-sites (los 4 eventos) ----
def test_signal_and_progress_wired():
    src = _src("fq_bot_v3_2.py")
    # nueva senal + progreso (ledger) + progreso tactico -> vista signals
    assert src.count('reply_markup=_app_button("signals")') >= 3


def test_payment_wired():
    assert 'reply_markup=_app_button("subs")' in _src("fq_bot_v3_2.py")


def test_health_wired():
    assert 'view="health"' in _src("ops/maintenance.py")
