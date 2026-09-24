# CONTEXTO DE SESIÓN — 2026-09-24 · verificación por niveles + giro a Marea principal

> **Para la próxima conversación en frío.** Este archivo guarda todo el contexto de la sesión
> del 2026-09-24 para poder retomar sin releerla. Se lee después de la ruta de arranque en frío
> de `marea/vault/COLA_TRABAJO.md`. Cuando su contenido esté absorbido en `ESTADO.md` /
> `DECISIONES.md` / `COLA_TRABAJO.md`, este archivo se puede archivar.

## 1. Qué se hizo (rama `claude/marea-kyc-verification-tiers-cb7cx6`, 8 commits sobre `main`)

Origen: un colaborador (Evan) revisó el modelo de screening/KYC de Marea y propuso reglas. Se
cerró el lazo *hallazgo → regla → dominio puro con prueba*.

**Reglas nuevas en `marea/vault/RULINGS.md` (R-069…R-072):**
- **R-069 / L16** — el tope por nivel se hace cumplir donde vive el dinero; `min(cap_país, cap_nivel)`.
- **R-070** — anti-structuring: retiros sobre ventana móvil acumulada (30 días, valor de trabajo).
- **R-071** — screening de sanciones bidireccional; *rechazar no es confiscar*.
- **R-072** — lista cerrada de disparadores de KYC (tope, anti-structuring, subir de nivel).

**Dominio puro nuevo: `marea/src/domain/niveles.ts` (23 pruebas en `tests/niveles.test.ts`):**
- `ESCALERA` (N0–N3), `effectiveCapUsd`, `effectiveCapForUser` (R-069/L16).
- `detectStructuring` (R-070).
- `kycTrigger` (R-072), `screenDestino` (R-071).
- `evaluarOperacion` — la compuerta que compone las cuatro reglas en un punto.
- **No importa `eligibility.ts` ni abre la puerta**; recibe el tope de país por parámetro.

**Documentación sincronizada:** `NIVELES_VERIFICACION.md`, `VOICE.md` (recordatorio fiscal),
`ENCARGO_LEGAL.md` (P11→P18), maquetados `niveles-verificacion.html` + `planos-construccion.html`
(nuevo Plano 07) y sus PDF regenerados, `MEMORY/marea/README.md`, `MEMORY/ESTADO.md`.
`COLA_TRABAJO.md` reescrita para arranque en frío. `LINEA_BASE.md` creado.

**Estado de pruebas:** typecheck verde · suite **310 verdes / 6 rojas** (las 6 son preexistentes,
de catálogo caducado — ver `LINEA_BASE.md`; se arreglan con `npm run roll`, no con código).

**Commits (más reciente arriba):**
```
3d7152f U-V5 compuerta compuesta          4001dc0 U-V4 sync doc
063ec23 U-V3 KYC cerrado + screening      14ef8b2 U-V2 anti-structuring
d261ff7 U-V1 escalera + tope efectivo     52a156f cola arranque en frío
3706b1e sync maquetado niveles            f187950 cablea R-069…R-072 + planos
```

**Sin abrir PR ni mergear a `main`** (no se pidió). La rama está lista para PR o para el giro de §3.

## 2. Reglas y decisiones nuevas (ver `DECISIONES.md §22`)

- **Redeploy libre a producción para Marea** mientras no haya soft launch ni >10 usuarios activos,
  hasta que la plataforma o un dev diga lo contrario. **Acotada a Marea**: no toca el gate
  measure-first del bot ni su disciplina (el bot tiene suscriptores de pago). "Libre" ≠ "sin
  pruebas": suite y typecheck se corren igual.
- **Marea pasa a ser el proyecto principal**: `main` = Marea, el bot a su propia rama. Planificado,
  no ejecutado — se hace en esta conversación en frío (runbook abajo).

## 3. PRIMERA TAREA DE LA SESIÓN EN FRÍO — runbook del giro `main` → Marea

> **No ejecutar sin RasDG presente confirmando cada paso destructivo.** Toca la rama de
> despliegue de un producto vivo con suscriptores de pago.

**Situación de partida.** Hoy `main` contiene el repo entero (bot en la raíz + Marea en `marea/`).
Railway corre **dos servicios separados**:
- Bot: raíz, `python launcher.py`, `railway.toml` de la raíz (excluye `marea/**` de watchPatterns).
- Marea: Root Directory `marea`, `marea/railway.toml`.

Ambos servicios rastrean, hoy, la misma rama (`main`). "Que `main` sea Marea" es sobre todo un
cambio de **foco de proyecto y de a qué rama apunta cada servicio de Railway**, no un movimiento
de archivos (el monorepo puede quedarse como está).

**Opción recomendada (mínimo riesgo, sin reescribir historia):**
1. **Confirmar con RasDG** el nombre de la rama del bot (p. ej. `bot-senales` o `senales`).
2. Crear esa rama desde `main` actual y empujarla: `git branch bot-senales main && git push -u origin bot-senales`.
3. En el **dashboard de Railway**, re-apuntar el **servicio del bot** a `bot-senales` (Settings →
   Source → Branch). Verificar que sigue desplegando y que los contadores no se resetean.
4. Dejar el **servicio de Marea** apuntando a `main`. A partir de aquí, un push a `main` redeploya
   Marea (regla de redeploy libre aplica).
5. Fusionar la rama de verificación (`claude/marea-kyc-verification-tiers-cb7cx6`) a `main` cuando
   RasDG lo pida — ahí es donde Marea empieza a vivir en `main`.
6. Actualizar `CLAUDE.md` (dice "bot vivo en producción, rama main") y `railway.toml` si hace falta,
   para que reflejen: `main` = Marea; el bot vive en su rama. Actualizar `ESTADO.md`.

**Lo que NO se hace:** reescribir la historia de `main`; borrar la rama del bot; dejar el servicio
del bot sin rama (cortaría el deploy a los suscriptores de pago). El paso 3 va **antes** de que
`main` cambie de contenido.

**Alternativa (si se prefiere que `main` sea sólo Marea, sin el bot):** extraer el bot a su propio
repo. Es más limpio a largo plazo pero mucho más caro (historia, CI, secretos). Discutir antes de
tomarla; por defecto, la opción recomendada de arriba mantiene el monorepo.

## 4. Estado del dominio de verificación y qué sigue

- `domain/niveles.ts` está **completo como dominio puro**, pero **no cableado a la app**. Cablearlo
  de verdad necesita un modelo de estado de usuario que hoy no existe (`Cuenta` en
  `apiAdapter.ts` es sólo `usuario/puntos/correo/posiciones`) y toca la zona del 2º dev (pantalla
  del verificador). No se construyó `nivelFor(usuario)` para no especular una forma inexistente.
- Los **números** (tope de N2, ventana de anti-structuring, umbral fiscal) esperan al abogado
  (P11, P15–P18 del encargo). El código deja el hueco parametrizado y conservador.
- **Backlog de liquidez/cadena** (siguiente cola tras verificación) en `COLA_TRABAJO.md §3`:
  subsidio de la semilla (R-067), presupuesto y freno (L9), frescura del oráculo (L8), árbol de
  época (L15), contratos. Con el giro a Marea principal y el redeploy libre, este backlog es el
  terreno natural para "construir largo y tendido".

_Escrito 2026-09-24. Cuando esté absorbido en ESTADO/DECISIONES/COLA, archívese._
