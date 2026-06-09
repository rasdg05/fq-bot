# -*- coding: utf-8 -*-
"""
================================================================================
  EXECUTION - capa de ejecución en PAPEL + gobernador de riesgo
  by RasDG_Sol + Claude

  El puente disciplinado del research al capital. Empieza en 0% real: ejecuta
  contra precios reales SIN órdenes reales, acumula un track record forward
  sellado, y solo se sube el tamaño cuando el reconciliador (bt_forward) sigue
  verde. Agnóstico al bróker: el PaperBroker imita la interfaz que luego tendrá
  el adapter live (sub-cuentas de exchange vía ccxt).

  Piezas (puras, sin red — testeables directo):
    · RiskGovernor : el cerebro de seguridad. Decide tamaño aprobado o RECHAZA
      por: riesgo/trade, pérdida diaria (regla de DD), nº de posiciones, riesgo
      total abierto, y kill-switch global. Arranca con porcentajes BAJOS.
    · Account      : equity, pico, PnL del día, posiciones abiertas.
    · HashLedger   : registro append-only con cadena SHA-256 (commit-then-reveal):
      cada orden se sella ANTES de conocer el desenlace -> imposible editar el
      historial sin romper la cadena. Es la base del proof of work auditable.
    · PaperBroker  : abre/resuelve posiciones, calcula PnL en R y en quote.
    · fan_out      : reparte UNA señal a varias cuentas encadenadas, cada una
      pasando por su gobernador (con tope de cuentas correlacionadas).
================================================================================
"""
import os
import json
import hashlib
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional

log = logging.getLogger("execution")

LONG, SHORT = 1, -1


# ============================================================
# ESTADO
# ============================================================
@dataclass
class Position:
    account_id: str
    symbol: str
    direction: int          # LONG(+1) / SHORT(-1)
    entry: float
    stop: float
    tp: float
    size: float             # unidades del subyacente
    risk_frac: float        # fracción del equity arriesgada al stop
    pid: int = 0

    @property
    def risk_dist(self):
        return abs(self.entry - self.stop)


@dataclass
class Account:
    account_id: str
    equity: float
    day_start_equity: float = None
    peak_equity: float = None
    open: list = field(default_factory=list)

    def __post_init__(self):
        if self.day_start_equity is None:
            self.day_start_equity = self.equity
        if self.peak_equity is None:
            self.peak_equity = self.equity

    def open_risk_frac(self):
        return sum(p.risk_frac for p in self.open)

    def day_pnl_frac(self):
        return (self.equity - self.day_start_equity) / self.day_start_equity

    def drawdown_frac(self):
        return (self.peak_equity - self.equity) / self.peak_equity

    def start_new_day(self):
        self.day_start_equity = self.equity


# ============================================================
# GOBERNADOR DE RIESGO
# ============================================================
@dataclass
class GovernorConfig:
    max_risk_frac: float = 0.0025        # 0.25% por trade (arranque bajo)
    max_daily_loss_frac: float = 0.04    # corta el día al -4% (regla de DD)
    max_open_positions: int = 3
    max_total_risk_frac: float = 0.02    # riesgo simultáneo total
    kill_switch: bool = False            # freno global (drift/DD/manual)


class RiskGovernor:
    """Decide, por cuenta, si una señal pasa y con cuánto riesgo. NUNCA sube por
    encima de los topes; ante la duda, rechaza. Es el componente que hace seguro
    encadenar cuentas y subir el tamaño de forma gradual."""

    def __init__(self, config=None):
        self.cfg = config or GovernorConfig()

    def decide(self, account: Account, requested_risk: float = None):
        c = self.cfg
        if c.kill_switch:
            return {"approved": False, "risk_frac": 0.0, "reason": "kill-switch activo"}
        if account.day_pnl_frac() <= -c.max_daily_loss_frac:
            return {"approved": False, "risk_frac": 0.0,
                    "reason": f"pérdida diaria {account.day_pnl_frac():.2%} <= -{c.max_daily_loss_frac:.0%}"}
        if len(account.open) >= c.max_open_positions:
            return {"approved": False, "risk_frac": 0.0,
                    "reason": f"máx posiciones abiertas ({c.max_open_positions})"}
        risk = c.max_risk_frac if requested_risk is None else min(requested_risk, c.max_risk_frac)
        room = c.max_total_risk_frac - account.open_risk_frac()
        if room <= 0:
            return {"approved": False, "risk_frac": 0.0,
                    "reason": f"riesgo total {account.open_risk_frac():.2%} en el tope"}
        risk = min(risk, room)
        if risk <= 0:
            return {"approved": False, "risk_frac": 0.0, "reason": "riesgo resultante 0"}
        return {"approved": True, "risk_frac": float(risk), "reason": "ok"}


# ============================================================
# LEDGER SELLADO (commit-then-reveal)
# ============================================================
class HashLedger:
    """Registro append-only con cadena SHA-256. Cada entrada sella prev_hash +
    su contenido. Sellar la ORDEN al abrir (antes del desenlace) = pre-registro:
    no se puede reescribir el historial sin romper la cadena. verify() lo prueba.
    """
    def __init__(self):
        self.records = []

    def _hash(self, prev, payload):
        blob = json.dumps({"prev": prev, "payload": payload}, sort_keys=True,
                          default=str).encode()
        return hashlib.sha256(blob).hexdigest()

    def append(self, payload: dict):
        prev = self.records[-1]["hash"] if self.records else "genesis"
        h = self._hash(prev, payload)
        rec = {"seq": len(self.records), "prev": prev, "hash": h, "payload": payload}
        self.records.append(rec)
        return rec

    def verify(self):
        """True si la cadena es íntegra (nadie editó una entrada pasada)."""
        prev = "genesis"
        for rec in self.records:
            if rec["prev"] != prev or rec["hash"] != self._hash(prev, rec["payload"]):
                return False
            prev = rec["hash"]
        return True


class DurableHashLedger(HashLedger):
    """HashLedger con respaldo append-only en disco (JSONL). El track record
    forward es el PRODUCTO de la fase paper: en RAM se evapora en cada restart
    del contenedor. Aquí cada append se vuelca como una línea JSON; load() rehidrata
    y verifica la cadena -> sobrevive a reinicios. Sigue siendo stdlib/testeable.
    """

    def __init__(self, path):
        super().__init__()
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)

    def append(self, payload: dict):
        rec = super().append(payload)
        with open(self.path, "a") as fh:
            fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
        return rec

    @classmethod
    def load(cls, path):
        """Rehidrata desde el JSONL (si existe) y verifica la cadena. Lanza si
        está corrupta (manipulación o escritura parcial)."""
        obj = cls(path)
        if os.path.exists(path):
            recs = []
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        recs.append(json.loads(line))
            obj.records = recs
            if recs and not obj.verify():
                raise ValueError("cadena del ledger durable corrupta al cargar")
        return obj


# ============================================================
# BROKER EN PAPEL
# ============================================================
class PaperBroker:
    """Ejecuta en papel: imita la interfaz del adapter live pero sin red ni
    capital. Calcula sizing desde el riesgo aprobado, sella la orden al abrir y
    realiza PnL en R y en quote al resolver."""

    def __init__(self, ledger: HashLedger = None):
        self.ledger = ledger or HashLedger()
        self._pid = 0

    def open(self, account: Account, signal: dict, risk_frac: float, ts=None):
        entry, stop = float(signal["entry"]), float(signal["stop"])
        rdist = abs(entry - stop)
        if rdist <= 0:
            raise ValueError("riesgo nulo (entry == stop)")
        size = account.equity * risk_frac / rdist
        self._pid += 1
        pos = Position(account_id=account.account_id, symbol=signal["symbol"],
                       direction=int(signal["direction"]), entry=entry, stop=stop,
                       tp=float(signal["tp"]), size=size, risk_frac=risk_frac, pid=self._pid)
        account.open.append(pos)
        # SELLA la orden ANTES de conocer el desenlace (proof of work).
        self.ledger.append({"event": "OPEN", "ts": ts, "account": account.account_id,
                            "pid": pos.pid, "symbol": pos.symbol, "direction": pos.direction,
                            "entry": entry, "stop": stop, "tp": pos.tp,
                            "risk_frac": risk_frac, "size": size,
                            "equity_at_open": account.equity})
        return pos

    def resolve(self, account: Account, pos: Position, exit_price: float,
                reason: str = "manual", ts=None):
        pnl_quote = pos.direction * (exit_price - pos.entry) * pos.size
        pnl_r = pos.direction * (exit_price - pos.entry) / pos.risk_dist
        account.equity += pnl_quote
        account.peak_equity = max(account.peak_equity, account.equity)
        if pos in account.open:
            account.open.remove(pos)
        self.ledger.append({"event": "CLOSE", "ts": ts, "account": account.account_id,
                            "pid": pos.pid, "exit": float(exit_price), "reason": reason,
                            "pnl_quote": pnl_quote, "pnl_r": pnl_r,
                            "equity_after": account.equity})
        return {"pnl_quote": pnl_quote, "pnl_r": pnl_r, "reason": reason}

    def resolve_on_bar(self, account: Account, pos: Position, high: float,
                       low: float, pessimistic: bool = True, ts=None):
        """Resuelve contra una vela: si toca TP y/o SL. Empate intra-vela ->
        pesimista (stop primero), igual que el etiquetado de research."""
        if pos.direction == LONG:
            hit_tp, hit_sl = high >= pos.tp, low <= pos.stop
        else:
            hit_tp, hit_sl = low <= pos.tp, high >= pos.stop
        if hit_sl and (pessimistic or not hit_tp):
            return self.resolve(account, pos, pos.stop, "stop", ts)
        if hit_tp:
            return self.resolve(account, pos, pos.tp, "tp", ts)
        return None


# ============================================================
# FAN-OUT A CUENTAS ENCADENADAS
# ============================================================
def fan_out(signal: dict, accounts, governor: RiskGovernor, broker: PaperBroker,
            max_correlated: int = None, requested_risk: float = None, ts=None):
    """Reparte UNA señal a varias cuentas, cada una pasando por su gobernador.
    max_correlated acota cuántas cuentas pueden tomar la MISMA (symbol,dirección)
    a la vez (control de correlación al encadenar). Devuelve lista de resultados.
    """
    results = []
    taken = 0
    for acc in accounts:
        if max_correlated is not None and taken >= max_correlated:
            results.append({"account": acc.account_id, "approved": False,
                            "reason": f"tope de correlación ({max_correlated})"})
            continue
        d = governor.decide(acc, requested_risk=requested_risk)
        if not d["approved"]:
            results.append({"account": acc.account_id, "approved": False, "reason": d["reason"]})
            continue
        pos = broker.open(acc, signal, d["risk_frac"], ts=ts)
        taken += 1
        results.append({"account": acc.account_id, "approved": True,
                        "risk_frac": d["risk_frac"], "pid": pos.pid})
    return results
