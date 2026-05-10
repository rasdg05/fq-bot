[README(3).md](https://github.com/user-attachments/files/27565137/README.3.md)
# FQ v4.1 Signal Bot v3.2 — Bugatti + Claude + Evolution Patch

**Fibonacci Cuántico v4.1 — Emergent Time and Curved Price-Space**
Bot de señales para SOL/USDT perpetual con co-pilot Claude integrado y cognición entrópica autoevolutiva.

> *"El sistema no recuerda. Destila."*
> — RasDG_Sol

---

## Novedades v3.2: Evolution Patch

El bot ahora destila cada señal en distribuciones de buckets, mide la entropía de Shannon sobre el portfolio de setups, y modula P_master con un coeficiente `kappa_evo` (±15%) basado en desempeño histórico. Cada 25 señales cerradas, Opus 4.6 audita el ledger completo y propone ajustes.

**El gate Θ(D) sigue siendo veto absoluto.** El parche evolutivo opera POST-gate, no PRE-gate.

### Lo que hace el módulo de cognición entrópica

**Ledger persistente (SQLite):**
- Cada señal se registra con su contexto: dirección, niveles, P_master raw y final, kappa_evo aplicado, sesión, tier de convicción, indicadores, decoherencia
- Outcome tracker: monitorea cada señal contra velas posteriores hasta que toca TP1/2/3/4, SL, o timeout (8h)
- Backup automático del .db a Telegram cada 10 señales totales

**Entropía de Shannon sobre buckets dimensionales:**
- Bucket key: `sesion | tier | direccion | curvatura`
- H_total: 0 = sistema colapsado en 1 setup, 1 = exploración sana
- Marginales por dimensión (sesión, tier, dirección, curvatura)
- KL divergence entre últimas 25 señales y las 25 anteriores → detecta drift de régimen

**Modulador κ_evo (post-gate):**
- Calcula expectancy R por bucket sobre señales cerradas
- Si `n ≥ 8` cerradas en el bucket: aplica modulador suave en `[0.85, 1.15]`
- Mapeo lineal: expectancy +1.5R → κ=1.15, expectancy −1.5R → κ=0.85
- Si bucket vacío o `n < 8`: κ=1.0 (neutral, no modula)

**Self-audit Opus cada 25 cerradas:**
- Le pasa a Opus: WR global, expectancy, profit factor por tier, top 5 buckets ganadores y perdedores, entropía por dimensión, drift KL
- Opus diagnostica: atractores tóxicos, edges ocultos, sobreajuste, deriva de régimen
- Sugerencias concretas con números (subir/bajar PMASTER_MIN, ajustar cooldown)
- **Sugerencias, no instrucciones** — RasDG aplica manualmente

---

## Master Equation v4.1 (con Evolution Patch)

```
P_master_raw   = Θ(D) · κ(p) · φⁿ · W_clock · H_Laplacian
P_master_final = P_master_raw · κ_evo
```

| Símbolo | Significado |
|---------|-------------|
| `Θ(D)` | Gate de decoherencia (3/3 narrativas) — **veto absoluto, no se modula** |
| `κ(p)` | Curvatura del P-Space por masas de liquidez |
| `φⁿ` | Acoplamiento de leverage a convicción |
| `W_clock` | Tiempo emergente por sesión |
| `H_Laplacian` | Armonicidad discreta del precio |
| `κ_evo` | **NUEVO**: modulador entrópico [0.85, 1.15] basado en historia del bucket |

Si `Θ(D) = 0` → `P_master = 0` → no trade. **κ_evo no puede activar una señal que el gate ya rechazó.**

---

## Comandos Telegram

### Operativos (heredados v3.1)

| Comando | Función |
|---------|---------|
| `/status` | Estado del bot, mercado, última señal |
| `/analisis` | Análisis FQ + lectura Sonnet |
| `/niveles` | Plan de entrada + afinación Sonnet |
| `/pspace` | Masas P-Space + libro + lectura Sonnet |
| `/sesion` | Sesión activa, W_clock, calendario |
| `/macro` | Decoherencia macro BTC/ETH |
| `/claude` o `/ia` | Lectura táctica manual |

### Evolution v3.2

| Comando | Función |
|---------|---------|
| `/metrics` | Win rate, expectancy R, profit factor por tier |
| `/entropy` | Shannon H + KL drift + distribuciones por dimensión |
| `/ledger` | Últimas 10 señales con outcome y PnL en R |
| `/evolve` | Buckets activos del modulador κ_evo |
| `/audit` | Trigger manual de self-audit Opus |

---

## Configuración Railway

### Variables de entorno (sin cambios)

```
TELEGRAM_TOKEN=<token del bot de @BotFather>
TELEGRAM_CHAT_ID=<chat ID del usuario o grupo>
ANTHROPIC_API_KEY=<sk-ant-... de console.anthropic.com>
FQ_LEDGER_PATH=/data/fq_ledger.db   # opcional, default /tmp/fq_ledger.db
```

> **Importante para Railway:** si quieres que el ledger sobreviva a redeploys, usa el plan con persistent volume y apunta `FQ_LEDGER_PATH` al mount path (ej. `/data/fq_ledger.db`). Si no, el ledger se borra en cada redeploy — pero el backup a Telegram cada 10 señales te da una copia de respaldo descargable.

### Estructura del repo

```
/
├── fq_bot_v3_2.py          ← punto de entrada principal (renombrar a fq_bot.py si quieres)
├── claude_integration.py   ← módulo Claude (sin cambios)
├── claude_evolution.py     ← NUEVO: adapter Claude para self-audit
├── entropy_cognition.py    ← NUEVO: ledger + entropía + κ_evo
├── market_context.py       ← módulo datos externos (sin cambios)
├── requirements.txt
└── README.md
```

`requirements.txt` no cambia — `sqlite3` es stdlib de Python.

---

## Parámetros operativos del Evolution Patch

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| `KAPPA_EVO_MAX` | 0.15 | Cap absoluto ±15% sobre P_master |
| `KAPPA_EVO_MIN_SAMPLES` | 8 | Mínimo de señales cerradas en bucket para modular |
| `AUDIT_EVERY_N_CLOSED` | 25 | Frecuencia de self-audit Opus |
| `OUTCOME_TIMEOUT_HOURS` | 8 | Una señal sin resolver se marca timeout |
| `BACKUP_EVERY_N_SIGNED` | 10 | Cada 10 señales totales, backup .db a Telegram |

### Tipos de outcome

| Outcome | Significado | PnL R |
|---------|-------------|-------|
| `tp1` | Tomó primer take profit | +0.6R aprox |
| `tp2` | Tomó TP2 | +1.5R aprox |
| `tp3` | Tomó TP divino (TP3) | +2.8R aprox |
| `tp4` | Tomó TP máximo | +variable |
| `sl` | Tocó stop loss | −1.0R |
| `timeout` | No resolvió en 8h, cierre al last close | variable |

> Importante: el tracker es **conservador**. Si en una vela tocan SL y TP, asume SL primero. Esto puede sub-reportar wins reales en mercados muy volátiles. Si esto te molesta, podemos refinar usando close > 50% del rango como heurística de "qué tocó primero", pero por ahora el conservador es más seguro para no inflar métricas.

---

## Reglas de oro (v3.2)

1. **Sin Θ(D) no hay trade.** El gate booleano es absoluto. κ_evo no lo invalida ni lo activa.
2. **κ_evo está capeado en [0.85, 1.15].** No puede mover P_master más del 15% en ninguna dirección.
3. **κ_evo sin data → 1.0.** Buckets con menos de 8 señales cerradas no modulan.
4. **El SL nunca se mueve hacia atrás.**
5. **El SL se ancla a estructura.**
6. **Sesgo estructural confirmado domina.**
7. **Cooldown 1h entre señales.**
8. **Leverage cap absoluto 8x (φ³).**
9. **Self-audit propone, no aplica.** Las sugerencias de Opus son lectura, no escritura.
10. **La decisión final siempre es del trader.**

---

## Cómo leer la salida del Evolution Patch

### `/metrics`
Te dice si el sistema gana plata. Si Profit Factor < 1.2 con n > 25, el edge es marginal o nulo.

### `/entropy`
- **H_total bajo (<0.5):** el sistema solo dispara en 1-2 setups → riesgo de sobreajuste, baja resiliencia
- **H_total alto (>0.85):** sistema explora buen abanico, buena diversificación
- **KL drift > 1.5:** el régimen de mercado cambió respecto a las 25 señales anteriores. Los buckets ganadores históricos pueden no servir hasta que se acumule data nueva
- **KL drift > 0.7 y < 1.5:** atención, shift moderado

### `/evolve`
Lista de buckets con su WR y expectancy. Los que tienen `[MOD]` están activamente modulando κ_evo. Los que tienen `[watch]` están juntando data.

### `/audit`
Lectura cualitativa de Opus sobre el ledger destilado. Léelo como auditoría, no como recomendación binding.

---

## Filosofía del Evolution Patch

El bot no aprende como un agente RL clásico. **El bot destila.**

Cada señal vive como un punto en un espacio de 4 dimensiones discretas (sesión × tier × dirección × curvatura). En lugar de memorizar trayectorias específicas (lo cual sería frágil), el sistema mide la distribución de resultados sobre cada celda del espacio. Si una celda acumula expectancy positiva con suficiente muestreo, el modulador la afila marginalmente. Si acumula expectancy negativa, la atenúa.

Esto se conecta directamente con la filosofía cuántica del FQ: el sistema no busca "predecir" cada vela. Busca caracterizar la distribución estadística sobre la cual el colapso (la señal) ocurre. La entropía de Shannon mide qué tan "delocalizada" está la actividad del bot — si todas las señales colapsan en el mismo bucket, el sistema está sobreajustado a un atractor y eso es exactamente lo que debe corregirse.

El silencio sigue siendo disciplina. La evolución no es señal nueva — es señal mejor.

---

## Disclaimer

Este bot es una herramienta de análisis personal del autor. No es asesoría financiera. Trading con leverage involucra riesgo de pérdida total. El usuario es responsable de sus propias decisiones operativas. Claude es un asistente de IA — sus interpretaciones son sugerencias, no instrucciones. El modulador κ_evo es post-gate y no puede invalidar el veto matemático del gate Θ(D), pero es un componente adaptativo y por lo tanto puede comportarse de formas no anticipadas en regímenes de mercado fuera de la distribución histórica del ledger.

---

## Licencia

Propietario — RasDG_Sol. Uso personal.

#FQv41 #BugattiEdition #ClaudeCopilot #EvolutionPatch #RasDG
