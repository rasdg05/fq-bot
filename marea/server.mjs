#!/usr/bin/env node
/**
 * Servidor de Marea para un contenedor (Railway, Fly, cualquier PaaS).
 *
 * Hace dos cosas, y las dos importan lo mismo:
 *
 *   1. Sirve la app construida (`dist/`).
 *   2. Corre el ciclo de vida —liquidar y reponer— cada hora, dentro del mismo
 *      proceso, para que el producto no dependa de que la computadora de nadie
 *      esté encendida (AGENTE §2).
 *
 * Los dos archivos que el ciclo escribe (`mercados.json`, `resoluciones.json`)
 * se sirven **desde disco en cada petición**, no desde la build: así una
 * liquidación se ve en la app sin volver a construir ni redeployar.
 *
 * Sin git aquí: en un contenedor el disco es efímero y empujar al repo desde
 * producción sería pedir problemas. El estado que importa se recalcula solo en
 * la siguiente corrida — el liquidador es idempotente justo para esto.
 */
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { readFile, stat } from "node:fs/promises";
import { existsSync } from "node:fs";
import { extname, join, normalize } from "node:path";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(fileURLToPath(import.meta.url));
const DIST = join(ROOT, "dist");
/** Donde el ciclo escribe. Un volumen montado aquí sobrevive a los redeploys. */
const ESTADO = process.env.MAREA_DATA_DIR ?? join(ROOT, "public");
const PORT = Number(process.env.PORT ?? 8080);
const CICLO_MS = Number(process.env.MAREA_CICLO_MS ?? 3_600_000);

const TIPOS = {
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

/** Los que el ciclo reescribe: siempre frescos, nunca de caché. */
const VIVOS = new Set(["/mercados.json", "/resoluciones.json"]);

const bitacora = {
  arranque: new Date().toISOString(),
  ultimoCiclo: null,
  ultimoError: null,
  corridas: 0,
};

function log(linea) {
  console.log(`${new Date().toISOString()} ${linea}`);
}

function correr(script) {
  return new Promise((resolve, reject) => {
    const hijo = spawn("npx", ["tsx", script], {
      cwd: ROOT,
      stdio: "inherit",
      env: { ...process.env, NODE_USE_ENV_PROXY: "1" },
    });
    hijo.on("error", reject);
    hijo.on("exit", (code) =>
      code === 0 ? resolve() : reject(new Error(`${script} salió con ${code}`)),
    );
  });
}

/**
 * Un paso que falla no puede tumbar el servidor ni impedir el siguiente: son
 * problemas distintos y sólo uno mueve saldo.
 */
async function ciclo() {
  bitacora.corridas += 1;
  for (const script of ["scripts/settle.mts", "scripts/roll.mts"]) {
    try {
      await correr(script);
    } catch (error) {
      bitacora.ultimoError = `${script}: ${error.message}`;
      log(`ciclo: falló ${script} — ${error.message}`);
    }
  }
  bitacora.ultimoCiclo = new Date().toISOString();
  log(`ciclo terminado (corrida ${bitacora.corridas})`);
}

async function servir(req, res) {
  const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
  const ruta = normalize(decodeURIComponent(url.pathname));

  // salud: para que Railway sepa si esto está vivo y tú si el ciclo corre
  if (ruta === "/salud") {
    res.writeHead(200, { "content-type": TIPOS[".json"] });
    res.end(JSON.stringify(bitacora, null, 2));
    return;
  }

  // los archivos que el ciclo reescribe se leen de disco en cada petición
  if (VIVOS.has(ruta)) {
    const vivo = join(ESTADO, ruta.slice(1));
    if (existsSync(vivo)) {
      res.writeHead(200, {
        "content-type": TIPOS[".json"],
        "cache-control": "no-store",
      });
      res.end(await readFile(vivo));
      return;
    }
  }

  // nada de subir por el árbol con `..`
  const destino = join(DIST, ruta);
  if (!destino.startsWith(DIST)) {
    res.writeHead(403).end("prohibido");
    return;
  }

  let archivo = destino;
  const info = existsSync(archivo) ? await stat(archivo) : null;
  // la navegación es estado, no rutas: cualquier ruta desconocida es la app
  if (!info || info.isDirectory()) archivo = join(DIST, "index.html");

  const tipo = TIPOS[extname(archivo)] ?? "application/octet-stream";
  const cacheable = archivo.includes(`${join(DIST, "assets")}`);
  res.writeHead(200, {
    "content-type": tipo,
    "cache-control": cacheable ? "public, max-age=31536000, immutable" : "no-cache",
  });
  res.end(await readFile(archivo));
}

if (!existsSync(join(DIST, "index.html"))) {
  console.error("Falta dist/index.html: corre `npm run build` antes de servir.");
  process.exit(1);
}

createServer((req, res) => {
  servir(req, res).catch((error) => {
    log(`error sirviendo ${req.url}: ${error.message}`);
    if (!res.headersSent) res.writeHead(500, { "content-type": "text/plain" });
    res.end("error");
  });
}).listen(PORT, () => log(`Marea sirviendo en :${PORT}`));

// el ciclo arranca en cuanto el servidor está arriba, y sigue cada hora
void ciclo();
setInterval(() => void ciclo(), CICLO_MS);
