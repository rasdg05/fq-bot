# HANDOFF — estado de soft launch

## Veredicto

**SOFT_LAUNCH_READY** para la superficie construida, con el alcance declarado
abajo. `npm run validate` → `verdict: PASS` (V1–V24 + RT/1–RT/10).

## Checklist de soft launch

- [x] Wallet: crear (primario) y conectar (secundario), con error accionable
- [x] Feed con Edge visible, regla de 4 pp aplicada en dominio
- [x] Detalle de mercado con criterio de resolución antes del CTA
- [x] Iniciar depósito (tarjeta / transferencia), con caída de proveedor cubierta
- [x] Portafolio vacío y con datos
- [x] Estados de error accionables en español, con reintento cuando aplica
- [x] Métricas móviles: targets ≥ 44 px, CTA en zona de pulgar, cero desborde
      horizontal a 390 px, contraste ≥ 4.5:1 en ambos temas

## Caminos documentados

**Camino feliz (con fondos).** Splash → promesa → crear wallet → depositar →
feed → detalle → lado → monto → operar → portafolio.

**Camino sin fondos (explore-before-fund).** Splash → promesa → crear wallet →
`Explorar mercados` → feed → detalle completo (incluido el criterio de
resolución) → intento de operar → hoja de depósito en contexto. En ningún punto
anterior se pide dinero, documento ni frase semilla.

## Presupuesto de activación

3 taps hasta el feed (`Empezar` → `Crear wallet` → `Explorar mercados`), splash
de 1.4 s y latencia de adapters medida en pruebas. Con 12 s de presupuesto
humano por paso el camino cabe holgadamente en los 75 s objetivo.

## Hallazgos del ciclo de audit que se volvieron regla

| Hallazgo | Severidad | Regla |
|---|---|---|
| Doble tap disparaba dos veces las acciones de dinero: el candado leía estado de React, que aún no había re-renderizado | Crítico | R-016 |
| Los colores de token con modificador de opacidad (`bg-bg/95`) no pintan fondo: header y tabs quedaban transparentes sobre el contenido | Crítico | R-017 |
| Un Edge negativo mostraba icono de tendencia al alza | Importante | R-018 |
| `onboarding_completed` podía marcarse sin haber llegado al feed | Importante | R-015 |
| El volumen se formateaba como `184.3 k$` | Menor | — (corregido en `compactUsd`) |

## Fuera de alcance (declarado, no omitido)

Order book nativo, market maker propio, comentarios y social, multi-idioma
completo, notificaciones push avanzadas, rediseño de marca fuera de tokens.
La ejecución es agregación: el copy del detalle lo declara explícitamente.

## Lo que falta antes de tocar dinero real

Esto es producto terminado sobre datos simulados. Antes del soft launch con
dinero hacen falta, fuera de esta superficie:

1. Implementar `MarketDataAdapter` y `WalletAdapter` contra proveedores reales
   (el contrato ya está cerrado; la UI no cambia).
2. Resolver custodia y marco legal por país, según `marca/vision_apuestas_wallet.md` §5.
3. Conectar `errorReporter` y `analyticsAdapter` a sinks reales
   (`error_reporting: true`).
4. Medir LCP/INP/CLS en dispositivos reales; los objetivos declarados
   (≤ 2.5 s / ≤ 200 ms / ≤ 0.1) todavía no están medidos en campo.
