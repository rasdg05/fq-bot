# Experimento measure-first: order-flow (CVD) en CME — MNQ / MGC

> El #1 del deep-search y el de MAYOR prior: es tu edge PROBADO (CVD pasó el gate en
> cripto) recomputado del libro propio del venue. NO reinventa nada — corre tu
> `validate_cvd_signed_flow.py` existente sobre datos de CME. Costo: **$0 de tu bolsa**
> (crédito gratis de Databento; los trades son chicos).

## La idea en una línea

Tu gate de CVD ya existe y consume `[ts, buy_vol, sell_vol]` por barra 5m. Falta UNA cosa:
ese parquet para MNQ/MGC, construido de los **trades firmados de CME** (Databento, Tag 5797
aggressor). El adaptador `tools/fetch_cvd_databento.py` (ya hecho + testeado) lo produce.
Entonces tu gate corre **sin tocar una línea**, ahora sobre TradFi.

## Tu parte: jalar los trades de Databento (crédito gratis)

1. Cuenta en databento.com → API key. Nuevos usuarios: **$125 de crédito**.
2. **Sondea el costo ANTES de bajar nada** (pay-as-you-go, medido por GB):

```python
import databento as db
c = db.Historical("TU_API_KEY")
q = dict(dataset="GLBX.MDP3", schema="trades", symbols=["MNQ.c.0"],
         stype_in="continuous", start="2021-01-01", end="2026-01-01")
print(c.metadata.get_cost(**q))     # <-- el $ exacto; trades de un micro 5y = pocos GB, dentro del crédito
```

3. Baja los trades (front-month continuo) y guárdalos:

```python
data = c.timeseries.get_range(**q)  # mismo q
df = data.to_df()                   # trae ts_event (ns), price, size, side ('B'/'A'/'N')
df.to_parquet("mnq_trades.parquet")
# repite para MGC:  symbols=["MGC.c.0"]  -> mgc_trades.parquet
```

`.c.0` = front-month continuo (Databento continuous symbology). El order-flow NO necesita el
libro completo MBO/L3 (eso es lo caro): **con `trades` basta para el CVD**. Escalas a MBP-10
sólo si el CVD pasa y quieres OFI multi-nivel.

### Oro (MGC/GC) — la decisión measure-first

El order-flow informativo vive en el contrato **líquido**: para oro es **GC (full-size, 100 oz)**,
no el micro. MGC y GC son el mismo oro (arbitraje los amarra), pero el micro tiene tape más
delgado. Entonces: **jala el CVD de GC, ejecutas en MGC.** (Igual para índices: CVD de NQ/ES,
ejecución en MNQ.) Pull:

```python
q_gold = dict(dataset="GLBX.MDP3", schema="trades", symbols=["GC.c.0"],   # GC líquido
              stype_in="continuous", start="2021-01-01", end="2026-01-01")
print(c.metadata.get_cost(**q_gold))
c.timeseries.get_range(**q_gold).to_df().to_parquet("gc_trades.parquet")
```

## Correr el gate (mi parte, ya lista)

```bash
# 1) trades CME -> schema CVD del bot (agrega 5m, firma por aggressor).
#    --notional recomendado en TradFi (size*price -> comparable entre instrumentos).
python tools/fetch_cvd_databento.py --in mnq_trades.parquet --out data/cme/cvd_MNQ.parquet --notional
python tools/fetch_cvd_databento.py --in gc_trades.parquet  --out data/cme/cvd_GC.parquet  --notional

# 2) el gate PROBADO, sin cambios, ahora sobre TradFi (CVD de GC contra entradas de oro)
python tools/validate_cvd_signed_flow.py \
    --cube <cube_TradFi_MNQ>.parquet --cvd data/cme/cvd_MNQ.parquet --tp tp4 --horizon 576
python tools/validate_cvd_signed_flow.py \
    --cube <cube_TradFi_MGC>.parquet --cvd data/cme/cvd_GC.parquet  --tp tp4 --horizon 576
```

Lee el veredicto: `DSR(confirmado) ... EDGE REAL ✓ (cablear)` o `NO pasa`. Igual que en cripto.

## ⚠️ El único punto de correctness

Verifica el encoding de `side` contra una muestra. Databento por defecto: `B`=buy-aggressor,
`A`=sell-aggressor (el adaptador ya asume eso). Sanity check: imprime unas filas de trades y
confirma que el CVD acumulado **sube cuando el precio sube**. Si sale invertido:

```bash
python tools/fetch_cvd_databento.py --in mnq_trades.parquet --out data/cme/cvd_MNQ.parquet --buy A --sell B
```

Es lo ÚNICO que puede invertir el signo; el resto es aritmética blindada por tests.

## Estado

- ✅ Adaptador + tests: `tools/fetch_cvd_databento.py`, `tests/test_fetch_cvd_databento.py`
  (5 verdes, incluye drop-in con `fetch_cvd.cvd_features`).
- ✅ Gate: `tools/validate_cvd_signed_flow.py` (YA existía — corre tal cual).
- ⏳ **Tu parte:** jalar los trades (crédito Databento) + el **cubo TradFi MNQ/MGC** (tu cosecha
  5y). Con esos dos, corres el veredicto en minutos.

*Prior ALTO: esto es lo más parecido a lo que ya sabes que funciona. Si el CVD firmado de CME
confirma dirección como en cripto, pasa el gate -> dormido -> forward en micros -> producto.*
