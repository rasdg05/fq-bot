# -*- coding: utf-8 -*-
"""
================================================================================
  CVD (Cumulative Volume Delta) PROXY - FQ research
  by RasDG_Sol + Claude

  Delta de volumen comprador/vendedor APROXIMADO desde velas OHLCV y detector
  de divergencia precio-CVD para la estrategia "precio llega al nivel de
  interes + divergencia de CVD = entrada".

  HONESTIDAD DEL DATO: el pipeline (vivo y research) consume OHLCV puro; el
  exchange no expone el lado agresor por vela. Esto es un PROXY:
    - mode="range": delta = vol * ((c-l)-(h-c))/(h-l)  (posicion del cierre en
      el rango; +vol si cierra en el high, -vol si cierra en el low, 0 si doji
      de rango cero). Es la aproximacion money-flow clasica.
    - mode="body":  delta = vol * sign(c-o)  (cruda, todo el volumen al lado
      del cuerpo).
  Si el diagnostico separa con el proxy, el paso siguiente es pagar el dato
  real (taker buy/sell por vela) y re-medir; si ni el proxy separa, la linea
  muere barata (RETRIEVAL_PLAN: estandar anti-espejismo).

  CAUSALIDAD: estas funciones operan SOLO sobre el DataFrame que reciben (el
  caller pasa velas CERRADAS hasta el instante de la decision). Aqui no se lee
  reloj de pared NI se descarga nada (leccion §6.7: el replay decide que velas
  existen, no la hora del click).

  El detector de divergencia replica deliberadamente la forma de
  market_context.detect_rsi_divergence (mitades de ventana, swing por mitad)
  para que la comparacion "divergencia RSI vs divergencia CVD" sea de oscilador
  a oscilador, no de algoritmo a algoritmo.
================================================================================
"""
import numpy as np

__all__ = ["delta_proxy", "cvd_series", "detect_cvd_divergence",
           "divergence_alignment"]


def delta_proxy(df, mode="range"):
    """Delta de volumen por vela (numpy array, mismo largo que df).

    mode="range": vol * ((close-low)-(high-close))/(high-low); 0 si high==low.
    mode="body":  vol * sign(close-open).
    """
    o = np.asarray(df["open"], dtype="float64")
    h = np.asarray(df["high"], dtype="float64")
    l = np.asarray(df["low"], dtype="float64")
    c = np.asarray(df["close"], dtype="float64")
    v = np.asarray(df["volume"], dtype="float64")
    if mode == "body":
        return v * np.sign(c - o)
    if mode != "range":
        raise ValueError(f"mode desconocido: {mode!r} (usa 'range' o 'body')")
    rng = h - l
    pos = np.zeros_like(rng)
    nz = rng > 0
    pos[nz] = ((c[nz] - l[nz]) - (h[nz] - c[nz])) / rng[nz]
    return v * pos


def cvd_series(df, mode="range"):
    """CVD = suma acumulada del delta proxy, anclada al inicio del df recibido.

    El ancla es arbitraria a proposito: la divergencia compara swings DENTRO
    de la ventana, donde la constante de integracion se cancela.
    """
    return np.cumsum(delta_proxy(df, mode=mode))


def detect_cvd_divergence(df, lookback=96, mode="range"):
    """Divergencia precio-CVD en las ultimas `lookback` velas CERRADAS.

    Espejo de market_context.detect_rsi_divergence:
      Bullish: precio hace LL (min de la 2a mitad < min de la 1a) pero el CVD
               en esos minimos hace HL (los vendedores no confirman el LL).
      Bearish: precio hace HH pero el CVD hace LH (los compradores no
               confirman el HH).
    Sin umbral absoluto (el CVD no tiene escala fija como el RSI 35/65).
    Devuelve dict {"type", "cvd_change", "price_change_pct"} o None.
    """
    if df is None or len(df) < 10:
        return None
    sub = df.iloc[-lookback:] if len(df) > lookback else df
    closes = np.asarray(sub["close"], dtype="float64")
    cvd = cvd_series(sub, mode=mode)
    if len(closes) < 10:
        return None

    half = len(closes) // 2
    min1 = int(closes[:half].argmin())
    min2 = half + int(closes[half:].argmin())
    max1 = int(closes[:half].argmax())
    max2 = half + int(closes[half:].argmax())

    if closes[min2] < closes[min1] and cvd[min2] > cvd[min1]:
        return {"type": "DIVERGENCIA BULLISH",
                "cvd_change": float(cvd[min2] - cvd[min1]),
                "price_change_pct": float((closes[min2] - closes[min1])
                                          / closes[min1] * 100)}
    if closes[max2] > closes[max1] and cvd[max2] < cvd[max1]:
        return {"type": "DIVERGENCIA BEARISH",
                "cvd_change": float(cvd[max1] - cvd[max2]),
                "price_change_pct": float((closes[max2] - closes[max1])
                                          / closes[max1] * 100)}
    return None


def divergence_alignment(divergence, direction):
    """Clasifica la divergencia respecto a la direccion del trade (+1/-1).

    'alineada'  : LONG con bullish / SHORT con bearish (la entrada del playbook
                  CVD: el precio llego al nivel y el delta no confirma el move
                  contra nosotros).
    'contra'    : divergencia del lado opuesto.
    'sin_div'   : no hubo divergencia en la ventana.
    """
    if not divergence:
        return "sin_div"
    bullish = "BULLISH" in str(divergence.get("type", ""))
    if (int(direction) > 0) == bullish:
        return "alineada"
    return "contra"
