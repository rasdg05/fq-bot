# -*- coding: utf-8 -*-
"""
================================================================================
  BATCH LLM — la mitad de coste para el trabajo que puede esperar
================================================================================

La Batches API cuesta el 50% de la tarifa normal a cambio de una ventana de
hasta 24 h (la mayoria de lotes cierran en menos de 1 h). Eso es un trueque
excelente para lo que se genera con horas de antelacion, y **inaceptable** para
lo que gatea una decision.

De ahi la unica regla de este modulo: **una superficie se declara o no se
batchea.** `BATCHABLE` dice por que aguanta la espera; `NEVER_BATCH` dice que
decision gatea cada superficie que no. Una superficie no declarada tampoco pasa
-- se falla cerrado, porque el modo de fallo de equivocarse aqui no es pagar de
mas: es retrasar 24 h un aviso que debia salir ya.

El caso que mas importa es `audit`. El self-audit puede poner
`_ledger_health.ok=False` y suspender el track record cuando detecta una
distribucion imposible. Meterlo en un lote significaria publicar durante un dia
entero un numero que el propio auditor ya no defiende — exactamente el fallo de
julio, ahora por ahorrar unos centavos.

Nota sobre el alcance (medido, no supuesto)
-------------------------------------------
Los barridos del CI que el brief nombraba — `cross_asset_sweep`, ablaciones,
walkforward — **no llaman a la API de Anthropic**: son numpy/pandas/lightgbm
puros, y `research.yml` les pone `ANTHROPIC_API_KEY: "ci-dummy"` justamente
porque nadie la usa. Ahi no hay tarifa que partir por la mitad. Lo que si es no
interactivo y tolera latencia es la generacion de contenido programado, y eso es
lo que este modulo abarata.

Uso:
    ids = batch_llm.submit([("lectura-2026-08-05", "Tema de hoy: ..."), ...],
                           surface="lectura", model=..., max_tokens=1200,
                           system=SYSTEM_PROMPT)
    ...  # horas despues
    textos = batch_llm.collect(ids)     # {custom_id: texto}
================================================================================
"""
import logging
import os

log = logging.getLogger(__name__)

# Superficies que PUEDEN esperar, con el motivo. Si no puedes escribir el
# motivo, la superficie no entra.
BATCHABLE = {
    "lectura": "se genera para un slot fijo del dia; se puede preparar la vispera",
    "cta": "copy rotativo sin fecha; se prepara por lotes semanales",
}

# Superficies que NO pueden esperar, con la decision que gatean. Estan escritas
# aqui para que el intento de batchearlas falle con la razon delante.
NEVER_BATCH = {
    "audit": "puede suspender el track record (fallo_de_medicion). Retrasarlo 24h "
             "significa publicar un dia entero un numero que el auditor ya no "
             "defiende — el fallo de julio, por ahorrar centavos",
    "signal_copilot": "acompana una senal viva; llega tarde y no acompana nada",
    "tactical": "responde a un comando del usuario en Telegram",
    "salud": "es el panel que se consulta cuando algo va mal",
}


class NotBatchableError(RuntimeError):
    """Se intento diferir una superficie que no puede esperar."""


def assert_batchable(surface):
    """Levanta si la superficie no esta declarada como diferible.

    Falla CERRADO a proposito: una superficie desconocida se rechaza en vez de
    aceptarse. Equivocarse hacia el lado permisivo no cuesta dinero, cuesta un
    aviso que llega 24 h tarde.
    """
    if surface in BATCHABLE:
        return True
    motivo = NEVER_BATCH.get(surface)
    if motivo:
        raise NotBatchableError(
            "'%s' no se batchea: %s" % (surface, motivo))
    raise NotBatchableError(
        "'%s' no esta declarada. Anadela a BATCHABLE con el motivo por el que "
        "aguanta 24h, o a NEVER_BATCH con la decision que gatea." % surface)


def enabled():
    """FQ_LLM_BATCH. OFF -> los llamadores siguen en linea (comportamiento
    historico, byte-identico)."""
    return os.environ.get("FQ_LLM_BATCH", "0").strip() in ("1", "true", "yes")


def _client():
    import claude_integration as ci
    return ci.get_client()


def submit(jobs, *, surface, model, max_tokens, system=None, client=None):
    """Encola un lote. Devuelve el batch_id.

    `jobs` es una secuencia de (custom_id, prompt). El custom_id es la clave con
    la que volveran los resultados — ponle algo que identifique el trabajo
    (fecha, slot, tema), nunca un indice: la API los devuelve EN CUALQUIER ORDEN.

    El `system` se manda como bloque cacheado y compartido por todas las
    peticiones del lote: es identico en todas y el descuento de cache se apila
    sobre el 50% del batch.
    """
    assert_batchable(surface)
    if not jobs:
        return None
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    ids = [cid for cid, _ in jobs]
    if len(set(ids)) != len(ids):
        # Un custom_id repetido hace ambiguo el resultado: dos trabajos
        # distintos colapsarian en una sola clave al recogerlos.
        raise ValueError("custom_id duplicado en el lote: %s" % sorted(
            {i for i in ids if ids.count(i) > 1}))

    def _params(prompt):
        kw = {"model": model, "max_tokens": max_tokens,
              "messages": [{"role": "user", "content": prompt}]}
        if system:
            kw["system"] = [{"type": "text", "text": system,
                             "cache_control": {"type": "ephemeral"}}]
        return MessageCreateParamsNonStreaming(**kw)

    cl = client or _client()
    batch = cl.messages.batches.create(
        requests=[Request(custom_id=cid, params=_params(p)) for cid, p in jobs])
    log.info("[batch] %s encolado: %s (%d peticiones)",
             surface, batch.id, len(jobs))
    return batch.id


def status(batch_id, *, client=None):
    """(processing_status, conteos). 'ended' = terminado (con o sin errores)."""
    cl = client or _client()
    b = cl.messages.batches.retrieve(batch_id)
    counts = getattr(b, "request_counts", None)
    return b.processing_status, {
        "succeeded": getattr(counts, "succeeded", None),
        "errored": getattr(counts, "errored", None),
        "processing": getattr(counts, "processing", None),
    }


def collect(batch_id, *, client=None):
    """{custom_id: texto} de los que salieron bien, y la lista de los que no.

    Devuelve (ok, fallidos). Los fallidos NO se convierten en cadena vacia: un
    trabajo que expiro o dio error no es 'un texto vacio', y confundirlos
    publicaria un hueco como si fuera contenido.
    """
    cl = client or _client()
    ok, fallidos = {}, []
    for res in cl.messages.batches.results(batch_id):
        tipo = res.result.type
        if tipo != "succeeded":
            fallidos.append((res.custom_id, tipo))
            continue
        msg = res.result.message
        if getattr(msg, "stop_reason", None) == "refusal":
            fallidos.append((res.custom_id, "refusal"))
            continue
        texto = "".join(b.text for b in msg.content
                        if getattr(b, "type", None) == "text").strip()
        if not texto:
            fallidos.append((res.custom_id, "vacio"))
            continue
        ok[res.custom_id] = texto
    if fallidos:
        log.warning("[batch] %s: %d peticiones sin resultado utilizable: %s",
                    batch_id, len(fallidos), fallidos[:5])
    return ok, fallidos
