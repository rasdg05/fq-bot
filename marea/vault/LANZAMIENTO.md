# LANZAMIENTO — todo desde tu máquina, sin CI

Marea no necesita GitHub Actions para nada. Los workflows quedan en el repo por
si algún día los enciendes, pero **el camino principal es local**: verificar,
publicar y recolectar datos corren desde tu terminal.

Dos cosas que conviene saber antes de decidir: Actions es gratis e ilimitado en
repos **públicos**, y GitHub Pages en repo **privado** sí requiere plan de pago.
Si el repo es privado, ese camino estaba cerrado de todos modos.

> **Si eliges Railway (Opción A del Paso 1), este paso 0 no hace falta**:
> Railway construye desde GitHub y no necesita nada en tu computadora. El paso 0
> es sólo para el camino de Cloudflare Pages o para correr la app en local.

## Paso 0 · Bajar el código a tu máquina

Todo esto se escribe en la **Terminal** de tu computadora (en Mac: ⌘ + Espacio,
escribe "Terminal", Enter). Cada bloque se pega tal cual y se presiona Enter.

Primero, comprobar que tienes Node instalado:

```bash
node -v
```

Si responde algo como `v20.x` o `v22.x`, listo. Si dice "command not found",
instálalo desde https://nodejs.org (botón LTS) y vuelve a abrir la Terminal.

Después, bajar el repo y pararte en la rama con el trabajo:

```bash
cd ~
git clone https://github.com/rasdg05/fq-bot.git
cd fq-bot
git checkout claude/marea-autonomous-build-96mklt
cd marea
npm install
```

`npm install` tarda un par de minutos la primera vez y sólo se corre una vez.

Si ya tenías el repo bajado, en vez de clonar:

```bash
cd ~/fq-bot
git fetch origin claude/marea-autonomous-build-96mklt
git checkout claude/marea-autonomous-build-96mklt
git pull origin claude/marea-autonomous-build-96mklt
cd marea && npm install
```

## Paso 1 · Publicar

Hay dos caminos. **Elige uno**, no los dos.

### Opción A · Railway (si ya lo pagas, es el mejor)

Railway ya corre tu bot de Python (`railway.toml` de la raíz → `python
launcher.py`). Ese servicio es un *worker*: no sirve páginas y no sabe nada de
Marea. Marea va como **un segundo servicio**, en el mismo repo, con su propia
configuración en `marea/railway.toml`.

La ventaja de este camino es grande: el ciclo de vida —liquidar y reponer— corre
**dentro del contenedor cada hora**, así que no necesitas dejar tu computadora
prendida ni instalar ningún cron. El Paso 2 de abajo te lo puedes saltar.

En el panel de Railway, dentro del mismo proyecto:

1. **New → GitHub Repo → `rasdg05/fq-bot`**.
2. En el servicio nuevo, **Settings → Root Directory: `marea`**. Esto es lo que
   hace que use `marea/railway.toml` y no el del bot.
3. **Settings → Branch: `claude/marea-autonomous-build-96mklt`** (o `main`, si
   ya lo mergeaste).
4. **Settings → Networking → Generate Domain**. Te da la URL pública.
5. Deploy. Tarda unos minutos: instala, construye y arranca.

No hace falta configurar variables de entorno: la app funciona sin ninguna. Si
más adelante quieres analítica, ahí van `VITE_ANALYTICS_ENDPOINT` y
`VITE_ERROR_ENDPOINT` (son de build, así que hay que redeployar).

Para saber si está vivo y si el ciclo está corriendo, abre `TU-URL/salud`:

```json
{ "arranque": "…", "ultimoCiclo": "…", "ultimoError": null, "corridas": 3 }
```

Si `ultimoCiclo` tiene más de una hora o `ultimoError` no es `null`, algo se
rompió y hay que mirar los logs del servicio.

Ojo con una cosa: el disco de Railway es efímero salvo que montes un volumen. Sin
volumen, cada redeploy reinicia el estado del liquidador — y no pasa nada grave,
porque vuelve a leer las fuentes y recalcula, que para eso es idempotente. Si
quieres conservar la historia, monta un volumen y pon
`MAREA_DATA_DIR=/data` en las variables del servicio.

### Opción B · Cloudflare Pages (gratis, sin Railway)

```bash
npm run deploy       # verifica, construye y publica
```

Con este camino, el ciclo de vida **sí** depende del Paso 2 en tu máquina.

`npm run deploy` corre los tipos, el `VALIDATION_REPORT` completo y la build
antes de subir nada. Si algo falla, **no publica** — que es el punto.

La primera vez va a fallar al final, en el paso de subir, porque todavía no
tienes sesión en el hosting. Es lo esperado. Se arregla así:

1. Crea la cuenta gratis en https://dash.cloudflare.com/sign-up (correo y
   contraseña, no pide tarjeta).
2. En la Terminal:

```bash
npx wrangler login
```

   Se abre el navegador y te pide autorizar. Das "Allow" y ya.

3. Vuelve a correr `npm run deploy`. Si te pregunta si quieres crear el
   proyecto `marea`, di que sí y acepta la rama que proponga.

Al terminar te imprime la URL, algo como `https://marea.pages.dev`. Ésa es tu
app en vivo. Cada vez que quieras publicar cambios, es sólo `npm run deploy`
otra vez.

Alternativas, todas con capa gratis y todas desde la terminal:

```bash
npm run deploy -- --host netlify
npm run deploy -- --host vercel
npm run deploy -- --host surge
```

La app es una sola página y la navegación es estado, así que **no necesita
reglas de reescritura ni servidor**: cualquier hosting estático la sirve tal
cual. La build pesa unos 390 kB, 96 kB comprimidos.

Para ver qué se publicaría sin publicar: `npm run deploy -- --dry`.

## Paso 2 · Que el producto se mantenga solo

**Sáltate este paso si elegiste Railway**: allá el ciclo ya corre solo dentro
del contenedor.

Una sola línea, en la misma Terminal, dentro de `fq-bot/marea`:

```bash
npm run cron:install
```

Eso programa una tarea **cada hora** en tu computadora que hace tres cosas:

1. **Liquida** los mercados que ya resolvieron y autoriza el pago.
2. **Repone** el catálogo con los mercados de la semana.
3. **Guarda** la superficie de volatilidad del día.

Para probarla ahora mismo sin esperar a la hora:

```bash
npm run daily
```

Para ver que sigue viva, la bitácora:

```bash
tail -20 data/daily.log
```

Para cambiar el minuto en que corre: `npm run cron:install -- --minuto 20`.
Para quitarla: `npm run cron:install -- --uninstall`.

Usa launchd en macOS y crontab en Linux. Es segura para correr sola: lo que ya
está hecho no se rehace, si no hay red no inventa un archivo, y si git falla el
dato igual quedó en disco.

**La computadora tiene que estar encendida** para que corra. Si la apagas no se
pierde nada — la siguiente corrida retoma — pero un mercado puede tardar más en
pagarse. Los mercados de cripto se resuelven en la primera corrida después de
que cierra la vela; los institucionales esperan a que tú los confirmes.

Cada día que se salta de volatilidad es un dato que no se recupera. Con unos
seis meses ya se puede recalibrar el modelo del Edge.

## Verificar sin publicar (opcional)

```bash
npm run ci      # tipos + VALIDATION_REPORT + build. Lo mismo que haría el CI
npm run test    # sólo las pruebas
npm run perf    # rendimiento en laboratorio (necesita `npx vite preview` aparte)
```

## Cuando un mercado te pida confirmación

Los mercados que resuelve una institución (INEGI, Banxico, BCRA, DANE) no se
pueden leer por programa. El liquidador los deja marcados y te los lista:

```
⚠ mx-inpc-anual: la fuente necesita confirmación humana · Confirmar en INEGI: https://…
```

Abres la liga, ves la cifra, y confirmas. Eso todavía no tiene botón: por ahora
me lo dices y yo lo registro. Es lo único del ciclo que no corre solo, y es a
propósito — inventar un resultado sería peor que tardarse.

## Qué revisar después de publicar

1. Abre la URL en el teléfono, no en el escritorio. El producto es móvil.
2. Un tap desde el splash hasta el feed.
3. Abre un mercado: tiene que verse el reparto del pozo y el criterio de
   resolución antes del botón de apostar.
4. Apuesta: el saldo baja y la posición aparece en el portafolio.
5. Confirma que en ninguna pantalla aparece un símbolo de moneda — se juega con
   puntos y eso tiene que quedar claro sin que nadie lo explique.

## Lo que sigue estando pendiente y no depende de código

Está en `COMPLIANCE.md` y `ACELERACION.md`. Resumen: para jugar con puntos no
hace falta nada más. Para dinero hacen falta la consulta legal por país y la
llave del proveedor de wallet — ninguna de las dos se resuelve desde aquí.
