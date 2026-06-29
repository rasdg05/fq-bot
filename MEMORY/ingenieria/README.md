# Ingeniería — la ecuación del motor (memoria de proceso)

> Para cualquier agente/persona que toque el motor: ésta es la **ecuación completa de FQ, de la
> vela al disparo**, extraída del código real (`fusion_engine._compute_p_master_refined` +
> `evaluate_signal`). El PDF (`ecuacion-fq.pdf`) es la versión visual; abajo está en texto para
> que se pueda leer sin renderizar.

## El pipeline (de inicio a fin)
1. **Input** — OHLCV multi-TF: primario (5m) + contexto 4h/1h + sub-TF. Indicadores **causales** (sin look-ahead).
2. **FieldState** — sesgo(4h,1h) · liquidez(barridos, zona Premium/Discount) · confluencia(Fibonacci, order-blocks, FVG) · killzone(sesiones ICT) · CHoCH · conceptos ICT.
3. **Gates A→D** (vetan): A sesgo alineado → B liquidez → C confluencia ≥ 3 (+ toques fib) → D killzone/CRT/memoria.
4. **Ecuación maestra** — se computa `P_master` (convicción).
5. **Fase E (tiempo emergente)** — Monte-Carlo de cientos de trayectorias → `sync_score` → dilatación `σ_τ` sobre P_master y el horizonte, + P(stop) y E[R].
6. **Disparo**.
7. **Overlays validados** — CVD✓ · F2-persist✓ · KL-bajo (Calidad) → broadcast VIP.

## La ecuación maestra (P_master)
```
P_raw    = φ · w_eff · h_lap · [1 + 0.15·(N − 2)] · f_confl · f_ICT
P_master = P_raw · κ_evo · σ_τ · v_vol · b_sesión
```
| término | qué es |
|---|---|
| **φ** | 1.618… razón áurea — escalar base de convicción |
| **w_eff** | peso de timing (híbrido reloj ↔ killzone): el "cuándo" |
| **h_lap** | check Laplaciano de estructura (1.0 válido · 0.7 si no) |
| **N** | nº de masas de confluencia · **f_confl** = factor de confluencia (≥3 zonas) |
| **f_ICT** | 1 + n_conceptos · bonus (order-blocks, FVG, liquidez… capeado) |
| **κ_evo** | **memoria aprendida** del bucket (Thompson/forward) — lo único que aprende del registro |
| **σ_τ** | dilatación de tiempo emergente (Fase E, Monte-Carlo de sincronía) |
| **v_vol** | modulador de calidad de volumen [0.75 – 1.20] |
| **b_sesión** | sesgo de sesión (London/NY/Asia × bias diario) |

## La condición de disparo
```
DISPARO  ⟺  (Fase A ∧ B ∧ C ∧ D ✓)  ∧  (P_master ≥ P_min)  ∧  (R:R ≥ RR_min)
```
…y **solo difunde a VIP** si además pasa el overlay validado: **CVD✓ · F2✓ · KL-bajo (tier Calidad)**.

## La distinción que NO se debe olvidar (anti-humo)
`P_master` es el **motor de convicción** — la calidad del setup (ICT/estructura/φ). **El edge que
pasó el gate (DSR) es el OVERLAY:** CVD (order-flow), F2 (persistencia), KL (régimen). O sea:
P_master decide qué tan bueno SE VE el setup; los edges validados deciden si la **estadística** lo
respalda. Marketing solo afirma sobre el overlay validado, no sobre P_master suelto
(ver `../ROLES/MARKETING.md`).

> Pointers: `../ROLES/INGENIERIA.md` (invariantes) · `../CEMENTERIO.md` (validado vs muerto) ·
> el código fuente `fusion_engine.py`.
