#!/usr/bin/env node
/**
 * VALIDATION_REPORT — suite V1–V24 + red-team.
 *
 * Parte estática (esta herramienta): V1, V10, V11, V24.
 * Parte de comportamiento: vitest. Cada prueba cuyo nombre empieza con `V<n>`
 * o `RT/<n>` se cosecha de aquí y entra al reporte con su veredicto real.
 */
import { existsSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
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

/* ------------------------------- S1 -------------------------------------- */
check("S1", "ningún secreto ni credencial incrustada en el código", () => {
  const problems = [];
  const patterns = [
    /\bsk[-_](?:live|test|prod)[-_][A-Za-z0-9]{8,}/,
    /\bBearer\s+[A-Za-z0-9._-]{20,}/,
    /\b(?:api[_-]?key|secret|password|token)\s*[:=]\s*["'][^"'$\s]{16,}["']/i,
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  ];
  for (const file of code) {
    const text = read(file);
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) problems.push(`${rel(file)} parece llevar un secreto: "${match[0].slice(0, 24)}…"`);
    }
  }
  // toda integración entra por configuración de entorno, nunca por literal
  const config = read(join(SRC, "lib", "config.ts"));
  if (!/VITE_/.test(config)) problems.push("config.ts no lee variables de entorno");
  return problems;
});

/* ------------------------------- T1 -------------------------------------- */
check("T1", "la telemetría no puede sacar datos sensibles del dispositivo", () => {
  const problems = [];
  const analytics = read(join(SRC, "adapters", "analytics", "httpAnalytics.ts"));
  const reporter = read(join(SRC, "adapters", "errors", "httpErrorReporter.ts"));

  const listOf = (text, name) => {
    const start = text.indexOf(name);
    if (start === -1) return null;
    const open = text.indexOf("[", start);
    const close = text.indexOf("]", open);
    return text.slice(open + 1, close);
  };

  const allowed = listOf(analytics, "ALLOWED_PROPS");
  const context = listOf(reporter, "CONTEXT_ALLOWED");
  if (!allowed || !context) return ["falta la lista blanca de propiedades"];

  // ninguna de estas puede estar permitida, ni por descuido futuro (R-020)
  const forbidden = ["address", "email", "phone", "telefono", "size", "amount", "balance", "query", "title", "user_message"];
  for (const [name, list] of [["analítica", allowed], ["errores", context]]) {
    for (const key of forbidden) {
      if (new RegExp(`["']${key}["']`).test(list)) {
        problems.push(`la lista blanca de ${name} permite "${key}"`);
      }
    }
  }
  // el reporter nunca manda el mensaje que ve el usuario
  if (/user_message_es/.test(reporter)) {
    problems.push("el reporter de errores envía el mensaje del usuario");
  }
  return problems;
});

/* ------------------------------- C1 -------------------------------------- */
check("C1", "una build con dinero real exige la puerta de elegibilidad activa", () => {
  const flags = read(join(SRC, "lib", "flags.ts"));
  const mock = /mock_data:\s*true/.test(flags);
  const enforced = /eligibility_enforced:\s*true/.test(flags);
  // con datos simulados no se mueve dinero y la puerta puede estar abierta;
  // en cuanto deja de ser simulado, encenderla es obligatorio (COMPLIANCE §4)
  if (!mock && !enforced) {
    return [
      "la build ya no es simulada pero `eligibility_enforced` sigue apagado: " +
        "no se puede recibir dinero sin la tabla de países activa",
    ];
  }
  return [];
});

/* ------------------------------- P1 -------------------------------------- */
check("P1", "el motor de puntos no puede convertirse en dinero por descuido", () => {
  const problems = [];
  const points = read(join(SRC, "domain", "points.ts"));
  const flags = read(join(SRC, "lib", "flags.ts"));

  // el canje no existe como función: habilitarlo exige borrar código (R-026)
  if (!/export function canCashOut\(\): false/.test(points)) {
    problems.push("canCashOut ya no está clavado en false: el canje dejó de ser imposible");
  }
  if (!/no se prestan|insuficiente/.test(points)) {
    problems.push("el ledger de puntos permite saldo negativo: eso es crédito");
  }
  // con dinero real hay que declarar el motor y la puerta de elegibilidad
  if (/market_engine:\s*"parimutuel_money"/.test(flags) && !/eligibility_enforced:\s*true/.test(flags)) {
    problems.push("el motor pasó a dinero sin encender la puerta de elegibilidad");
  }

  // ninguna pantalla arma montos a mano: todo pasa por la unidad vigente
  const screens = code.filter((file) => /screens|components/.test(file));
  for (const file of screens) {
    const text = read(file);
    // `compactUsd` y `usd` sólo son legítimos tras comprobar que NO hay pozo
    for (const match of text.matchAll(/\b(compactUsd|usd)\(/g)) {
      const line = text.slice(0, match.index).split("\n").length;
      // se mira el bloque alrededor: el uso legítimo va tras comprobar el pozo
      const context = text.split("\n").slice(Math.max(0, line - 6), line + 1).join(" ");
      if (!/\bpool\b|isPointsMode|!points/.test(context)) {
        problems.push(
          `${rel(file)}:${line} usa ${match[1]}() sin comprobar la unidad vigente`,
        );
      }
    }
  }
  return problems;
});

/* ------------------------------- P2 -------------------------------------- */
check("P2", "ningún mercado propio se publica sin fuente verificable", () => {
  const catalog = read(join(SRC, "adapters", "ownMarkets", "catalog.ts"));
  const problems = [];
  // la validación tiene que correr al cargar el módulo, no en producción
  if (!/assertPublishable/.test(catalog)) {
    problems.push("el catálogo no valida sus especificaciones de resolución");
  }
  const sources = [...catalog.matchAll(/sourceUrl:\s*"([^"]+)"/g)].map((m) => m[1]);
  if (sources.length === 0) problems.push("el catálogo no cita ninguna fuente");
  for (const url of sources) {
    if (!/^https:\/\//.test(url)) problems.push(`fuente no pública: ${url}`);
  }
  const criteria = [...catalog.matchAll(/criterion:\s*\n?\s*"([^"]+)"/g)].map((m) => m[1]);
  for (const criterion of criteria) {
    if (/marea (decide|determina)/i.test(criterion)) {
      problems.push(`criterio discrecional: "${criterion.slice(0, 40)}…"`);
    }
  }
  return problems;
});

/* ------------------------------- E1 -------------------------------------- */
check("E1", "el Edge sale sólo de referencia externa medida", () => {
  const problems = [];
  const wiring = read(join(SRC, "adapters", "index.ts"));

  // el modelo de precio es investigación hasta que pase su calibración: no
  // puede colarse al camino de producción por un import distraído (R-038)
  if (/createPriceModelProvider/.test(wiring)) {
    problems.push(
      "src/adapters/index.ts enchufa el modelo de precio: hoy el Edge sólo sale de referencia externa",
    );
  }
  // y la referencia sí tiene que estar enchufada, o el Edge es cero siempre
  if (!/loadReference/.test(wiring)) {
    problems.push("la referencia externa no está enchufada: el Edge sería cero en todas partes");
  }

  // la puerta del modelo sigue cerrada mientras la calibración no pase
  const lock = JSON.parse(readFileSync(join(ROOT, "vault", "calibration.lock.json"), "utf8"));
  const model = read(join(SRC, "domain", "priceModel.ts"));
  const max = Number(model.match(/MAX_USABLE_ECE_PP\s*=\s*([\d.]+)/)?.[1] ?? NaN);
  if (!Number.isFinite(max)) problems.push("no se pudo leer el máximo admisible del modelo");
  for (const tipo of ["cierre", "toca"]) {
    const entry = lock[tipo];
    if (!entry) {
      problems.push(`el lock de calibración no declara "${tipo}"`);
      continue;
    }
    // la coherencia importa: `usable` no puede decir que sí si el error no pasa
    if (entry.usable !== entry.eceOutOfSample <= max) {
      problems.push(
        `el lock de "${tipo}" dice usable=${entry.usable} con ${entry.eceOutOfSample} pp y máximo ${max} pp`,
      );
    }
  }
  return problems;
});

/* ------------------------------- D1 -------------------------------------- */
check("D1", "el dataset de volatilidad llega de verdad al repo", () => {
  // se ignoró en silencio una vez: el .gitignore de la raíz excluye `data/`
  // y los archivos del día se quedaban sólo en disco. Un dataset que no se
  // versiona no se acumula, y acumularse es todo su valor (R-037).
  const problems = [];
  const dir = join(ROOT, "data", "iv");
  if (!existsSync(dir)) return ["falta data/iv: el recolector nunca corrió"];

  const dias = readdirSync(dir).filter((f) => f.endsWith(".json"));
  if (dias.length === 0) problems.push("no hay ningún día guardado en data/iv");

  for (const dia of dias) {
    const rel = `data/iv/${dia}`;
    const ignored = spawnSync("git", ["check-ignore", "-q", rel], { cwd: ROOT });
    // salida 0 = está ignorado, que es justo lo que no queremos
    if (ignored.status === 0) problems.push(`${rel} está ignorado por git y no se versiona`);
  }
  return problems;
});

/* ------------------------------- L1 -------------------------------------- */
check("L1", "todo mercado publicado tiene camino de liquidación", () => {
  // el agujero que encontramos revisando el estado real: los mercados cerraban
  // y nadie los pagaba nunca. La puerta vive aquí para que no vuelva (R-040).
  const problems = [];
  const wiring = read(join(SRC, "adapters", "index.ts"));
  if (!/loadSettlements/.test(wiring)) {
    problems.push("la app no lee resoluciones: los mercados cerrarían sin pagar");
  }
  const store = read(join(SRC, "state", "store.tsx"));
  if (!/creditSettlements/.test(store)) {
    problems.push("nada acredita los pagos al ledger: apostar restaría y nada devolvería");
  }
  if (!existsSync(join(ROOT, "scripts", "settle.mts"))) {
    problems.push("falta el liquidador automático (scripts/settle.mts)");
  }

  // un liquidador que dejó de correr es indistinguible de uno que corre bien
  // si nadie mira la fecha del archivo que publica
  const publicado = join(ROOT, "public", "resoluciones.json");
  if (existsSync(publicado)) {
    const { generatedAt } = JSON.parse(readFileSync(publicado, "utf8"));
    const horas = (Date.now() - new Date(generatedAt).getTime()) / 3_600_000;
    if (!Number.isFinite(horas)) problems.push("resoluciones.json no declara cuándo se generó");
    else if (horas > 36) {
      problems.push(
        `el liquidador no corre desde hace ${Math.round(horas)} h: corre \`npm run settle\``,
      );
    }
  }
  return problems;
});

/* ------------------------------- M1 -------------------------------------- */
check("M1", "el feed no se queda sin mercados abiertos", () => {
  // un catálogo con fechas fijas caduca y el feed se vacía sin avisar (R-041)
  const problems = [];
  const MINIMO = 6;
  const ahora = Date.now();
  const fechas = [
    ...read(join(SRC, "adapters", "ownMarkets", "catalog.ts")).matchAll(
      /closesAt:\s*"([^"]+)"/g,
    ),
  ].map((m) => Date.parse(m[1]));

  const catalogoPublicado = join(ROOT, "public", "mercados.json");
  if (existsSync(catalogoPublicado)) {
    const { seeds = [] } = JSON.parse(readFileSync(catalogoPublicado, "utf8"));
    for (const seed of seeds) fechas.push(Date.parse(seed.closesAt));
  }

  const abiertos = fechas.filter((fecha) => fecha > ahora).length;
  if (abiertos < MINIMO) {
    problems.push(
      `sólo ${abiertos} mercados abiertos (mínimo ${MINIMO}): corre \`npm run roll\` ` +
        `o escribe mercados nuevos en el catálogo`,
    );
  }
  return problems;
});

/* ------------------------------- O1 -------------------------------------- */
check("O1", "lo automatizable no se deja en manos de una persona", () => {
  // decir "hace falta un humano" sin haber buscado la API es pereza con
  // disfraz de prudencia (AGENTE §2). Esto cuenta cuánto queda manual.
  const problems = [];
  // se mide el feed real, no sólo el archivo escrito a mano: lo que importa
  // es qué proporción de lo que ve el usuario se resuelve sin una persona
  const catalog = read(join(SRC, "adapters", "ownMarkets", "catalog.ts"));
  let total = (catalog.match(/^\s{4}id:/gm) ?? []).length;
  let conRegla = (catalog.match(/^\s{4}rule:/gm) ?? []).length;

  const publicado = join(ROOT, "public", "mercados.json");
  if (existsSync(publicado)) {
    const { seeds = [] } = JSON.parse(readFileSync(publicado, "utf8"));
    total += seeds.length;
    conRegla += seeds.filter((seed) => seed.rule).length;
  }
  if (total === 0) problems.push("el catálogo no tiene mercados");
  else if (conRegla / total < 0.5) {
    problems.push(
      `sólo ${conRegla} de ${total} mercados se resuelven solos: busca la API de los demás`,
    );
  }
  // y el oráculo de series tiene que estar enchufado, o las reglas no sirven
  const oracles = read(join(SRC, "adapters", "oracles", "priceOracle.ts"));
  if (!/createSeriesOracle/.test(oracles)) {
    problems.push("el oráculo de series no está en la lista de oráculos");
  }
  return problems;
});

/* ------------------------------- A1 -------------------------------------- */
check("A1", "todo camino de dinero pasa por la puerta y por contabilidad", () => {
  const problems = [];
  const solicitudes = read(join(SRC, "domain", "solicitudes.ts"));
  // una solicitud de dinero no puede nacer sin consultar la elegibilidad: si
  // se crea primero y se valida después, el camino ya está abierto (R-045)
  if (!/eligibilityFor/.test(solicitudes)) {
    problems.push("las solicitudes de dinero no consultan la puerta de elegibilidad");
  }
  // y el retiro no puede saltarse la revisión humana
  if (!/pendiente: \["en_revision"/.test(solicitudes)) {
    problems.push("un retiro puede saltarse la revisión");
  }

  // el contrato de custodia declara que es simulado y no sabe firmar (R-022).
  // Se mira el código sin comentarios: el módulo documenta a propósito lo que
  // NO trae, y buscar el nombre en la prosa daría un falso positivo
  const contrato = read(join(SRC, "adapters", "custodia", "contrato.ts"));
  const codigo = contrato
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");
  if (!/esSimulado/.test(codigo)) {
    problems.push("el contrato de custodia no declara que es simulado");
  }
  for (const prohibido of ["firmar", "privateKey", "signTransaction", "sendTransaction"]) {
    if (codigo.includes(prohibido)) {
      problems.push(`el contrato expone ${prohibido}: eso espera opinión legal`);
    }
  }

  // ningún país puede mover dinero todavía
  const elegibilidad = read(join(SRC, "domain", "eligibility.ts"));
  if (/status: "permitido"/.test(elegibilidad)) {
    problems.push("hay un país en `permitido` sin que conste la opinión legal");
  }

  // la comisión que se resta tiene que quedar asentada (R-064)
  const store = read(join(ROOT, "server", "store.mts"));
  if (!/CUENTAS_SISTEMA\.tesoreria/.test(store)) {
    problems.push("la comisión no llega a la tesorería contable");
  }
  return problems;
});

/* ------------------------------- H1 -------------------------------------- */
check("H1", "ningún mercado depende de que una persona lo confirme", () => {
  // R-062 topa en tres los mercados abiertos que dependen de que una persona
  // se siente a mirarlos. La regla existía desde hace tiempo y **no tenía
  // verificación**: por eso llegó a haber seis sin que nadie se enterara. Una
  // regla escrita recuerda; una verificación impide (AGENTE §7).
  const problems = [];
  const catalog = read(join(SRC, "adapters", "ownMarkets", "catalog.ts"));
  const total = (catalog.match(/^\s{4}id:/gm) ?? []).length;
  const conRegla = (catalog.match(/^\s{4}rule:/gm) ?? []).length;
  const aMano = total - conRegla;
  // el tope pasó de tres a CERO: un mercado de confirmación manual no dice
  // quién lo confirma, ni cuándo, ni cómo. Sin nadie de guardia es una promesa
  // que no se puede cumplir, y publicar mercados sin proceso de resolución
  // rompe lo único que sostiene el producto (R-040)
  const TOPE = 0;
  if (aMano > TOPE) {
    problems.push(
      `${aMano} de ${total} mercados dependen de que una persona los confirme, y el tope es ${TOPE}: ` +
        `busca la API o no publiques la pregunta`,
    );
  }
  return problems;
});

/* ------------------------------- G1 -------------------------------------- */
check("G1", "un mercado se puede compartir y la liga trae vista previa", () => {
  const problems = [];
  if (!existsSync(join(ROOT, "server", "compartir.mts"))) {
    problems.push("no existe el módulo de vista previa: las ligas se verían pelonas");
  } else {
    const compartir = read(join(ROOT, "server", "compartir.mts"));
    for (const etiqueta of ["og:title", "og:description", "og:url"]) {
      if (!compartir.includes(etiqueta)) problems.push(`falta la etiqueta ${etiqueta}`);
    }
    // lo que venga del catálogo se escapa: el título entra al HTML
    if (!/escapar/.test(compartir)) problems.push("el HTML de la vista previa no escapa el título");
  }
  const detalle = read(join(SRC, "screens", "MarketDetailScreen.tsx"));
  if (!/market-share/.test(detalle)) problems.push("el detalle no tiene botón de compartir");
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
