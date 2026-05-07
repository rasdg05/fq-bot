# FQ v4.1 Signal Bot — RasDG_Sol

Bot de señales de trading basado en el sistema **Fibonacci Cuántico v4.1**.

Monitorea SOL/USDT perpetual en Binance cada 15 minutos y envía señales a Telegram únicamente cuando se cumple el gate de decoherencia 3/3 + confluencia P-Space + ruptura de armonicidad Laplaciana.

## Filosofía

> "Solo unas pocas señales por día. Calidad sobre cantidad. Theta(D) = 0 → no trade."

## Variables de entorno requeridas

```
TELEGRAM_TOKEN     = token del bot de Telegram
TELEGRAM_CHAT_ID   = tu chat ID
```

## Reglas FQ v4.1 implementadas

- **Theta(D) gate 3/3**: macro (BTC+ETH) + técnica (>=5/7 MAs) + liquidez (RSI multi-período)
- **P-Space**: requiere >=2 masas en confluencia
- **Laplaciano discreto**: ruptura armonicidad como factor multiplicador
- **W_clock**: ponderación por sesión CDMX (Asia 0.5 / London 0.8 / NY 1.0 / Overlap 1.2)
- **Ventana operativa**: 05:00 - 17:00 CDMX
- **Cooldown**: 2 horas mínimo entre señales
- **TPs divinos**: phi^-2, phi^-1, phi (TP3 = TP DIVINO), phi extendido
- **R:R TP divino mínimo 2.0** o no se envía señal

## Deployment

Diseñado para Railway. Push a GitHub → Railway lo detecta automáticamente.

#FQv41 #RasDG
