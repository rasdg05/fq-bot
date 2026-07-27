#!/usr/bin/env node
/**
 * Tarea diaria, para correr desde tu máquina sin depender de CI.
 *
 * Toma la superficie de volatilidad del día y la guarda en el repo. Está hecha
 * para vivir en un cron: es idempotente (si el día ya está guardado no hace
 * nada), no rompe si no hay red, y deja rastro en `data/iv/daily.log`.
 *
 *   npm run daily            # toma, commitea y sube
 *   npm run daily -- --no-push   # sólo commitea, sin subir
 */
import { execFileSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const LOG = join(ROOT, "data", "iv", "daily.log");
const push = !process.argv.includes("--no-push");

function log(line) {
  const stamp = new Date().toISOString();
  const text = `${stamp} ${line}`;
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
const archivo = join(ROOT, "data", "iv", `${fecha}.json`);

if (existsSync(archivo)) {
  log(`el día ${fecha} ya estaba guardado, no hay nada que hacer`);
  process.exit(0);
}

try {
  log(`tomando la superficie del ${fecha}…`);
  run("npx", ["tsx", "scripts/collect-iv.mts"]);
} catch (error) {
  // sin red hoy: mañana se retoma. No se inventa un archivo vacío.
  log(`falló la toma: ${error.message?.split("\n")[0] ?? error}`);
  process.exit(1);
}

if (!existsSync(archivo)) {
  log("la toma terminó pero no dejó archivo: se aborta sin commitear");
  process.exit(1);
}

try {
  const pendiente = run("git", ["status", "--porcelain", "data/iv"], { quiet: true });
  if (!pendiente.trim()) {
    log("no hay cambios que commitear");
    process.exit(0);
  }

  run("git", ["add", "data/iv"], { quiet: true });
  run("git", ["commit", "-m", `datos: superficie de volatilidad del ${fecha}`], {
    quiet: true,
  });
  log("commiteado");

  if (push) {
    const rama = run("git", ["rev-parse", "--abbrev-ref", "HEAD"], { quiet: true }).trim();
    // el cron puede cruzarse con tu trabajo: rebase antes de subir
    run("git", ["pull", "--rebase", "--autostash", "origin", rama], { quiet: true });
    run("git", ["push", "origin", `HEAD:${rama}`], { quiet: true });
    log(`subido a ${rama}`);
  }
} catch (error) {
  // el dato ya está en disco: un fallo de git no lo pierde
  log(`git falló, pero el archivo del día quedó guardado: ${error.message?.split("\n")[0]}`);
  process.exit(1);
}
