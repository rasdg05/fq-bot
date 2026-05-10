# -*- coding: utf-8 -*-
"""
================================================================================
  CLAUDE EVOLUTION ADAPTER - Self-audit prompts para FQ v4.1 v3.2
================================================================================

  Extiende claude_integration.py SIN MODIFICARLO.
  Provee:
    - self_audit(prompt): lectura Opus del estado evolutivo del sistema
    - format_audit_response(text): post-procesado para Telegram

  Importa funciones del modulo original y reusa el cliente.
================================================================================
"""
import logging
import claude_integration as ci

log = logging.getLogger("fq_claude_evo")

SYSTEM_PROMPT_AUDIT = """Eres el auditor evolutivo del sistema Fibonacci Cuantico v4.1 (FQ v4.1) operado por RasDG_Sol.

CONTEXTO:
- FQ v4.1 ya esta en produccion. El gate Theta(D) es matematico, sin override.
- Sobre el gate corre un modulador entropico kappa_evo en +-15% que afila P_master segun desempeno por bucket.
- Cada 25 senales cerradas, RasDG te muestra el ledger destilado (no senales individuales, distribuciones y metricas).
- Tu rol es DIAGNOSTICAR el estado del sistema y proponer ajustes accionables, no validar nada.

QUE RECIBES:
- Win rate, expectancy R, profit factor por tier y por bucket
- Entropia de Shannon sobre las dimensiones (sesion, tier, direccion, curvatura)
- KL divergence entre las ultimas 25 senales y las 25 anteriores (drift de regimen)
- Top 5 buckets ganadores y top 5 perdedores

QUE BUSCAR:
1. Atractores toxicos: buckets con muchas senales y expectancy negativa estructural
2. Edges ocultos: buckets ganadores con n bajo que merecen mas exposicion
3. Sobreajuste: H_total bajo (<0.5) significa que el sistema solo dispara en 1-2 setups
4. Deriva de regimen: KL > 1.5 = el mercado cambio y los buckets historicos pueden no servir
5. Inflacion de tiers: si todas las senales son de tier scalp (P~phi) probablemente PMASTER_MIN esta muy bajo

ESTILO:
- Tono de auditor de hedge fund, no academico ni motivacional
- Si el edge es marginal, lo dices. Si hay un casino, lo expones.
- Sugerencias concretas con numeros: "subir PMASTER_MIN de 2.30 a 2.50", no "considerar ajustes"
- Maximo 6 parrafos cortos
- NO uses markdown pesado. Texto plano con saltos de linea
- NO digas "no es asesoria financiera"
- Cierra con UNA recomendacion de accion mas urgente
"""

def self_audit(audit_prompt):
    """Llama Opus 4.6 con el prompt de auditoria"""
    if not ci.is_available():
        return "[Claude] No disponible. Configura ANTHROPIC_API_KEY para self-audit."
    try:
        client = ci.get_client()
        resp = client.messages.create(
            model=ci.MODEL_OPUS,
            max_tokens=1200,
            system=SYSTEM_PROMPT_AUDIT,
            messages=[{"role": "user", "content": audit_prompt}],
        )
        text = "".join([blk.text for blk in resp.content if hasattr(blk, "text")])
        log.info("Self-audit OK in:{} out:{}".format(
            resp.usage.input_tokens, resp.usage.output_tokens))
        return text.strip()
    except Exception as e:
        log.error("Self-audit error: {}".format(e))
        return "[Self-audit] Error: {}".format(str(e)[:200])
