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
import { metaDeMercado } from "./compartir.mts";
import type { OwnMarketSeed } from "../src/adapters/ownMarkets/catalog";

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
let seeds: OwnMarketSeed[] = todosLosSeeds(ROOT);
sembrarPozos(store, seeds);

const bitacora = {
  arranque: new Date().toISOString(),
  ultimoCiclo: null as ResumenCiclo | null,
  corridas: 0,
};

function log(linea: string) {
  console.log(`${new Date().toISOString()} ${linea}`);
}

async function ciclo() {
  bitacora.corridas += 1;
  try {
    // el catálogo puede haber crecido: se relee antes de liquidar
    seeds = todosLosSeeds(ROOT);
    sembrarPozos(store, seeds);
    const resumen = await correrCiclo(store, seeds);
    bitacora.ultimoCiclo = resumen;
    log(
      `ciclo ${bitacora.corridas}: ${resumen.leidos} leídos · ${resumen.pagados} pagados · ` +
        `${resumen.acreditado} puntos acreditados · ${resumen.atorados.length} atorados`,
    );
    for (const error of resumen.errores) log(`  ⚠ ${error}`);
  } catch (error) {
    log(`ciclo falló entero: ${String(error)}`);
  }
}

async function servir(req: IncomingMessage, res: ServerResponse) {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const ruta = normalize(decodeURIComponent(url.pathname));

  if (ruta === "/salud") {
    res.writeHead(200, { "content-type": TIPOS[".json"], "cache-control": "no-store" });
    res.end(JSON.stringify({ ...bitacora, datos: store.resumen(), mercados: seeds.length }, null, 2));
    return;
  }

  if (ruta.startsWith("/api/")) {
    // la referencia se refresca de fondo: el feed nunca la espera (R-047)
    void refrescarReferencia();
    try {
      const atendido = await manejarApi(req, res, ruta, {
        store,
        seeds: () => seeds,
        seguro: (req.headers["x-forwarded-proto"] ?? "http") === "https",
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
   * Liga compartible de un mercado: `/m/<id>`. Se sirve la misma app, pero con
   * las etiquetas de vista previa rellenas con la pregunta y la probabilidad —
   * un enlace que en WhatsApp se ve como texto pelón no lo abre nadie.
   */
  if (ruta.startsWith("/m/")) {
    const id = ruta.slice(3);
    const mercado = listarMercados(store, seeds).find((m) => m.id === id);
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
});

// el mercado abre con el ciclo ya corrido, y sigue cada cuarto de hora
void ciclo();
setInterval(() => void ciclo(), CICLO_MS);
void listarMercados(store, seeds);
