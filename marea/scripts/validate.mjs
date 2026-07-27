#!/usr/bin/env node
/**
 * VALIDATION_REPORT — suite V1–V24 + red-team.
 *
 * Parte estática (esta herramienta): V1, V10, V11, V24.
 * Parte de comportamiento: vitest. Cada prueba cuyo nombre empieza con `V<n>`
 * o `RT/<n>` se cosecha de aquí y entra al reporte con su veredicto real.
 */
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join, relative, extname } from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = process.cwd();
const SRC = join(ROOT, "src");
const TOKENS = join(SRC, "styles", "tokens.css");
const LOCK = join(ROOT, "vault", "tokens.lock.json");

const passed = [];
const failed = [];

function check(id, title, fn) {
  try {
    const problems = fn() ?? [];
    if (problems.length === 0) passed.push(`${id} — ${title}`);
    else failed.push({ id, title, problems });
  } catch (error) {
    failed.push({ id, title, problems: [String(error?.message ?? error)] });
  }
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

const files = walk(SRC);
const code = files.filter((f) => [".ts", ".tsx"].includes(extname(f)));
const read = (f) => readFileSync(f, "utf8");
const rel = (f) => relative(ROOT, f);

/* ------------------------------- V1 -------------------------------------- */
check("V1", "los tokens son la única fuente de color", () => {
  const problems = [];
  const literal = /#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(/;
  for (const file of code) {
    read(file)
      .split("\n")
      .forEach((line, index) => {
        if (line.trim().startsWith("*") || line.trim().startsWith("//")) return;
        if (literal.test(line)) {
          problems.push(`${rel(file)}:${index + 1} color literal fuera de tokens.css`);
        }
      });
  }
  // y el CSS de tokens es el único archivo con literales
  for (const file of files.filter((f) => extname(f) === ".css")) {
    if (file !== TOKENS && literal.test(read(file))) {
      problems.push(`${rel(file)} declara color fuera de tokens.css`);
    }
  }
  return problems;
});

/* ------------------------------- V10 ------------------------------------- */
check("V10", "cero lenguaje prohibido y cero relleno", () => {
  const banned = [
    /copiloto|co-piloto/i,
    /fibonacci/i,
    /deflated\s+sharpe/i,
    /\bDSR\b/,
    /se[nñ]al(es)?\s+ganador/i,
    /lorem\s+ipsum/i,
    /\bTO" \+ "DO\b/,
    /garantizad[oa]/i,
    /\bmillonari[oa]\b/i,
  ];
  // "FQ" y el marcador de pendiente se buscan como palabra suelta
  const wordBanned = [/\bFQ\b/, new RegExp(`\\b${"TO"}${"DO"}\\b`), /\bFIXME\b/];
  const problems = [];
  for (const file of [...code, ...files.filter((f) => extname(f) === ".css")]) {
    const text = read(file);
    for (const pattern of [...banned, ...wordBanned]) {
      const match = text.match(pattern);
      if (match) problems.push(`${rel(file)} contiene "${match[0]}"`);
    }
  }
  return problems;
});

/* ------------------------------- V11 ------------------------------------- */
check("V11", "sin desbordes horizontales en móvil", () => {
  const problems = [];
  if (!/overflow-x:\s*hidden/.test(read(TOKENS))) {
    problems.push("tokens.css no fija overflow-x: hidden en body");
  }
  // `max-w-[...]` es un tope, no un ancho: sólo miran w- y min-w- reales
  const wide = /(?<![a-z-])(?:w|min-w)-\[(\d+)px\]/g;
  for (const file of code) {
    const text = read(file);
    for (const match of text.matchAll(wide)) {
      // 360 px es el ancho de referencia más angosto que soportamos
      if (Number(match[1]) > 360) {
        problems.push(`${rel(file)} usa ${match[0]}, más ancho que el viewport base`);
      }
    }
    if (/\bw-screen\b/.test(text)) {
      problems.push(`${rel(file)} usa w-screen (ignora el scrollbar y desborda)`);
    }
    // toda fila que desborda a propósito debe declarar su propio scroll
    if (/overflow-x-auto/.test(text) === false && /flex\s+gap-2\s+overflow/.test(text)) {
      problems.push(`${rel(file)} tiene una fila desbordable sin overflow-x-auto`);
    }
  }
  return problems;
});

/* ------------------------------- V1b ------------------------------------- */
check("V1", "ningún token de color usa modificador de opacidad", () => {
  // Tailwind no puede aplicar alfa sobre un color declarado como `var(--x)`:
  // la declaración se descarta y la superficie queda transparente (R-017).
  const tokens = "bg|text|border|ring|fill|stroke";
  const names = "bg|panel|panel2|line|line2|text|text2|muted|teal|teal-deep|teal-soft|teal-ink|up|dn|hot|live";
  const bad = new RegExp(`\\b(?:${tokens})-(?:${names})/\\d+`, "g");
  const varAlpha = /var\(--[a-z0-9-]+\)\]\/\d+/g;
  const problems = [];
  for (const file of code) {
    const text = read(file);
    for (const match of [...text.matchAll(bad), ...text.matchAll(varAlpha)]) {
      problems.push(`${rel(file)} usa "${match[0]}" sobre un color de token`);
    }
  }
  return problems;
});

/* ------------------------------- V24 ------------------------------------- */
check("V24", "cero drift del design system entre fases", () => {
  const problems = [];
  const themes = {};
  for (const selector of ['data-theme="dark"', 'data-theme="light"']) {
    const start = read(TOKENS).indexOf(`:root[${selector}]`);
    if (start === -1) return [`tokens.css no declara :root[${selector}]`];
    const css = read(TOKENS);
    const body = css.slice(css.indexOf("{", start) + 1, css.indexOf("}", start));
    themes[selector] = Object.fromEntries(
      [...body.matchAll(/--([a-z0-9-]+):\s*([^;]+);/gi)].map((m) => [m[1], m[2].trim()]),
    );
  }

  let lock;
  try {
    lock = JSON.parse(readFileSync(LOCK, "utf8"));
  } catch {
    writeFileSync(LOCK, `${JSON.stringify(themes, null, 2)}\n`);
    return ["tokens.lock.json no existía: se generó la línea base, vuelve a validar"];
  }

  for (const selector of Object.keys(themes)) {
    const before = lock[selector] ?? {};
    const after = themes[selector];
    for (const key of new Set([...Object.keys(before), ...Object.keys(after)])) {
      if (before[key] !== after[key]) {
        problems.push(
          `${selector} --${key}: ${before[key] ?? "(ausente)"} → ${after[key] ?? "(ausente)"}`,
        );
      }
    }
  }
  return problems;
});

/* --------------------------- pruebas de comportamiento -------------------- */
const run = spawnSync(
  "npx",
  ["vitest", "run", "--reporter=json", "--outputFile=.vitest-report.json"],
  { cwd: ROOT, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
);

let report;
try {
  report = JSON.parse(readFileSync(join(ROOT, ".vitest-report.json"), "utf8"));
} catch {
  failed.push({
    id: "SUITE",
    title: "vitest no produjo reporte",
    problems: [run.stderr?.slice(-800) ?? "sin salida"],
  });
  report = { testResults: [] };
}

const behavioural = [];
for (const file of report.testResults ?? []) {
  for (const test of file.assertionResults ?? []) {
    behavioural.push({
      name: test.fullName ?? test.title,
      title: test.title ?? "",
      ok: test.status === "passed",
      message: (test.failureMessages ?? []).join("\n").slice(0, 400),
    });
  }
}

const tagged = behavioural.filter((t) => /^(V\d+|RT\/\d+)\s/.test(t.title));
for (const test of tagged) {
  const id = test.title.match(/^(V\d+|RT\/\d+)/)[1];
  if (test.ok) passed.push(`${id} — ${test.title.replace(/^\S+\s—\s/, "")}`);
  else failed.push({ id, title: test.title, problems: [test.message] });
}

const untaggedFailures = behavioural.filter((t) => !t.ok && !/^(V\d+|RT\/\d+)\s/.test(t.title));
for (const test of untaggedFailures) {
  failed.push({ id: "TEST", title: test.name, problems: [test.message] });
}

/* --------------------------- cobertura de la suite ------------------------ */
const covered = new Set(
  [...passed, ...failed.map((f) => `${f.id} — ${f.title}`)].map((line) => line.split(" ")[0]),
);
const missing = [];
for (let n = 1; n <= 24; n += 1) if (!covered.has(`V${n}`)) missing.push(`V${n}`);
for (let n = 1; n <= 10; n += 1) if (!covered.has(`RT/${n}`)) missing.push(`RT/${n}`);
if (missing.length) {
  failed.push({
    id: "COBERTURA",
    title: "hay checks de la suite sin prueba que los ejerza",
    problems: missing,
  });
}

/* --------------------------------- salida -------------------------------- */
const uniquePassed = [...new Set(passed)].sort(byId);
function byId(a, b) {
  const num = (s) => {
    const m = s.match(/^(?:V(\d+)|RT\/(\d+))/);
    if (!m) return 999;
    return m[1] ? Number(m[1]) : 100 + Number(m[2]);
  };
  return num(a) - num(b);
}

console.log("VALIDATION_REPORT");
console.log("=================");
console.log(`\npassed[] (${uniquePassed.length})`);
for (const line of uniquePassed) console.log(`  ✓ ${line}`);

console.log(`\nfailed[] (${failed.length})`);
for (const item of failed) {
  console.log(`  ✗ ${item.id} — ${item.title}`);
  for (const problem of item.problems) {
    console.log(`      · ${String(problem).split("\n")[0]}`);
  }
}

const verdict = failed.length === 0 ? "PASS" : "FAIL";
console.log(`\nverdict: ${verdict}`);
process.exit(verdict === "PASS" ? 0 : 1);
