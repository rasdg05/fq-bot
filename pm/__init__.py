# -*- coding: utf-8 -*-
"""
Paquete Polymarket. Vive dentro de fq-bot a proposito: reusa el gobernador de
riesgo (execution.RiskGovernor), el ledger sellado (execution.HashLedger) y el
reconciliador (reconciler.Reconciler) en vez de reescribirlos.

Estado: Fase 0 (medicion read-only). Sin claves, sin ordenes, sin dinero.
Ver POLYMARKET_AUDIT.md para la auditoria de la tesis y el plan por fases.
"""
