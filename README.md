[README_DEPLOY.md](https://github.com/user-attachments/files/27770355/README_DEPLOY.md)
# FQ v4.1.1 — Refactor ICT/SMC

Capa interpretativa estructural sobre el motor matemático FQ v4.1, sin tocarlo.

## Archivos del refactor

| Archivo | Acción |
|---|---|
| `ict_smc.py` | **Nuevo.** Subir a la raíz del repo Railway. |
| `killzones_pd.py` | **Nuevo.** Subir a la raíz. |
| `fusion_engine.py` | **Nuevo.** Subir a la raíz. |
| `field_reports.py` | **Nuevo.** Subir a la raíz. |
| `fq_bot_v3_2.py` | **Reemplaza el actual.** Tiene `_evaluate_setup_v411` y delegate condicional. |
| `entropy_cognition_patch.py` | **Patch.** Pegar el bloque al final de `entropy_cognition.py` existente. |

## Despliegue por fases (feature flags)

Todas las variables de entorno arrancan en `0`. El bot mantiene comportamiento legacy hasta que enciendas un flag.

### Modo 1 — Producción intacta (default)
```
FQ_ENABLE_ICT=0
FQ_ENABLE_FIELD=0
```
El bot opera exactamente como v3.2. Cero cambio.

### Modo 2 — ICT layer ON, sin reportes de campo
```
FQ_ENABLE_ICT=1
FQ_ENABLE_FIELD=0
```
- `evaluate_setup` delega a `fusion_engine.evaluate_signal`.
- Las 4 fases A/B/C/D filtran antes de calcular `P_master`.
- Si pasa: dispara señal con plantilla Capa 5 (`build_signal_report`).
- Si falla: silencio (como v3.2 cuando los gates no pasan).

### Modo 3 — Lectura de campo activa
```
FQ_ENABLE_ICT=1
FQ_ENABLE_FIELD=1
```
- Igual al Modo 2, pero además emite **reportes de campo** cuando fase A/B/C/D falla.
- Reportes solo a admin/VIP (no al free tier).
- Permite ver QUÉ está mirando el bot incluso cuando no dispara.

### Modo 4 — Comando manual `/campo`
Disponible siempre que `FQ_ENABLE_ICT=1`. Devuelve lectura on-demand del estado del campo sin disparar señal.

## Migración del schema SQLite

Idempotente. En `main()` se llama `ev.migrate_schema_v2()` automáticamente al arrancar. Agrega columnas v2 (`killzone`, `pd_zone`, `pd_hierarchy`, `confluence_count`, `bias_4h`, `bias_1h`, `bucket_key_v2`, etc.) sin tocar las viejas. Si las columnas ya existen, no falla.

## Híbrido `w_clock` ↔ `w_killzone`

Decisión adoptada del Punto 3. El sistema arranca usando 100% `w_clock_legacy` (asia/london/ny/overlap) y migra gradualmente a `w_killzone` (silver_bullet_lo/ny, london_open_kz, ny_am_kz, etc.) conforme acumula señales cerradas con bucket key v2:

```
alpha = max(0, 1 - n_closed_v2 / 50)
w_effective = w_clock_legacy * alpha + w_killzone * (1 - alpha)
```

Cuando llegues a 50 cerradas con buckets v2, `alpha = 0` y el bot opera 100% por killzones. **No requiere intervención manual.**

## Cierre del loop — memoria de outcome

Fase D del agente carga `BucketMemory` del bucket actual (killzone × tier × dirección × pd_zone × hierarchy) y rechaza la señal si:
- `confidence == "active"` (≥16 cerradas) AND `win_rate < 30%`
- O hay racha de 4+ pérdidas consecutivas

El sistema ahora **usa** su historia, no solo la guarda.

## Riesgos / mitigación

- **Si fusion_engine falla** → `_evaluate_setup_v411` captura la excepción y devuelve `False`. El bot continúa sin disparar pero no crashea.
- **Si los módulos nuevos no se encuentran** → `ICT_MODULES_AVAILABLE = False`, el delegate no se activa, flujo legacy intacto.
- **Si las columnas v2 ya existen** → `migrate_schema_v2` ignora silenciosamente y continúa.
- **Si bucket v2 está vacío** → `kappa_evo = 1.0` neutral, no afecta P_master.

## Próximas señales

Cuando enciendas `FQ_ENABLE_ICT=1`, recibirás en Telegram el formato Capa 5 completo con:
- Estado del campo (sesgo 4H+1H, zona PD, alineación)
- Liquidez (pools sup/inf, sweeps recientes con/sin reacción)
- Nodo en observación (confluencia ICT listada elemento por elemento, jerarquía PD, tipo colapso/superposición)
- Matemática cuántica (W_killzone, W_legacy, W_effective con alpha, f_confluencia, kappa_evo)
- Veredicto de fase + memoria del bucket
- Acción con SL anclado a EMA50 y TPs por φ

## Comandos nuevos

| Comando | Función |
|---|---|
| `/campo` | Lectura on-demand del estado del campo (requiere `FQ_ENABLE_ICT=1`) |

Los demás (`/metrics`, `/entropy`, `/ledger`, `/evolve`, `/audit`) siguen funcionando como antes — y los buckets v2 empezarán a alimentarlos automáticamente.

#FQv411 #ICTSMC #RasDG
