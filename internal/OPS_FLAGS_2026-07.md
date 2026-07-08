# Ops — flags de Railway (sesión 2026-07-08)

> Referencia de las variables de entorno nuevas/relevantes tras la sesión NASDAQ + cross-asset +
> arreglos de portal. Todas default OFF → byte-idéntico hasta encenderlas. Se ponen en Railway →
> servicio `worker` → Variables.

## Producto en vivo (cripto VIP/FREE)

| Flag | Default | Qué hace | Recomendado |
|---|---|---|---|
| `FQ_CROSS_ASSET` | OFF | Badge "NASDAQ CONFIRMA" + bump de convicción cuando la señal cripto se alinea con el move 6h de NASDAQ (validado OOS: alineada +0.431R vs contra +0.169). Lee NASDAQ de `FQ_NASDAQ_URL`. | `=1` para medir forward |
| `FQ_NASDAQ_URL` | Yahoo chart 5m ^NDX | Fuente de la dirección de NASDAQ (proxy gratis). | dejar default; cambiar si Yahoo bloquea |
| `FQ_FREE_TO_VIP` | OFF | Manda TODO el stream FREE (pares cosecha) al VIP/trial etiquetado 'Señal FREE' (NO al admin). "Los VIP ven todo." | `=1` si quieres que VIP vea las cosecha |
| `FQ_FREE_TIER` | **ON** | Entrega la flota FREE (10 cosecha) a usuarios tier free de la BD. | dejar ON |
| `FQ_KL_THR` | 0.34 | Umbral del filtro KL de cadencia VIP. 0.40 = más señales, mismo edge OOS (GATE-A). | `=0.40` (dial validado) |

## Ruido del portal (calma admin — sesión "no quiero un desmadre")

| Flag | Default | Qué hace |
|---|---|---|
| `FQ_MOTOR_PAPER_NOTIFY` | **OFF** | Push "🧪 Motor base (paper)" por cada apertura paper. OFF = silencio (el digest agregado y el fire free siguen). `=1` solo para depurar. |
| `FQ_FREE_ADMIN_ECHO` | ON | Echo "📤 FREE · N entregada(s)" al admin — pero SOLO si N>0 (embudo vacío → silencio). |
| `FQ_REGIME_TAGS` | OFF | Estampa kl_low/irrev/funding en el ledger del motor paper (enriquece el forward). | `=1` recomendado |

## Notas
- El **embudo free está vacío** (0 usuarios tier free en la BD) — la flota transmite a nadie hasta
  que entre gente al bot en modo free (marketing, no código).
- **Precios**: el bug DOGE ($0.07=$0.07=$0.07) está arreglado — decimales dinámicos por magnitud.
- **NASDAQ como producto propio**: aún NO desplegado (necesita feed tick en vivo); lo que SÍ está
  cableado es el cross-asset (usa solo la DIRECCIÓN de NASDAQ, proxy gratis).
- Rotar la **API key de Databento** (expuesta en chat) sigue pendiente.
