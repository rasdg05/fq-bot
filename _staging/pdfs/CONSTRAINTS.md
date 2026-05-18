# CONSTRAINTS.md — Invariantes del Motor FQ

Este archivo define las reglas duras del motor Fibonacci Cuántico que NO pueden 
ser violadas por ninguna extensión, refactor o integración de conocimiento externo.

Cualquier propuesta de cambio que rompa una de estas reglas debe ser marcada 
explícitamente como CONFLICTO y requiere aprobación manual antes de implementarse.

---




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
