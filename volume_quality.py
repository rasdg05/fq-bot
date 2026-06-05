# -*- coding: utf-8 -*-
"""
================================================================================
  VOLUME QUALITY MODULE - FQ v5.2
  by RasDG_Sol + Claude

  Calidad de volumen / liquidez como gate y modulador.

  Problema que resuelve:
    Hasta v5.1 el motor de decision (fusion_engine.evaluate_signal) usaba
    estructura ICT + matematica + killzone weight, pero NUNCA consultaba el
    volumen real. Eso dejaba pasar setups "coherentes matematicamente pero
    sin momentum" (traps) tipicos de horas muertas (ultima hora NY, viernes
    tarde, asia tardia).

  Tres primitivas:
    1) volume_score(df): vol_last / vol_ma_window. Cruda, [0, 3].
    2) volume_modulator(vol_score): multiplicador suave de P_master.
    3) is_dead_window() + volume_veto(): veto duro solo cuando coinciden
       baja liquidez y franja muerta. Es el unico nuevo veto.

  Diseno: dependency-light (numpy/pandas opcional via duck-typing) para
  permitir tests sin tocar fetch_ohlcv.
================================================================================
"""
import os
import logging
from datetime import datetime, timezone, timedelta

log = logging.getLogger("fq_volume_quality")

CDMX_TZ = timezone(timedelta(hours=-6))

# ============================================================
# FEATURE FLAGS (env-driven, alineados con plan de rollout)
# ============================================================
VOL_GATE_ENABLED      = os.environ.get("FQ_VOL_GATE_ENABLED", "1").strip() in ("1", "true", "yes")
VOL_VETO_DEAD_HOURS   = os.environ.get("FQ_VOL_VETO_DEAD_HOURS", "1").strip() in ("1", "true", "yes")

# Franja de manipulacion 2 PM (peticion RasDG, jun-2026): la hora de las 2 PM
# CDMX (14:00-15:00) es una franja fuerte de manipulacion que historicamente
# sangraba la cuenta (ej: ALERTA TACTICA SHORT @14:50 -> SL). Se trata como
# franja muerta DIARIA: bloquea promocion de tacticas al VIP y veta señales VIP
# de bajo volumen. El penalty de killzone 15:00-16:00 sigue aparte.
DEAD_2PM_MANIP        = os.environ.get("FQ_DEAD_2PM_MANIP", "1").strip() in ("1", "true", "yes")
DEAD_2PM_START        = float(os.environ.get("FQ_DEAD_2PM_START", "14.0"))
DEAD_2PM_END          = float(os.environ.get("FQ_DEAD_2PM_END", "15.0"))

# Asia-open bull-fakeout guard (peticion RasDG, jun-2026).
# La apertura asiatica (killzone asia_open, 17:00-18:30 CDMX) suele ABRIR con un
# BULL FAKEOUT: un empuje alcista en liquidez delgada que barre buy-stops /
# induce longs, deja un FVG alcista, y luego REVIERTE. Acumular un LONG dentro de
# ese FVG con volumen bajo es justo la trampa. Caso real: ALERTA TACTICA ACUMULA
# LONG SOL/USDT @17:55 CDMX (asia_open, "Volumen bajo") -> SL en los primeros 5
# min. El gate de ACUMULAR usa un piso de volumen relajado (0.60) "porque la vela
# de zona es de bajo volumen por naturaleza", pero en la apertura asiatica ESE es
# el sintoma del fakeout, no de un pullback sano.
#   Guard: un LONG tactico solo se promueve en asia_open si trae volumen genuino
#   (>= ASIA_FAKEOUT_VOL_MIN, "Normal"). Asi un displacement alcista real con
#   volumen sigue pasando; el barrido de baja liquidez queda fuera. No toca los
#   shorts (el fakeout es alcista) ni el resto de killzones.
ASIA_FAKEOUT_GUARD    = os.environ.get("FQ_ASIA_FAKEOUT_GUARD", "1").strip() in ("1", "true", "yes")
ASIA_FAKEOUT_VOL_MIN  = float(os.environ.get("FQ_ASIA_FAKEOUT_VOL_MIN", "0.85"))
ASIA_OPEN_KZ_NAME     = os.environ.get("FQ_ASIA_OPEN_KZ_NAME", "asia_open").strip()

# Umbrales (calibrables via env sin tocar codigo)
VOL_SCORE_LOW         = float(os.environ.get("FQ_VOL_SCORE_LOW", "0.60"))     # bajo umbral
VOL_SCORE_NORMAL      = float(os.environ.get("FQ_VOL_SCORE_NORMAL", "0.85"))  # normal
VOL_SCORE_HIGH        = float(os.environ.get("FQ_VOL_SCORE_HIGH", "1.30"))    # alto
VOL_MOD_MIN           = float(os.environ.get("FQ_VOL_MOD_MIN", "0.75"))       # multiplicador piso
VOL_MOD_MAX           = float(os.environ.get("FQ_VOL_MOD_MAX", "1.20"))       # multiplicador techo
VOL_VETO_THRESHOLD    = float(os.environ.get("FQ_VOL_VETO_THRESHOLD", "0.60"))

# Ventana de calculo (velas de vol_ma)
VOL_WINDOW            = int(os.environ.get("FQ_VOL_WINDOW", "20"))


# ============================================================
# 1) VOLUME SCORE
# ============================================================
def volume_score(df, window=None):
    """
    Calcula el ratio vol_last / vol_ma(window) sobre el DataFrame de velas.

    Args:
        df: pandas DataFrame con columna "volume" (lo que devuelve fetch_ohlcv).
        window: ventana de la media movil. Default VOL_WINDOW (20).

    Returns:
        dict con:
          score:     ratio crudo, clip [0, 3]. 1.0 = volumen normal.
          vol_last:  volumen de la vela mas reciente.
          vol_ma:    media de las window velas previas (excluye la ultima).
          body_pct:  cuerpo de la vela / rango total (0-1).
          is_climax: True si score >= 2.0 y body_pct >= 0.5 (vela climax,
                     potencialmente exhaustion).

    Si df tiene menos de window+1 velas, devuelve neutral score=1.0.
    """
    w = window or VOL_WINDOW
    try:
        n = len(df)
    except Exception:
        return _neutral()
    if n < w + 1:
        return _neutral()

    try:
        # Vol de la vela mas reciente
        vol_last = float(df["volume"].iloc[-1])
        # Media de las w velas previas (excluye la actual para evitar self-bias)
        vol_ma = float(df["volume"].iloc[-(w + 1):-1].mean())
        if vol_ma <= 0:
            return _neutral()
        score = vol_last / vol_ma
        # Clip a rango razonable
        if score < 0.0:
            score = 0.0
        if score > 3.0:
            score = 3.0

        # Body pct para detector de climax
        high = float(df["high"].iloc[-1])
        low = float(df["low"].iloc[-1])
        open_ = float(df["open"].iloc[-1])
        close = float(df["close"].iloc[-1])
        rng = max(high - low, 1e-9)
        body_pct = abs(close - open_) / rng

        is_climax = score >= 2.0 and body_pct >= 0.5

        return {
            "score":     round(score, 3),
            "vol_last":  vol_last,
            "vol_ma":    vol_ma,
            "body_pct":  round(body_pct, 3),
            "is_climax": is_climax,
        }
    except Exception as e:
        log.warning("volume_score error: {}".format(e))
        return _neutral()


def _neutral():
    """Resultado neutral cuando no hay datos suficientes."""
    return {"score": 1.0, "vol_last": 0.0, "vol_ma": 0.0,
            "body_pct": 0.0, "is_climax": False}


# ============================================================
# 2) VOLUME MODULATOR (suave - multiplicador sobre P_master)
# ============================================================
def volume_modulator(vol_score_value):
    """
    Mapea vol_score -> multiplicador de P_master en [VOL_MOD_MIN, VOL_MOD_MAX].

    Curva lineal por tramos:
       score <= LOW    (0.60) -> VOL_MOD_MIN  (0.75)
       score == NORMAL (1.00) -> 1.0
       score >= HIGH   (1.30) -> VOL_MOD_MAX  (1.20)

    No introduce vetos: solo escala. El veto duro vive en volume_veto().
    """
    if not VOL_GATE_ENABLED:
        return 1.0
    try:
        s = float(vol_score_value)
    except (TypeError, ValueError):
        return 1.0

    if s <= VOL_SCORE_LOW:
        return VOL_MOD_MIN
    if s <= 1.0:
        # interp [LOW..1.0] -> [MIN..1.0]
        t = (s - VOL_SCORE_LOW) / max(1.0 - VOL_SCORE_LOW, 1e-9)
        return VOL_MOD_MIN + (1.0 - VOL_MOD_MIN) * t
    if s <= VOL_SCORE_HIGH:
        # interp [1.0..HIGH] -> [1.0..MAX]
        t = (s - 1.0) / max(VOL_SCORE_HIGH - 1.0, 1e-9)
        return 1.0 + (VOL_MOD_MAX - 1.0) * t
    return VOL_MOD_MAX


# ============================================================
# 3) DEAD WINDOW DETECTION
# ============================================================
def is_dead_window(now_cdmx=None):
    """
    True si la hora actual cae en franja muerta donde el bot historicamente
    da falsos positivos:
      - 14:00-15:00 CDMX (manipulacion 2 PM, sesgo de barrido pre-NY-close)
      - 15:00-16:00 CDMX (ultima hora de NY, post-Silver Bullet PM)
      - viernes >= 14:00 CDMX (corren las ultimas horas de la semana)

    El veto absoluto de fin de semana sigue en killzones_pd.is_weekend_closed;
    aqui solo cubrimos las franjas DONDE EL MERCADO ESTA ABIERTO pero la
    liquidez se evapora o la manipulacion domina.
    """
    if now_cdmx is None:
        now_cdmx = datetime.now(CDMX_TZ)
    weekday = now_cdmx.weekday()  # 0=Mon ... 6=Sun
    h = now_cdmx.hour + now_cdmx.minute / 60.0

    # Manipulacion 2 PM (diaria): hora fuerte de barridos antes del cierre NY.
    if DEAD_2PM_MANIP and DEAD_2PM_START <= h < DEAD_2PM_END:
        return True

    # Ultima hora NY (lun-jue + vie temprano)
    if 15.0 <= h < 16.0:
        return True

    # Viernes tarde: liquidez se va antes del cierre semanal real
    if weekday == 4 and h >= 14.0:
        return True

    return False


def dead_window_label(now_cdmx=None):
    """Etiqueta legible de por que la ventana es muerta. None si no lo es."""
    if now_cdmx is None:
        now_cdmx = datetime.now(CDMX_TZ)
    weekday = now_cdmx.weekday()
    h = now_cdmx.hour + now_cdmx.minute / 60.0
    if DEAD_2PM_MANIP and DEAD_2PM_START <= h < DEAD_2PM_END:
        return "manipulacion 2PM"
    if 15.0 <= h < 16.0:
        return "ultima hora NY"
    if weekday == 4 and h >= 14.0:
        return "viernes tarde"
    return None


# ============================================================
# 4) VOLUME VETO (gate duro - SOLO cuando coinciden bajo vol Y franja muerta)
# ============================================================
def volume_veto(vol_score_value, is_dead=None, now_cdmx=None):
    """
    Decide si rechazar la senal por baja liquidez en franja muerta.

    Args:
        vol_score_value: score crudo de volume_score().score
        is_dead: bool opcional. Si None, se calcula con is_dead_window(now_cdmx).
        now_cdmx: datetime CDMX opcional (para testing).

    Returns:
        (vetoed: bool, reason: str)

    Politica conservadora: solo veta cuando AMBAS condiciones se dan. Esto
    evita matar setups validos en mananas de alto volumen fuera de killzone
    (que el sistema legacy ya castigaba erroneamente).
    """
    if not (VOL_GATE_ENABLED and VOL_VETO_DEAD_HOURS):
        return False, ""

    if is_dead is None:
        is_dead = is_dead_window(now_cdmx)
    if not is_dead:
        return False, ""

    try:
        s = float(vol_score_value)
    except (TypeError, ValueError):
        return False, ""

    if s < VOL_VETO_THRESHOLD:
        label = dead_window_label(now_cdmx) or "franja muerta"
        return True, "vol={:.2f} < {:.2f} en {}".format(s, VOL_VETO_THRESHOLD, label)
    return False, ""


# ============================================================
# 4.b) ASIA-OPEN BULL-FAKEOUT GUARD
# ============================================================
def asia_open_fakeout_veto(direction, vol_score_value, killzone_name):
    """Veta LONGs tacticos de bajo volumen en la apertura asiatica (bull fakeout).

    Args:
        direction:     "long" / "short" del setup.
        vol_score_value: score crudo de volume_score().score (vela CERRADA).
        killzone_name: nombre de la killzone activa (killzones_pd.current_killzone).

    Returns:
        (vetoed: bool, reason: str)

    Politica: solo dispara cuando coinciden las tres condiciones del patron
    (asia_open + LONG + volumen por debajo de "Normal"). Un displacement alcista
    genuino con volumen >= ASIA_FAKEOUT_VOL_MIN pasa; los shorts y las demas
    killzones no se tocan. Override total con FQ_ASIA_FAKEOUT_GUARD=0.
    """
    if not ASIA_FAKEOUT_GUARD:
        return False, ""
    if killzone_name != ASIA_OPEN_KZ_NAME:
        return False, ""
    if str(direction).lower() != "long":
        return False, ""
    try:
        s = float(vol_score_value)
    except (TypeError, ValueError):
        return False, ""
    if s < ASIA_FAKEOUT_VOL_MIN:
        return True, "asia_open bull fakeout: long vol={:.2f}<{:.2f}".format(
            s, ASIA_FAKEOUT_VOL_MIN)
    return False, ""


# ============================================================
# 5) LABELS HUMANOS (para los reportes)
# ============================================================
def volume_quality_label(vol_score_value):
    """Score crudo -> etiqueta cualitativa para mensajes de Telegram."""
    try:
        s = float(vol_score_value)
    except (TypeError, ValueError):
        return "—"
    if s >= VOL_SCORE_HIGH:
        return "Alto"
    if s >= VOL_SCORE_NORMAL:
        return "Normal"
    if s >= VOL_SCORE_LOW:
        return "Bajo"
    return "Muy bajo"


# ============================================================
# SELF-TESTS  -  python volume_quality.py
# ============================================================
def _run_self_tests():
    print("Running volume_quality self-tests...\n")

    # Test 1: dead window detection
    morning_cdmx = datetime(2026, 6, 1, 9, 0, tzinfo=CDMX_TZ)  # lunes mañana
    late_ny_cdmx = datetime(2026, 6, 1, 15, 30, tzinfo=CDMX_TZ)
    manip_2pm_cdmx = datetime(2026, 6, 1, 14, 50, tzinfo=CDMX_TZ)  # lunes 2PM (manipulacion)
    fri_late_cdmx = datetime(2026, 6, 5, 14, 30, tzinfo=CDMX_TZ)  # viernes
    sat_cdmx = datetime(2026, 6, 6, 9, 0, tzinfo=CDMX_TZ)         # sabado (no dead aqui)
    assert is_dead_window(morning_cdmx) is False
    assert is_dead_window(late_ny_cdmx) is True, "15:30 CDMX deberia ser dead window"
    assert is_dead_window(manip_2pm_cdmx) is True, "14:50 CDMX (2PM) deberia ser dead window"
    assert dead_window_label(manip_2pm_cdmx) == "manipulacion 2PM"
    assert is_dead_window(fri_late_cdmx) is True, "viernes 14:30 CDMX deberia ser dead window"
    # sabado no se cubre aqui (es_weekend_closed lo veta en otro lado)
    assert is_dead_window(sat_cdmx) is False
    print("  [OK] is_dead_window")

    # Test 2: volume_modulator curva
    assert abs(volume_modulator(1.0) - 1.0) < 1e-6, "score=1.0 -> mult=1.0"
    assert abs(volume_modulator(0.60) - VOL_MOD_MIN) < 1e-6, "score=LOW -> mult=MIN"
    assert abs(volume_modulator(1.30) - VOL_MOD_MAX) < 1e-6, "score=HIGH -> mult=MAX"
    assert volume_modulator(0.0) == VOL_MOD_MIN
    assert volume_modulator(5.0) == VOL_MOD_MAX
    # monotonia
    samples = [volume_modulator(s) for s in (0.0, 0.5, 0.8, 1.0, 1.1, 1.3, 2.0)]
    assert samples == sorted(samples), "modulator debe ser monotono creciente"
    print("  [OK] volume_modulator (curva monotona, anclajes correctos)")

    # Test 3: volume_veto - SOLO cuando coinciden ambos
    v1, _ = volume_veto(0.40, is_dead=True)
    assert v1 is True, "bajo vol + dead -> veto"
    v2, _ = volume_veto(0.40, is_dead=False)
    assert v2 is False, "bajo vol pero NO dead -> no veto"
    v3, _ = volume_veto(1.20, is_dead=True)
    assert v3 is False, "alto vol incluso en dead -> no veto"
    v4, _ = volume_veto(0.40, now_cdmx=morning_cdmx)
    assert v4 is False, "bajo vol en horario activo -> no veto"
    v5, _ = volume_veto(0.40, now_cdmx=late_ny_cdmx)
    assert v5 is True, "bajo vol en ultima hora NY -> veto"
    print("  [OK] volume_veto (solo dispara con AND)")

    # Test 4: volume_score con df mock
    class _FakeDF:
        def __init__(self, vols, opens, closes, highs, lows):
            self.vols = vols
            self.opens = opens
            self.closes = closes
            self.highs = highs
            self.lows = lows
            self._cols = {"volume": vols, "open": opens, "close": closes,
                          "high": highs, "low": lows}
        def __len__(self):
            return len(self.vols)
        def __getitem__(self, key):
            return _FakeSeries(self._cols[key])

    class _FakeSeries:
        def __init__(self, data):
            self.data = data
        @property
        def iloc(self):
            return _FakeIloc(self.data)

    class _FakeIloc:
        def __init__(self, data):
            self.data = data
        def __getitem__(self, idx):
            if isinstance(idx, slice):
                return _FakeSeries(self.data[idx])
            return self.data[idx]
        def mean(self):
            return sum(self.data) / len(self.data)

    # Sumar mean al FakeSeries para que df["volume"].iloc[-21:-1].mean() funcione
    _FakeSeries.mean = lambda self: sum(self.data) / max(len(self.data), 1)

    # 21 velas: 20 con vol=100, ultima con vol=200 -> score=2.0
    vols = [100] * 20 + [200]
    opens = [10] * 21
    closes = [10.5] * 20 + [11.5]
    highs = [11] * 20 + [12]
    lows = [10] * 21
    df = _FakeDF(vols, opens, closes, highs, lows)
    vs = volume_score(df)
    assert abs(vs["score"] - 2.0) < 1e-6, "score esperado 2.0, got {}".format(vs["score"])
    assert vs["is_climax"] is True, "vol=2x + body grande -> climax"
    print("  [OK] volume_score con df mock (score=2.0, climax detectado)")

    # Test 5: volume_score con datos insuficientes -> neutral
    short_df = _FakeDF([100] * 5, [10] * 5, [10] * 5, [10] * 5, [10] * 5)
    vs_short = volume_score(short_df)
    assert vs_short["score"] == 1.0, "df corto -> score neutral 1.0"
    print("  [OK] volume_score con df corto (neutral 1.0)")

    # Test 5.b: asia-open bull-fakeout guard
    v_long_lowvol, _ = asia_open_fakeout_veto("long", 0.70, "asia_open")
    assert v_long_lowvol is True, "long de bajo vol en asia_open -> veto (fakeout)"
    v_long_vol, _ = asia_open_fakeout_veto("long", 1.00, "asia_open")
    assert v_long_vol is False, "long con volumen genuino en asia_open -> pasa"
    v_short, _ = asia_open_fakeout_veto("short", 0.40, "asia_open")
    assert v_short is False, "el fakeout es alcista; los shorts no se tocan"
    v_other_kz, _ = asia_open_fakeout_veto("long", 0.40, "ny_am_kz")
    assert v_other_kz is False, "guard solo aplica a asia_open"
    print("  [OK] asia_open_fakeout_veto (long bajo vol en asia_open)")

    # Test 6: labels cualitativos
    assert volume_quality_label(0.5) == "Muy bajo"
    assert volume_quality_label(0.7) == "Bajo"
    assert volume_quality_label(1.0) == "Normal"
    assert volume_quality_label(1.4) == "Alto"
    print("  [OK] volume_quality_label")

    print("\nALL TESTS PASSED")


if __name__ == "__main__":
    _run_self_tests()
