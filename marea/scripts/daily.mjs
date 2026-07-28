#!/usr/bin/env node
/**
 * La tarea que mantiene vivo el producto, para correr desde tu máquina sin
 * depender de CI. Hace tres cosas, en este orden:
 *
 *   1. liquidar  — lee las fuentes y paga los mercados que ya resolvieron (B1)
 *   2. reponer   — escribe los mercados de la semana para que el feed no se
 *                  vacíe (B2)
 *   3. guardar   — la superficie de volatilidad del día, que sólo se acumula
 *                  si se toma todos los días (R-037)
 *
 * Está hecha para vivir en un cron cada hora: es idempotente (lo que ya está
 * hecho no se rehace), no rompe si no hay red, y deja rastro en `data/`.
 *
 *   npm run daily                # las tres cosas, commitea y sube
 *   npm run daily -- --no-push   # sólo commitea
 *   npm run daily -- --solo liquidar
 */
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const LOG = join(ROOT, "data", "daily.log");
const push = !process.argv.includes("--no-push");
const soloIndex = process.argv.indexOf("--solo");
const solo = soloIndex >= 0 ? process.argv[soloIndex + 1] : null;

function log(line) {
  const text = `${new Date().toISOString()} ${line}`;
  console.log(text);
  try {
    mkdirSync(dirname(LOG), { recursive: true });
    appendFileSync(LOG, `${text}\n`);
  } catch {
    /* sin log seguimos: el dato importa más que la bitácora */
  }
}

function run(command, args, options = {}) {
  return execFileSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    stdio: options.quiet ? ["ignore", "pipe", "pipe"] : "inherit",
    env: { ...process.env, NODE_USE_ENV_PROXY: "1" },
  });
}

const fecha = new Date().toISOString().slice(0, 10);
const archivoIv = join(ROOT, "data", "iv", `${fecha}.json`);

/**
 * Cada paso se intenta por separado. Que falle la volatilidad no puede impedir
 * que se paguen los mercados: son problemas distintos y sólo uno mueve saldo.
 */
const pasos = [
  {
    nombre: "liquidar",
    // lo más importante de la lista: sin esto, la gente apuesta y no cobra
    correr: () => run("npx", ["tsx", "scripts/settle.mts"]),
  },
  {
    nombre: "reponer",
    correr: () => run("npx", ["tsx", "scripts/roll.mts"]),
  },
  {
    nombre: "volatilidad",
    saltar: () => existsSync(archivoIv),
    correr: () => run("npx", ["tsx", "scripts/collect-iv.mts"]),
  },
];

let fallos = 0;
for (const paso of pasos) {
  if (solo && solo !== paso.nombre) continue;
  if (paso.saltar?.()) {
    log(`${paso.nombre}: ya estaba hecho hoy`);
    continue;
  }
  try {
    log(`${paso.nombre}: empezando…`);
    paso.correr();
    log(`${paso.nombre}: listo`);
  } catch (error) {
    // sin red hoy: en la próxima corrida se retoma. No se inventa un archivo.
    fallos += 1;
    log(`${paso.nombre}: falló — ${error.message?.split("\n")[0] ?? error}`);
  }
}

const rutas = ["data/iv", "data/settlements.json", "public/mercados.json", "public/resoluciones.json"];

try {
  const pendiente = run("git", ["status", "--porcelain", ...rutas], { quiet: true });
  if (!pendiente.trim()) {
    log("no hay cambios que commitear");
    process.exit(fallos > 0 ? 1 : 0);
  }

  run("git", ["add", ...rutas], { quiet: true });
  run("git", ["commit", "-m", `datos: liquidación y catálogo del ${fecha}`], { quiet: true });
  log("commiteado");

  if (push) {
    const rama = run("git", ["rev-parse", "--abbrev-ref", "HEAD"], { quiet: true }).trim();
    // el cron puede cruzarse con tu trabajo: rebase antes de subir
    run("git", ["pull", "--rebase", "--autostash", "origin", rama], { quiet: true });
    run("git", ["push", "origin", `HEAD:${rama}`], { quiet: true });
    log(`subido a ${rama}`);
  }
} catch (error) {
  // los datos ya están en disco: un fallo de git no los pierde
  log(`git falló, pero lo del día quedó guardado: ${error.message?.split("\n")[0]}`);
  process.exit(1);
}

process.exit(fallos > 0 ? 1 : 0);
