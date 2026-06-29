#!/usr/bin/env python3
"""probe_dukascopy — confirma que dukascopy-python sirve data TradFi PROFUNDA.

NO baja años. (1) resuelve los instrumentos (oro/plata/SP500/Nasdaq/oil) en la
librería, (2) prueba un fetch 5m reciente + uno de hace ~2 años (confirma que la
historia es profunda de verdad), (3) reporta. De-risk antes de construir el fetcher
completo + la cosecha. Corre en el runner (Hetzner) — datafeed.dukascopy.com.
"""
import sys
from datetime import datetime, timedelta, timezone

try:
    import dukascopy_python as dk
    from dukascopy_python import instruments as I
except Exception as e:
    print("IMPORT ERR (¿pip install dukascopy-python?):", e)
    raise SystemExit(1)

print("== Dukascopy probe ==")
print("dukascopy_python version:", getattr(dk, "__version__", "?"))
INTERVAL = getattr(dk, "INTERVAL_MIN_5", getattr(dk, "INTERVAL_MINUTE_5", None))
OFFER = getattr(dk, "OFFER_SIDE_BID", getattr(dk, "OFFER_SIDE_BIDS", None))
print("INTERVAL_MIN_5:", INTERVAL, "| OFFER_SIDE_BID:", OFFER)
print("atributos top-level (muestra):", [a for a in dir(dk) if a.isupper()][:12])

# resuelve instrumentos por keyword (robusto a cómo los nombre la librería)
TARGETS = {"oro(XAU)": "XAUUSD", "plata(XAG)": "XAGUSD", "sp500": "USA500",
           "nasdaq": "USA100", "wti": "LIGHT", "brent": "BRENT", "dow": "USA30"}
resolved = {}
allnames = [n for n in dir(I) if "INSTRUMENT" in n]
print("\n--- instrumentos (resolución por keyword) ---")
for label, kw in TARGETS.items():
    k = kw.upper().replace("_", "")
    matches = [n for n in allnames if k in n.upper().replace("_", "")]
    if matches:
        resolved[label] = matches[0]
        print("  %-10s -> %s%s" % (label, matches[0], "  (+%d más)" % (len(matches) - 1) if len(matches) > 1 else ""))
    else:
        print("  %-10s -> NO encontrado (kw=%s)" % (label, kw))

def _fetch(inst, d0, d1):
    return dk.fetch(inst, INTERVAL, OFFER, d0, d1)

print("\n--- profundidad de historia (5m) ---")
now = datetime.now(timezone.utc).replace(tzinfo=None)
for label in ("oro(XAU)", "sp500", "wti"):
    if label not in resolved:
        print("  %-10s sin instrumento" % label); continue
    inst = getattr(I, resolved[label])
    try:
        recent = _fetch(inst, now - timedelta(days=5), now)
        n_rec = len(recent)
    except Exception as e:
        print("  %-10s recent ERR: %s" % (label, str(e)[:90])); continue
    try:
        far = _fetch(inst, now - timedelta(days=730), now - timedelta(days=726))
        n_far = len(far)
        f0 = str(far.index[0]) if n_far else "—"
    except Exception as e:
        n_far, f0 = -1, "ERR:" + str(e)[:60]
    verdict = "HISTORIA PROFUNDA ✓ (hay data de hace 2 años)" if n_far and n_far > 0 else "🚩 sin 2 años"
    print("  %-10s  recientes(5d)=%-5d  hace~2años(4d)=%s  primero=%s  %s" % (
        label, n_rec, n_far, f0, verdict))
print("\nGuía: si hay barras de hace ~2 años -> Dukascopy SÍ sirve para cubos profundos.")
