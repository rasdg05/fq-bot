#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FQ VIP BOT - entrypoint
  by RasDG_Sol + Claude

  Wrapper minimal sobre fq_bot_v3_2.py. Existe para:
    - Simetria con entry_public.py (railway tiene 2 servicios, cada uno apunta
      a su entry_*.py).
    - Permitir refactor futuro a un main() limpio sin tocar el monolito grande.

  Tipicamente Railway:
    startCommand = "python entry_vip.py"
    env vars: TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY,
              FQ_LEDGER_PATH=/data/fq_ledger.db (volumen montado)
================================================================================
"""
import sys

if __name__ == "__main__":
    import fq_bot_v3_2 as bot
    try:
        bot.main()
    except KeyboardInterrupt:
        sys.exit(0)
