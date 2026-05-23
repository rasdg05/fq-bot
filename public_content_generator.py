# -*- coding: utf-8 -*-
"""
================================================================================
  PUBLIC CONTENT GENERATOR - Sonnet para lecturas, Haiku para CTAs
  by RasDG_Sol + Claude

  Genera contenido editorial para el bot publico:
  - Lecturas del dia (Sonnet 4.6): contenido formativo sin revelar formulas
  - CTAs cortos (Haiku 4.5): texto promocional liviano

  IMPORTANTE:
  - JAMAS revelar formulas internas (phi, kappa_evo, Theta(D), etc.)
  - JAMAS dar senales accionables (entry, SL, TPs)
  - Lenguaje: directo, sin emoji, vibra "Mistral Emergent Time" (denso, probabilistico)
================================================================================
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
        "id": "killzone_ny",
        "titulo": "Por que importa la sesion NY.",
        "guia": (
            "Explica brevemente por que la sesion New York (apertura 7:30-10:00 CDMX) "
            "concentra mas volumen institucional que Asia. Menciona que las trampas "
            "(false breakouts) caen en esa ventana y las extensiones medibles "
            "se cumplen con mas probabilidad. No reveles formulas, no des niveles."
        ),
    },
    {
        "id": "liquidez_pools",
        "titulo": "Donde realmente se mueve el dinero.",
        "guia": (
            "Explica que la liquidez (clusters de stops) es donde las instituciones "
            "buscan ejecutar. Highs y lows iguales = magnet de liquidez. Sin dar "
            "niveles especificos, ilustra el concepto general. No reveles formulas."
        ),
    },
    {
        "id": "discount_premium",
        "titulo": "Por que comprar caro no funciona.",
        "guia": (
            "Explica el concepto de zona discount vs premium (Fibonacci basico). "
            "Comprar en discount = menor riesgo, mas cerca del SL. Vender en "
            "premium = mismo principio inverso. Sin formulas, sin niveles."
        ),
    },
    {
        "id": "ote_concepto",
        "titulo": "El sweet spot del retroceso.",
        "guia": (
            "Habla del concepto OTE (Optimal Trade Entry): la zona del 62-79% "
            "de retroceso Fibonacci, con el 70.5% como el punto mas eficiente. "
            "Explica por que ahi el riesgo/beneficio es estructuralmente mejor. "
            "Sin dar precios de nada."
        ),
    },
    {
        "id": "displacement",
        "titulo": "Cuando el mercado dice la verdad.",
        "guia": (
            "Explica el concepto de displacement: velas con body grande y wicks "
            "chicos = movimiento decisivo, no ruido. Por que estas velas suelen "
            "marcar el inicio de algo real vs los flujos de ranging."
        ),
    },
    {
        "id": "inducement",
        "titulo": "Liquidez fabricada para ser cazada.",
        "guia": (
            "Habla del concepto de inducement: mini pullbacks que crean liquidez "
            "de timeframe bajo, que las manos fuertes barren antes del impulso "
            "real. Por que esa liquidez es 'comida' antes del movimiento."
        ),
    },
    {
        "id": "power_of_3",
        "titulo": "Acumulacion, manipulacion, distribucion.",
        "guia": (
            "Explica el ciclo AMD (Power of 3): rango -> manipulacion (sweep) -> "
            "movimiento real al lado contrario. Ilustra con un ejemplo conceptual "
            "del cierre asiatico hacia NY. Sin numeros, sin dar setups."
        ),
    },
    {
        "id": "structure_shift",
        "titulo": "Cambio de caracter antes del giro.",
        "guia": (
            "Explica Market Structure Shift (MSS) como la primera senal de cambio "
            "estructural: precio reversa antes de completar break of structure. "
            "Por que es lectura temprana del giro y por que requiere confirmacion."
        ),
    },
    {
        "id": "risk_disciplina",
        "titulo": "Por que el SL no se mueve.",
        "guia": (
            "Habla del principio de SL inmutable: una vez decidido, no se toca. "
            "Por que mover SL para 'darle aire' destruye el edge estadistico. "
            "Mencion al concepto de expectancy positiva agregada en el tiempo."
        ),
    },
    {
        "id": "false_signals",
        "titulo": "Por que la mayoria de senales son ruido.",
        "guia": (
            "Reflexion sobre por que un sistema selectivo (1-3 trades/dia maximo) "
            "vence a uno hiperactivo. La calidad sobre la cantidad. Como filtros "
            "multi-capa reducen falsos positivos. Sin nombrar formulas internas."
        ),
    },
    {
        "id": "weekend_silencio",
        "titulo": "Por que el bot calla los fines de semana.",
        "guia": (
            "Explica por que fin de semana = veto operativo. Liquidez delgada, "
            "spreads abiertos, sin volumen institucional. Operar weekend es "
            "jugar al casino. La paciencia es parte del sistema."
        ),
    },
    {
        "id": "memoria_bucket",
        "titulo": "Un sistema que aprende de cada cierre.",
        "guia": (
            "Habla a alto nivel del concepto de memoria estadistica: cada setup "
            "que se cierra alimenta una distribucion que ajusta el peso de "
            "futuros setups similares. Sin tecnicismos de Thompson sampling, "
            "sin formulas. Solo el concepto general."
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
Eres el editor de contenido publico del sistema FQ (Fibonacci Quantum) de RasDG_Sol.
Tu trabajo es generar lecturas educativas cortas (50-90 palabras) para un canal de Telegram publico.

REGLAS ABSOLUTAS:
1. NUNCA reveles formulas internas (no menciones phi, kappa_evo, Theta(D), P_master, w_clock, alpha).
2. NUNCA des niveles operativos (no precios de entry, SL, TPs, supports/resistances).
3. Tono: directo, profesional, sin emoji, sin hype. Como un editorial de Mistral Emergent Time o Financial Times.
4. Lenguaje: espanol neutro, sin modismos.
5. No uses bold/italic, son texto plano (envoltorio lo hace el sistema).
6. Cierra con una frase que invite a pensar, no a comprar.
7. EXACTAMENTE 6-10 lineas cortas. Ni mas ni menos.

OUTPUT: solo el cuerpo de la lectura. Sin titulo (el sistema lo agrega aparte). Sin saludo.
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
Eres copywriter del canal publico FQ. Genera UN parrafo corto (3-5 lineas)
que motive a probar el VIP sin sonar comercial. Tono profesional, sin emoji,
sin hype. No menciones precio (otra parte del mensaje lo dice).
Output: solo el texto. Sin titulo.
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
