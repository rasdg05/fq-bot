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
import sqlite3
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
    entry_fill_type: str = None   # 'maker'|'taker' por-trade (lo fija el ejecutor
                                  # maker); None -> _settle usa el flag global del
                                  # cost model. No afecta el sizing.

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
            fh.flush()
            os.fsync(fh.fileno())          # durabilidad: la línea queda EN DISCO antes de volver
        return rec

    def _rewrite_atomic(self):
        """Reescribe el JSONL saneado desde self.records, atómico (tmp + os.replace),
        mismo patrón crash-safe que los fetchers. Usado para limpiar una cola rota."""
        tmp = self.path + ".tmp"
        with open(tmp, "w") as fh:
            for rec in self.records:
                fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    @classmethod
    def load(cls, path):
        """Rehidrata desde el JSONL y verifica la cadena. SANA un torn-write de la
        ÚLTIMA línea (JSON parcial de un crash a media escritura → se descarta y se
        reescribe atómico), pero LANZA ante manipulación del pasado (cadena rota =
        tamper-evidente). Antes brickeaba el ledger ante cualquier línea parcial."""
        obj = cls(path)
        if not os.path.exists(path):
            return obj
        with open(path) as fh:
            lines = [ln.strip() for ln in fh.readlines()]
        idxs = [i for i, s in enumerate(lines) if s]
        recs = []
        healed_tail = False
        for k, i in enumerate(idxs):
            try:
                recs.append(json.loads(lines[i]))
            except ValueError:                     # JSONDecodeError ⊂ ValueError
                if k == len(idxs) - 1:             # inválida en la ÚLTIMA línea -> torn write
                    healed_tail = True
                    break
                raise ValueError("ledger durable corrupto: línea inválida no-terminal #%d" % i)
        obj.records = recs
        if recs and not obj.verify():
            raise ValueError("cadena del ledger durable corrupta al cargar")
        if healed_tail:                            # quita la cola rota del archivo (atómico)
            obj._rewrite_atomic()
        return obj


# ============================================================
# LEDGER SQLITE MULTI-SÍMBOLO (consolidación)
# ============================================================
class SqliteHashLedger(HashLedger):
    """HashLedger persistido en SQLite multi-símbolo: UN archivo para TODOS los
    símbolos (consultable, 1 backup), preservando la cadena SHA-256 en columnas
    prev/hash. Reemplaza el JSONL-por-símbolo -> registro forward unificado y base
    del cerebro. MISMA interfaz (.records / append / verify) -> reconciler y
    ledger_report no cambian. Reversible: el bot solo lo usa con FQ_LEDGER_SQLITE=1.
    """

    def __init__(self, db_path, symbol):
        super().__init__()
        self.db_path = db_path
        self.symbol = symbol
        d = os.path.dirname(db_path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL")     # lectores concurrentes (backup/cerebro)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS motor_ledger ("
            "symbol TEXT NOT NULL, seq INTEGER NOT NULL, prev TEXT NOT NULL, "
            "hash TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(symbol, seq))")
        self._conn.commit()

    def append(self, payload: dict):
        rec = super().append(payload)                     # encadena en RAM (self.records[-1])
        self._conn.execute(
            "INSERT INTO motor_ledger(symbol, seq, prev, hash, payload) VALUES (?,?,?,?,?)",
            (self.symbol, rec["seq"], rec["prev"], rec["hash"],
             json.dumps(rec["payload"], sort_keys=True, default=str)))
        self._conn.commit()                               # commit = durable (journal/WAL)
        return rec

    @classmethod
    def load(cls, db_path, symbol):
        """Rehidrata la cadena de UN símbolo desde la tabla y la verifica (LANZA si
        está manipulada). Las filas SQLite son atómicas -> no hay torn-write que sanar."""
        obj = cls(db_path, symbol)
        cur = obj._conn.execute(
            "SELECT seq, prev, hash, payload FROM motor_ledger WHERE symbol=? ORDER BY seq",
            (symbol,))
        obj.records = [{"seq": s, "prev": p, "hash": h, "payload": json.loads(pl)}
                       for (s, p, h, pl) in cur.fetchall()]
        if obj.records and not obj.verify():
            raise ValueError("cadena del ledger SQLite corrupta (symbol=%s)" % symbol)
        return obj


def _motor_db_path(jsonl_path):
    """Ruta del SQLite multi-símbolo: FQ_MOTOR_DB, o fq_motor.db junto al JSONL."""
    return os.environ.get("FQ_MOTOR_DB") or os.path.join(
        os.path.dirname(jsonl_path) or "/data", "fq_motor.db")


def _symbol_from_jsonl(jsonl_path):
    """motor_paper_BTC_USDT.jsonl -> 'BTC/USDT' (el 1er '_' vuelve a ser '/')."""
    base = os.path.basename(jsonl_path)
    if base.startswith("motor_paper_") and base.endswith(".jsonl"):
        base = base[len("motor_paper_"):-len(".jsonl")]
    return base.replace("_", "/", 1)


def open_motor_ledger(jsonl_path, symbol):
    """Ledger del motor (CARGADO) según FQ_LEDGER_SQLITE: SQLite multi-símbolo (1
    archivo, consultable) o el JSONL legacy por símbolo. Reversible (default OFF=JSONL,
    byte-idéntico al comportamiento previo). AUTO-MIGRA one-time: si el SQLite está vacío
    para el símbolo pero existe su JSONL, importa la historia al cargar -> el corte es
    un solo flag, sin riesgo de arrancar con el store vacío."""
    if os.environ.get("FQ_LEDGER_SQLITE", "0").strip() in ("1", "true", "yes"):
        led = SqliteHashLedger.load(_motor_db_path(jsonl_path), symbol)
        if not led.records and jsonl_path and os.path.exists(jsonl_path):
            src = DurableHashLedger.load(jsonl_path)      # cadena verificada
            for rec in src.records:
                led.append(rec["payload"])               # re-aplica payloads -> cadena idéntica
            if src.records:
                log.info("[ledger] auto-migrado %s: %d filas JSONL -> SQLite", symbol, len(led.records))
        return led
    return DurableHashLedger.load(jsonl_path)


# ============================================================
# BROKER EN PAPEL
# ============================================================
class PaperBroker:
    """Ejecuta en papel: imita la interfaz del adapter live pero sin red ni
    capital. Calcula sizing desde el riesgo aprobado, sella la orden al abrir y
    realiza PnL en R y en quote al resolver."""

    def __init__(self, ledger: HashLedger = None, cost=None):
        self.ledger = ledger or HashLedger()
        self._pid = 0
        # Modelo de costes OPCIONAL (duck-typed: maker_entry, maker_tp_exit,
        # slippage_frac, taker_fee, maker_fee -> p.ej. bt_engine.CostModel).
        #   None  -> PnL BRUTO (comportamiento historico, sin costos).
        #   set   -> resolve() resta fees + slippage por lado => el ledger forward
        #            mide NETO. Es el cimiento honesto del track record y la base
        #            del A/B taker-vs-maker (FQ_EXEC_MODE). Funding: commit 2.
        self.cost = cost

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
        exit_price = float(exit_price)
        pnl_quote, fees_quote, fill_type = self._settle(pos, exit_price, reason)
        # R-multiple NETO: PnL en quote / riesgo en quote (size * dist al stop).
        # Con cost=None es identico al bruto historico (size se cancela).
        risk_quote = pos.size * pos.risk_dist
        pnl_r = pnl_quote / risk_quote if risk_quote else 0.0
        account.equity += pnl_quote
        account.peak_equity = max(account.peak_equity, account.equity)
        if pos in account.open:
            account.open.remove(pos)
        close = {"event": "CLOSE", "ts": ts, "account": account.account_id,
                 "pid": pos.pid, "exit": exit_price, "reason": reason,
                 "pnl_quote": pnl_quote, "pnl_r": pnl_r,
                 "equity_after": account.equity}
        if self.cost is not None:
            close["fees_quote"] = fees_quote
            close["fill_type"] = fill_type     # pierna de ENTRADA: 'maker'|'taker'
        self.ledger.append(close)
        return {"pnl_quote": pnl_quote, "pnl_r": pnl_r, "reason": reason}

    def _settle(self, pos: Position, exit_price: float, reason: str):
        """PnL en quote tras costes. Replica EXACTO el modelo de bt_engine.simulate
        (fuente de verdad: bt_engine.py:161-186): slippage adverso por lado + fee
        taker/maker por lado sobre el notional. Las piernas maker no pagan slippage
        (pones el precio); el STOP y el timeout cruzan el book -> taker. El TP es
        maker solo si maker_tp_exit y la salida fue por target. Sin cost model ->
        PnL BRUTO (compat). Funding (dependiente del hold): commit 2.
        Devuelve (pnl_quote, fees_quote, fill_type_entrada).
        """
        c = self.cost
        if c is None:
            return pos.direction * (exit_price - pos.entry) * pos.size, 0.0, "taker"
        d = pos.direction
        # Tipo de fill de la ENTRADA: lo fija el ejecutor maker por-trade
        # (pos.entry_fill_type: 'maker' si la limite penetro, 'taker' si fallback a
        # mercado). Si no se fijo (modo taker puro / construccion directa) -> flag
        # global del cost model.
        ft = pos.entry_fill_type
        entry_maker = (ft == "maker") if ft is not None \
            else bool(getattr(c, "maker_entry", False))
        exit_maker = bool(getattr(c, "maker_tp_exit", False)) and reason == "tp"
        eff_entry = pos.entry if entry_maker else pos.entry * (1 + d * c.slippage_frac)
        eff_exit = exit_price if exit_maker else exit_price * (1 - d * c.slippage_frac)
        gross = d * (eff_exit - eff_entry) * pos.size
        fees = ((c.maker_fee if entry_maker else c.taker_fee) * pos.size * pos.entry
                + (c.maker_fee if exit_maker else c.taker_fee) * pos.size * exit_price)
        return gross - fees, fees, ("maker" if entry_maker else "taker")

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
