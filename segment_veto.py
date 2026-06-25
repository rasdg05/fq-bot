# -*- coding: utf-8 -*-
"""
================================================================================
  VETO DE SESION (F2.6 — RETRIEVAL_PLAN §6.8)
  by RasDG_Sol + Claude
================================================================================
Predicado PURO que veta una senal por su SEGMENTO temporal:

  - killzone (p.ej. london_open_kz)          -> FQ_SEGMENT_VETO_KILLZONES
  - bloque horario UTC de 4h (p.ej. 00-04)   -> FQ_SEGMENT_VETO_UTC_BLOCKS
  - dia de la semana (p.ej. lun)             -> FQ_SEGMENT_VETO_WEEKDAYS

Los predicados se combinan con OR: la senal CAE al veto si encaja en CUALQUIERA.

Reglas grabadas a fuego (§6.7 / §6.8 del RETRIEVAL_PLAN):

  * Juzga el TIMESTAMP DE LA VELA (en vivo y en replay), NUNCA datetime.now().
    La guarda tests/test_no_wallclock.py verifica que este modulo no introduce
    relojes de pared (esta en su inventario con baseline 0).
  * MISMO predicado en research (replay), en el regrade offline
    (tools/regrade_events.py) y en vivo (capa de decision POST evaluate_signal,
    JAMAS dentro de fusion_engine) -> cero divergencia backtest/live.
  * Reversible: default OFF. Con FQ_SEGMENT_VETO_*="" -> .active == False -> el
    veto es un no-op (ni filtra en research ni veta en vivo).

El killzone de una senal es field.killzone (== columna `field_killzone` del
cubo de research), computado por killzones_pd con el reloj de la VELA. El
predicado lo RECIBE ya computado (paridad exacta con lo que decidio el motor);
si no se le pasa, lo deriva del timestamp con
killzones_pd.current_killzone(now_cdmx=<ts de la vela>) — explicito, sin reloj
de pared.

Uso vivo (escalar):
    veto = segment_veto.from_env()
    if veto.active and veto.vetoes(killzone=field.killzone, ts_utc=candle_ts):
        ...  # no difundir

Uso research/offline (vectorizado, mismas columnas que el cubo):
    veto = segment_veto.parse(killzones="london_open_kz")
    labeled = labeled[~veto.mask(labeled)]
"""
from dataclasses import dataclass
from datetime import datetime, timezone

import killzones_pd

# lun=0 .. dom=6 (igual que datetime.weekday() y pandas Series.dt.dayofweek)
DIAS = ("lun", "mar", "mie", "jue", "vie", "sab", "dom")

ENV_KILLZONES = "FQ_SEGMENT_VETO_KILLZONES"
ENV_UTC_BLOCKS = "FQ_SEGMENT_VETO_UTC_BLOCKS"
ENV_WEEKDAYS = "FQ_SEGMENT_VETO_WEEKDAYS"

_UTC = timezone.utc


def _as_utc_datetime(ts):
    """Normaliza ts (datetime / pandas.Timestamp / str ISO) a un datetime UTC
    tz-aware. Un ts naive se asume UTC (convencion OHLCV: OKX/ccxt entrega UTC,
    igual que `entry_ts` del cubo). Devuelve None si ts es None/NaT.

    NUNCA llama a datetime.now(): el timestamp viene SIEMPRE de la vela."""
    if ts is None:
        return None
    # pandas.Timestamp / NaT -> datetime (NaT.to_pydatetime() es NaT, lo cazamos)
    if hasattr(ts, "to_pydatetime"):
        if getattr(ts, "value", 0) != ts.value:  # NaT compara distinto a si mismo
            return None
        ts = ts.to_pydatetime()
    elif isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if not isinstance(ts, datetime):
        raise TypeError("timestamp de vela no soportado: %r" % (type(ts),))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_UTC)
    return ts.astimezone(_UTC)


def killzone_of(ts):
    """Killzone de una vela a partir de SU timestamp (sin reloj de pared).

    Es el fallback del predicado cuando no se le pasa field.killzone: deriva el
    nombre con el MISMO killzones_pd que usa el motor, pasandole el ts de la
    vela como `now_cdmx` (explicito). Devuelve None si ts es None."""
    dt = _as_utc_datetime(ts)
    if dt is None:
        return None
    now_cdmx = dt.astimezone(killzones_pd.CDMX_TZ)
    return killzones_pd.current_killzone(now_cdmx=now_cdmx)["name"]


@dataclass(frozen=True)
class SegmentVeto:
    """Configuracion inmutable del veto. Construir con parse()/from_env()."""

    killzones: frozenset = frozenset()
    utc_blocks: frozenset = frozenset()   # horas de inicio de bloque 4h: 0,4,...,20
    weekdays: frozenset = frozenset()      # 0=lun .. 6=dom

    @property
    def active(self):
        """True si hay AL MENOS un predicado configurado (si no, no-op)."""
        return bool(self.killzones or self.utc_blocks or self.weekdays)

    def describe(self):
        """Descripcion legible (para logs), formato del regrade historico."""
        parts = []
        if self.killzones:
            parts.append("killzone in %s" % sorted(self.killzones))
        if self.utc_blocks:
            parts.append("bloque_utc in %s" % sorted(self.utc_blocks))
        if self.weekdays:
            parts.append("dia in %s" % [DIAS[d] for d in sorted(self.weekdays)])
        return " OR ".join(parts) if parts else "(sin veto)"

    def reason(self, killzone=None, ts_utc=None):
        """Motivo (str) si la senal CAE al veto, o None si pasa.

        killzone: field.killzone ya computado (PREFERIDO: paridad con el motor).
                  Si es None y hay veto por killzone, se deriva de ts_utc.
        ts_utc:   timestamp de la VELA (para bloque-UTC, dia, y el fallback de
                  killzone). datetime / pandas.Timestamp / str ISO; naive=UTC.
        """
        if not self.active:
            return None
        if self.killzones:
            kz = killzone
            if kz is None and ts_utc is not None:
                kz = killzone_of(ts_utc)
            if kz is not None and str(kz) in self.killzones:
                return "killzone=%s" % kz
        if (self.utc_blocks or self.weekdays) and ts_utc is not None:
            dt = _as_utc_datetime(ts_utc)
            if dt is not None:
                if self.utc_blocks:
                    blk = (dt.hour // 4) * 4
                    if blk in self.utc_blocks:
                        return "utc_block=%02d-%02d" % (blk, blk + 4)
                if self.weekdays and dt.weekday() in self.weekdays:
                    return "dia=%s" % DIAS[dt.weekday()]
        return None

    def vetoes(self, killzone=None, ts_utc=None):
        """True si la senal cae al veto (azucar sobre reason())."""
        return self.reason(killzone=killzone, ts_utc=ts_utc) is not None

    def mask(self, df, killzone_col="field_killzone", ts_col="entry_ts"):
        """Mascara booleana vectorizada (True = vetada) sobre un DataFrame de
        eventos. MISMA semantica que reason() — el path de research/offline.

        Requiere pandas/numpy (presentes en research; el loop vivo usa el path
        escalar y no toca esto). Si el veto no esta activo devuelve todo False."""
        import numpy as np
        import pandas as pd

        m = np.zeros(len(df), dtype=bool)
        if not self.active or len(df) == 0:
            return m
        if self.killzones and killzone_col in df.columns:
            m |= df[killzone_col].astype(str).isin(self.killzones).to_numpy()
        if (self.utc_blocks or self.weekdays) and ts_col in df.columns:
            ts = pd.to_datetime(df[ts_col])
            if self.utc_blocks:
                m |= ts.dt.hour.floordiv(4).mul(4).isin(self.utc_blocks).to_numpy()
            if self.weekdays:
                m |= ts.dt.dayofweek.isin(self.weekdays).to_numpy()
        return m


def _parse_killzones(s):
    return frozenset(k.strip() for k in str(s or "").split(",") if k.strip())


def _parse_utc_blocks(s):
    """'00-04,04-08' -> {0, 4} (hora de INICIO del bloque 4h). Toma el numero
    antes del '-'; el matching usa (hora//4)*4, asi que los inicios utiles son
    multiplos de 4 (00,04,08,12,16,20) — igual que el regrade historico."""
    out = set()
    for b in str(s or "").split(","):
        b = b.strip()
        if b:
            out.add(int(b.split("-")[0]))
    return frozenset(out)


def _parse_weekdays(s):
    out = set()
    for d in str(s or "").split(","):
        d = d.strip().lower()
        if not d:
            continue
        if d not in DIAS:
            raise ValueError("dia desconocido %r (usa: %s)" % (d, ",".join(DIAS)))
        out.add(DIAS.index(d))
    return frozenset(out)


def parse(killzones="", utc_blocks="", weekdays=""):
    """Construye un SegmentVeto desde strings CSV (mismo formato que las envs y
    que los flags de tools/regrade_events.py)."""
    return SegmentVeto(
        killzones=_parse_killzones(killzones),
        utc_blocks=_parse_utc_blocks(utc_blocks),
        weekdays=_parse_weekdays(weekdays),
    )


def from_env(env=None, prefix="FQ_SEGMENT_VETO"):
    """Lee <prefix>_KILLZONES / _UTC_BLOCKS / _WEEKDAYS. Default OFF.

    prefix permite un veto INDEPENDIENTE por consumidor sin tocar el global: el
    track gold paper usa prefix='FQ_GOLD_SEGMENT_VETO' para vetar SOLO en paper
    (admin) sin afectar la senal VIP a clientes (paper-first)."""
    import os
    env = os.environ if env is None else env
    return parse(
        killzones=env.get(prefix + "_KILLZONES", ""),
        utc_blocks=env.get(prefix + "_UTC_BLOCKS", ""),
        weekdays=env.get(prefix + "_WEEKDAYS", ""),
    )
