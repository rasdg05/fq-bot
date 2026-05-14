# -*- coding: utf-8 -*-
"""
================================================================================
  ICT/SMC MODULE - FQ v4.1.1 Refactor
  Deteccion estructural ICT/Smart Money Concepts para FieldState
  by RasDG_Sol + Claude
================================================================================

  Filosofia:
    Modulo INERTE. Solo detecta. No decide, no veta, no modifica flujo.
    read_field(df_15m, df_1h, df_4h, df_1m, masses, lap) -> FieldState

  Promueve sin duplicar:
    - market_context.detect_choch (ya existia, ahora alimenta gate)
    - market_context.detect_breakout
    - market_context.detect_rsi_divergence

  ASCII-only.
================================================================================
"""
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np

log = logging.getLogger("fq_ict_smc")

# Promociones desde market_context (ya existian, ahora se usan estructuralmente)
try:
    from market_context import detect_choch, detect_breakout, detect_rsi_divergence
except ImportError:
    detect_choch = lambda df, lookback=20: None
    detect_breakout = lambda df, period=20: None
    detect_rsi_divergence = lambda df, lookback=15: None

# ============================================================
# CONFIG
# ============================================================
PIVOT_STRENGTH        = 2          # velas a cada lado para confirmar pivot
LIQUIDITY_TOLERANCE   = 0.003      # 0.3% para considerar "equal high/low"
SWEEP_LOOKBACK        = 8          # velas para detectar sweep reciente
OB_LOOKBACK           = 30         # velas para buscar OB valido
OB_DISPLACEMENT_PCT   = 0.004      # 0.4% min de desplazamiento post-OB
FVG_LOOKBACK          = 20         # velas para buscar FVGs
CRT_LOOKBACK          = 15         # velas TF bajo para CRT

# Fib levels relativos al range
FIB_LEVELS_LONG  = [0.618, 0.705, 0.786]   # discount profundo para LONG
FIB_LEVELS_SHORT = [0.382, 0.295, 0.214]   # premium profundo para SHORT

# ============================================================
# DATACLASSES
# ============================================================
@dataclass
class PivotPoint:
    ts:       Any           # datetime o pd.Timestamp
    price:    float
    kind:     str           # "high" o "low"
    idx:      int           # indice en el df

@dataclass
class LiquidityPool:
    price:        float
    touches:      int
    swept:        bool
    swept_ts:     Optional[Any] = None
    reaction:     bool = False
    side:         str = "high"      # "high" o "low"

@dataclass
class OrderBlock:
    low:               float
    high:              float
    ts:                Any
    direction:         str          # "bullish" o "bearish"
    displacement_pct:  float
    still_valid:       bool = True
    mitigated_pct:     float = 0.0

@dataclass
class FVG:
    top:           float
    bottom:        float
    ts:            Any
    direction:     str       # "bullish" o "bearish"
    filled_pct:    float = 0.0

@dataclass
class CRTSignal:
    confirmed:       bool
    crt_type:        Optional[str] = None    # "bullish_crt" o "bearish_crt"
    range_high:      Optional[float] = None
    range_low:       Optional[float] = None
    sweep_side:      Optional[str] = None
    close_internal:  Optional[bool] = None

@dataclass
class BucketMemory:
    bucket_key:       str
    n_total:          int = 0
    n_closed:         int = 0
    win_rate:         float = 0.0
    expectancy_r:     float = 0.0
    profit_factor:    float = 0.0
    last_n_outcomes:  List[str] = field(default_factory=list)
    streak:           int = 0
    kappa_evo:        float = 1.0
    confidence:       str = "empty"     # empty | watch | active

# ============================================================
# FIELDSTATE - objeto central
# ============================================================
@dataclass
class FieldState:
    # METADATA
    ts:                Any = None
    price:             float = 0.0
    symbol:            str = "SOL/USDT"

    # FASE A: sesgo estructural + PD zone
    bias_4h:           str = "rango"
    bias_1h:           str = "rango"
    bias_15m:          str = "rango"
    bias_aligned:      bool = False
    score_4h:          int = 0
    score_1h:          int = 0
    range_low:         float = 0.0
    range_high:        float = 0.0
    equilibrium:       float = 0.0
    pd_pct:            float = 0.5
    pd_zone:           str = "equilibrium"
    last_mss:          Optional[Dict[str, Any]] = None
    last_bos:          Optional[Dict[str, Any]] = None
    choch:             Optional[Dict[str, Any]] = None
    swing_highs:       List[PivotPoint] = field(default_factory=list)
    swing_lows:        List[PivotPoint] = field(default_factory=list)

    # FASE B: liquidez
    pool_high:         Optional[LiquidityPool] = None
    pool_low:          Optional[LiquidityPool] = None
    recent_sweep:      Optional[Dict[str, Any]] = None
    has_fuel:          bool = False

    # FASE C: confluencia ICT
    order_blocks:      Dict[str, Optional[OrderBlock]] = field(
                           default_factory=lambda: {"bullish": None, "bearish": None})
    fvgs:              List[FVG] = field(default_factory=list)
    breaker:           Optional[OrderBlock] = None
    fib_levels:        Dict[str, float] = field(default_factory=dict)
    current_node:      Optional[float] = None
    confluence_list:   List[str] = field(default_factory=list)
    confluence_count:  int = 0
    node_type:         str = "superposicion"
    pd_hierarchy:      str = "nula"

    # FASE D: timing + CRT
    killzone:          str = "fuera"
    killzone_priority: str = "baja"
    w_killzone:        float = 0.60
    w_clock_legacy:    float = 0.50
    w_effective:       float = 0.50
    minutes_in_kz:     int = 0
    minutes_to_next_kz: int = 0
    crt:               Optional[CRTSignal] = None

    # MEMORIA DE OUTCOME (cierre del loop)
    bucket_memory:     Optional[BucketMemory] = None

    # DECOHERENCIA THETA(D) heredada
    theta_d:           Dict[str, Any] = field(default_factory=dict)

    # P-Space legacy
    pspace_count:      int = 0
    support_weight:    float = 0.0
    resistance_weight: float = 0.0

    # ─── METODOS DERIVADOS ─────────────────────────────

    def aligned_with_direction(self, direction):
        """Regla #6 reforzada con PD Arrays. Returns (bool, reason)."""
        if self.bias_4h == "rango":
            return False, "Bias 4H en rango — sin direccion estructural"
        if not self.bias_aligned:
            return False, "Bias desalineado: 4H={} 1H={}".format(self.bias_4h, self.bias_1h)
        if direction == "long" and "alcista" not in self.bias_4h:
            return False, "LONG contra sesgo 4H {}".format(self.bias_4h)
        if direction == "short" and "bajista" not in self.bias_4h:
            return False, "SHORT contra sesgo 4H {}".format(self.bias_4h)
        if direction == "long" and self.pd_zone != "discount":
            return False, "LONG en zona {} (requiere discount)".format(self.pd_zone)
        if direction == "short" and self.pd_zone != "premium":
            return False, "SHORT en zona {} (requiere premium)".format(self.pd_zone)
        return True, "Sesgo alineado + zona PD correcta"

    def confluence_factor(self):
        """f_confluence en [1.00, 1.35]"""
        hierarchy_weights = {
            "maxima":     1.35,
            "alta":       1.25,
            "media-alta": 1.15,
            "media":      1.08,
            "nula":       1.00,
        }
        base = hierarchy_weights.get(self.pd_hierarchy, 1.00)
        if self.confluence_count >= 5:
            base = min(1.35, base * 1.03)
        return base

    def is_actionable(self):
        """Sanity gate previo. Returns (evaluable, reason or None)."""
        if self.bias_4h == "rango":
            return False, "Mercado en rango macro 4H"
        if not self.has_fuel:
            return False, "Sin pools de liquidez identificables"
        if self.confluence_count < 3:
            return False, "Confluencia ICT insuficiente ({}/3)".format(self.confluence_count)
        return True, None

    def propose_direction(self):
        """Que direccion propone el campo? Returns 'long', 'short' o None."""
        if not self.bias_aligned:
            return None
        if "alcista" in self.bias_4h and self.pd_zone == "discount":
            return "long"
        if "bajista" in self.bias_4h and self.pd_zone == "premium":
            return "short"
        return None

    def bucket_key_v2(self, tier, direction):
        """Bucket dimensional v2: killzone × tier × dir × pd_zone × hierarchy"""
        return "{}|{}|{}|{}|{}".format(
            self.killzone, tier, direction, self.pd_zone, self.pd_hierarchy
        )

    def summary_line(self):
        crt_str = "Y" if (self.crt and self.crt.confirmed) else "N"
        return ("FIELD[{kz}|{p}] b4={b4} b1={b1} pd={pd}({pct:.0%}) "
                "conf={cf} hier={hi} fuel={fu} crt={crt}").format(
            kz=self.killzone, p=self.killzone_priority,
            b4=self.bias_4h, b1=self.bias_1h,
            pd=self.pd_zone, pct=self.pd_pct,
            cf=self.confluence_count, hi=self.pd_hierarchy,
            fu="Y" if self.has_fuel else "N", crt=crt_str)

    def to_dict(self):
        """Serializar para snapshots/ledger. Maneja dataclasses anidados."""
        def _conv(o):
            if hasattr(o, "__dataclass_fields__"):
                return {k: _conv(v) for k, v in asdict(o).items()}
            if isinstance(o, list):
                return [_conv(x) for x in o]
            if isinstance(o, dict):
                return {k: _conv(v) for k, v in o.items()}
            if isinstance(o, (datetime, pd.Timestamp)):
                return o.isoformat() if hasattr(o, "isoformat") else str(o)
            return o
        return _conv(self)

# ============================================================
# DETECCION DE PIVOTS
# ============================================================
def find_pivots(df, strength=PIVOT_STRENGTH, lookback=50):
    """Encuentra swing highs y lows en las ultimas N velas"""
    if len(df) < strength * 2 + 5:
        return [], []
    highs = df["high"].values
    lows = df["low"].values
    n = min(lookback, len(df) - strength)
    start = max(strength, len(df) - n)
    pivot_highs, pivot_lows = [], []
    for i in range(start, len(df) - strength):
        is_ph = all(highs[i] > highs[i-j] for j in range(1, strength+1)) and \
                all(highs[i] > highs[i+j] for j in range(1, strength+1))
        is_pl = all(lows[i] < lows[i-j] for j in range(1, strength+1)) and \
                all(lows[i] < lows[i+j] for j in range(1, strength+1))
        if is_ph:
            ts = df["timestamp"].iloc[i] if "timestamp" in df.columns else i
            pivot_highs.append(PivotPoint(ts=ts, price=float(highs[i]), kind="high", idx=i))
        if is_pl:
            ts = df["timestamp"].iloc[i] if "timestamp" in df.columns else i
            pivot_lows.append(PivotPoint(ts=ts, price=float(lows[i]), kind="low", idx=i))
    return pivot_highs, pivot_lows

# ============================================================
# SESGO ESTRUCTURAL MULTI-TF
# ============================================================
def detect_bias_for_tf(df):
    """Sesgo direccional usando momentum + posicion vs EMAs. Returns dict."""
    if df is None or len(df) < 20:
        return {"bias": "rango", "score": 0}
    last = df.iloc[-1]
    price = float(last["close"])
    closes = df["close"].iloc[-20:].values

    mom_5  = (closes[-1] - closes[-6]) / closes[-6] if len(closes) >= 6 else 0
    mom_20 = (closes[-1] - closes[0]) / closes[0] if len(closes) >= 20 else 0

    ema50 = last.get("ema50")
    ema200 = last.get("ema200")
    above_50 = ema50 is not None and not pd.isna(ema50) and price > float(ema50)
    above_200 = ema200 is not None and not pd.isna(ema200) and price > float(ema200)

    score = 0
    score += 1 if mom_5 > 0 else (-1 if mom_5 < 0 else 0)
    score += 1 if mom_20 > 0 else (-1 if mom_20 < 0 else 0)
    score += 1 if above_50 else -1
    score += 2 if above_200 else -2

    if score >= 3:    bias = "alcista"
    elif score >= 1:  bias = "alcista debil"
    elif score <= -3: bias = "bajista"
    elif score <= -1: bias = "bajista debil"
    else:             bias = "rango"
    return {"bias": bias, "score": score, "mom_5": mom_5*100, "mom_20": mom_20*100}

# ============================================================
# PD ZONES (Premium/Discount/Equilibrium)
# ============================================================
def detect_pd_zone(df, lookback=50):
    """Calcula rango operativo y posicion en PD"""
    if len(df) < lookback:
        lookback = len(df)
    high = float(df["high"].iloc[-lookback:].max())
    low  = float(df["low"].iloc[-lookback:].min())
    price = float(df["close"].iloc[-1])
    rng = high - low
    if rng <= 0:
        return {"range_high": high, "range_low": low, "equilibrium": (high+low)/2,
                "pd_pct": 0.5, "pd_zone": "equilibrium"}
    pd_pct = (price - low) / rng
    equilibrium = (high + low) / 2
    if pd_pct < 0.40:    zone = "discount"
    elif pd_pct > 0.60:  zone = "premium"
    else:                zone = "equilibrium"
    return {"range_high": high, "range_low": low, "equilibrium": equilibrium,
            "pd_pct": pd_pct, "pd_zone": zone}

# ============================================================
# LIQUIDITY POOLS + SWEEPS
# ============================================================
def detect_liquidity_pools(df, pivot_highs, pivot_lows, tolerance=LIQUIDITY_TOLERANCE):
    """Detecta equal highs/lows y sweeps recientes"""
    pool_high = pool_low = None
    if pivot_highs and len(pivot_highs) >= 2:
        recent = pivot_highs[-3:] if len(pivot_highs) >= 3 else pivot_highs[-2:]
        prices = [p.price for p in recent]
        max_p = max(prices)
        touches = sum(1 for p in prices if abs(p - max_p) / max_p <= tolerance)
        if touches >= 2:
            pool_high = LiquidityPool(price=max_p, touches=touches, swept=False,
                                       side="high")
    if pivot_lows and len(pivot_lows) >= 2:
        recent = pivot_lows[-3:] if len(pivot_lows) >= 3 else pivot_lows[-2:]
        prices = [p.price for p in recent]
        min_p = min(prices)
        touches = sum(1 for p in prices if abs(p - min_p) / min_p <= tolerance)
        if touches >= 2:
            pool_low = LiquidityPool(price=min_p, touches=touches, swept=False,
                                      side="low")

    # Detectar sweeps recientes
    recent_sweep = None
    if len(df) >= SWEEP_LOOKBACK + 2:
        recent_df = df.iloc[-SWEEP_LOOKBACK:]
        # Sweep high: high de vela rompe pool_high pero close vuelve abajo
        if pool_high:
            for i, row in recent_df.iterrows():
                hi = float(row["high"])
                cl = float(row["close"])
                if hi > pool_high.price and cl < pool_high.price:
                    pool_high.swept = True
                    pool_high.swept_ts = row.get("timestamp", i)
                    # Reaccion: precio sigue bajando en velas siguientes?
                    pos = recent_df.index.get_loc(i)
                    if pos < len(recent_df) - 2:
                        post = recent_df.iloc[pos+1:pos+3]
                        if len(post) > 0 and float(post["close"].iloc[-1]) < cl * 0.998:
                            pool_high.reaction = True
                            recent_sweep = {"direction": "high", "price": hi,
                                           "ts": pool_high.swept_ts, "reaction": True}
                    break
        if pool_low:
            for i, row in recent_df.iterrows():
                lo = float(row["low"])
                cl = float(row["close"])
                if lo < pool_low.price and cl > pool_low.price:
                    pool_low.swept = True
                    pool_low.swept_ts = row.get("timestamp", i)
                    pos = recent_df.index.get_loc(i)
                    if pos < len(recent_df) - 2:
                        post = recent_df.iloc[pos+1:pos+3]
                        if len(post) > 0 and float(post["close"].iloc[-1]) > cl * 1.002:
                            pool_low.reaction = True
                            recent_sweep = {"direction": "low", "price": lo,
                                           "ts": pool_low.swept_ts, "reaction": True}
                    break
    return pool_high, pool_low, recent_sweep

# ============================================================
# ORDER BLOCKS
# ============================================================
def detect_order_blocks(df, lookback=OB_LOOKBACK):
    """Detecta ultimo OB bullish y bearish validos"""
    if len(df) < lookback + 5:
        return {"bullish": None, "bearish": None}
    bullish_ob = bearish_ob = None
    end = len(df) - 2

    # Bullish OB: ultima vela ROJA antes de impulso alcista con desplazamiento
    for i in range(end, max(end - lookback, 1), -1):
        c0 = df.iloc[i]
        if float(c0["close"]) >= float(c0["open"]):
            continue
        # Buscar impulso alcista en velas siguientes (i+1, i+2, i+3)
        if i + 3 >= len(df):
            continue
        c3 = df.iloc[i+3]
        displacement = (float(c3["close"]) - float(c0["high"])) / float(c0["high"])
        if displacement >= OB_DISPLACEMENT_PCT:
            current_price = float(df["close"].iloc[-1])
            still_valid = current_price > float(c0["low"])
            mit_pct = max(0.0, min(1.0,
                (float(c0["high"]) - max(float(c0["low"]),
                 float(df["low"].iloc[i+1:].min()))) /
                (float(c0["high"]) - float(c0["low"]) + 1e-9)))
            ts = c0.get("timestamp", i) if hasattr(c0, "get") else i
            bullish_ob = OrderBlock(
                low=float(c0["low"]), high=float(c0["high"]), ts=ts,
                direction="bullish", displacement_pct=displacement*100,
                still_valid=still_valid, mitigated_pct=mit_pct
            )
            break

    # Bearish OB: ultima vela VERDE antes de impulso bajista
    for i in range(end, max(end - lookback, 1), -1):
        c0 = df.iloc[i]
        if float(c0["close"]) <= float(c0["open"]):
            continue
        if i + 3 >= len(df):
            continue
        c3 = df.iloc[i+3]
        displacement = (float(c0["low"]) - float(c3["close"])) / float(c0["low"])
        if displacement >= OB_DISPLACEMENT_PCT:
            current_price = float(df["close"].iloc[-1])
            still_valid = current_price < float(c0["high"])
            mit_pct = max(0.0, min(1.0,
                (min(float(c0["high"]),
                 float(df["high"].iloc[i+1:].max())) - float(c0["low"])) /
                (float(c0["high"]) - float(c0["low"]) + 1e-9)))
            ts = c0.get("timestamp", i) if hasattr(c0, "get") else i
            bearish_ob = OrderBlock(
                low=float(c0["low"]), high=float(c0["high"]), ts=ts,
                direction="bearish", displacement_pct=displacement*100,
                still_valid=still_valid, mitigated_pct=mit_pct
            )
            break
    return {"bullish": bullish_ob, "bearish": bearish_ob}

# ============================================================
# FAIR VALUE GAPS
# ============================================================
def detect_fvgs(df, lookback=FVG_LOOKBACK, max_return=5):
    """FVG: gap entre high de vela N-1 y low de vela N+1 (bullish)
       o low de N-1 y high de N+1 (bearish)"""
    if len(df) < 4:
        return []
    fvgs = []
    end = len(df) - 1
    start = max(2, end - lookback)
    current_price = float(df["close"].iloc[-1])
    for i in range(start, end):
        c_prev = df.iloc[i-1]
        c_curr = df.iloc[i]
        c_next = df.iloc[i+1] if i+1 < len(df) else None
        if c_next is None:
            continue
        # Bullish FVG: prev_high < next_low
        if float(c_prev["high"]) < float(c_next["low"]):
            top = float(c_next["low"])
            bottom = float(c_prev["high"])
            # filled_pct: cuanto del gap se ha rellenado por precio posterior
            post = df.iloc[i+1:]
            min_post = float(post["low"].min()) if len(post) > 0 else top
            filled = max(0.0, min(1.0, (top - min_post) / (top - bottom + 1e-9)))
            ts = c_curr.get("timestamp", i) if hasattr(c_curr, "get") else i
            fvgs.append(FVG(top=top, bottom=bottom, ts=ts,
                           direction="bullish", filled_pct=filled))
        # Bearish FVG: prev_low > next_high
        elif float(c_prev["low"]) > float(c_next["high"]):
            top = float(c_prev["low"])
            bottom = float(c_next["high"])
            post = df.iloc[i+1:]
            max_post = float(post["high"].max()) if len(post) > 0 else bottom
            filled = max(0.0, min(1.0, (max_post - bottom) / (top - bottom + 1e-9)))
            ts = c_curr.get("timestamp", i) if hasattr(c_curr, "get") else i
            fvgs.append(FVG(top=top, bottom=bottom, ts=ts,
                           direction="bearish", filled_pct=filled))
    # Devolver solo los no rellenados completamente
    open_fvgs = [f for f in fvgs if f.filled_pct < 0.5]
    return open_fvgs[-max_return:]

# ============================================================
# FIB LEVELS
# ============================================================
def compute_fib_levels(range_low, range_high):
    """Niveles Fibonacci sobre el rango actual"""
    rng = range_high - range_low
    if rng <= 0:
        return {}
    return {
        "0.236": range_low + rng * 0.236,
        "0.382": range_low + rng * 0.382,
        "0.500": range_low + rng * 0.500,
        "0.618": range_low + rng * 0.618,
        "0.705": range_low + rng * 0.705,
        "0.786": range_low + rng * 0.786,
    }

# ============================================================
# CRT (Candle Range Theory)
# ============================================================
def detect_crt(df, lookback=CRT_LOOKBACK):
    """CRT: vela de rango + sweep + close interno en TF bajo"""
    if df is None or len(df) < 3:
        return CRTSignal(confirmed=False)
    # Buscar en las ultimas 3 velas
    for offset in [1, 2]:
        if len(df) < offset + 2:
            continue
        idx = len(df) - 1 - offset
        if idx < 1:
            continue
        range_candle = df.iloc[idx - 1]
        sweep_candle = df.iloc[idx]
        rh = float(range_candle["high"])
        rl = float(range_candle["low"])
        sh = float(sweep_candle["high"])
        sl = float(sweep_candle["low"])
        sc = float(sweep_candle["close"])
        # Bullish CRT: sweep barre low del range, close vuelve dentro
        if sl < rl and rl <= sc <= rh:
            return CRTSignal(confirmed=True, crt_type="bullish_crt",
                            range_high=rh, range_low=rl,
                            sweep_side="low", close_internal=True)
        # Bearish CRT: sweep barre high, close vuelve dentro
        if sh > rh and rl <= sc <= rh:
            return CRTSignal(confirmed=True, crt_type="bearish_crt",
                            range_high=rh, range_low=rl,
                            sweep_side="high", close_internal=True)
    return CRTSignal(confirmed=False)

# ============================================================
# CONFLUENCIA + JERARQUIA PD
# ============================================================
def build_confluence(price, field, atr_proxy):
    """Construye lista de elementos ICT presentes en el nivel actual"""
    conf = []
    near = atr_proxy * 0.6  # 60% del ATR como zona "cercana"

    # Fib levels cercanos
    for label, lvl in field.fib_levels.items():
        if abs(price - lvl) <= near:
            conf.append("fib_" + label)

    # OB cercanos
    ob_bull = field.order_blocks.get("bullish")
    if ob_bull and ob_bull.still_valid:
        if ob_bull.low - near <= price <= ob_bull.high + near:
            conf.append("bullish_ob")
    ob_bear = field.order_blocks.get("bearish")
    if ob_bear and ob_bear.still_valid:
        if ob_bear.low - near <= price <= ob_bear.high + near:
            conf.append("bearish_ob")

    # FVGs cercanos no rellenados
    for fvg in field.fvgs:
        if fvg.filled_pct < 0.5:
            if fvg.bottom - near <= price <= fvg.top + near:
                conf.append("fvg_" + fvg.direction)
                break

    # Sweep reciente
    if field.recent_sweep and field.recent_sweep.get("reaction"):
        conf.append("recent_sweep_" + field.recent_sweep["direction"])

    # CHoCH presente
    if field.choch:
        conf.append("choch")

    # Zona PD correcta
    if field.pd_zone in ("discount", "premium"):
        conf.append("pd_" + field.pd_zone)

    return conf

def compute_pd_hierarchy(confluence_list, pd_zone):
    """Jerarquia segun Capa 3 spec"""
    if pd_zone == "equilibrium":
        return "nula"
    has_ob = any(c.endswith("_ob") for c in confluence_list)
    has_fvg = any(c.startswith("fvg_") for c in confluence_list)
    has_fib = any(c.startswith("fib_") for c in confluence_list)
    if has_ob and has_fvg and has_fib:
        return "maxima"
    if has_ob and has_fib:
        return "alta"
    if has_fvg and has_fib:
        return "media-alta"
    if has_fib:
        return "media"
    return "nula"

# ============================================================
# READ_FIELD - el agregador principal
# ============================================================
def read_field(df_15m, df_1h, df_4h, df_1m, masses, lap):
    """
    Construye el FieldState completo. UNICA funcion publica que el
    fusion_engine necesita llamar.
    """
    f = FieldState()
    if df_15m is None or len(df_15m) < 30:
        return f

    f.ts = datetime.now(timezone.utc)
    f.price = float(df_15m["close"].iloc[-1])

    # ATR proxy para zonas "cercanas"
    last = df_15m.iloc[-1]
    atr = last.get("atr14")
    atr_proxy = float(atr) if atr is not None and not pd.isna(atr) else f.price * 0.005

    # === FASE A: sesgo + PD ===
    bias_4h_data = detect_bias_for_tf(df_4h)
    bias_1h_data = detect_bias_for_tf(df_1h)
    bias_15m_data = detect_bias_for_tf(df_15m)
    f.bias_4h = bias_4h_data["bias"]
    f.bias_1h = bias_1h_data["bias"]
    f.bias_15m = bias_15m_data["bias"]
    f.score_4h = bias_4h_data["score"]
    f.score_1h = bias_1h_data["score"]
    f.bias_aligned = (
        ("alcista" in f.bias_4h and "alcista" in f.bias_1h) or
        ("bajista" in f.bias_4h and "bajista" in f.bias_1h)
    )

    pd_data = detect_pd_zone(df_15m)
    f.range_low = pd_data["range_low"]
    f.range_high = pd_data["range_high"]
    f.equilibrium = pd_data["equilibrium"]
    f.pd_pct = pd_data["pd_pct"]
    f.pd_zone = pd_data["pd_zone"]
    f.fib_levels = compute_fib_levels(f.range_low, f.range_high)

    # Pivots + CHoCH
    pivot_highs, pivot_lows = find_pivots(df_15m)
    f.swing_highs = pivot_highs
    f.swing_lows = pivot_lows
    f.choch = detect_choch(df_15m, lookback=20)

    # === FASE B: liquidez ===
    pool_h, pool_l, recent_sweep = detect_liquidity_pools(df_15m, pivot_highs, pivot_lows)
    f.pool_high = pool_h
    f.pool_low = pool_l
    f.recent_sweep = recent_sweep
    # has_fuel: hay pool identificado, swept o no, cercano
    nearby = atr_proxy * 4  # 4x ATR como "operable"
    f.has_fuel = False
    if pool_h and abs(pool_h.price - f.price) <= nearby:
        f.has_fuel = True
    if pool_l and abs(pool_l.price - f.price) <= nearby:
        f.has_fuel = True
    if recent_sweep:
        f.has_fuel = True

    # === FASE C: confluencia ICT ===
    f.order_blocks = detect_order_blocks(df_15m)
    f.fvgs = detect_fvgs(df_15m)
    # current_node: Fib level mas cercano
    if f.fib_levels:
        f.current_node = min(f.fib_levels.values(), key=lambda lvl: abs(lvl - f.price))
    f.confluence_list = build_confluence(f.price, f, atr_proxy)
    f.confluence_count = len(f.confluence_list)
    f.pd_hierarchy = compute_pd_hierarchy(f.confluence_list, f.pd_zone)
    f.node_type = "colapso" if f.confluence_count >= 3 else "superposicion"

    # === FASE D: CRT (killzone se llena en killzones_pd.py externo) ===
    f.crt = detect_crt(df_1m if df_1m is not None and len(df_1m) >= 5 else df_15m)

    # === P-Space legacy data ===
    if masses:
        f.pspace_count = masses.get("count", 0)
        f.support_weight = masses.get("support_weight", 0.0)
        f.resistance_weight = masses.get("resistance_weight", 0.0)

    return f
