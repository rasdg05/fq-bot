# LANZAMIENTO — todo desde tu máquina, sin CI

Marea no necesita GitHub Actions para nada. Los workflows quedan en el repo por
si algún día los enciendes, pero **el camino principal es local**: verificar,
publicar y recolectar datos corren desde tu terminal.

Dos cosas que conviene saber antes de decidir: Actions es gratis e ilimitado en
repos **públicos**, y GitHub Pages en repo **privado** sí requiere plan de pago.
Si el repo es privado, ese camino estaba cerrado de todos modos.

## Publicar

```bash
cd marea
npm install          # una sola vez
npm run deploy       # verifica, construye y publica
```

`npm run deploy` corre los tipos, el `VALIDATION_REPORT` completo y la build
antes de subir nada. Si algo falla, **no publica** — que es el punto.

La primera vez hace falta una cuenta gratuita del hosting y entrar una vez:

```bash
npx wrangler login   # Cloudflare Pages (por defecto)
```

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

## Verificar sin publicar

```bash
npm run ci      # tipos + VALIDATION_REPORT + build. Lo mismo que haría el CI
npm run test    # sólo las pruebas
npm run perf    # rendimiento en laboratorio (necesita `npx vite preview` aparte)
```

## La superficie de volatilidad, a diario

Es el dataset que hace falta para recalibrar el modelo del Edge. Su historia no
existe en ningún endpoint público: se construye guardándola un día a la vez.

```bash
npm run daily            # toma el día, commitea y sube
npm run cron:install     # y que corra solo todos los días a las 20:05
```

`cron:install` usa launchd en macOS y crontab en Linux. Para cambiar la hora:
`npm run cron:install -- --hora 21`. Para quitarlo: `-- --uninstall`.

La tarea es segura para un cron: si el día ya está guardado no hace nada, si no
hay red no inventa un archivo, y si git falla el dato igual quedó en disco.
Deja bitácora en `data/iv/daily.log`.

**No hace falta que corra todos los días sin excepción**, pero cada día que se
salta es un dato que no se recupera. Con unos seis meses ya se puede recalibrar.

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
