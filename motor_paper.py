# -*- coding: utf-8 -*-
"""
================================================================================
  MOTOR PAPER (RETRIEVAL_PLAN §6.10.1) — paper del MOTOR BASE + veto + shadow maker
  by RasDG_Sol + Claude
================================================================================
Mide el SUBSET CORRECTO para validar FORWARD el techo +0.10R: senales del MOTOR
BASE (el `fire` de fusion_engine.evaluate_signal) filtradas por el veto de
sesion (default london_open_kz + asia_open), abiertas en PAPEL (taker = fill REAL) y
midiendo en paralelo si una LIMITE maker en el entry se habria llenado por
PENETRACION — el dato de ADVERSE SELECTION que decide si el techo es capturable.

Por que existe (§6.10.1): el paper ORO (gold_paper) abre senales del gate de la
ficcion NY = POBLACION INCORRECTA para esta espada. Este runtime abre la
poblacion correcta: el motor base + veto, que es donde se midio el +0.10R.

Invariantes:
  · PARALELO al ORO, NO lo reemplaza. 0% real. Ledger durable propio. Default
    OFF (FQ_MOTOR_PAPER). No toca el motor (fusion_engine) ni el ORO.
  · El monolito llama on_bar(fire, ...) con el `fire` CRUDO de evaluate_signal
    (pre QTE / pre veto-VIP) -> misma poblacion que el replay de research.
  · Veto PROPIO (FQ_MOTOR_PAPER_VETO_*), independiente del veto VIP en vivo:
    asi mide el config del techo SIN exigir el veto a clientes (desacopla la
    mision 2 de la 3). "" -> mide el motor base puro.
  · Shadow maker = mismo modelo de fill que el ORO (gold_paper.process_maker_pending).
    El fill-rate es microestructura (nivel->penetracion), no del gate.
================================================================================
"""
import os
import logging

from execution import (RiskGovernor, Account, PaperBroker, DurableHashLedger,
                       SqliteHashLedger, open_motor_ledger, _motor_db_path, _symbol_from_jsonl)
from live_driver import normalize_fire_report
from bt_engine import CostModel
import gold_paper
import segment_veto

log = logging.getLogger("motor_paper")


def cost_from_exec_mode(mode):
    """Traduce FQ_EXEC_MODE a un CostModel para el PaperBroker (mismo modelo de
    costes que el backtest, bt_engine.CostModel):
      ''/otro -> None  : PnL BRUTO (comportamiento historico; default, reversible).
      'taker' -> neto, ambas piernas taker (fee 5bps + slippage 1bp por lado).
      'maker' -> neto con ENTRADA maker (fee 2bps, SIN slippage de entrada); stop
                 y timeout siguen taker. TP maker solo si FQ_MAKER_TP_EXIT=1.
    El A/B taker-vs-maker sobre el MISMO set de senales mide cuanto edge te
    devuelve no pagar el spread. Funding: commit 2.
    """
    mode = (mode or "").strip().lower()
    if mode not in ("taker", "maker"):
        return None
    maker = (mode == "maker")
    tp_maker = maker and (os.environ.get("FQ_MAKER_TP_EXIT", "0").strip()
                          in ("1", "true", "yes"))
    return CostModel(maker_entry=maker, maker_tp_exit=tp_maker)


class MotorPaperRuntime:
    """Por vela del TF del motor: resolver abiertas -> shadow maker -> si `fire`
    y no vetada, abrir en paper (taker) + armar la limite maker shadow. Track
    record + provenance (killzone/tf) en un ledger durable, segmentable offline
    (tools/motor_paper_stats.py)."""

    def __init__(self, symbol, *, account, governor=None, broker=None,
                 veto=None, tp_key="tp1", notify_fn=None, requested_risk=None,
                 digest_every=0, maker_sim=True, maker_eps_bps=1.0,
                 maker_ttl_bars=6, cost=None, cvd_path=None, cvd_imb_min=0.50):
        self.symbol = symbol
        self.account = account
        self.governor = governor or RiskGovernor()
        self.broker = broker or PaperBroker(cost=cost)
        self.veto = veto if veto is not None else segment_veto.SegmentVeto()
        self.tp_key = tp_key
        self.notify_fn = notify_fn
        self.requested_risk = requested_risk
        self.digest_every = digest_every
        self._ticks = 0
        self.counts = {"fire": 0, "opened": 0, "vetoed": 0}
        self.maker_sim = bool(maker_sim)
        self.maker_eps = float(maker_eps_bps) / 10_000.0
        self.maker_ttl_bars = int(maker_ttl_bars)
        self._maker_pending = []
        # EJECUCION maker (FQ_EXEC_MODE=maker -> cost.maker_entry): en vez de abrir
        # taker al instante, encola una limite en el nivel y la abre al PENETRAR
        # (maker) o, si expira el TTL, a mercado (fallback taker). Deriva del cost
        # del broker -> 0 cambio cuando no hay maker (todos los tests actuales).
        self.maker_exec = bool(getattr(self.broker.cost, "maker_entry", False))
        self._pending_entries = []
        # Capa 3 (order-flow CVD) como MEDICION paralela al regime tag: si
        # FQ_CVD_FILTER=1, cada fire se taguea con confirmado/no (CAUSAL) + su R
        # forward -> mide si el uplift +0.1R (validado 5 anos, DSR ✓) se replica EN
        # VIVO antes de graduar a conviction/sizing. cvd_path=None -> inerte (default).
        self.cvd_path = cvd_path
        self.cvd_ccy = _ccy_of(symbol)
        self.cvd_imb_min = float(cvd_imb_min)

    @classmethod
    def from_env(cls, symbol, *, notify_fn=None, ledger_path=None):
        """Arma el runtime desde el entorno:
          FQ_MOTOR_PAPER_LEDGER_PATH ledger durable (default /data/motor_paper_<slug>.jsonl)
          FQ_MOTOR_PAPER_EQUITY      equity de la cuenta paper (default 10000)
          FQ_MOTOR_PAPER_VETO_KILLZONES veto propio (default london_open_kz,asia_open)
          FQ_MOTOR_PAPER_VETO_UTC_BLOCKS / _WEEKDAYS  vetos secundarios (default "")
          FQ_MOTOR_PAPER_TP          nivel del cubo a usar como TP (default tp1)
          FQ_MOTOR_PAPER_MAKER_SIM   shadow maker (default 1: es el punto del track)
          FQ_GOLD_MAKER_EPS_BPS / _TTL_BARS  mismo modelo de fill que el ORO
          FQ_MOTOR_PAPER_DIGEST_EVERY (cae a FQ_GOLD_DIGEST_EVERY) digest admin

        ledger_path: override explícito del ledger. CRÍTICO para correr DOS
        símbolos en paralelo (SOL + BTC): sin esto ambos heredarían el MISMO
        FQ_MOTOR_PAPER_LEDGER_PATH y mezclarían sus trades en un solo archivo.
        El resto de la config (TP/veto/maker/equity) SÍ se comparte a propósito:
        el único variable del experimento debe ser el símbolo.
        """
        slug = symbol.replace("/", "_").replace(":", "_")
        led_path = ledger_path or os.environ.get(
            "FQ_MOTOR_PAPER_LEDGER_PATH", "/data/motor_paper_%s.jsonl" % slug)
        exec_mode = os.environ.get("FQ_EXEC_MODE", "")
        cost = cost_from_exec_mode(exec_mode)
        broker = PaperBroker(ledger=open_motor_ledger(led_path, symbol), cost=cost)
        equity = float(os.environ.get("FQ_MOTOR_PAPER_EQUITY", "10000"))
        acc = Account("paper-motor-%s" % symbol, equity)
        # Veto PROPIO: default = london_open_kz + asia_open (ambos -EV en SOL Y BTC,
        # OOS; asia_open con n menor -> confianza moderada, lo confirma el forward).
        # "" -> motor base sin veto.
        veto = segment_veto.parse(
            killzones=os.environ.get("FQ_MOTOR_PAPER_VETO_KILLZONES", "london_open_kz,asia_open"),
            utc_blocks=os.environ.get("FQ_MOTOR_PAPER_VETO_UTC_BLOCKS", ""),
            weekdays=os.environ.get("FQ_MOTOR_PAPER_VETO_WEEKDAYS", ""))
        tp_key = os.environ.get("FQ_MOTOR_PAPER_TP", "tp1")
        digest_every = int(os.environ.get(
            "FQ_MOTOR_PAPER_DIGEST_EVERY",
            os.environ.get("FQ_GOLD_DIGEST_EVERY", "0")))
        maker_eps = float(os.environ.get("FQ_GOLD_MAKER_EPS_BPS", "1.0"))
        maker_ttl = int(os.environ.get("FQ_GOLD_MAKER_TTL_BARS", "6"))
        maker_sim = os.environ.get("FQ_MOTOR_PAPER_MAKER_SIM", "1").strip() \
            in ("1", "true", "yes")
        # Capa 3 order-flow (measurement-first): FQ_CVD_FILTER=1 lee el parquet del
        # colector FQ_CVD_COLLECT y taguea cada fire (confirmado/no, CAUSAL). Default
        # OFF -> path None -> inerte. imb_min 0.50 = umbral VALIDADO (DSR, 5 anos).
        cvd_path = None
        if os.environ.get("FQ_CVD_FILTER", "0").strip() in ("1", "true", "yes"):
            cvd_dir = os.environ.get("FQ_CVD_DIR") or (
                "/data" if os.path.isdir("/data") else "data/okx")
            cvd_path = os.path.join(cvd_dir, "cvd.parquet")
        cvd_imb_min = float(os.environ.get("FQ_CVD_IMB_MIN", "0.50"))
        log.info("[motor] runtime paper MOTOR BASE activo (%s, veto=%s, "
                 "maker_shadow=%s, exec=%s, cvd=%s, ledger=%s)", symbol, veto.describe(),
                 maker_sim, exec_mode.strip() or "bruto",
                 ("on@%.2f" % cvd_imb_min) if cvd_path else "off", led_path)
        return cls(symbol, account=acc, broker=broker, veto=veto, tp_key=tp_key,
                   notify_fn=notify_fn, digest_every=digest_every,
                   maker_sim=maker_sim, maker_eps_bps=maker_eps,
                   maker_ttl_bars=maker_ttl, cvd_path=cvd_path, cvd_imb_min=cvd_imb_min)

    def _maybe_digest(self):
        if self.digest_every and self._ticks % self.digest_every == 0 \
                and self.notify_fn is not None:
            try:
                self.notify_fn(None, {"digest": dict(self.counts),
                                      "ticks": self._ticks,
                                      "open": len(self.account.open)}, None)
            except Exception as e:
                log.warning("[motor] digest: %s", e)

    def on_bar(self, fire, field, report, df_primary, price, *,
               high=None, low=None, ts=None, tf_id=None):
        """Procesa una vela. `fire` = disparo CRUDO de evaluate_signal. high/low
        resuelven abiertas + shadow maker. Devuelve {fire, opened, resolved}."""
        # 1) resolver abiertas (empate pesimista, = etiquetado de research) +
        #    shadow maker contra ESTA vela (antes de abrir: una limite no se
        #    llena en su vela 0).
        resolved = []
        maker_opened = []
        if high is not None and low is not None:
            for pos in list(self.account.open):
                out = self.broker.resolve_on_bar(self.account, pos, high, low, ts=ts)
                if out is not None:
                    resolved.append({"pid": pos.pid, **out})
            # EJECUCION maker: abrir las entradas pendientes que penetraron (maker)
            # o expiraron el TTL (fallback taker). DESPUES de resolver -> la nueva
            # no se resuelve en su propia vela (sin look-ahead). SHADOW solo si NO
            # hay ejecucion (mide sin tocar posiciones = comportamiento historico).
            if self.maker_exec:
                if self._pending_entries:
                    maker_opened = self._process_pending_entries(
                        high, low, price, ts=ts, tf_id=tf_id)
            elif self.maker_sim and self._maker_pending:
                self._maker_pending = gold_paper.process_maker_pending(
                    self._maker_pending, self.broker.ledger, high, low, ts,
                    eps=self.maker_eps, ttl_bars=self.maker_ttl_bars)
        self._ticks += 1
        try:      # cockpit "show" (FQ_COCKPIT): telemetría NO-crítica; jamás rompe la vela
            import cockpit
            if cockpit.enabled():
                cockpit.tick(self.symbol, ts=ts, price=price,
                             closes=(df_primary["close"].to_numpy(dtype=float)[-64:]
                                     if df_primary is not None else None),
                             killzone=getattr(field, "killzone", None),
                             counts=self.counts, n_open=len(self.account.open))
                for r in resolved:
                    cockpit.log_event(self.symbol, "close",
                                      "cierre pid=%s R=%+.2f" % (r.get("pid"), r.get("pnl_r") or 0))
        except Exception:
            pass

        # 2) si el motor disparo: aplicar veto propio; si pasa, abrir en paper
        opened = None
        if fire:
            self.counts["fire"] += 1
            kz = getattr(field, "killzone", None)
            regime = _regime_of(report)   # stable/deriva/... para segmentar el R forward
            try:  # cockpit: evento real (no-crítico)
                import cockpit
                cockpit.log_event(self.symbol, "fire", "FIRE del motor [%s/%s]" % (tf_id, kz))
            except Exception:
                pass
            why = self.veto.reason(killzone=kz, ts_utc=ts) if self.veto.active else None
            if why:
                self.counts["vetoed"] += 1
                self.broker.ledger.append({
                    "event": "MOTOR_VETOED", "ts": ts, "tf": tf_id,
                    "killzone": kz, "why": why})
                try:
                    import cockpit
                    cockpit.log_event(self.symbol, "veto", "vetado: %s" % why)
                except Exception:
                    pass
            else:
                sig = normalize_fire_report(report, self.symbol, tp_key=self.tp_key)
                if sig is not None:
                    cvd = self._cvd_confirm(sig.get("direction"), ts)  # tag CAUSAL (None si filtro off)
                    d = self.governor.decide(self.account,
                                             requested_risk=self.requested_risk)
                    if d["approved"]:
                        if self.maker_exec:
                            # encola una limite en el nivel; se abre al PENETRAR
                            # (maker) o, si expira el TTL, a mercado (fallback taker)
                            # en las velas siguientes (no en esta).
                            self._pending_entries.append({
                                "sig": sig, "risk_frac": d["risk_frac"], "killzone": kz,
                                "regime": regime, "cvd": cvd, "tf": tf_id, "waited": 0,
                                "regime_tags": _regime_tags(df_primary, sig.get("entry"),
                                                            symbol=self.symbol)})
                            self.broker.ledger.append({
                                "event": "MAKER_ENTRY_PENDING", "ts": ts, "tf": tf_id,
                                "killzone": kz, "limit": sig["entry"],
                                "direction": sig["direction"]})
                        else:
                            pos = self.broker.open(self.account, sig, d["risk_frac"], ts=ts)
                            self.counts["opened"] += 1
                            try:  # cockpit: evento real (no-crítico)
                                import cockpit
                                cockpit.log_event(self.symbol, "open",
                                                  "%s abierta @ %.4f" % (
                                                      "LONG" if sig["direction"] > 0 else "SHORT",
                                                      sig["entry"]))
                            except Exception:
                                pass
                            opened = {"pid": pos.pid, "killzone": kz, "tf": tf_id,
                                      "risk_frac": d["risk_frac"], **sig}
                            # provenance: liga el pid con killzone/tf para segmentar
                            # el ledger forward (base vs +veto, por killzone/tf).
                            self.broker.ledger.append({
                                "event": "MOTOR_OPEN_META", "ts": ts, "pid": pos.pid,
                                "tf": tf_id, "killzone": kz, "regime": regime,
                                **_cvd_meta(cvd),
                                **_regime_tags(df_primary, sig.get("entry"), symbol=self.symbol)})
                            if self.maker_sim:
                                self._maker_pending.append({
                                    "pid": pos.pid, "direction": pos.direction,
                                    "limit": pos.entry, "waited": 0})
                            if self.notify_fn is not None:
                                try:
                                    self.notify_fn(sig, {"killzone": kz, "tf": tf_id,
                                                         "symbol": self.symbol}, pos)
                                except Exception as e:
                                    log.warning("[motor] notify_fn: %s", e)
                    else:
                        log.info("[motor] fire rechazado por gobernador: %s",
                                 d.get("reason"))
        self._maybe_digest()
        return {"fire": bool(fire), "opened": opened, "resolved": resolved,
                "maker_opened": maker_opened}

    def _process_pending_entries(self, high, low, price, *, ts=None, tf_id=None):
        """EJECUCION maker (FQ_EXEC_MODE=maker). Por cada entrada pendiente, una
        limite en sig['entry'] (= nivel de la senal), evaluada desde la vela
        SIGUIENTE a la del disparo (encolada DESPUES de procesar -> nunca se
        evalua en su vela 0):
          · PENETRA dentro de TTL  -> abre MAKER en el nivel (2bps, sin slippage).
          · TTL sin llenar -> FALLBACK TAKER a mercado (price actual), con el R:R
            REAL de esa entrada peor (el sizing sale de |price-stop|). Pero si el
            precio ya REBASO el TP mientras esperaba (el runner se escapo entero),
            NO se persigue -> MISS: esa es la adverse selection que el maker paga.
        Devuelve la lista de aperturas de esta vela. Llamada DESPUES de resolver
        abiertas -> la nueva no se resuelve en su propia vela (sin look-ahead).
        """
        still, opened = [], []
        for pe in self._pending_entries:
            sig = pe["sig"]
            d, limit = sig["direction"], sig["entry"]
            if gold_paper.maker_penetrated(d, limit, high, low, self.maker_eps):
                pos = self._open_pending(sig, pe, fill_type="maker",
                                         bars_waited=pe["waited"] + 1, ts=ts)
                if pos is not None:
                    opened.append({"pid": pos.pid, "fill_type": "maker",
                                   "killzone": pe.get("killzone"), "tf": pe.get("tf"),
                                   "risk_frac": pe["risk_frac"], **sig})
                continue
            pe["waited"] += 1
            if pe["waited"] >= self.maker_ttl_bars:
                tp = sig["tp"]
                ran_past_tp = (price >= tp) if d > 0 else (price <= tp)
                if ran_past_tp:
                    self.broker.ledger.append({
                        "event": "MAKER_RUNAWAY", "ts": ts, "tf": pe.get("tf"),
                        "killzone": pe.get("killzone"), "limit": limit,
                        "tp": tp, "price": float(price), "bars_waited": pe["waited"]})
                    continue
                chase = {**sig, "entry": float(price)}
                pos = self._open_pending(chase, pe, fill_type="taker",
                                         bars_waited=pe["waited"], ts=ts)
                if pos is not None:
                    opened.append({"pid": pos.pid, "fill_type": "taker",
                                   "killzone": pe.get("killzone"), "tf": pe.get("tf"),
                                   "risk_frac": pe["risk_frac"], **chase})
            else:
                still.append(pe)
        self._pending_entries = still
        return opened

    def _open_pending(self, sig, pe, *, fill_type, bars_waited, ts=None):
        """Abre una posicion desde una entrada pendiente y la marca con su
        fill_type (lo lee resolve()->_settle para cobrar maker o taker). Sella
        MOTOR_OPEN_META (provenance killzone/tf + fill_type + bars_waited) y avisa
        al admin. Devuelve la Position, o None si el riesgo es nulo (entry==stop)."""
        if abs(float(sig["entry"]) - float(sig["stop"])) <= 0:
            return None
        pos = self.broker.open(self.account, sig, pe["risk_frac"], ts=ts)
        pos.entry_fill_type = fill_type
        self.counts["opened"] += 1
        self.broker.ledger.append({
            "event": "MOTOR_OPEN_META", "ts": ts, "pid": pos.pid,
            "tf": pe.get("tf"), "killzone": pe.get("killzone"),
            "regime": pe.get("regime"),
            "fill_type": fill_type, "bars_waited": bars_waited,
            **_cvd_meta(pe.get("cvd")), **pe.get("regime_tags", {})})
        if self.notify_fn is not None:
            try:
                self.notify_fn(sig, {"killzone": pe.get("killzone"), "tf": pe.get("tf"),
                                     "fill_type": fill_type, "symbol": self.symbol}, pos)
            except Exception as e:
                log.warning("[motor] notify_fn: %s", e)
        return pos

    def _cvd_confirm(self, direction, ts):
        """Confirmacion de order-flow CAUSAL en el ts del fire (measurement-first,
        FQ_CVD_FILTER). Devuelve dict {confirmed, imbalance, cvd_slope, n} o None
        (filtro off / sin data / sin direccion). JAMAS rompe el motor (defensivo).
        Tag PARALELO a `regime`: mide FORWARD si el +0.1R de uplift del CVD (validado
        5 anos, DSR ✓) se replica antes de graduar a conviction/sizing client-facing."""
        if not self.cvd_path or direction is None:
            return None
        try:
            ms = _ts_ms(ts)
            if ms is None:
                return None
            return _fetch_cvd().cvd_confirmation(
                self.cvd_path, self.cvd_ccy, ms, direction, imb_min=self.cvd_imb_min)
        except Exception as e:
            log.debug("[motor] cvd_confirm: %s", e)
            return None


def _regime_of(report):
    """Extrae el regime ('stable'/'deriva'/...) del report del motor. Defensivo:
    acepta dict {'state':...}, string, o None. Se sella en MOTOR_OPEN_META para
    medir el R FORWARD segmentado por regime (clave si FQ_DERIVA_VETO=0: ¿los fires
    de deriva aguantan como los de stable, o arrastran? — eso NO está en el cubo)."""
    try:
        r = report.get("regime") if isinstance(report, dict) else None
        return r.get("state") if isinstance(r, dict) else r
    except Exception:
        return None


_FETCH_CVD = None


def _fetch_cvd():
    """Importa tools/fetch_cvd LAZY (solo si FQ_CVD_FILTER=1 alguna vez dispara la
    medicion). 'tools' no es paquete -> mete tools/ en sys.path 1 vez, mismo patron
    que el validador. Cacheado a nivel modulo. Si falla (sin pandas) -> el caller
    lo atrapa y el filtro queda inerte (nunca rompe el motor)."""
    global _FETCH_CVD
    if _FETCH_CVD is None:
        import sys
        td = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
        if td not in sys.path:
            sys.path.insert(0, td)
        import fetch_cvd as _mod
        _FETCH_CVD = _mod
    return _FETCH_CVD


def _ccy_of(symbol):
    """'SOL/USDT:USDT' / 'BTCUSDT' / 'SOL' -> 'SOL': mapea el simbolo del motor al
    ccy del colector CVD (BTC/ETH/SOL/...)."""
    s = str(symbol or "").upper().split("/")[0].split(":")[0]
    for q in ("USDT", "USDC", "USD", "PERP"):
        if s.endswith(q) and len(s) > len(q):
            return s[:-len(q)]
    return s


def _ts_ms(ts):
    """epoch-ms desde un ts heterogeneo (pandas Timestamp / datetime / int seg|ms /
    None). El colector CVD indexa en ms; el motor pasa el ts de la VELA (Timestamp).
    Defensivo: None si no se puede convertir."""
    if ts is None:
        return None
    try:
        v = getattr(ts, "value", None)                    # pandas Timestamp -> ns
        if isinstance(v, int):
            return v // 1_000_000
        if hasattr(ts, "timestamp"):                      # datetime
            return int(ts.timestamp() * 1000)
        n = int(ts)
        return n if n > 1_000_000_000_000 else n * 1000   # ms ya vs seg->ms
    except Exception:
        return None


def _cvd_meta(cvd):
    """Campos CVD para MOTOR_OPEN_META. {} si no hubo medicion (filtro off / sin
    data) -> ledger IDENTICO al historico cuando FQ_CVD_FILTER=0 (backward-compat)."""
    if not cvd:
        return {}
    return {"cvd_confirmed": bool(cvd.get("confirmed")),
            "cvd_imbalance": cvd.get("imbalance")}


def cvd_confirm_live(symbol, ts, direction, imb_min=None):
    """Confirmacion de order-flow CAUSAL para UNA senal en vivo, resolviendo el
    colector desde el entorno (igual que from_env). Para el badge VIP del monolito
    (FQ_CVD_VIP_CONVICTION). Devuelve dict {confirmed, imbalance, ...} o None si el
    filtro esta off / no hay parquet / sin direccion. JAMAS lanza (defensivo)."""
    if os.environ.get("FQ_CVD_FILTER", "0").strip() not in ("1", "true", "yes"):
        return None
    if direction is None:
        return None
    try:
        cvd_dir = os.environ.get("FQ_CVD_DIR") or (
            "/data" if os.path.isdir("/data") else "data/okx")
        cvd_path = os.path.join(cvd_dir, "cvd.parquet")
        if not os.path.exists(cvd_path):
            return None
        ms = _ts_ms(ts)
        if ms is None:
            return None
        if imb_min is None:
            imb_min = float(os.environ.get("FQ_CVD_IMB_MIN", "0.50"))
        return _fetch_cvd().cvd_confirmation(
            cvd_path, _ccy_of(symbol), ms, direction, imb_min=imb_min)
    except Exception as e:
        log.debug("[motor] cvd_confirm_live: %s", e)
        return None


def persist_confirm_live(symbol, ts, direction, thr=None):
    """Persistencia/memoria del flujo CAUSAL para UNA senal en vivo (espejo de
    cvd_confirm_live; 2o medidor VALIDADO ortogonal al CVD en BTC). Lee el MISMO
    colector (FQ_CVD_FILTER). Devuelve {persistent, ac1, netdir, n} o None si el filtro
    esta off / no hay parquet / sin direccion. JAMAS lanza (defensivo)."""
    if os.environ.get("FQ_CVD_FILTER", "0").strip() not in ("1", "true", "yes"):
        return None
    if direction is None:
        return None
    try:
        cvd_dir = os.environ.get("FQ_CVD_DIR") or (
            "/data" if os.path.isdir("/data") else "data/okx")
        cvd_path = os.path.join(cvd_dir, "cvd.parquet")
        if not os.path.exists(cvd_path):
            return None
        ms = _ts_ms(ts)
        if ms is None:
            return None
        if thr is None:
            thr = float(os.environ.get("FQ_PERSIST_THR", "0.0"))
        return _fetch_cvd().persistence_confirmation(
            cvd_path, _ccy_of(symbol), ms, direction, thr=thr)
    except Exception as e:
        log.debug("[motor] persist_confirm_live: %s", e)
        return None


_KL_MOD = None


def _kl_mod():
    """Importa tools/validate_regime_irreversibility LAZY (solo si el filtro KL está activo).
    Mismo patrón que _fetch_cvd. Cacheado a nivel módulo."""
    global _KL_MOD
    if _KL_MOD is None:
        import sys
        td = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
        if td not in sys.path:
            sys.path.insert(0, td)
        import validate_regime_irreversibility as _m
        _KL_MOD = _m
    return _KL_MOD


def kl_regime_live(closes, thr=None):
    """Régimen por irreversibilidad temporal (grafo de visibilidad + KL) sobre la ventana de
    precio que el bot YA tiene en mano (sin red). low=True -> régimen reversible/mean-reverting
    (donde el edge de FQ paga: KL DSR 0.999 BTC / 0.950 SOL en el cube); False -> trending/
    irreversible (el edge muere). thr default FQ_KL_THR=0.34 (la mediana medida en el cube).
    Devuelve {low, irrev} o None. JAMAS lanza (defensivo)."""
    try:
        import numpy as np
        y = np.asarray(closes, dtype=float)
        y = y[np.isfinite(y)]
        if len(y) < 16:
            return None
        irr = float(_kl_mod().irreversibility(y[-64:]))
        if thr is None:
            thr = float(os.environ.get("FQ_KL_THR", "0.34"))
        return {"low": bool(irr <= thr), "irrev": irr}
    except Exception as e:
        log.debug("[motor] kl_regime_live: %s", e)
        return None


_VP_MOD = None


def _vp_mod():
    """Importa volume_profile LAZY (solo si FQ_REGIME_TAGS taggea). Cacheado."""
    global _VP_MOD
    if _VP_MOD is None:
        import volume_profile as _m
        _VP_MOD = _m
    return _VP_MOD


# --- FUNDING relativo (pctl 90d) — el gate que PASÓ in-cube (validate_long_gates,
# 2026-07-03: LONG & pctl<=0.5 -> +0.173R vs +0.121; DSR 1.000/CPCV 80%/PBO 0.04).
# Se sella DORMIDO como tag forward (mismo camino que el CVD: gate -> dormido ->
# forward -> producto). Cache 1h por símbolo: el funding cambia cada 8h, un fetch
# por hora sobra. Defensivo: cualquier fallo -> sin tag, JAMÁS rompe el fire.
_FUND_CACHE = {}


def _okx_inst(symbol):
    """'SOL/USDT' | 'SOL-USDT-SWAP' | 'SOLUSDT' -> instId de OKX ('SOL-USDT-SWAP')."""
    s = str(symbol or "").upper()
    if s.endswith("-SWAP"):
        return s
    ccy = s.split("/")[0].split(":")[0].replace("-USDT", "").replace("USDT", "")
    return "%s-USDT-SWAP" % ccy if ccy else None


def funding_pctl_live(symbol, ttl_s=3600, n_hist=300):
    """(rate, pctl90d) del funding del perp en OKX (endpoint PÚBLICO, paginado como
    tools/fetch_okx_funding.py). pctl = fracción de la historia (~90d a 8h) <= rate
    actual — el MISMO constructo relativo que pasó el gate (validado sobre historia
    Binance; en vivo se compara el venue contra su PROPIA historia). None,None si falla."""
    import time as _t
    inst = _okx_inst(symbol)
    if not inst:
        return None, None
    c = _FUND_CACHE.get(inst)
    if c and _t.time() - c[0] < ttl_s:
        return c[1], c[2]
    try:
        import json
        import urllib.request
        rates, after = [], None
        for _ in range(3):                       # 3 páginas x 100 = ~100 días de eventos 8h
            q = "instId=%s&limit=100" % inst + ("&after=%s" % after if after else "")
            req = urllib.request.Request(
                "https://www.okx.com/api/v5/public/funding-rate-history?" + q,
                headers={"User-Agent": "fq-bot"})
            with urllib.request.urlopen(req, timeout=10) as r:
                rows = json.loads(r.read().decode()).get("data") or []
            if not rows:
                break
            rates.extend((float(x["fundingRate"]), int(x["fundingTime"])) for x in rows)
            after = rows[-1]["fundingTime"]
        if len(rates) < 30:
            return None, None
        rates.sort(key=lambda x: x[1])
        hist = [r for r, _ in rates][-n_hist:]
        rate = hist[-1]
        pctl = float(sum(1 for h in hist if h <= rate)) / len(hist)
        _FUND_CACHE[inst] = (_t.time(), rate, pctl)
        return rate, pctl
    except Exception as e:
        log.debug("[motor] funding_pctl_live: %s", e)
        return None, None


def _regime_tags(df_primary, entry_price, symbol=None):
    """Tags de régimen para MOTOR_OPEN_META, gateado por FQ_REGIME_TAGS. {} si off ->
    ledger byte-idéntico (backward-compat). CAUSAL; sin red SALVO el funding (fetch
    público OKX cacheado 1h, defensivo — un fallo deja el tag ausente, nunca rompe).
      kl_low/kl_irrev  : KL-irreversibilidad (validado en cube; ventana 64, FIEL).
      poc_dist/vp_zone : distancia al POC del día EN CURSO (developing) de df_primary
                         -> proxy live. El POC-distance ESTRICTO (día PREVIO, el que
                         pasó el gate) se mide forward OFFLINE con gate_poc_distance.py
                         sobre el ledger (entry_ts + entry_price). vp_basis lo aclara.
      funding_rate/funding_pctl : funding del perp y su percentil ~90d (validado
                         in-cube 2026-07-03; juez forward en by_funding del reporte).
    """
    if os.environ.get("FQ_REGIME_TAGS", "0").strip() not in ("1", "true", "yes"):
        return {}
    out = {}
    try:
        kl = kl_regime_live(df_primary["close"].to_numpy(dtype=float))
        if kl is not None:
            out["kl_low"] = bool(kl["low"])
            out["kl_irrev"] = round(float(kl["irrev"]), 4)
        prof = _vp_mod().daily_volume_profile(df_primary)
        if prof is not None and entry_price:
            half = max((prof.vah - prof.val) / 2.0, 1e-9)
            out["poc_dist"] = round(abs(float(entry_price) - prof.poc) / half, 4)
            out["vp_zone"] = _vp_mod().vp_position(float(entry_price), prof)
            out["vp_basis"] = "developing"
        if symbol:
            rate, pctl = funding_pctl_live(symbol)
            if pctl is not None:
                out["funding_rate"] = round(float(rate), 8)
                out["funding_pctl"] = round(float(pctl), 3)
    except Exception as e:
        log.debug("[motor] regime_tags: %s", e)
    return out


def ledger_report(path):
    """Lee el ledger del motor paper y devuelve un dict de stats (cartera +
    fill-rate maker + adverse selection + R por regime). Reusado por el comando
    /paper del bot y por tools/motor_paper_stats.py. Devuelve None si el ledger no
    existe. DurableHashLedger.load verifica la cadena SHA-256 (LANZA si está rota)."""
    import os
    if os.environ.get("FQ_LEDGER_SQLITE", "0").strip() in ("1", "true", "yes"):
        db = _motor_db_path(path)                         # SQLite multi-símbolo
        if not os.path.exists(db):
            return None
        led = SqliteHashLedger.load(db, _symbol_from_jsonl(path))
    else:
        if not os.path.exists(path):                      # JSONL legacy por símbolo
            return None
        led = DurableHashLedger.load(path)
    recs = [r["payload"] for r in led.records]
    pnl, kz, maker, vetoed, ftype, regime_m, cvd_m = {}, {}, {}, {}, {}, {}, {}
    kl_m, poc_m, fund_m = {}, {}, {}
    n_runaway = 0
    net = False
    for p in recs:
        ev, pid = p.get("event"), p.get("pid")
        if ev == "CLOSE":
            pnl[pid] = p.get("pnl_r")
            if p.get("fill_type") is not None:        # resolve() con cost -> NETO
                net = True
        elif ev == "MOTOR_OPEN_META":
            kz[pid] = p.get("killzone")
            regime_m[pid] = p.get("regime")
            if p.get("cvd_confirmed") is not None:    # solo si FQ_CVD_FILTER taggeo
                cvd_m[pid] = bool(p.get("cvd_confirmed"))
            if p.get("kl_low") is not None:           # solo si FQ_REGIME_TAGS taggeo
                kl_m[pid] = bool(p.get("kl_low"))
            if p.get("poc_dist") is not None:
                poc_m[pid] = float(p.get("poc_dist"))
            if p.get("funding_pctl") is not None:     # solo si FQ_REGIME_TAGS taggeo
                fund_m[pid] = float(p.get("funding_pctl"))
            if p.get("fill_type") is not None:        # modo EJECUCION maker
                ftype[pid] = p.get("fill_type")
        elif ev == "MAKER_FILL":
            maker[pid] = "FILL"
        elif ev == "MAKER_MISS":
            maker[pid] = "MISS"
        elif ev == "MAKER_RUNAWAY":                   # runner perdido (sin posicion)
            n_runaway += 1
        elif ev == "MOTOR_VETOED":
            k = p.get("killzone")
            vetoed[k] = vetoed.get(k, 0) + 1
    closed = {pid: r for pid, r in pnl.items() if r is not None}

    def _agg(rs):
        rs = [r for r in rs if r is not None]
        n = len(rs)
        if not n:
            return {"n": 0, "mean": None, "wr": None, "total": 0.0}
        return {"n": n, "mean": sum(rs) / n,
                "wr": sum(1 for r in rs if r > 0) / n, "total": sum(rs)}

    def _by_poc_split(closed_r, pm):
        vals = sorted(pm[p] for p in closed_r if p in pm)
        if len(vals) < 4:
            return {"far": _agg([]), "near": _agg([]), "n_tagged": len(pm)}
        med = vals[len(vals) // 2]
        far = [closed_r[p] for p in closed_r if pm.get(p) is not None and pm[p] >= med]
        near = [closed_r[p] for p in closed_r if pm.get(p) is not None and pm[p] < med]
        return {"far": _agg(far), "near": _agg(near),
                "thr": round(med, 3), "n_tagged": len(pm)}

    n_fill = sum(1 for v in maker.values() if v == "FILL")
    n_miss = sum(1 for v in maker.values() if v == "MISS")
    # Modo EJECUCION maker (FQ_EXEC_MODE=maker): fills reales vs fallback taker vs
    # runaway (el runner que el maker se perdio). El fill-rate REAL mete los
    # runaways en el denominador (son misses de verdad, no instrumentacion).
    n_mk = sum(1 for v in ftype.values() if v == "maker")
    n_tk = sum(1 for v in ftype.values() if v == "taker")
    exec_total = n_mk + n_tk + n_runaway
    return {
        "records": len(recs), "n_open_meta": len(kz), "n_closed": len(closed),
        "n_vetoed": sum(vetoed.values()), "vetoed_by_kz": vetoed, "net": net,
        "portfolio": _agg(list(closed.values())),
        "fill": _agg([closed[p] for p in closed if maker.get(p) == "FILL"]),
        "miss": _agg([closed[p] for p in closed if maker.get(p) == "MISS"]),
        "n_fill": n_fill, "n_miss": n_miss,
        "fill_rate": (n_fill / (n_fill + n_miss)) if (n_fill + n_miss) else None,
        "exec": bool(exec_total),
        "n_maker": n_mk, "n_taker": n_tk, "n_runaway": n_runaway,
        "exec_fill_rate": (n_mk / exec_total) if exec_total else None,
        "maker": _agg([closed[p] for p in closed if ftype.get(p) == "maker"]),
        "taker": _agg([closed[p] for p in closed if ftype.get(p) == "taker"]),
        # R FORWARD segmentado por regime (stable vs deriva): el juez de FQ_DERIVA_VETO=0.
        "by_regime": {rg: _agg([closed[p] for p in closed if regime_m.get(p) == rg])
                      for rg in sorted({r for r in regime_m.values() if r})},
        # R FORWARD por order-flow (CVD confirmado vs no): el juez de FQ_CVD_FILTER.
        # ¿el +0.1R de uplift del backtest 5y se replica EN VIVO? Vacio si filtro off.
        "by_cvd": {
            "confirmed": _agg([closed[p] for p in closed if cvd_m.get(p) is True]),
            "unconfirmed": _agg([closed[p] for p in closed if cvd_m.get(p) is False]),
            "n_tagged": len(cvd_m),
        },
        # R FORWARD por régimen KL (irrev-bajo = donde vive el edge, DSR ✓ cube).
        # Juez forward de FQ_REGIME_TAGS. Vacio si el tag off.
        "by_kl": {
            "low": _agg([closed[p] for p in closed if kl_m.get(p) is True]),
            "high": _agg([closed[p] for p in closed if kl_m.get(p) is False]),
            "n_tagged": len(kl_m),
        },
        # R FORWARD por POC-distance del día (developing): lejos vs cerca del POC.
        # El estricto (día previo, gateado) se mide offline con gate_poc_distance.py.
        "by_poc": _by_poc_split(closed, poc_m),
        # R FORWARD por FUNDING relativo (pctl 90d del propio símbolo). Juez forward del
        # funding-gate que PASÓ el gate in-cube (validate_long_gates: LONG & pctl<=0.5 ->
        # +0.173R vs +0.121, DSR 1.000/CPCV 80%/PBO 0.04). Umbral FIJO 0.5 = el validado.
        "by_funding": {
            "low": _agg([closed[p] for p in closed if fund_m.get(p) is not None and fund_m[p] <= 0.5]),
            "high": _agg([closed[p] for p in closed if fund_m.get(p) is not None and fund_m[p] > 0.5]),
            "n_tagged": len(fund_m),
        },
    }


def format_report_telegram(rep):
    """Resumen compacto del ledger motor paper para admin (HTML Telegram)."""
    if rep is None:
        return "📄 <b>Motor paper</b>: sin ledger aún (el archivo no existe)."
    if rep["n_closed"] == 0:
        return ("📄 <b>Motor paper</b>: {r} registros · {o} abiertas · "
                "{v} vetadas — aún SIN cierres. El motor dispara lento "
                "(~1-2/sem); cada fire entra aquí.").format(
                    r=rep["records"], o=rep["n_open_meta"], v=rep["n_vetoed"])
    p = rep["portfolio"]
    label = "NETO" if rep.get("net") else "GROSS"
    out = ["📄 <b>Motor paper (subset correcto §6.10.1)</b>",
           "cartera: n={n} · exp≈{m:+.3f}R {g} · WR {w:.0f}%".format(
               n=p["n"], m=p["mean"], w=p["wr"] * 100.0, g=label)]
    if rep.get("exec"):
        # EJECUCION maker: fill-rate REAL (runaways = miss) + maker vs fallback.
        out.append("ejecución maker: <b>{r:.0f}%</b> fill "
                   "(maker {nm} / fallback taker {nt} / runaway {nr})".format(
                       r=(rep["exec_fill_rate"] or 0.0) * 100.0, nm=rep["n_maker"],
                       nt=rep["n_taker"], nr=rep["n_runaway"]))
        mk, tk = rep["maker"], rep["taker"]
        if mk["n"] and tk["n"]:
            tag = "⚠ adverse selection" if mk["mean"] < tk["mean"] else "✓ sin adverse sel."
            out.append("MAKER exp≈{a:+.3f}R vs FALLBACK taker {b:+.3f}R — {t}".format(
                a=mk["mean"], b=tk["mean"], t=tag))
    elif rep["fill_rate"] is not None:
        f, m = rep["fill"], rep["miss"]
        out.append("fill-rate maker: <b>{r:.0f}%</b> (FILL {nf} / MISS {nm})".format(
            r=rep["fill_rate"] * 100.0, nf=rep["n_fill"], nm=rep["n_miss"]))
        if f["n"] and m["n"]:
            tag = "⚠ adverse selection" if f["mean"] < m["mean"] else "✓ sin adverse sel."
            out.append("FILLED exp≈{ff:+.3f}R vs MISSED {mm:+.3f}R — {t}".format(
                ff=f["mean"], mm=m["mean"], t=tag))
    by_reg = rep.get("by_regime") or {}
    closed_reg = {rg: a for rg, a in by_reg.items() if a["n"]}
    if closed_reg:
        seg = " · ".join("{rg} n={n} {m:+.3f}R WR{w:.0f}%".format(
            rg=rg, n=a["n"], m=a["mean"], w=a["wr"] * 100.0)
            for rg, a in sorted(closed_reg.items()))
        out.append("por regime: " + seg)
        if "deriva" in closed_reg and "stable" in closed_reg:
            dv, sv = closed_reg["deriva"]["mean"], closed_reg["stable"]["mean"]
            tag = "✓ deriva aguanta" if dv >= sv - 0.02 else "⚠ deriva ARRASTRA (revisar FQ_DERIVA_VETO)"
            out.append("  → {t}: deriva {d:+.3f}R vs stable {s:+.3f}R".format(t=tag, d=dv, s=sv))
    by_cvd = rep.get("by_cvd") or {}
    cf, un = by_cvd.get("confirmed") or {}, by_cvd.get("unconfirmed") or {}
    if cf.get("n") or un.get("n"):
        def _seg(a):
            return ("n={n} {m:+.3f}R WR{w:.0f}%".format(
                n=a["n"], m=a["mean"], w=a["wr"] * 100.0)) if a.get("n") else "n=0"
        out.append("order-flow CVD: confirmado %s · no-conf %s" % (_seg(cf), _seg(un)))
        if cf.get("n") and un.get("n"):
            upl = cf["mean"] - un["mean"]
            tag = "✓ replica uplift (DSR pendiente)" if upl >= 0.08 else "· aún sin separación"
            out.append("  → uplift {u:+.3f}R {t} — meta ≥30 conf para graduar".format(
                u=upl, t=tag))
    if rep["n_vetoed"]:
        out.append("vetadas: %d" % rep["n_vetoed"])
    out.append("<i>0% real · meta ≥30-50 fills para decidir (§6.10)</i>")
    return "\n".join(out)
