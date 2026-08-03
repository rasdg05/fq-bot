Muestras de la Fase 0 (JSONL comprimido, una linea por muestra y mercado).
Las escribe .github/workflows/pm_probe.yml cada 3 horas.
Se leen con: python -m pm.analyze --bankroll 500

Cuando la Fase 0 cierre y haya veredicto, este directorio se puede borrar.
