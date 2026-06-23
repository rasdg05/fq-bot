# -*- coding: utf-8 -*-
"""
measure_engine_edge.py - La pregunta final: el MOTOR REAL bate el breakeven?

Los cosecha_cubes son las setups evaluadas por el fusion_engine real sobre
historico, con outcome (pnl_r) y todos los scores internos. Aca medimos la
expectancy de las senales que el motor DISPARO (fired), con costos exactos por
trade (fee en R = fee*entry/|entry-stop|), split IS/OOS, y el gradiente por
confluencia/p_master (la seleccion del motor concentra edge?).

vs el sprint anterior: los factores naive tocaban ~0R (breakeven). La pregunta:
el stack completo, disparando selectivo, cruza a positivo y ESTABLE IS<->OOS?

Pure numpy/pandas. CONSTRAINTS 7.
"""
import numpy as np
import pandas as pd

CUBES = {"SOL": "cosecha_cubes/tp_cube_SOL_USDT.parquet",
         "BTC": "cosecha_cubes/tp_cube_BTC_USDT.parquet"}
FEE_MAKER = 0.0004   # round-trip ~4 bps (maker OKX)
FEE_TAKER = 0.0010   # round-trip ~10 bps (taker)
OOS_FRAC = 0.30


def load():
    frames = []
    for s, p in CUBES.items():
        df = pd.read_parquet(p)
        df["symbol"] = s
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def st(R):
    R = np.asarray(R, float); R = R[np.isfinite(R)]
    if len(R) == 0:
        return None
    gp = R[R > 0].sum(); gl = -R[R < 0].sum()
    return dict(n=len(R), wr=(R > 0).mean(), exp=R.mean(),
                pf=(gp / gl if gl > 0 else np.inf), sumR=R.sum(),
                sh=R.mean() / (R.std() + 1e-9))


def show(tag, R):
    s = st(R)
    if s:
        print(f"  {tag:<22} n={s['n']:>6} exp={s['exp']:+.3f}R wr={s['wr']:.1%} "
              f"PF={s['pf']:.2f} sumR={s['sumR']:+.0f} Sh/t={s['sh']:+.3f}")
    else:
        print(f"  {tag:<22} (sin trades)")


def main():
    df = load()
    print(f"cube total: {len(df)} filas | cols outcome: fired/decision/pnl_r/outcome")
    print(f"  fired: {df.fired.value_counts().to_dict()}")
    if "decision" in df:
        print(f"  decision: {df.decision.value_counts().to_dict()}")
    if "outcome" in df:
        print(f"  outcome: {df.outcome.value_counts().to_dict()}")

    f = df[(df.fired == True) & df.pnl_r.notna()].copy()
    f["entry_ts"] = pd.to_datetime(f.entry_ts)
    span_days = (f.entry_ts.max() - f.entry_ts.min()).days or 1
    print(f"\nSENALES DISPARADAS: {len(f)} | {f.entry_ts.min().date()} -> {f.entry_ts.max().date()} "
          f"({span_days}d, ~{len(f)/span_days:.1f}/dia)")

    # fee exacto por trade (en R)
    risk = (f.entry_price - f.stop_price).abs()
    fee_maker_R = (FEE_MAKER * f.entry_price / risk.replace(0, np.nan)).clip(0, 2)
    fee_taker_R = (FEE_TAKER * f.entry_price / risk.replace(0, np.nan)).clip(0, 2)

    print("\n== EXPECTANCY GLOBAL (motor real, fired) ==")
    show("bruto (sin fee)", f.pnl_r)
    show("neto MAKER (~4bps)", f.pnl_r - fee_maker_R)
    show("neto TAKER (~10bps)", f.pnl_r - fee_taker_R)

    # IS/OOS por simbolo
    f["net_m"] = f.pnl_r - fee_maker_R
    splits = f.groupby("symbol").entry_ts.transform(lambda x: x.quantile(1 - OOS_FRAC))
    f["seg"] = np.where(f.entry_ts < splits, "IS", "OOS")
    print("\n== IS / OOS (neto maker) ==")
    show("IS", f[f.seg == "IS"].net_m)
    show("OOS", f[f.seg == "OOS"].net_m)
    for s in CUBES:
        sub = f[f.symbol == s]
        oos = st(sub[sub.seg == "OOS"].net_m); isn = st(sub[sub.seg == "IS"].net_m)
        if oos and isn:
            print(f"    {s}: IS exp={isn['exp']:+.3f} (n={isn['n']}) | OOS exp={oos['exp']:+.3f} (n={oos['n']})")

    # gradiente por confluencia del motor
    if "field_confluence_count" in f:
        print("\n== gradiente por field_confluence_count (neto maker, OOS) ==")
        oo = f[f.seg == "OOS"]
        for c in sorted(oo.field_confluence_count.dropna().unique()):
            show(f"conf={int(c)}", oo[oo.field_confluence_count == c].net_m)

    # gradiente por p_master
    if "p_master" in f:
        print("\n== gradiente por p_master (neto maker, OOS, terciles) ==")
        oo = f[f.seg == "OOS"].copy()
        q = oo.p_master.quantile([0, 1/3, 2/3, 1.0]).to_numpy()
        for k, lab in enumerate(["bajo", "medio", "alto"]):
            seg = oo[(oo.p_master >= q[k]) & (oo.p_master <= q[k+1])] if k == 2 else oo[(oo.p_master >= q[k]) & (oo.p_master < q[k+1])]
            show(f"p_master {lab}", seg.net_m)


if __name__ == "__main__":
    main()
