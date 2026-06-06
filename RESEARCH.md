# FQ — Harness de research (backtest / walk-forward / entrenamiento)

> Estado: **piezas puras y testeadas** (77 tests, sin red). La integracion con
> el motor real esta cableada (`bt_features` + `tools/run_research_real.py`):
> corre el MISMO `fusion_engine.evaluate_signal` del bot sobre el histgrico. Solo
> falta EJECUTARLO en el entorno del bot (Railway/local) con datos reales.

## Por que existe

Un fondo no compra un bot de senales; compra **edge verificable**: Sharpe,
out-of-sample, curva de equity con costes reales, y un track record que no
miente. Este harness convierte FQ de "servicio de senales" en "estrategia
investigable", y da la narrativa de atribucion honesta ("este modulo aporta;
este es peso muerto y se mata").

## El artefacto unico

El motor de replay historico produce **a la vez** cuatro cosas: el backtest, la
base out-of-sample, el dataset etiquetado para entrenar, y las metricas de
riesgo. No son cuatro proyectos: es uno.

## Modulos (planos, estilo del repo)

| Modulo | Etapa | Responsabilidad |
|---|---|---|
| `bt_data.py` | 1 | Descarga OHLCV historico multi-exchange (paginado, dedupe, gaps) -> Parquet. Mockeable sin red. |
| `bt_labeler.py` | 2 | Triple-barrier (Lopez de Prado): etiqueta cada senal {win,loss,timeout} + `pnl_r` + MFE/MAE. |
| `bt_walkforward.py` | 3 | Folds walk-forward con **purga + embargo** (sin fuga de etiquetas al test). |
| `bt_engine.py` | 4 | Backtest con **fees + slippage + funding** + sizing por riesgo -> trades netos + equity. |
| `bt_metrics.py` | 5 | Sharpe, Sortino, Calmar, max drawdown, profit factor, CAGR. Extiende `ledger_stats`. |
| `bt_train.py` | 6 | LightGBM sobre el walk-forward (OOS), AUC, importancia, expectancy por umbral. |
| `bt_ablation.py` | — | Poda de modulos por **supervivencia OOS**: baseline vs sin_M -> VIVE/MATAR. |
| `bt_features.py` | int | **Capa de integracion**: replay del motor REAL (fusion_engine.evaluate_signal) sobre el histgrico -> eventos + features que ve el bot. |

CLI: `tools/build_dataset.py` (descarga), `tools/research_demo.py` (pipeline
sintetico, plantilla), `tools/run_research_real.py` (**runner REAL**: cablea el
motor de produccion + ablacion por toggles de entorno).

## Flujo

```
bt_data → bt_labeler → bt_walkforward → bt_engine → bt_metrics
                                   ↘  bt_train (modelo OOS)
                                   ↘  bt_ablation (poda de modulos)
```

## Como correrlo con datos REALES (ya cableado)

La integracion esta hecha: `bt_features.replay_events` recorre el histgrico y
llama al MISMO `fusion_engine.evaluate_signal` del bot, registrando cada disparo
con sus niveles y features. `tools/run_research_real.py` orquesta todo. Corre en
el entorno del bot (Railway/local), donde estan los datos y las dependencias —
NO en un sandbox sin red.

```
# 1) datos (gratis; Binance Data Portal / ccxt). Una vez por TF.
python tools/build_dataset.py --symbol SOL/USDT --timeframe 15m --market swap --years 2 --exchanges binance
python tools/build_dataset.py --symbol SOL/USDT --timeframe 1h  --market swap --years 2 --exchanges binance
python tools/build_dataset.py --symbol SOL/USDT --timeframe 4h  --market swap --years 2 --exchanges binance
python tools/build_dataset.py --symbol SOL/USDT --timeframe 1m  --market swap --years 2 --exchanges binance

# 2) research completo: metricas OOS + modelo + poda de modulos
python tools/run_research_real.py --exchange binance --symbol SOL/USDT \
    --max-bars 96 --n-splits 8 --embargo 8
```

El runner produce: senales disparadas, etiquetado triple-barrier, metricas OOS
con costes, modelo LightGBM sobre walk-forward (AUC + importancia + expectancy
por umbral) y la poda de modulos. La **poda** re-corre el motor con cada modulo
apagado por env (`FQ_USE_SCORER=0`, `FQ_USE_REGIME=0`, `FQ_SESSION_BIAS=0`) y
compara la expectancy OOS: si apagarlo no empeora, el modulo es peso muerto.

Bloques internos (por si quieres armar tu propio script): replay (`bt_features`)
-> etiquetar (`bt_labeler.label_events`) -> folds (`bt_walkforward`) ->
backtest/metricas (`bt_engine`+`bt_metrics`) -> modelo (`bt_train`).

## Validacion contra el ledger

Las metricas de `bt_metrics` hablan el mismo idioma que `ledger_stats` (win_rate,
expectancy, profit_factor). La prueba de fuego ante un fondo: que la **equity en
vivo (ledger) coincida con la equity out-of-sample del backtest**. Esa
coincidencia es el producto.
```
