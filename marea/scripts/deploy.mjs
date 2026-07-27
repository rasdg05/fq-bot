#!/usr/bin/env node
/**
 * Publica Marea desde tu máquina, sin CI.
 *
 * Verifica, construye y sube a un hosting estático. El bundle no necesita
 * servidor ni reglas de reescritura: la app es una sola página y la navegación
 * es estado, así que cualquier hosting estático sirve.
 *
 *   npm run deploy                 # verifica, construye y sube
 *   npm run deploy -- --dry        # sólo verifica y construye
 *   npm run deploy -- --host netlify
 */
import { execFileSync } from "node:child_process";
import { existsSync, readdirSync, statSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DIST = join(ROOT, "dist");
const args = process.argv.slice(2);
const dry = args.includes("--dry");
const hostArg = args.indexOf("--host");
const host = hostArg >= 0 ? args[hostArg + 1] : (process.env.MAREA_HOST ?? "cloudflare");

/** Cada uno tiene capa gratis y se maneja desde la terminal. */
const HOSTS = {
  cloudflare: {
    nombre: "Cloudflare Pages",
    alta: "npx wrangler login",
    comando: ["npx", ["wrangler", "pages", "deploy", "dist", "--project-name", "marea"]],
  },
  netlify: {
    nombre: "Netlify",
    alta: "npx netlify login",
    comando: ["npx", ["netlify", "deploy", "--prod", "--dir", "dist"]],
  },
  vercel: {
    nombre: "Vercel",
    alta: "npx vercel login",
    comando: ["npx", ["vercel", "deploy", "--prod", "dist", "--yes"]],
  },
  surge: {
    nombre: "Surge",
    alta: "npx surge login",
    comando: ["npx", ["surge", "dist"]],
  },
};

const elegido = HOSTS[host];
if (!elegido) {
  console.error(`Hosting desconocido: "${host}". Opciones: ${Object.keys(HOSTS).join(", ")}`);
  process.exit(1);
}

function paso(titulo, fn) {
  process.stdout.write(`\n▸ ${titulo}\n`);
  fn();
}

const run = (command, argv) =>
  execFileSync(command, argv, { cwd: ROOT, stdio: "inherit", env: process.env });

try {
  paso("Tipos", () => run("npx", ["tsc", "-b", "--noEmit"]));
  paso("VALIDATION_REPORT", () => run("node", ["scripts/validate.mjs"]));
  paso("Build", () => {
    const salida = execFileSync("npm", ["run", "build"], {
      cwd: ROOT,
      encoding: "utf8",
      env: process.env,
    });
    process.stdout.write(salida);
    // un aviso del bundler suele ser un recurso que no se va a resolver:
    // mejor enterarse antes de publicar que por un 404 en el teléfono
    const avisos = salida
      .split("\n")
      .filter((linea) => /didn't resolve|\[warn\]|warning:/i.test(linea));
    if (avisos.length > 0) {
      console.warn(`\n⚠ La build dejó ${avisos.length} aviso(s):`);
      for (const aviso of avisos.slice(0, 5)) console.warn(`   ${aviso.trim()}`);
    }
  });
} catch {
  console.error("\n✗ La verificación falló. No se publica nada.");
  process.exit(1);
}

// una build vacía o sin index.html no se sube: es peor que no publicar
if (!existsSync(join(DIST, "index.html"))) {
  console.error("\n✗ dist/index.html no existe: la build no sirvió.");
  process.exit(1);
}
const peso = readdirSync(DIST, { recursive: true })
  .map((f) => join(DIST, String(f)))
  .filter((f) => existsSync(f) && statSync(f).isFile())
  .reduce((sum, f) => sum + statSync(f).size, 0);
console.log(`\n✓ Build lista: ${(peso / 1024).toFixed(0)} kB en dist/`);

if (dry) {
  console.log("\n--dry: no se publica. Para publicar, corre sin --dry.");
  process.exit(0);
}

console.log(`\n▸ Publicando en ${elegido.nombre}`);
try {
  run(...elegido.comando);
  console.log(`\n✓ Publicado en ${elegido.nombre}.`);
} catch {
  console.error(
    `\n✗ No se pudo publicar en ${elegido.nombre}.\n\n` +
      `Si es la primera vez, hace falta la cuenta (gratis) y entrar una vez:\n` +
      `  ${elegido.alta}\n\n` +
      `Después vuelve a correr \`npm run deploy\`.\n` +
      `Para usar otro: npm run deploy -- --host ${Object.keys(HOSTS)
        .filter((h) => h !== host)
        .join(" | ")}`,
  );
  process.exit(1);
}
