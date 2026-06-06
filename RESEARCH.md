# FQ — Harness de research (backtest / walk-forward / entrenamiento)

> Estado: **piezas puras y testeadas** (68 tests). Corren sin red. El paso que
> falta es de **integracion**: enchufar datos historicos reales y el pipeline de
> features real del motor. Hasta entonces, el harness se valida con datos
> sinteticos (ver `tools/research_demo.py`).

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

CLI: `tools/build_dataset.py` (descarga), `tools/research_demo.py` (pipeline
completo sintetico, plantilla de integracion).

## Flujo

```
bt_data → bt_labeler → bt_walkforward → bt_engine → bt_metrics
                                   ↘  bt_train (modelo OOS)
                                   ↘  bt_ablation (poda de modulos)
```

## Como pasar de sintetico a REAL (integracion pendiente)

1. **Datos** (gratis): `python tools/build_dataset.py --symbol SOL/USDT
   --timeframe 1m --market swap --years 2 --exchanges binance,bybit`. Fuente
   recomendada para histgrico completo: Binance Data Portal (data.binance.vision).
2. **Features**: reutilizar `fq_market_data.add_indicators` + `ict_smc` sobre las
   velas historicas para construir, por cada vela candidata, el mismo vector de
   features que el motor ve en vivo.
3. **Eventos**: definir las senales candidatas (cuando el motor dispararia) con
   su `entry_index`, `entry_price`, `stop_price`, `target_price`, `direction`.
4. **Etiquetar** con `bt_labeler.label_events` sobre las velas futuras.
5. **Folds** con `bt_walkforward.folds_from_labeled`.
6. **Backtest/metricas** con `bt_engine.simulate` + `bt_metrics`.
7. **Modelo** con `bt_train.train_walk_forward` (features reales).
8. **Poda**: expresar cada modulo del motor (`session_bias`, `regime_detector`,
   QTE, `volume_quality`, ...) como una mascara `df -> bool` y correr
   `bt_ablation.run_ablation`. Matar lo que no sobrevive OOS.

## Validacion contra el ledger

Las metricas de `bt_metrics` hablan el mismo idioma que `ledger_stats` (win_rate,
expectancy, profit_factor). La prueba de fuego ante un fondo: que la **equity en
vivo (ledger) coincida con la equity out-of-sample del backtest**. Esa
coincidencia es el producto.
```
