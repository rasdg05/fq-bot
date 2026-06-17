# -*- coding: utf-8 -*-
"""
FQ Mini App — superficie visual (Telegram WebApp) sobre el ledger.

Aditiva y de SOLO LECTURA: no toca el motor, el broadcast ni los pagos.
Sirve un panel admin (metricas del motor, suscriptores) y una app de
cliente (senales filtradas por tier) dentro de Telegram.

Modulos:
  auth.py    validacion HMAC del initData de Telegram (pura, testeable)
  data.py    capa de datos RO + shaping por rol (admin vs tier)
  notify.py  helpers para enviar mensajes con boton "Abrir app"
  server.py  app Flask: sirve la SPA + API JSON
"""
