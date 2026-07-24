#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  FQ COMBINED LAUNCHER - arranca VIP + Public en el mismo container
  by RasDG_Sol + Claude

  Railway no permite volumenes compartidos entre servicios (feature pendiente
  desde 2024). Para que el bot publico pueda leer /data/fq_ledger.db del bot
  VIP, ambos corren en el MISMO servicio Railway, sobre el mismo volumen.

  Este launcher:
   - Lanza entry_vip.py y entry_public.py como subprocesos hijos
   - Hereda stdout/stderr (Railway captura logs de ambos)
   - Si cualquier hijo muere, sale con rc != 0 -> Railway reinicia el container
   - Propaga SIGTERM/SIGINT a ambos hijos en shutdown

  ENV vars que deben estar presentes en el servicio Railway:
   VIP:    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ANTHROPIC_API_KEY, FQ_LEDGER_PATH
   PUBLIC: TELEGRAM_TOKEN_PUBLIC, FQ_VIP_BOT_USERNAME,
           FQ_PUBLIC_DB_PATH (/data/fq_public.db),
           FQ_VIP_LEDGER_PATH (/data/fq_ledger.db, mismo path que el VIP)
   FUNDING PAPER (opcional, 0% real, §6.15): FQ_FUNDING_PAPER=1 lanza
           tools/funding_paper.py --loop como hijo NO-CRITICO (si muere NO baja
           el bot VIP). Config por ENV: FQ_FUNDING_PAPER_INTERVAL (def 1800),
           _EXCHANGE (def okx), _BASE (def BTC), _SYMBOL (def BTC/USDT:USDT);
           ledger/equity/z/baseline los lee FundingPaperRuntime.from_env. El
           ledger durable va a /data (volumen). Default OFF.
   CARRY PAPER (opcional, 0% real, 2do motor market-neutral): FQ_CARRY_PAPER=1
           lanza tools/carry_paper.py --loop como hijo NO-CRITICO. Acumula el
           funding REALIZADO del basket CLEAN (validado multi-régimen) en un
           parquet durable en /data y mide el carry FORWARD. Config por ENV:
           FQ_CARRY_INTERVAL (def 3600), FQ_CARRY_BACKFILL (def 200),
           FQ_CARRY_DIR (def /data). Default OFF.
================================================================================
"""
import os
import sys
import signal
import subprocess
import time

def _public_enabled():
    """El bot publico solo corre con token PROPIO (distinto del VIP). Sin el,
    o con el MISMO token del VIP pegado en TELEGRAM_TOKEN_PUBLIC, no se lanza:
    dos pollers sobre un token = guerra de getUpdates (HTTP 409) + comandos
    robados. Misma regla que entry_public._resolve_public_token (defensa en
    profundidad alla; aqui evitamos hasta el proceso parqueado y su ruido de
    watchdog). Decision jun-2026: topologia de UN solo bot (todo por tiers en
    el VIP) -> sin token publico propio, 'public' queda fuera a proposito."""
    pub = (os.environ.get("TELEGRAM_TOKEN_PUBLIC") or "").strip()
    vip = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    return bool(pub) and pub != vip


def _funding_paper_enabled():
    """El paper-forward de funding-reversion (tools/funding_paper.py, §6.15) corre
    como hijo del launcher SOLO con FQ_FUNDING_PAPER=1. 0% real: acumula el track
    record FORWARD del edge ESTRUCTURAL (funding extremo revierte) en un ledger
    durable propio en /data. Default OFF -> no se lanza."""
    return (os.environ.get("FQ_FUNDING_PAPER") or "0").strip() in ("1", "true", "yes")


def _funding_paper_cmd():
    """Comando del paper-forward de funding. Config por ENV (Railway, sin tocar
    codigo): FQ_FUNDING_PAPER_INTERVAL/_EXCHANGE/_BASE/_SYMBOL; el resto
    (ledger/equity/umbrales z/baseline) lo lee FundingPaperRuntime.from_env."""
    interval = (os.environ.get("FQ_FUNDING_PAPER_INTERVAL") or "1800").strip()
    exchange = (os.environ.get("FQ_FUNDING_PAPER_EXCHANGE") or "okx").strip()
    base = (os.environ.get("FQ_FUNDING_PAPER_BASE") or "BTC").strip()
    # el symbol del precio DERIVA del base si no se fija (evita BASE=SOL con symbol
    # BTC por defecto = funding SOL contra precio BTC, un mismatch silencioso).
    symbol = (os.environ.get("FQ_FUNDING_PAPER_SYMBOL")
              or "{}/USDT:USDT".format(base)).strip()
    return [sys.executable, "-u", "tools/funding_paper.py", "--loop",
            "--interval", interval, "--exchange", exchange,
            "--funding-base", base, "--symbol", symbol]


def _oi_collect_enabled():
    """Colector FORWARD de Open Interest (tools/fetch_okx_oi.py, --loop). 0% real:
    acumula OI 5m en el Volume (/data) para el test de cascada/laser, que el
    historico corto de OKX no permite hacer hacia atras. Hijo NO-critico (un bug
    del colector jamas tira el bot VIP). Default OFF."""
    return (os.environ.get("FQ_OI_COLLECT") or "0").strip() in ("1", "true", "yes")


def _oi_collect_cmd():
    return [sys.executable, "-u", "tools/fetch_okx_oi.py", "--loop"]


def _carry_paper_enabled():
    """SEGUNDO motor (market-neutral): colector FORWARD del funding CARRY
    (tools/carry_paper.py, --loop). 0% real: acumula el funding REALIZADO del basket
    CLEAN (BTC/ETH/XRP/LTC/DOGE/ADA — validado multi-régimen, ver research/
    carry_regime.md) en un parquet durable en /data y mide el carry hacia adelante.
    Hijo NO-critico (un bug del colector jamas tira el bot VIP). Default OFF."""
    return (os.environ.get("FQ_CARRY_PAPER") or "0").strip() in ("1", "true", "yes")


def _carry_paper_cmd():
    return [sys.executable, "-u", "tools/carry_paper.py", "--loop"]


def _agg_oi_collect_enabled():
    """Colector FORWARD de OI AGREGADO multi-exchange (tools/fetch_agg_oi.py, --loop).
    Railway NO está geo-bloqueado -> le pega directo a OKX+Binance+Bybit y suma el OI
    en USD (el sandbox no puede: Binance/Bybit geo). 0% real, parquet durable en /data;
    junta OI agregado 5m para medir cambio/divergencia vs precio. Hijo NO-critico
    (un bug jamas tira el bot VIP). Default OFF. Supersede a FQ_OI_COLLECT (incluye OKX)."""
    return (os.environ.get("FQ_AGG_OI_COLLECT") or "0").strip() in ("1", "true", "yes")


def _agg_oi_collect_cmd():
    return [sys.executable, "-u", "tools/fetch_agg_oi.py", "--loop"]


def _cvd_collect_enabled():
    """Colector FORWARD de CVD REAL (tools/fetch_cvd.py, --loop): taker buy/sell por
    barra (order-flow FIRMADO) de OKX(+Binance en Railway). El research lo marcó como
    el signal de microestructura evidenciado (vs el volumen sin firmar del trigger
    actual). 0% real; junta el dato para validar forward antes de cablear a la señal.
    Hijo NO-critico. Default OFF."""
    return (os.environ.get("FQ_CVD_COLLECT") or "0").strip() in ("1", "true", "yes")


def _cvd_collect_cmd():
    return [sys.executable, "-u", "tools/fetch_cvd.py", "--loop"]


def _bots():
    # (name, cmd, critical): critical=True -> si muere, baja el container y Railway
    # reinicia (VIP/public/maintenance SON el producto). critical=False -> hijo
    # OPCIONAL (paper-forward): si muere se loguea y se deja morir SIN tumbar el
    # container -> un bug del experimento de funding NUNCA tira el bot VIP.
    bots = [("vip", [sys.executable, "-u", "entry_vip.py"], True)]
    if _public_enabled():
        bots.append(("public", [sys.executable, "-u", "entry_public.py"], True))
    bots.append(("maintenance", [sys.executable, "-u", "-m", "ops.maintenance"], True))
    if _funding_paper_enabled():
        bots.append(("funding-paper", _funding_paper_cmd(), False))
    if _oi_collect_enabled():
        bots.append(("oi-collect", _oi_collect_cmd(), False))
    if _carry_paper_enabled():
        bots.append(("carry-paper", _carry_paper_cmd(), False))
    if _agg_oi_collect_enabled():
        bots.append(("agg-oi", _agg_oi_collect_cmd(), False))
    if _cvd_collect_enabled():
        bots.append(("cvd-collect", _cvd_collect_cmd(), False))
    # Cockpit "show" (FQ_COCKPIT=1): interfaz de solo-lectura del motor. Hijo
    # OPCIONAL a propósito (regla RasDG): si el server muere, el bot VIP sigue.
    if os.environ.get("FQ_COCKPIT", "0").strip().lower() in ("1", "true", "yes"):
        bots.append(("cockpit", [sys.executable, "-u", "tools/cockpit_server.py"], False))
    # Análisis extra (FQ_ANALYSIS_EXTRA=1): capa de observación oro/Nasdaq para el
    # portal — NO emite señales, solo mide contexto (regime/funding) con datos
    # públicos (OKX/MEXC) y escribe cockpit_extra.json, que el server mezcla. Hijo
    # no-crítico y desacoplado: si muere, el panel de cripto del motor sigue intacto.
    if os.environ.get("FQ_ANALYSIS_EXTRA", "0").strip().lower() in ("1", "true", "yes"):
        bots.append(("analysis", [sys.executable, "-u", "tools/analysis_feeder.py"], False))
    return bots

GRACE_SECONDS = 8       # tiempo para que los hijos atiendan SIGTERM
POLL_INTERVAL = 3       # cada cuantos segundos chequeamos si murio alguien

_processes = []         # list of (name, Popen)
_shutting_down = False


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _log(msg):
    sys.stdout.write("{} [launcher] {}\n".format(_ts(), msg))
    sys.stdout.flush()


def _spawn(name, cmd):
    _log("starting {}: {}".format(name, " ".join(cmd)))
    env = os.environ.copy()
    # Marca para los hijos: corren BAJO el launcher (VIP + public en el MISMO
    # container). entry_public la usa para NO caer al fallback del token VIP:
    # dos pollers de getUpdates con el mismo token = HTTP 409 + comandos perdidos.
    env["FQ_LAUNCHER"] = "1"
    return subprocess.Popen(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        env=env,
    )


def _all_processes_exited():
    """True si TODOS los hijos terminaron. _processes son tuplas de 3
    (name, Popen, critical) -> hay que desempaquetar 3, no 2. (Antes:
    `for _, p in _processes` -> ValueError: too many values to unpack, crasheaba
    el apagado limpio en cada SIGTERM/deploy de Railway.)"""
    return all(p.poll() is not None for _name, p, _crit in _processes)


def _shutdown(signum=None, frame=None):
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    _log("shutdown (signal={}) - terminando hijos".format(signum))

    for name, p, _critical in _processes:
        if p.poll() is None:
            try:
                p.terminate()
            except Exception as e:
                _log("terminate {} fallo: {}".format(name, e))

    deadline = time.time() + GRACE_SECONDS
    while time.time() < deadline:
        if _all_processes_exited():
            break
        time.sleep(0.5)

    for name, p, _critical in _processes:
        if p.poll() is None:
            _log("{} no respondio en {}s - kill -9".format(name, GRACE_SECONDS))
            try:
                p.kill()
            except Exception:
                pass

    sys.exit(0)


def _apply_forward_measure():
    """FQ_FORWARD_MEASURE=1 — modo measure-first (auditoría 2026-07): prende los
    motores paper del set candidato (BCH/BNB/LINK, hoy default OFF) con broadcast
    OFF y tags de régimen ON, para acumular R FORWARD por símbolo SIN exponer
    clientes. Se aplica sobre os.environ ANTES de spawnear -> los hijos lo heredan.

    Regla clave: NO toca FQ_KL_FILTER. Measure-first = TAGGEAR, no gatear. El edge
    de BCH vive en irrev-ALTO, así que el filtro KL-bajo lo dañaría; aquí solo se
    graba el tag (kl_low) para comparar base vs base+KL en análisis. setdefault:
    cualquier valor que ya hayas puesto en Railway gana."""
    if os.environ.get("FQ_FORWARD_MEASURE", "0").strip().lower() not in ("1", "true", "yes"):
        return
    defaults = {
        "FQ_REGIME_TAGS": "1",                                    # graba kl_low -> bucket +KL
        "FQ_MOTOR_PAPER_BCH": "1", "FQ_BCH_VIP_BROADCAST": "0",
        "FQ_MOTOR_PAPER_BNB": "1", "FQ_BNB_VIP_BROADCAST": "0",
        "FQ_MOTOR_PAPER_LINK": "1", "FQ_LINK_VIP_BROADCAST": "0",
    }
    applied = []
    for k, v in defaults.items():
        if not os.environ.get(k, "").strip():
            os.environ[k] = v
            applied.append("{}={}".format(k, v))
    _log("FQ_FORWARD_MEASURE=1 -> measure-first: BCH/BNB/LINK paper, broadcast OFF, "
         "regime tags ON. setdefault aplicado: {}".format(", ".join(applied) or "(ya seteado)"))
    _log("  NO se toca FQ_KL_FILTER (se taggea, no se gatea). Lee: python tools/forward_measure.py")


def main():
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    _apply_forward_measure()                # measure-first: env de los hijos ANTES de spawnear

    bots = _bots()
    if not _public_enabled():
        _log("public: deshabilitado (sin TELEGRAM_TOKEN_PUBLIC propio) — "
             "topologia de un solo bot; todo por tiers en el VIP")
    _log("FQ launcher arrancando {} bots".format(len(bots)))
    for name, cmd, critical in bots:
        _processes.append((name, _spawn(name, cmd), critical))

    while True:
        time.sleep(POLL_INTERVAL)
        for name, p, critical in list(_processes):
            rc = p.poll()
            if rc is None:
                continue
            if critical:
                _log("{} salio con rc={} - saliendo para que Railway reinicie".format(name, rc))
                _shutdown()
                sys.exit(rc if rc not in (None, 0) else 1)
            else:
                # hijo OPCIONAL (funding paper): se murio -> log y se saca de la
                # vigilancia; el container (VIP) sigue vivo. SIN respawn: si crasheo
                # al arrancar, respawnear seria un loop -> el operador ve el log,
                # corrige el ENV y redeploya.
                _log("{} (opcional) salio con rc={} - lo dejo morir; el bot VIP sigue".format(name, rc))
                _processes.remove((name, p, critical))


if __name__ == "__main__":
    main()
