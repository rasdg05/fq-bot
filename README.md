[README(2).md](https://github.com/user-attachments/files/27545241/README.2.md)
# FQ v4.1 Signal Bot — Bugatti + Claude Copilot (v3.1)

**Fibonacci Cuántico v4.1 — Emergent Time and Curved Price-Space**
Bot de señales para SOL/USDT perpetual con co-pilot Claude integrado.

> *"El mercado no está en un estado definido. Está en superposición de historias competidoras. Una señal solo existe cuando colapsan."*
> — RasDG_Sol

---

## Novedades v3.1: Claude Copilot

El bot ahora integra Claude (Anthropic API) como **co-pilot táctico** que ve exactamente lo que el bot ve, vela por vela. No reemplaza el gate matemático Θ(D) — lo afila.

### Lo que ve Claude en cada llamada

**Estado interno (FQ):**
- Precio, indicadores, masas P-Space, decoherencia 3/3, P_master, sesión, W_clock

**Estado externo (derivados perpetual):**
- Funding rate y interpretación cualitativa
- Open Interest y tendencia (delta % en últimas N velas)
- Long/Short ratio y posición vs extremos
- Order book walls (acumulaciones de liquidez en bid/ask)
- Presión de libro 0.5% (compradores vs vendedores)

**Eventos pre-detectados por el bot:**
- CHoCH (Change of Character) bullish/bearish
- Breakouts con confirmación de cuerpo y volumen
- Divergencias RSI bullish/bearish
- Volumen anómalo (>2.5× MA20)
- Patrones de vela: hammer, shooting star, engulfing

**Evolución temporal:**
- Últimas 5 velas con OHLCV, RSI, color, % cuerpo, deltas

### Modelos por contexto

| Trigger | Modelo | Costo aprox |
|---------|--------|-------------|
| `/claude` o `/ia` (manual) | Sonnet 4.5 | ~$0.005 |
| `/analisis` follow-up | Sonnet 4.5 | ~$0.005 |
| `/pspace` follow-up | Sonnet 4.5 | ~$0.005 |
| `/niveles` follow-up | Sonnet 4.5 | ~$0.005 |
| Señal P_master ≥ φ³ (auto) | **Opus 4.6** | ~$0.030 |

**Costo estimado uso intenso:** ~$1–2/día.

---

## Filosofía

Este bot no busca señales. **Espera la decoherencia.**

A diferencia de sistemas técnicos clásicos que producen un score escalar de "confianza", FQ v4.1 implementa un **gate booleano** basado en decoherencia cuántica generalizada (Hartle, Solvay 2005). El bot solo emite señal cuando tres narrativas históricas independientes — macro, técnica y liquidez — colapsan en una trayectoria consistente. Si cualquiera de las tres permanece en superposición, `P_master = 0` y no hay trade.

Claude opera **después** del gate, no antes. El gate es matemático, sin override. Claude es un segundo par de ojos calibrado que afila el setup ya validado.

El silencio es disciplina. Calidad sobre cantidad.

---

## Master Equation v4.1

```
P_master = Θ(D) · κ(p) · φⁿ · W_clock · H_Laplacian
```

| Símbolo | Significado | Pilar teórico |
|---------|-------------|---------------|
| `Θ(D)` | Gate de decoherencia (3/3 narrativas) | Hartle (2005) |
| `κ(p)` | Curvatura del P-Space por masas de liquidez | Oreste (2011) |
| `φⁿ` | Acoplamiento de leverage a convicción | Fibonacci |
| `W_clock` | Tiempo emergente por sesión | Page–Wootters |
| `H_Laplacian` | Armonicidad discreta del precio | Knill, Harvard (2020) |

Si `Θ(D) = 0` → `P_master = 0` → no trade. **Sin excepción. Sin override.**

---

## Comandos Telegram

| Comando | Función | Claude follow-up |
|---------|---------|:----------------:|
| `/status` | Estado del bot, mercado, última señal | — |
| `/analisis` | Análisis FQ completo en vivo | ✓ Sonnet |
| `/niveles` | Plan de entrada con triggers contextuales | ✓ Sonnet |
| `/pspace` | Masas P-Space + libro de órdenes | ✓ Sonnet |
| `/sesion` | Sesión activa, W_clock, calendario completo | — |
| `/macro` | Decoherencia macro BTC/ETH | — |
| `/claude` o `/ia` | Lectura táctica completa manual | ✓ Sonnet |
| `/about` | Fundamentos teóricos del sistema | — |
| `/help` | Lista de comandos | — |

---

## Configuración Railway

### Variables de entorno

```
TELEGRAM_TOKEN=<token del bot de @BotFather>
TELEGRAM_CHAT_ID=<chat ID del usuario o grupo>
ANTHROPIC_API_KEY=<sk-ant-... de console.anthropic.com>
```

> **Nota:** si `ANTHROPIC_API_KEY` no está configurada, el bot funciona normalmente sin Claude. Los comandos `/claude` y los follow-ups simplemente devolverán un mensaje de configuración.

### Estructura del repo

```
/
├── fq_bot_v3_1.py         ← punto de entrada principal
├── claude_integration.py  ← módulo de integración Anthropic
├── market_context.py      ← módulo de datos externos + eventos
├── requirements.txt
└── README.md
```

### Procfile (opcional)

```
worker: python fq_bot_v3_1.py
```

---

## Estructura de cuatro pilares

| # | Pilar | Implementación |
|---|-------|----------------|
| I | Decoherencia 3/3 | Tests independientes: macro (BTC/ETH 15m), técnica (7 indicadores), liquidez (RSI 6/12/24) |
| II | Tiempo emergente | `W_clock` dinámico por sesión: Asia 0.50, London 0.80, NY 1.00, Overlap 1.20 |
| III | P-Space curvado | Detección de masas con peso (estructurales 1.0, técnicas 0.6–0.7, volumen 0.9, psicológicas 0.7) |
| IV | Laplaciano discreto | Operador `D = d + d*` sobre la serie de cierres, ratio > φ activa H_lap |

---

## Parámetros operativos

| Parámetro | Valor | Justificación |
|-----------|-------|---------------|
| Par | SOL/USDT Perpetual | Liquidez alta, volatilidad operable |
| Exchange (datos) | OKX | Feed gratuito vía CCXT + endpoints de derivados |
| Timeframe | 15m | Balance entre ruido y oportunidad |
| Ventana operativa | **24 HORAS** | W_clock modula, no bloquea |
| Macro threshold | 0.08% | Filtra ruido <0.08% en 1h |
| P-Space mínimo | 2 masas | Requiere confluencia real |
| P_master mínimo | 2.618 (φ²) | Threshold de convicción |
| P_master alto (Opus) | 4.236 (φ³) | Trigger del co-pilot Opus |
| Cooldown | 2h | Previene over-trading |
| Leverage máximo | 8x (φ³-coupled) | Cap absoluto independiente de score |
| Eval intra-vela | minuto 12 | Captura setups antes del cierre |

### Tiers de leverage por convicción

| `P_master` | Tier | Leverage | Sizing | Co-pilot |
|------------|------|----------|--------|:--------:|
| ≥ φ³ (4.236) | Alta convicción | 8x | 10% equity | **Opus 4.6** |
| ≥ φ² (2.618) | Standard | 5x | 5% equity | — |
| ≥ φ¹ (1.618) | Scalp | 3x | 2% equity | — |

**Modulador Asia (W=0.50):** auto-reduce un escalón de leverage (8x→5x, 5x→3x) y mitad de sizing.

---

## Plan de entrada contextual (`/niveles`)

El bot detecta el sesgo estructural (momentum 5v + 20v + posición vs EMA50/EMA200) y según las masas P-Space cercanas decide entre tres modos operativos:

| Modo | Cuándo | Trigger |
|------|--------|---------|
| **PULLBACK** | Masa dentro de 0.5× ATR | Vela 15m de rechazo + volumen ≥ 1.3× MA20 |
| **BREAKOUT** | Masa dentro de 1.5× ATR (arriba/abajo) | Cierre 15m con cuerpo > 60% rango + volumen ≥ 1.5× MA20 + retest exitoso |
| **WAIT** | Sin masa cercana | Esperar pullback profundo a EMA50 o estructura |

Cada plan incluye: zona de espera, trigger preciso, confirmación en 3 puntos, invalidación con cierre 15m, plan B en dirección contraria. Después del plan FQ, **Claude lo afina** con su lectura.

---

## Reglas de oro (no negociables)

1. **Sin Θ(D) no hay trade.** El gate booleano no admite override. Claude no puede invalidarlo.
2. **El SL nunca se mueve hacia atrás** (Regla 4).
3. **El SL se ancla a estructura** (EMA50, soporte estructural), nunca a Bollinger envelopes.
4. **Sesgo estructural confirmado domina** — un CHoCH bajista no se anula con RSI alcista (Regla 6).
5. **Cooldown 2h entre señales** — previene cascadas emocionales.
6. **Leverage cap absoluto 8x** — independiente de cualquier score.
7. **La decisión final siempre es del trader.** Claude sugiere, RasDG decide.

---

## Stack técnico

- **Python 3.10+**
- `ccxt` — feeds de datos OKX
- `pandas` + `pandas-ta` — indicadores técnicos
- `requests` — Telegram Bot API + endpoints OKX adicionales
- `anthropic` — SDK oficial de Anthropic (Sonnet 4.5 + Opus 4.6)
- Threading: 1 hilo principal (eval) + 1 hilo listener (comandos)

---

## Disclaimer

Este bot es una herramienta de análisis personal del autor. No es asesoría financiera. Trading con leverage involucra riesgo de pérdida total. El usuario es responsable de sus propias decisiones operativas. Claude es un asistente de IA — sus interpretaciones son sugerencias, no instrucciones.

---

## Licencia

Propietario — RasDG_Sol. Uso personal.

#FQv41 #BugattiEdition #ClaudeCopilot #RasDG
