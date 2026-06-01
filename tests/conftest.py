# -*- coding: utf-8 -*-
"""
Config compartida de pytest. Asegura que la raiz del repo este en sys.path
para que los modulos planos (branding, vip_format, ...) importen sin instalar.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
