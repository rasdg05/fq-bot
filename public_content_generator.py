# -*- coding: utf-8 -*-
"""
Public content generator. Lecturas editoriales y CTAs opcionales via LLM.

Reglas absolutas:
- Jamas revelar formulas internas (phi, kappa_evo, Theta(D), etc.).
- Jamas dar niveles operativos (entry, SL, TPs).
- Jamas nombrar version, modelo de IA, frameworks ni jerga de motor.
- Tono: directo, profesional, sin emoji.
"""
import os
import logging
from datetime import datetime, timezone

log = logging.getLogger("fq_public_content")

try:
    from anthropic import Anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False
    Anthropic = None

# ============================================================
# CONFIG
# ============================================================
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_HAIKU  = "claude-haiku-4-5-20251001"
MAX_TOKENS_LECTURA = 380     # ~80-100 palabras formateadas
MAX_TOKENS_CTA     = 180

_client = None

def _get_client():
    global _client
    if not _HAS_ANTHROPIC or not ANTHROPIC_API_KEY:
        return None
    if _client is None:
        _client = Anthropic(api_key=ANTHROPIC_API_KEY)
    return _client

def is_available():
    return _get_client() is not None

# ============================================================
# TEMAS ROTATIVOS PARA LECTURAS (12 temas - una rotacion mensual)
# ============================================================
TEMAS_LECTURAS = [
    {
        "id": "sesion_ny",
        "titulo": "Por que importa la sesion de Nueva York.",
        "guia": (
            "Explica por que la apertura de Nueva York concentra mas volumen "
            "institucional que Asia. Mas movimiento, mas trampas, extensiones "
            "que se cumplen mas. Sin niveles. Sin nombres tecnicos."
        ),
    },
    {
        "id": "liquidez_pools",
        "titulo": "Donde realmente se mueve el dinero.",
        "guia": (
            "Explica que la liquidez (clusters de stops) es donde las instituciones "
            "buscan ejecutar. Highs y lows iguales atraen orden. Sin niveles "
            "especificos."
        ),
    },
    {
        "id": "discount_premium",
        "titulo": "Por que comprar caro no funciona.",
        "guia": (
            "Explica zona barata vs cara con Fibonacci basico. Comprar barato = "
            "menor riesgo, mas cerca del SL. Vender caro = mismo principio. "
            "Sin formulas, sin niveles."
        ),
    },
    {
        "id": "retroceso_optimo",
        "titulo": "El punto eficiente del retroceso.",
        "guia": (
            "Habla del retroceso optimo: la zona profunda de un movimiento donde "
            "el riesgo es estructural y el potencial es maximo. Sin nombrar "
            "siglas, sin porcentajes especificos, sin precios."
        ),
    },
    {
        "id": "displacement",
        "titulo": "Cuando el mercado dice la verdad.",
        "guia": (
            "Explica velas con cuerpo grande y mechas chicas: movimiento "
            "decisivo, no ruido. Por que marcan el inicio de algo real."
        ),
    },
    {
        "id": "trampa_liquidez",
        "titulo": "Liquidez fabricada para ser cazada.",
        "guia": (
            "Habla de los micro pullbacks que crean ordenes de stop que las "
            "manos fuertes barren antes del movimiento real. Sin nombres."
        ),
    },
    {
        "id": "ciclo_mercado",
        "titulo": "Acumulacion, manipulacion, distribucion.",
        "guia": (
            "Explica el ciclo: rango -> trampa -> movimiento al lado contrario. "
            "Ilustra con un ejemplo conceptual de Asia hacia Nueva York. Sin "
            "siglas, sin numeros, sin setups."
        ),
    },
    {
        "id": "cambio_estructura",
        "titulo": "Cambio de caracter antes del giro.",
        "guia": (
            "Explica que el primer rompimiento contrario al impulso es la "
            "primera huella del giro. Lectura temprana que necesita "
            "confirmacion. Sin siglas tecnicas."
        ),
    },
    {
        "id": "sl_inmutable",
        "titulo": "Por que el SL no se mueve.",
        "guia": (
            "El SL una vez puesto no se toca. Moverlo para 'darle aire' "
            "destruye el edge estadistico. Mencion a expectancy positiva "
            "agregada en el tiempo."
        ),
    },
    {
        "id": "selectividad",
        "titulo": "Por que la mayoria de senales son ruido.",
        "guia": (
            "Un sistema selectivo (1-3 trades/dia) vence a uno hiperactivo. "
            "Calidad sobre cantidad. Sin nombrar formulas, sin tecnicismos."
        ),
    },
    {
        "id": "weekend_silencio",
        "titulo": "Por que el sistema calla los fines de semana.",
        "guia": (
            "Fin de semana: liquidez delgada, spreads anchos, sin volumen "
            "institucional. Operar weekend es jugar al casino. Paciencia "
            "es parte del sistema."
        ),
    },
    {
        "id": "memoria_estadistica",
        "titulo": "Un sistema que aprende de cada cierre.",
        "guia": (
            "Habla a alto nivel del concepto de memoria estadistica: cada cierre "
            "ajusta el peso de futuros setups similares. Solo el concepto general. "
            "Sin tecnicismos ni nombres de algoritmo."
        ),
    },
]

def pick_topic_for_today():
    """Rota tema deterministicamente segun dia del ano - asi nunca repite el mismo dia"""
    day_of_year = datetime.now(timezone.utc).timetuple().tm_yday
    idx = day_of_year % len(TEMAS_LECTURAS)
    return TEMAS_LECTURAS[idx]

# ============================================================
# PROMPT PARA LECTURAS (Sonnet)
# ============================================================
SYSTEM_PROMPT_LECTURA = """\
Eres el editor del canal publico de FQ. Generas lecturas educativas cortas
(50-90 palabras) para Telegram.

REGLAS ABSOLUTAS:
1. NUNCA reveles formulas internas (phi, kappa, Theta, P_master, alpha, omega).
2. NUNCA nombres versiones del producto, fases de desarrollo, nombres de modelos
   de IA, frameworks tecnicos (Thompson, Monte Carlo, QAOA), ni jerga del motor.
3. NUNCA des niveles operativos (precios de entry, SL, TPs, supports/resistances).
4. Tono: directo, profesional, sin emoji, sin hype. Estilo editorial financiero.
5. Espanol neutro, sin modismos.
6. Texto plano, sin bold/italic.
7. Cierra con una frase que invite a pensar, no a comprar.
8. Exactamente 6-10 lineas cortas.

OUTPUT: solo el cuerpo. Sin titulo (el sistema lo agrega). Sin saludo.
"""

def generate_lectura():
    """Genera la lectura del dia con Sonnet. Devuelve (titulo, cuerpo) o (None, None) si falla."""
    client = _get_client()
    if client is None:
        log.warning("No Claude client - skipping lectura generation")
        return None, None
    topic = pick_topic_for_today()
    user_msg = "Tema de hoy: {}\n\nGuia: {}".format(topic["titulo"], topic["guia"])
    try:
        resp = client.messages.create(
            model=MODEL_SONNET,
            max_tokens=MAX_TOKENS_LECTURA,
            system=SYSTEM_PROMPT_LECTURA,
            messages=[{"role": "user", "content": user_msg}],
        )
        cuerpo = ""
        for block in resp.content:
            if hasattr(block, "text"):
                cuerpo += block.text
        cuerpo = cuerpo.strip()
        if not cuerpo:
            return None, None
        return topic["titulo"], cuerpo
    except Exception as e:
        log.error("generate_lectura: {}".format(e))
        return None, None

# ============================================================
# CTAs EXTRA con Haiku (opcional - hoy usamos templates estaticos en public_format)
# Reservamos esta funcion para variantes generadas si quieres expansion futura
# ============================================================
SYSTEM_PROMPT_CTA = """\
Copy del canal publico de FQ. Un parrafo corto (3-5 lineas) que motive a
probar el VIP sin sonar comercial. Sin emoji, sin hype. Sin nombrar version,
modelo de IA, framework, ni jerga interna del motor. No menciones precio
(va en otra parte). Output: solo el texto, sin titulo.
"""

def generate_cta_variant(seed_topic="edge sistematico"):
    """Genera variante de CTA con Haiku. Para uso ocasional, no diario."""
    client = _get_client()
    if client is None:
        return None
    try:
        resp = client.messages.create(
            model=MODEL_HAIKU,
            max_tokens=MAX_TOKENS_CTA,
            system=SYSTEM_PROMPT_CTA,
            messages=[{"role": "user", "content": "Tema: {}".format(seed_topic)}],
        )
        text = ""
        for block in resp.content:
            if hasattr(block, "text"):
                text += block.text
        return text.strip() or None
    except Exception as e:
        log.error("generate_cta_variant: {}".format(e))
        return None
