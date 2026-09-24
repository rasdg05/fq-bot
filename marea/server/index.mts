import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { gzipSync } from "node:zlib";
import { readFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { dirname, extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { Store } from "./store.mts";
import { manejarApi } from "./api.mts";
import {
  listarMercados,
  refrescarReferencia,
  sembrarPozos,
  todosLosSeeds,
} from "./mercados.mts";
import { correrCiclo, type ResumenCiclo } from "./ciclo.mts";
import { crearTicker } from "./precios.mts";
import { MercadosVivos } from "./vivos.mts";
import { MINIMO_ABIERTOS, reponer, type ResumenReposicion } from "./reposicion.mts";
import { cargarEspn } from "../src/adapters/oracles/matchOracle";
import type { PartidoDeLaLiga } from "../src/adapters/ownMarkets/templates";
import { metaDeLogro, metaDeMercado } from "./compartir.mts";
import { logroDe, tarjetaPng } from "./tarjeta.mts";
import { createRegistroDeEventos } from "./eventos.mts";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";
import { congelados, type SettlementState } from "../src/domain/settlement";

/**
 * Marea, servidor completo: sirve la app, guarda las cuentas y corre el ciclo
 * de vida cada hora dentro del mismo proceso.
 *
 * Un solo servicio a propósito. Railway no comparte volúmenes entre servicios,
 * y el pozo, las apuestas y la liquidación tienen que ver el mismo disco o no
 * son el mismo mercado.
 */

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIST = join(ROOT, "dist");
const DATOS = process.env.MAREA_DATA_DIR ?? join(ROOT, "data", "servidor");
const PORT = Number(process.env.PORT ?? 8080);
const CICLO_MS = Number(process.env.MAREA_CICLO_MS ?? 900_000);
/**
 * Los mercados vivos corren en su propio reloj. Un cuarto de hora es una
 * cadencia sana para un mercado que cierra el domingo y absurda para uno que
 * dura cinco minutos: con el ciclo lento, una vela se pagaría diez minutos
 * después de haberse resuelto.
 */
const CICLO_VIVO_MS = Number(process.env.MAREA_CICLO_VIVO_MS ?? 10_000);
/** Cada cuánto se planifica la siguiente vela. Barato: es aritmética de reloj. */
const PLAN_VIVO_MS = Number(process.env.MAREA_PLAN_VIVO_MS ?? 1_000);
const PRECIO_MS = Number(process.env.MAREA_PRECIO_MS ?? 3_000);

const TIPOS: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".webmanifest": "application/manifest+json",
};

/**
 * Caché de lo ya comprimido. Los assets llevan hash en el nombre y son
 * inmutables, así que comprimir una vez y guardar es correcto y gratis.
 *
 * Sin esto el servidor mandaba 426 kB donde `vite preview` mandaba 180 kB, y
 * eso costaba 1.3 s de LCP en una red lenta — medido, no supuesto (R-047).
 */
const comprimidos = new Map<string, Uint8Array>();

/** Sólo comprime lo que comprime bien; una imagen ya viene comprimida. */
function comprimible(tipo: string): boolean {
  return /^(text\/|application\/(json|javascript|manifest))/.test(tipo);
}

function aceptaGzip(req: IncomingMessage): boolean {
  return /\bgzip\b/.test(String(req.headers["accept-encoding"] ?? ""));
}

const store = new Store(DATOS);
const registrarEventos = createRegistroDeEventos(join(DATOS, "eventos"));
let seeds: OwnMarketSeed[] = todosLosSeeds(ROOT);
sembrarPozos(store, seeds);

/**
 * Cripto en vivo. El ticker lee el precio una vez para todos —el motor FQ si
 * está configurado, Kraken si no— y el planificador mantiene siempre abierta
 * una vela de 5 min y una de 15 por activo.
 *
 * Los mercados vivos **no** se siembran en disco al nacer: el pozo se crea con
 * la primera apuesta. Por eso no pasan por `sembrarPozos`.
 */
const ticker = crearTicker({
  urlFq: process.env.MAREA_FQ_PRECIOS_URL,
  intervaloMs: PRECIO_MS,
  onError: (mensaje) => log(`precios: ${mensaje}`),
});
const vivos = new MercadosVivos(store, ticker);

/**
 * El catálogo completo de este instante: lo publicado en el repo, lo que el
 * servidor repuso solo, y lo que está corriendo ahora mismo.
 *
 * Los tres tienen que estar. Un mercado que se cae de esta lista se cae también
 * del ciclo de liquidación —que itera sobre semillas— y las apuestas que tenga
 * dentro no se resuelven nunca.
 */
function catalogo(): OwnMarketSeed[] {
  return [...seeds, ...store.seedsGeneradas(), ...vivos.seeds()];
}

const bitacora = {
  arranque: new Date().toISOString(),
  ultimoCiclo: null as ResumenCiclo | null,
  corridas: 0,
  vivos: { abiertos: 0, conApuestas: 0, pagados: 0, errores: 0 },
  ultimaReposicion: null as ResumenReposicion | null,
};

/**
 * Los partidos de Liga MX de los próximos días, leídos de ESPN.
 *
 * Un día que no contesta no cancela la semana: se pierde ese día y se sigue.
 * Es la misma tolerancia que tiene `roll`, y por la misma razón — una fuente
 * caída puede dejar el feed más corto, no vacío.
 */
async function partidosDeLaSemana(dias = 7): Promise<PartidoDeLaLiga[]> {
  const partidos: PartidoDeLaLiga[] = [];
  const hoy = Date.now();
  for (let i = 0; i < dias; i += 1) {
    const dia = new Date(hoy + i * 86_400_000).toISOString().slice(0, 10);
    try {
      for (const evento of await cargarEspn(fetch, "mex.1", dia)) {
        const competidores = evento.competitions[0]?.competitors ?? [];
        const local = competidores.find((c) => c.homeAway === "home");
        const visitante = competidores.find((c) => c.homeAway === "away");
        if (!local || !visitante) continue;
        partidos.push({
          inicio: evento.date,
          local: local.team.displayName,
          visitante: visitante.team.displayName,
        });
      }
    } catch {
      // un día que no responde no cancela la semana entera
    }
  }
  return partidos;
}

function log(linea: string) {
  console.log(`${new Date().toISOString()} ${linea}`);
}

async function ciclo() {
  bitacora.corridas += 1;
  try {
    // el catálogo puede haber crecido: se relee antes de liquidar
    seeds = todosLosSeeds(ROOT);

    /**
     * Y se repone **antes** de liquidar, no después: si el feed está corto, lo
     * que menos ayuda es esperar un cuarto de hora más.
     *
     * Esto vive aquí y no en un cron porque el cron vivía en la máquina de
     * alguien. Nadie lo corrió desde agosto y la app llegó a septiembre con
     * cuatro mercados. Un proceso que depende de que alguien se acuerde no
     * existe (AGENTE §2).
     */
    try {
      const repuesto = await reponer(store, [...seeds, ...vivos.seeds()], Date.now(), {
        spot: () => ({
          "BTC/USD": ticker.precio("BTC/USD")?.precio,
          "ETH/USD": ticker.precio("ETH/USD")?.precio,
        }),
        partidos: (dias) => partidosDeLaSemana(dias),
        env: process.env,
        avisar: (mensaje) => log(`reposición: ${mensaje}`),
      });
      bitacora.ultimaReposicion = repuesto;
      /**
       * Se registra también cuando **quiso** reponer y no pudo. Callarse ahí es
       * exactamente el fallo que dejó la app vacía un mes: nada estaba roto,
       * nada aparecía, y nadie tenía cómo enterarse.
       */
      if (repuesto.creados.length > 0) {
        log(
          `reposición: ${repuesto.creados.length} mercados nuevos ` +
            `(había ${repuesto.abiertosAntes} duraderos abiertos)`,
        );
      } else if (repuesto.abiertosAntes < MINIMO_ABIERTOS) {
        log(
          `reposición: el feed está corto (${repuesto.abiertosAntes} de ${MINIMO_ABIERTOS}) ` +
            `y no se creó nada — ${repuesto.frenados.length} frenados, ` +
            `${repuesto.errores.length} errores`,
        );
      }
      for (const frenado of repuesto.frenados) {
        log(`  ⛔ ${frenado.id} no se creó: ${frenado.motivo}`);
      }
      for (const error of repuesto.errores) log(`  ⚠ reposición: ${error}`);
    } catch (error) {
      log(`reposición falló entera: ${String(error)}`);
    }

    const conRepuestos = [...seeds, ...store.seedsGeneradas()];
    sembrarPozos(store, conRepuestos);
    const resumen = await correrCiclo(store, conRepuestos);
    bitacora.ultimoCiclo = resumen;
    log(
      `ciclo ${bitacora.corridas}: ${resumen.leidos} leídos · ${resumen.pagados} pagados · ` +
        `${resumen.acreditado} puntos acreditados · ${resumen.atorados.length} atorados` +
        (resumen.huerfanos.length > 0 ? ` · ${resumen.huerfanos.length} huérfanas devueltas` : ""),
    );
    for (const error of resumen.errores) log(`  ⚠ ${error}`);
  } catch (error) {
    log(`ciclo falló entero: ${String(error)}`);
  }
}

/**
 * El ciclo de las velas. Corre cada pocos segundos y **sólo** sobre los
 * mercados vivos que tienen apuestas: los demás no tienen nada que liquidar, y
 * escribirles un estado de liquidación sería llenar el archivo de mercados que
 * nadie tocó.
 *
 * Es el mismo `correrCiclo` del catálogo normal, con los mismos oráculos y la
 * misma matemática. Lo único distinto es cada cuánto se llama.
 */
let cicloVivoEnVuelo = false;
async function cicloVivo() {
  if (cicloVivoEnVuelo) return;
  cicloVivoEnVuelo = true;
  try {
    vivos.tick();
    const pendientes = vivos.seedsConApuestas();
    bitacora.vivos.abiertos = vivos.seeds().length;
    bitacora.vivos.conApuestas = pendientes.length;
    if (pendientes.length === 0) return;

    const resumen = await correrCiclo(store, pendientes);
    bitacora.vivos.pagados += resumen.pagados + resumen.anulados;
    bitacora.vivos.errores += resumen.errores.length;
    if (resumen.pagados + resumen.anulados > 0) {
      log(
        `vela: ${resumen.pagados} pagadas · ${resumen.anulados} anuladas · ` +
          `${Math.round(resumen.acreditado)} puntos acreditados`,
      );
    }
    for (const error of resumen.errores) log(`  ⚠ vela ${error}`);
  } catch (error) {
    log(`ciclo vivo falló: ${String(error)}`);
  } finally {
    cicloVivoEnVuelo = false;
  }
}

async function servir(req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const ruta = normalize(decodeURIComponent(url.pathname));

  if (ruta === "/salud") {
    res.writeHead(200, { "content-type": TIPOS[".json"], "cache-control": "no-store" });
    res.end(
      JSON.stringify(
        {
          ...bitacora,
          datos: store.resumen(),
          mercados: seeds.length,
          /**
           * Lo que estaba pasando y no se veía.
           *
           * Durante más de un mes el resumen del ciclo dijo «0 atorados · 0
           * errores» mientras varios mercados llevaban semanas sin resolverse y
           * había apuestas cuyo mercado ya no existía. Ninguna de las dos cosas
           * era un error —el oráculo contestaba `sin_dato` y el ciclo itera
           * sobre las semillas— y por eso ninguna aparecía. Aparecen aquí.
           */
          congelados: congelados(
            seeds
              .map((seed) => ({ state: store.liquidacion(seed.id), spec: seed.resolution }))
              .filter((x): x is { state: SettlementState; spec: typeof x.spec } => !!x.state),
            Date.now(),
          ),
          huerfanas: store.apuestasHuerfanas(seeds.map((seed) => seed.id)),
          // de dónde sale el precio que se está enseñando, y si el motor está
          // degradado. Es lo primero que se mira cuando una card se queda sin
          // número
          precios: ticker.estado(),
        },
        null,
        2,
      ),
    );
    return;
  }

  if (ruta.startsWith("/api/")) {
    // la referencia se refresca de fondo: el feed nunca la espera (R-047)
    void refrescarReferencia();
    try {
      const atendido = await manejarApi(req, res, ruta, {
        store,
        seeds: catalogo,
        seguro: (req.headers["x-forwarded-proto"] ?? "http") === "https",
        registrarEventos,
        vivos,
        precios: ticker,
      });
      if (!atendido) {
        res.writeHead(404, { "content-type": TIPOS[".json"] });
        res.end(JSON.stringify({ error: "No encontramos eso." }));
      }
    } catch (error) {
      log(`api ${ruta}: ${String(error)}`);
      if (!res.headersSent) res.writeHead(500, { "content-type": TIPOS[".json"] });
      res.end(JSON.stringify({ error: "Algo falló de nuestro lado. Vuelve a intentar." }));
    }
    return;
  }

  /**
   * Tarjeta de resultado: `/tarjeta/<usuario>.png`.
   *
   * Se genera en el servidor y se cachea una hora: la imagen cambia cuando
   * liquida un mercado, no cuando alguien recarga. Sólo lleva datos propios y
   * agregados — el nombre, cuántas le atinó y su racha (R-058).
   */
  if (ruta.startsWith("/tarjeta/") && ruta.endsWith(".png")) {
    const usuario = decodeURIComponent(ruta.slice("/tarjeta/".length, -4));
    const logro = logroDe(store, usuario);
    if (!logro) {
      res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
      res.end("No encontramos a esa persona.");
      return;
    }
    try {
      const png = await tarjetaPng(logro, ROOT);
      res.writeHead(200, {
        "content-type": "image/png",
        "cache-control": "public, max-age=3600",
      });
      res.end(png);
    } catch (error) {
      // que falle una imagen no puede tumbar la ruta: se dice y se sigue
      console.error("tarjeta:", error);
      res.writeHead(500, { "content-type": "text/plain; charset=utf-8" });
      res.end("No pudimos generar la tarjeta.");
    }
    return;
  }

  /**
   * Página de la tarjeta: `/logro/<usuario>`. Es la que se comparte — lleva la
   * imagen en sus etiquetas de vista previa, porque un PNG suelto en WhatsApp
   * no trae ni título ni contexto.
   */
  if (ruta.startsWith("/logro/")) {
    const usuario = decodeURIComponent(ruta.slice("/logro/".length));
    const logro = logroDe(store, usuario);
    const html = await readFile(join(DIST, "index.html"), "utf8");
    const salida = logro ? metaDeLogro(html, logro, url.origin) : html;
    const gzip = aceptaGzip(req);
    res.writeHead(200, {
      "content-type": TIPOS[".html"],
      "cache-control": "no-cache",
      ...(gzip ? { "content-encoding": "gzip", vary: "Accept-Encoding" } : {}),
    });
    res.end(gzip ? gzipSync(salida) : salida);
    return;
  }

  /**
   * Liga compartible de un mercado: `/m/<id>`. Se sirve la misma app, pero con
   * las etiquetas de vista previa rellenas con la pregunta y la probabilidad —
   * un enlace que en WhatsApp se ve como texto pelón no lo abre nadie.
   */
  if (ruta.startsWith("/m/")) {
    const id = ruta.slice(3);
    const mercado = listarMercados(store, catalogo(), Date.now(), ticker).find(
      (m) => m.id === id,
    );
    const html = await readFile(join(DIST, "index.html"), "utf8");
    const salida = mercado ? metaDeMercado(html, mercado, url.origin) : html;
    const gzip = aceptaGzip(req);
    res.writeHead(200, {
      "content-type": TIPOS[".html"],
      "cache-control": "no-cache",
      ...(gzip ? { "content-encoding": "gzip", vary: "Accept-Encoding" } : {}),
    });
    res.end(gzip ? gzipSync(salida) : salida);
    return;
  }

  const destino = join(DIST, ruta);
  if (!destino.startsWith(DIST)) {
    res.writeHead(403).end("prohibido");
    return;
  }

  let archivo = destino;
  const info = existsSync(archivo) ? await stat(archivo) : null;
  // la navegación es estado, no rutas: cualquier ruta desconocida es la app
  if (!info || info.isDirectory()) archivo = join(DIST, "index.html");

  const cacheable = archivo.startsWith(join(DIST, "assets"));
  const tipo = TIPOS[extname(archivo)] ?? "application/octet-stream";
  const cabeceras: Record<string, string> = {
    "content-type": tipo,
    "cache-control": cacheable ? "public, max-age=31536000, immutable" : "no-cache",
  };

  let cuerpo: Uint8Array = await readFile(archivo);
  if (comprimible(tipo) && aceptaGzip(req)) {
    const enCache = comprimidos.get(archivo);
    cuerpo = enCache ?? gzipSync(cuerpo);
    if (!enCache && cacheable) comprimidos.set(archivo, cuerpo);
    cabeceras["content-encoding"] = "gzip";
    cabeceras.vary = "Accept-Encoding";
  }

  res.writeHead(200, cabeceras);
  res.end(cuerpo);
}

if (!existsSync(join(DIST, "index.html"))) {
  console.error("Falta dist/index.html. Corre `npm run build` antes de arrancar.");
  process.exit(1);
}

if (!process.env.MAREA_SECRETO) {
  log(
    "⚠ Sin MAREA_SECRETO: las sesiones se firman con una llave nueva en cada " +
      "arranque, así que un redeploy saca a todos. Configúralo en el servicio.",
  );
}

createServer((req, res) => {
  servir(req, res).catch((error) => {
    log(`error sirviendo ${req.url}: ${String(error)}`);
    if (!res.headersSent) res.writeHead(500, { "content-type": "text/plain" });
    res.end("error");
  });
}).listen(PORT, () => {
  log(`Marea en :${PORT} · datos en ${DATOS} · ${seeds.length} mercados`);
  log(`estado inicial: ${JSON.stringify(store.resumen())}`);

  // ningún mercado debe depender de que una persona lo confirme. Los que se
  // leen con token sí dependen de que el token esté puesto: sin él degradan a
  // confirmación humana en silencio, y "en silencio" es cómo se descubre tarde
  const sinLlave = seeds.filter((seed) => {
    if (seed.rule?.kind !== "serie") return false;
    if (seed.rule.fuente === "banxico") return !process.env.BANXICO_TOKEN;
    if (seed.rule.fuente === "inegi") return !process.env.INEGI_TOKEN;
    return false;
  });
  if (sinLlave.length > 0) {
    log(
      `⚠ ${sinLlave.length} mercados no se pueden resolver solos por falta de token ` +
        `(${sinLlave.map((s) => s.id).join(", ")}). ` +
        `Configura BANXICO_TOKEN / INEGI_TOKEN en el servicio o esos mercados se atoran.`,
    );
  } else {
    log("todos los mercados se resuelven solos: cero confirmación humana");
  }
});

// el mercado abre con el ciclo ya corrido, y sigue cada cuarto de hora
void ciclo();
setInterval(() => void ciclo(), CICLO_MS);
void listarMercados(store, seeds);

/**
 * Cripto en vivo, en tres relojes distintos porque son tres trabajos distintos:
 * leer el precio, planificar la vela siguiente y liquidar la que cerró.
 */
ticker.arrancar();
// la primera vela se planifica en cuanto haya precio; sin él no se inventa un
// strike y el planificador simplemente no crea nada esta vuelta
setTimeout(() => vivos.tick(), 500).unref?.();
setInterval(() => vivos.tick(), PLAN_VIVO_MS).unref?.();
setInterval(() => void cicloVivo(), CICLO_VIVO_MS).unref?.();
log(
  `cripto en vivo: precio cada ${PRECIO_MS} ms desde ` +
    `${process.env.MAREA_FQ_PRECIOS_URL ? "el motor FQ (respaldo Kraken)" : "Kraken"} · ` +
    `liquidación cada ${CICLO_VIVO_MS} ms`,
);
