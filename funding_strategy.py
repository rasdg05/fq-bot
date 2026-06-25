# -*- coding: utf-8 -*-
"""
================================================================================
  FUNDING_STRATEGY — la senal de REVERSION de funding (edge ESTRUCTURAL)
  by RasDG_Sol + Claude

  El pivote post-§6.14: el deflactado MATO la PREDICCION direccional (DSR 0.41 =
  suerte). En vez de adivinar hacia donde va el precio, COSECHAMOS una tension
  estructural del libro de perpetuos:

    Cuando el funding es EXTREMADAMENTE positivo, los LONGS pagan a los shorts
    cada ventana (~8h). Financiar ese lado es insostenible: el premio atrae
    shorts / desincentiva longs -> presion de REVERSION del precio a la baja.
    Simetrico cuando es extremadamente negativo (shorts pagan -> reversion al
    alza). fund_zscore (funding_oi, ya causal) mide ese extremo.

  La senal es un FADE del extremo:
    fund_zscore >= +z_enter  -> SHORT (-1)   [longs crowded/overpaying; fade]
    fund_zscore <= -z_enter  -> LONG  (+1)   [shorts crowded; fade]
    |fund_zscore| <= z_exit  -> FLAT  (0)    [extremo relajado; salir]
  Con HISTERESIS: una vez dentro, se MANTIENE la posicion hasta cruzar la banda
  de salida (z_exit < z_enter) -> no se entra/sale en cada cruce de ruido.

  Pieza PURA (numpy/pandas; sin red, sin estado, sin reloj). Dos funciones:
    · funding_reversion_signal : fund_zscore -> posicion por barra en {-1,0,+1}.
    · positions_to_trades      : la serie de posiciones -> eventos de entrada/salida
                                 (entry_index, direction, entry_price) que enchufan
                                 EXACTAMENTE en bt_labeler.label_events / el harness
                                 OOS+OOT+DEFLATED existente.

  CAUSAL por construccion (lo que se revisa): la posicion en la barra t es funcion
  SOLO de fund_zscore(t), y fund_zscore ya es causal en funding_oi (funding
  liquidado, shift, merge_asof backward, ventana trailing). No se mira ninguna
  barra futura ni dentro de la senal ni al construir los trades (el stop/target de
  cada evento sale del precio de ENTRADA y un ancho fijo en R; el desenlace lo
  decide el labeler con las velas POSTERIORES, igual que toda senal del harness).
================================================================================
"""
import numpy as np
import pandas as pd

LONG, SHORT, FLAT = 1, -1, 0


def funding_reversion_signal(fund_zscore, *, z_enter=2.0, z_exit=0.5):
    """Posicion de REVERSION por barra a partir del z-score de funding (causal).

    fund_zscore : array-like (o Series) del z-score de funding YA causal y alineado
                  a cada barra del primario (funding_oi.fund_zscore). NaN = sin
                  lectura (warmup): se trata como FLAT y NO arrastra estado.
    z_enter     : umbral de ENTRADA (|z| >= z_enter abre el fade). Default 2.0.
    z_exit      : umbral de SALIDA (|z| <= z_exit cierra a 0). Default 0.5.
                  Debe ser < z_enter (histeresis); si no, ValueError.

    Reglas (FADE del extremo, con histeresis de banda):
      - z >= +z_enter -> SHORT (-1)        (longs pagan caro -> revierte abajo)
      - z <= -z_enter -> LONG  (+1)        (shorts pagan caro -> revierte arriba)
      - estando SHORT: se MANTIENE -1 mientras z > +z_exit; al caer a <= +z_exit
        (o cruzar a negativo extremo) se reevalua.
      - estando LONG : se MANTIENE +1 mientras z < -z_exit.
      - |z| <= z_exit -> FLAT (0).
      - en la zona intermedia (z_exit < |z| < z_enter) se ARRASTRA la posicion
        previa (es la histeresis: ni se abre nada nuevo ni se cierra todavia).
      - un cruce DIRECTO de un extremo al opuesto (z pasa de >=+z_enter a
        <=-z_enter) voltea la posicion en esa barra.
      - NaN -> FLAT en esa barra (warmup / hueco), sin heredar estado.

    Devuelve un np.ndarray int8 de la MISMA longitud que fund_zscore, en {-1,0,+1}.
    PURO y CAUSAL: la posicion en t usa solo z[t] y la posicion en t-1 (que a su vez
    solo dependio de z[<=t-1]); jamas mira z[>t].
    """
    z_enter = float(z_enter)
    z_exit = float(z_exit)
    if not (z_exit < z_enter):
        raise ValueError(
            f"z_exit ({z_exit}) debe ser < z_enter ({z_enter}) para histeresis")
    if z_enter <= 0:
        raise ValueError(f"z_enter debe ser > 0 (got {z_enter})")

    z = np.asarray(
        pd.to_numeric(pd.Series(np.asarray(fund_zscore).ravel()), errors="coerce"),
        dtype="float64")
    n = len(z)
    pos = np.zeros(n, dtype="int8")
    prev = FLAT
    for i in range(n):
        zi = z[i]
        if not np.isfinite(zi):
            pos[i] = FLAT                 # warmup/hueco: plano, NO arrastra
            prev = FLAT
            continue
        if zi >= z_enter:                 # extremo positivo -> FADE short
            cur = SHORT
        elif zi <= -z_enter:              # extremo negativo -> FADE long
            cur = LONG
        elif abs(zi) <= z_exit:           # extremo relajado -> salir
            cur = FLAT
        else:                             # zona intermedia -> histeresis: mantener
            cur = prev
        pos[i] = cur
        prev = cur
    return pos


def positions_to_trades(
    positions, df_primary, *, stop_r_pct=0.01, target_rr=1.0,
    price_col="close", ts_col="timestamp", reverse_closes=True,
):
    """Convierte la serie de POSICIONES por barra en EVENTOS de entrada para el
    harness (bt_labeler.label_events / OOS / OOT / DEFLATED). Detecta los FLANCOS:
    un evento nace cada vez que se ENTRA a una posicion no-plana desde plano, o se
    VOLTEA directamente al lado opuesto.

    positions : array-like en {-1,0,+1} alineado posicionalmente a df_primary
                (p.ej. la salida de funding_reversion_signal). Longitud == len(df).
    df_primary: OHLCV del primario; aporta entry_price (price_col) y entry_ts
                (ts_col) por entry_index. Define el espacio de entry_index (0..n-1).
    stop_r_pct: ancho del stop como FRACCION del precio de entrada (0.01 = 1%). El
                target sale a target_rr * R del entry. R = entry*stop_r_pct.
    target_rr : multiplo de R hasta el take-profit (1.0 = +1R, definicion de win
                del ledger; el harness puede re-etiquetar a otros TP via el cubo).
    reverse_closes: si True, una barra donde se VOLTEA (de +1 a -1 o viceversa) o
                se SALE a 0 marca el fin del trade abierto (informativo en el evento
                via 'exit_index'); el desenlace REAL lo decide el labeler con la
                barrera triple, no este corte (la senal solo fija la ENTRADA).

    Cada evento (dict) trae las claves que bt_labeler.label_events exige:
      entry_index, entry_price, stop_price, target_price, direction
    mas metadatos (entry_ts, exit_index, fund_zscore_at NO se calcula aqui:
    funding_oi.attach_* lo anexa por entry_index si se quiere). Devuelve un
    DataFrame de eventos (orden cronologico por entry_index). PURO y CAUSAL: el
    stop/target dependen SOLO del precio de entrada; el flanco se detecta con
    pos[i] y pos[i-1] (pasado). No mira velas futuras.
    """
    pos = np.asarray(positions).ravel()
    n = len(pos)
    n_df = len(df_primary)
    if n != n_df:
        raise ValueError(
            f"positions ({n}) y df_primary ({n_df}) deben tener la misma longitud")
    if n == 0:
        return _empty_trades()

    price = pd.to_numeric(df_primary[price_col], errors="coerce").to_numpy()
    ts = (pd.to_datetime(df_primary[ts_col]).to_numpy()
          if ts_col in df_primary.columns else np.full(n, np.datetime64("NaT")))
    pos_int = pos.astype("int64")

    events = []
    open_dir = FLAT
    open_idx = None
    for i in range(n):
        d = int(pos_int[i])
        if d == open_dir:
            continue                       # sin cambio de estado
        # se cerro o se volteo lo que estaba abierto -> registra exit_index
        if open_dir != FLAT and open_idx is not None and reverse_closes:
            events[-1]["exit_index"] = i
        if d != FLAT:
            entry_price = float(price[i]) if np.isfinite(price[i]) else None
            if entry_price is None or entry_price <= 0:
                # precio invalido en la barra de entrada: no se abre (no inventa)
                open_dir = FLAT
                open_idx = None
                continue
            risk = entry_price * float(stop_r_pct)
            stop_price = entry_price - d * risk
            target_price = entry_price + d * risk * float(target_rr)
            events.append({
                "entry_index": int(i),
                "entry_ts": ts[i],
                "entry_price": entry_price,
                "stop_price": float(stop_price),
                "target_price": float(target_price),
                "direction": int(d),
                "exit_index": None,
            })
            open_dir = d
            open_idx = i
        else:
            open_dir = FLAT
            open_idx = None

    if not events:
        return _empty_trades()
    return pd.DataFrame(events)


def _empty_trades():
    """DataFrame vacio con el esquema de eventos (para len()==0 sin crash)."""
    cols = ["entry_index", "entry_ts", "entry_price", "stop_price",
            "target_price", "direction", "exit_index"]
    df = pd.DataFrame({c: [] for c in cols})
    df["entry_index"] = df["entry_index"].astype("int64")
    df["direction"] = df["direction"].astype("int64")
    return df
