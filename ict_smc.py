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

    # === FASE E: conceptos ICT v3 (PDF "14 Most Important ICT Concepts") ===
    mss:               Optional[Any] = None    # MSSEvent
    inducement:        Optional[Any] = None    # Inducement
    power_of_3:        Optional[Any] = None    # PowerOf3
    bpr:               Optional[Any] = None    # BalancedPriceRange
    displacement:      Optional[Any] = None    # Displacement
    ote_zone:          Optional[Any] = None    # OTEZone

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

    # === FASE E: conceptos ICT v3 (PDF "14 ICT Concepts") ===
    direction_hint = f.propose_direction()
    f.breaker      = detect_breaker_block(df_15m, f.order_blocks)
    f.mss          = detect_mss(df_15m, pivot_highs, pivot_lows)
    f.last_mss     = f.mss  # alias para backcompat con FieldState legacy
    f.inducement   = detect_inducement(df_15m, pivot_highs, pivot_lows, direction_hint)
    f.power_of_3   = detect_power_of_3(df_15m, df_1h)
    f.bpr          = detect_balanced_price_range(df_15m, f.fvgs)
    f.displacement = detect_displacement(df_15m)
    f.ote_zone     = compute_ote_zone(df_15m, direction_hint, pivot_highs, pivot_lows)

    return f

# ============================================================
# CONCEPTOS ICT v3 - PDF "14 Most Important ICT Concepts"
# Cada detector es INERTE - devuelve dict/dataclass con info
# fusion_engine.py decide si usar o no segun config y direccion
# ============================================================

@dataclass
class BreakerBlock:
    """OB fallido que se convierte en zona contraria operable"""
    low:           float
    high:          float
    ts:            Any
    origin_dir:    str          # bullish_failed o bearish_failed
    new_dir:       str          # direccion contraria (la operable)
    confirmed:     bool = False
    mss_after:     bool = False

@dataclass
class MSSEvent:
    """Market Structure Shift - reverso ANTES de break of structure"""
    confirmed:     bool
    ts:            Any = None
    price:         float = 0.0
    direction:     Optional[str] = None    # bullish_mss o bearish_mss
    extreme_swept: bool = False             # rompio extremo demand/supply zone?

@dataclass
class Inducement:
    """Mini pullback que forma liquidez LTF antes del impulso real"""
    detected:      bool
    side:          Optional[str] = None      # 'high' o 'low' (donde se forma)
    price:         float = 0.0
    ts:            Any = None
    swept:         bool = False

@dataclass
class PowerOf3:
    """AMD: Accumulation / Manipulation / Distribution"""
    detected:      bool
    phase:         Optional[str] = None      # 'accumulation','manipulation','distribution'
    range_high:    Optional[float] = None
    range_low:     Optional[float] = None
    sweep_side:    Optional[str] = None      # 'high' o 'low'
    confirmed:     bool = False

@dataclass
class BalancedPriceRange:
    """Double FVG zone - imán de precio"""
    detected:      bool
    upper_fvg:     Optional[FVG] = None
    lower_fvg:     Optional[FVG] = None
    midpoint:      Optional[float] = None

@dataclass
class Displacement:
    """Movimiento direccional decisivo - body grande, wicks chicos"""
    detected:      bool
    direction:     Optional[str] = None      # bullish o bearish
    magnitude_pct: float = 0.0
    velocity:      float = 0.0               # candles for the move

@dataclass
class OTEZone:
    """Optimal Trade Entry: 62-79% retracement con 70.5% como sweet spot"""
    valid:         bool
    direction:     Optional[str] = None
    swing_high:    Optional[float] = None
    swing_low:     Optional[float] = None
    ote_lower:     Optional[float] = None    # 62%
    ote_sweet:     Optional[float] = None    # 70.5%
    ote_upper:     Optional[float] = None    # 79%
    in_zone:       bool = False
    distance_to_sweet_pct: float = 0.0       # 0 = en el sweet spot

# ----------------------------------------------------------------------
# 1. BREAKER BLOCK
#    Definicion ICT: un OB fallido (precio rompe su zona contraria al
#    impulso original), cuando precio retorna a esa zona, actua como
#    soporte/resistencia inverso.
# ----------------------------------------------------------------------
def detect_breaker_block(df, order_blocks):
    """
    Detecta breaker blocks. Devuelve BreakerBlock o None.
    OB bullish que rompe su low -> breaker bearish (resistencia)
    OB bearish que rompe su high -> breaker bullish (soporte)
    """
    if len(df) < 5:
        return None
    bull_ob = order_blocks.get("bullish")
    bear_ob = order_blocks.get("bearish")
    current_price = float(df["close"].iloc[-1])
    last_lows = df["low"].iloc[-5:].values
    last_highs = df["high"].iloc[-5:].values

    # Bullish OB fallido (precio rompio su low) -> breaker bearish
    if bull_ob and not bull_ob.still_valid:
        # Cerro debajo del low
        if min(last_lows) < bull_ob.low:
            return BreakerBlock(
                low=bull_ob.low, high=bull_ob.high, ts=bull_ob.ts,
                origin_dir="bullish_failed", new_dir="bearish",
                confirmed=current_price < bull_ob.high
            )
    # Bearish OB fallido (precio rompio su high) -> breaker bullish
    if bear_ob and not bear_ob.still_valid:
        if max(last_highs) > bear_ob.high:
            return BreakerBlock(
                low=bear_ob.low, high=bear_ob.high, ts=bear_ob.ts,
                origin_dir="bearish_failed", new_dir="bullish",
                confirmed=current_price > bear_ob.low
            )
    return None

# ----------------------------------------------------------------------
# 2. MSS (Market Structure Shift)
#    Definicion: reverso de la flow de ordenes ANTES de break of structure.
#    Bullish MSS: en tendencia bajista, precio sube por encima del ultimo
#    swing high relevante PERO sin haber roto previamente la estructura.
# ----------------------------------------------------------------------
def detect_mss(df, pivot_highs, pivot_lows, lookback=12):
    """MSS distinto a BOS: cambio de caracter sin estructura completa rota"""
    if len(df) < lookback or not pivot_highs or not pivot_lows:
        return MSSEvent(confirmed=False)
    recent_df = df.iloc[-lookback:]
    current_price = float(df["close"].iloc[-1])

    # Bullish MSS: tomar ultimo pivot high reciente, ver si lo superamos
    # PERO sin haber tenido un higher_low previamente
    recent_phs = [p for p in pivot_highs if p.idx >= len(df) - lookback - 5]
    recent_pls = [p for p in pivot_lows  if p.idx >= len(df) - lookback - 5]

    if recent_phs and recent_pls:
        last_ph = recent_phs[-1]
        last_pl = recent_pls[-1]
        # Si todos los lows recientes son LL (bearish bias) y precio rompe last_ph
        bearish_bias = all(
            pl.price < recent_pls[i].price
            for i, pl in enumerate(recent_pls[1:], 1)
        ) if len(recent_pls) >= 2 else False
        if bearish_bias and current_price > last_ph.price:
            return MSSEvent(
                confirmed=True, ts=df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                price=current_price, direction="bullish_mss",
                extreme_swept=last_pl.idx >= len(df) - 5
            )
        # Bullish bias -> bearish MSS
        bullish_bias = all(
            ph.price > recent_phs[i].price
            for i, ph in enumerate(recent_phs[1:], 1)
        ) if len(recent_phs) >= 2 else False
        if bullish_bias and current_price < last_pl.price:
            return MSSEvent(
                confirmed=True, ts=df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                price=current_price, direction="bearish_mss",
                extreme_swept=last_ph.idx >= len(df) - 5
            )
    return MSSEvent(confirmed=False)

# ----------------------------------------------------------------------
# 3. INDUCEMENT
#    Definicion: mini pullback dentro de un impulso mayor que forma
#    liquidez (highs/lows) en LTF, esperando ser barrido antes del
#    movimiento principal.
# ----------------------------------------------------------------------
def detect_inducement(df, pivot_highs, pivot_lows, direction_hint, lookback=10):
    """
    Inducement: highs/lows menores dentro del pullback.
    En tendencia long, busca un mini-high SUB-IMPULSO formando liquidez arriba.
    En tendencia short, busca un mini-low formando liquidez abajo.
    """
    if direction_hint not in ("long", "short") or len(df) < lookback:
        return Inducement(detected=False)
    recent_df = df.iloc[-lookback:]
    current_price = float(df["close"].iloc[-1])

    if direction_hint == "long":
        # Busca highs LOCALES (no extremos) entre la accion reciente
        mini_high = float(recent_df["high"].iloc[:-2].max()) if len(recent_df) >= 3 else None
        if mini_high and mini_high > current_price * 1.001:
            # Que NO sea el high absoluto (eso seria un BSL real, no inducement)
            absolute_high = float(df["high"].iloc[-50:].max()) if len(df) >= 50 else mini_high
            if mini_high < absolute_high * 0.997:
                swept = float(recent_df["high"].iloc[-2:].max()) > mini_high
                return Inducement(
                    detected=True, side="high", price=mini_high,
                    ts=recent_df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                    swept=swept
                )
    else:  # short
        mini_low = float(recent_df["low"].iloc[:-2].min()) if len(recent_df) >= 3 else None
        if mini_low and mini_low < current_price * 0.999:
            absolute_low = float(df["low"].iloc[-50:].min()) if len(df) >= 50 else mini_low
            if mini_low > absolute_low * 1.003:
                swept = float(recent_df["low"].iloc[-2:].min()) < mini_low
                return Inducement(
                    detected=True, side="low", price=mini_low,
                    ts=recent_df["timestamp"].iloc[-1] if "timestamp" in df.columns else None,
                    swept=swept
                )
    return Inducement(detected=False)

# ----------------------------------------------------------------------
# 4. POWER OF 3 (AMD: Accumulation, Manipulation, Distribution)
#    Definicion: precio acumula en un rango, manipula sweep de un lado,
#    distribuye al lado opuesto. Lee LTF para detectar la fase actual.
# ----------------------------------------------------------------------
def detect_power_of_3(df_15m, df_1h, range_window=12):
    """
    AMD usando 15m sobre rango de 1h.
    Accumulation: rango definido por highest-lowest en 1h
    Manipulation: sweep reciente del rango en 15m
    Distribution: post-sweep move > 2x el rango width
    """
    if len(df_15m) < range_window or df_1h is None or len(df_1h) < 4:
        return PowerOf3(detected=False)

    # Tomamos rango de ultimas 4 velas 1h = ~16 velas 15m
    range_df = df_1h.iloc[-4:]
    range_high = float(range_df["high"].max())
    range_low  = float(range_df["low"].min())
    range_width = range_high - range_low
    if range_width <= 0:
        return PowerOf3(detected=False)

    # Buscar sweep en las ultimas 12 velas 15m
    recent = df_15m.iloc[-range_window:]
    swept_high = float(recent["high"].max()) > range_high * 1.0008
    swept_low  = float(recent["low"].min()) < range_low * 0.9992
    current_close = float(df_15m["close"].iloc[-1])

    if swept_high and not swept_low:
        # Manipulation alta -> esperar distribucion bajista
        if current_close < range_low + range_width * 0.4:
            return PowerOf3(detected=True, phase="distribution",
                            range_high=range_high, range_low=range_low,
                            sweep_side="high", confirmed=True)
        return PowerOf3(detected=True, phase="manipulation",
                        range_high=range_high, range_low=range_low,
                        sweep_side="high", confirmed=False)
    if swept_low and not swept_high:
        if current_close > range_low + range_width * 0.6:
            return PowerOf3(detected=True, phase="distribution",
                            range_high=range_high, range_low=range_low,
                            sweep_side="low", confirmed=True)
        return PowerOf3(detected=True, phase="manipulation",
                        range_high=range_high, range_low=range_low,
                        sweep_side="low", confirmed=False)
    # Sin sweep claro -> seguimos en accumulation
    return PowerOf3(detected=True, phase="accumulation",
                    range_high=range_high, range_low=range_low,
                    sweep_side=None, confirmed=False)

# ----------------------------------------------------------------------
# 5. BALANCED PRICE RANGE (BPR)
#    Definicion: zona donde coinciden double FVG (uno bullish y uno
#    bearish solapados) -> magnet de precio.
# ----------------------------------------------------------------------
def detect_balanced_price_range(df, fvgs):
    """Detecta BPR: overlap entre un FVG bullish y uno bearish"""
    if len(fvgs) < 2:
        return BalancedPriceRange(detected=False)
    bull_fvgs = [f for f in fvgs if f.direction == "bullish"]
    bear_fvgs = [f for f in fvgs if f.direction == "bearish"]
    if not bull_fvgs or not bear_fvgs:
        return BalancedPriceRange(detected=False)

    for bf in bull_fvgs:
        for ef in bear_fvgs:
            # Overlap test
            overlap_low  = max(bf.bottom, ef.bottom)
            overlap_high = min(bf.top, ef.top)
            if overlap_low < overlap_high:
                return BalancedPriceRange(
                    detected=True,
                    upper_fvg=ef if ef.top > bf.top else bf,
                    lower_fvg=bf if bf.bottom < ef.bottom else ef,
                    midpoint=(overlap_low + overlap_high) / 2.0
                )
    return BalancedPriceRange(detected=False)

# ----------------------------------------------------------------------
# 6. DISPLACEMENT
#    Definicion: movimiento direccional decisivo, body grande, wicks chicos.
#    Magnitud >= 1.0% en una vela 15m con body > 70% del rango total.
# ----------------------------------------------------------------------
DISPLACEMENT_MIN_PCT = 0.010    # 1.0% movimiento
DISPLACEMENT_BODY_RATIO = 0.65   # body >= 65% del rango total

def detect_displacement(df, lookback=5):
    """Detecta displacement reciente (ultimas N velas)"""
    if len(df) < lookback:
        return Displacement(detected=False)
    recent = df.iloc[-lookback:]
    for _, row in recent.iterrows():
        o, c, h, l = float(row["open"]), float(row["close"]), float(row["high"]), float(row["low"])
        rng = h - l
        body = abs(c - o)
        if rng <= 0:
            continue
        body_ratio = body / rng
        pct_move = body / o if o > 0 else 0
        if pct_move >= DISPLACEMENT_MIN_PCT and body_ratio >= DISPLACEMENT_BODY_RATIO:
            return Displacement(
                detected=True,
                direction="bullish" if c > o else "bearish",
                magnitude_pct=pct_move * 100,
                velocity=1.0
            )
    return Displacement(detected=False)

# ----------------------------------------------------------------------
# 7. OPTIMAL TRADE ENTRY (OTE) - ESTRICTO
#    Definicion ICT: zona Fibonacci 62-79% del swing, con 70.5% como
#    el "sweet spot". Se calcula sobre el swing mas reciente.
# ----------------------------------------------------------------------
OTE_LOWER_PCT  = 0.62
OTE_SWEET_PCT  = 0.705
OTE_UPPER_PCT  = 0.79

def compute_ote_zone(df, direction, pivot_highs, pivot_lows):
    """
    OTE estricto sobre el swing mas reciente.
    LONG: swing low -> swing high mas alto; OTE = retracement del 62-79%
    SHORT: swing high -> swing low mas bajo; OTE = retracement del 62-79%
    """
    if direction not in ("long", "short") or not pivot_highs or not pivot_lows:
        return OTEZone(valid=False)

    current_price = float(df["close"].iloc[-1])
    if direction == "long":
        # Tomamos ultimo swing low + swing high posterior
        last_low = pivot_lows[-1] if pivot_lows else None
        # swing high posterior al low
        post_highs = [p for p in pivot_highs if p.idx > last_low.idx] if last_low else []
        if not last_low or not post_highs:
            return OTEZone(valid=False)
        swing_high = post_highs[-1]
        rng = swing_high.price - last_low.price
        if rng <= 0:
            return OTEZone(valid=False)
        ote_lower = swing_high.price - rng * OTE_LOWER_PCT
        ote_sweet = swing_high.price - rng * OTE_SWEET_PCT
        ote_upper = swing_high.price - rng * OTE_UPPER_PCT
        in_zone = (ote_upper <= current_price <= ote_lower)
        dist_sweet = abs(current_price - ote_sweet) / max(rng, 1e-9) * 100
        return OTEZone(
            valid=True, direction="long",
            swing_high=swing_high.price, swing_low=last_low.price,
            ote_lower=ote_lower, ote_sweet=ote_sweet, ote_upper=ote_upper,
            in_zone=in_zone, distance_to_sweet_pct=dist_sweet
        )
    else:  # short
        last_high = pivot_highs[-1] if pivot_highs else None
        post_lows = [p for p in pivot_lows if p.idx > last_high.idx] if last_high else []
        if not last_high or not post_lows:
            return OTEZone(valid=False)
        swing_low = post_lows[-1]
        rng = last_high.price - swing_low.price
        if rng <= 0:
            return OTEZone(valid=False)
        ote_lower = swing_low.price + rng * OTE_LOWER_PCT
        ote_sweet = swing_low.price + rng * OTE_SWEET_PCT
        ote_upper = swing_low.price + rng * OTE_UPPER_PCT
        in_zone = (ote_lower <= current_price <= ote_upper)
        dist_sweet = abs(current_price - ote_sweet) / max(rng, 1e-9) * 100
        return OTEZone(
            valid=True, direction="short",
            swing_high=last_high.price, swing_low=swing_low.price,
            ote_lower=ote_lower, ote_sweet=ote_sweet, ote_upper=ote_upper,
            in_zone=in_zone, distance_to_sweet_pct=dist_sweet
        )

# ----------------------------------------------------------------------
# COMPILADOR DE FLAGS POR CONCEPTO - para el bucket v3
# ----------------------------------------------------------------------
def compile_concept_flags(field):
    """
    Devuelve dict de flags por concepto, listo para bucket_key_v3 y ledger.
    Cada flag es True/False segun si el concepto estuvo activo en la senal.
    """
    return {
        "breaker":      bool(field.breaker and field.breaker.confirmed)
                        if getattr(field, "breaker", None) else False,
        "mss":          bool(field.mss and field.mss.confirmed)
                        if getattr(field, "mss", None) else False,
        "inducement":   bool(field.inducement and field.inducement.detected and
                             field.inducement.swept)
                        if getattr(field, "inducement", None) else False,
        "pwr3":         bool(field.power_of_3 and field.power_of_3.confirmed)
                        if getattr(field, "power_of_3", None) else False,
        "bpr":          bool(field.bpr and field.bpr.detected)
                        if getattr(field, "bpr", None) else False,
        "ote_strict":   bool(field.ote_zone and field.ote_zone.valid and
                             field.ote_zone.in_zone)
                        if getattr(field, "ote_zone", None) else False,
        "displacement": bool(field.displacement and field.displacement.detected)
                        if getattr(field, "displacement", None) else False,
    }
