# RETOMAR — la página para arrancar en frío

> Si abres una conversación nueva sobre Marea, empieza aquí. Son dos minutos y
> te ahorran el día. Escrita el 2026-09-11, al cerrar la sesión autónoma.
>
> El orden de lectura sigue siendo el de siempre: `CLAUDE.md` →
> `MEMORY/00-INDICE.md` → `marea/vault/AGENTE.md` (cómo se trabaja) → esta
> página (dónde está todo hoy).

---

## 1. La trampa que cuesta un día entero

**Producción no corre `main`.**

| | |
|---|---|
| Rama desplegada | `claude/marea-redesign-v6-b0240n` |
| URL | `https://fq-bot-production.up.railway.app` |
| Servicio | Railway, Root Directory = `marea` (ver `marea/railway.toml`) |
| `main` | Le faltan **15 commits**: el rediseño v6 y la cripto en vivo |

Esa rama nunca se fusionó a `main`. Si trabajas sobre `main`, tu código **no
llega a la app**; y si fusionas `main` a producción sin reconciliar primero, te
llevas por delante el rediseño y las velas de 5/15 min.

Cómo se descubrió, por si hay que repetirlo: `curl .../api/mercados` sirve
`shortTitle` y mercados `live`, y `git log --all -S"abreAt"` enseña que ese
código sólo vive en ramas sin fusionar.

**Pendiente y no es mío:** reconciliar `main` con producción. Mientras tanto,
todo lo de Marea se trabaja sobre `claude/marea-redesign-v6-b0240n`.

## 2. Cómo se verifica que algo funciona

```bash
cd marea
npm ci                       # una vez
npm run ci                   # tsc + validate + build — la puerta de cada commit
npx vitest run               # la suite
npm run mutaciones           # rompe el código a propósito y comprueba que la suite grita
```

**`npm run ci` es `tsc && build && validate`, en ese orden y a propósito.** Estuvo
seis semanas como `tsc && validate && build`, y como `validate` **siempre** falla
por el catálogo caducado, **`build` no llegaba a correr nunca**. Railway sí lo
corre, y directo: una rotura de build habría pasado toda la puerta local y
aparecido sólo en el deploy. Se descubrió cuando un deploy falló y fui a
comprobar si era mi código — y resultó que no lo había comprobado nunca.

**La línea base no es «verde».** `npm run ci` sale **FAIL con 8 fallos** y eso es
lo esperado: 6 pruebas de `vitest` más 2 verificaciones de `validate`, todas por
el catálogo estático caducado (R-041), ninguna de código. Comparar contra cero
en vez de contra la línea base es el error que `marea/vault/LINEA_BASE.md` existe
para evitar. **La regla es que el número de rojas no crece.**

Hoy: **8 rojas · 497 verdes**. Mutaciones: **95 · 92 detectadas · 3 equivalentes
documentadas · 0 huecos**.

## 3. Qué se construyó y dónde quedó

**El dominio de liquidez** (cola `COLA_TRABAJO.md`, unidades U0–U8). De las
invariantes de `LIQUIDEZ.md`, **L1, L2, L3, L5, L6, L8, L9 y L15 pasaron de
escritas a vivas**. U7 (contratos Solidity) se saltó: `forge` no es alcanzable.

**Los arreglos de producción** (fuera de la cola, a petición de RasDG):

| | Dónde |
|---|---|
| Plazo de atasco: 7 d visible, 30 d anula y devuelve | `domain/settlement.ts` |
| `atorado` deja de ser callejón sin salida | `domain/settlement.ts` + `server/ciclo.mts` |
| Auditores `congelados()` y `apuestasHuerfanas()`, expuestos en `/salud` | `settlement.ts`, `store.mts`, `index.mts` |
| Apuestas huérfanas devueltas íntegras | `server/ciclo.mts` |
| El feed no enseña puertas con candado | `server/mercados.mts` |
| El catálogo se repone **dentro del servidor** | `server/reposicion.mts` |
| Un mercado anulado no cuenta como fallo en la tabla | `server/tabla.mts` |
| Un mercado resuelto sólo lo ve quien apostó en él | `server/mercados.mts` (`visiblesPara`) |
| `npm run ci` sí corre el build | `package.json` |

## 4. Lo que NO está hecho, dicho en la misma frase

- **Nadie nace en modo `"subsidio"`.** El mecanismo está cableado y probado; el
  interruptor está apagado porque R-067 pide subsidio **con tope** y los topes no
  tienen cifras (P-002, P-004).
- **Los contratos no existen.** `forge` no es alcanzable en el entorno; npm sí
  trae `solc` y `hardhat`, y elegir cadena de construcción no es decisión de una
  sesión autónoma (P-006).
- **Las hojas de la época no se publican.** Es la tercera pata de L15 y no es
  código de dominio: sin ella, «auditable» sigue dependiendo de que contestemos.
- **Elegibilidad: todos los países en `pendiente`.** No se abre ni para probar.
- **Nada con dinero real.** Se juega con puntos.

## 5. Lo que espera una decisión tuya

Todo en `marea/vault/PREGUNTAS_ABIERTAS.md`, con qué se eligió y qué se descartó:

| | Qué falta |
|---|---|
| **P-002 · P-004** | Las tres cifras de los topes de subsidio, y cuándo encender el modo en `templates.ts` |
| **P-005** | Si vale la pena medir la cadencia real de las seis fuentes institucionales |
| **P-006** | Hardhat como cadena de contratos, esperar a una máquina con Foundry, o abrir GitHub releases en la red |
| **P-007** | Los dos plazos (7 d / 30 d) los elegí yo y no están medidos. Y sobre todo: **que un mercado incobrable devuelva en vez de quedarse congelado** es una decisión de producto que conviene confirmar antes de que haya dinero real |

## 6. Lo que no hay que volver a aprender

Tres cosas costaron caro y están escritas largo en `MEMORY/marea/BITACORA_AUTONOMA.md`:

1. **Un campo nuevo en el dominio no basta.** Había cuatro sitios que
   reconstruían el pozo a mano y tiraban `seedMode` en silencio. Un test de
   dominio puro no ve eso.
2. **Diez tests pasaban en verde sin probar lo que decía su nombre**, y no al
   azar: se concentran en guardas que nunca se disparan en el camino feliz y en
   propiedades adversarias. Por eso existe `npm run mutaciones`, con las 92
   mutaciones versionadas.
3. **`cuadre()` no ve el peor fallo.** No hay dinero descuadrado; hay dinero
   **quieto**. El resumen del ciclo dijo «0 atorados · 0 errores» durante 1008
   corridas mientras las apuestas de alguien llevaban un mes congeladas.

## 6bis. Lo que ya se verificó en producción

No es teoría: el 2026-09-11 el deploy entró y la primera corrida del ciclo anuló
9 mercados congelados desde agosto, devolvió **350 puntos** sin comisión y cerró
la huérfana `latam-libertadores-br`. `congelados: 0`, `huerfanas: {}`,
`cuadre: 0`. El catálogo se repuso solo y el feed pasó de **4 a 14 mercados
duraderos**, con partidos de Liga MX incluidos —ESPN responde desde Railway
aunque dé 403 desde un sandbox—. Y `br-ipca-5`, el mercado que llevaba semanas
colgado, resolvió con su evidencia: «IPCA acumulado 12 meses del 2026-07-01:
4.44 frente al umbral de 5».

## 7. Lo primero que haría al retomar

Mirar producción, que es la única fuente que no miente:

```bash
curl -s https://fq-bot-production.up.railway.app/salud | head -60
```

Después del deploy del 2026-09-11, ahí deberían verse `congelados` y `huerfanas`
—los dos campos nuevos—, y el log del servicio debería traer líneas de
`reposición:`. Si `congelados` sale largo, el plazo está haciendo su trabajo y
esos mercados se anularán solos a los 30 días de su fecha.

_Escrita el 2026-09-11. Si la fecha es vieja, confírmala contra `git log` y
contra `/salud`._
