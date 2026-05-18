# CONSTRAINTS.md — Invariantes del Motor FQ

Este archivo define las reglas duras del motor Fibonacci Cuántico que NO pueden 
ser violadas por ninguna extensión, refactor o integración de conocimiento externo.

Cualquier propuesta de cambio que rompa una de estas reglas debe ser marcada 
explícitamente como CONFLICTO y requiere aprobación manual antes de implementarse.

---

## 1. Invariantes operativas (6 reglas core, intocables)

1. **Ventana de sesión**: solo se opera en London, NY u Overlap (07:30–10:00 CDMX). 
   Asia queda excluida salvo override explícito documentado.
2. **CHoCH obligatorio**: ninguna entrada puede ejecutarse sin Change of Character 
   confirmado previo. f_CHoCH = φ = 1.618 solo si está confirmado.
3. **Mínimo 2 toques Fibonacci**: f_Fib requiere n_touches ≥ 2. Capeado en 1.35.
4. **SL inmovible**: el Stop Loss nunca se mueve una vez colocado. Ni trailing, 
   ni breakeven manual, ni "darle chance". Nunca.
5. **Leverage cap**: máximo 5x en operativa estándar. En v4.1, 8x es techo absoluto 
   solo si P_master justifica; scalp a 3x cuando P < φ².
6. **Umbral de entrada**: P_master ≥ 7/10 obligatorio. Sin excepciones.

## 2. Anclaje estructural del SL

- SL **debe** anclarse a nodos estructurales de P-Space (EMA50, soportes confirmados).
- SL **nunca** se ancla a Bollinger Bands (son targets de liquidity hunt, no soportes).
- Lección documentada: LONG $84.20 con SL en BB → hit $83.79, −$77 USDT (15 abr 2026).
- Fórmula vigente: `SL = entry × (1 − fib × (1 − φ⁻¹))`

## 3. Kill-switch Θ(D) — v4.1

Tres decoherencias simultáneas deben validarse. Si alguna falla, **P_master = 0**:

- Macro: BTC y ETH alineados en 15m con la dirección propuesta.
- MAs: ≥11/13 medias móviles alineadas en 5m + 15m.
- RSI: regime alignment en triple timeframe RSI(6/12/24).

κ(p) requiere ≥3 confluencias de masa en P-Space.

## 4. Constantes matemáticas (no redefinir)

- φ = 1.6180339887
- φ² = 2.618
- φ⁻¹ = 0.618
- α = 1/137.507 = 0.00727
- B = φ²/α + e + π = 364.6247
- ∠φ = 137.507°
- h = φ√(3/4) = 1.401258

## 5. Ecuación maestra (v3.0, base)

`P_master = P_base · W_session · (1 + α·|Ψ|²) · f_CHoCH · f_Fib · f_RSI · f_node`

Pesos de sesión: Asia 0.50 | London 0.80 | NY 1.00 | Overlap 1.20

Cualquier término nuevo propuesto desde los PDFs debe:
- Justificar matemáticamente su inserción
- No reescalar los pesos existentes
- Documentar el rango esperado del factor

## 6. TPs

- TP1 = entry × (1 + fib × φ⁻¹)
- TP2 = entry × (1 + fib × φ)
- v4.1: extensiones escalonadas en φ⁻¹, φ⁻², φ⁻³

## 7. Reglas de integración para extracciones

Cuando se proponga incorporar contenido de los PDFs:

- **NO** agregar nuevas dependencias sin justificar.
- **NO** modificar firmas de funciones públicas del motor sin marcar como BREAKING.
- **NO** introducir constantes que choquen con las del §4.
- **NO** reescribir módulos completos. Solo extender vía nuevos archivos o funciones aditivas.
- **SÍ** documentar de qué PDF y página viene cada fórmula/concepto integrado.

## 8. Estilo de código

- Mantener la convención del motor actual (revisar `/src/` antes de proponer).
- Comentarios en español para lógica de negocio, inglés para utilidades técnicas.
- Tests obligatorios para cualquier fórmula nueva incorporada.