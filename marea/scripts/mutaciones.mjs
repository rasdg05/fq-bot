/**
 * Barrido de mutaciones. Rompe el código a propósito y comprueba que la suite
 * se pone roja.
 *
 *   node scripts/mutaciones.mjs            # todas
 *   node scripts/mutaciones.mjs merkle     # sólo las que contengan "merkle"
 *
 * ## Por qué existe
 *
 * `COLA_TRABAJO.md` §0.5 dice: «rompe cada test nuevo a propósito una vez y
 * confirma que se pone rojo. Un test que nunca viste en rojo no sabes si prueba
 * algo». Es la regla más valiosa del repo y la más fácil de saltarse, porque
 * hacerlo a mano son cinco minutos por test y nadie los echa de menos.
 *
 * Y funciona. En la sesión que escribió esto, el barrido encontró **siete**
 * mutaciones que la suite no detectaba, y las tres peores eran de propiedades
 * adversarias: la separación de dominio del árbol de Merkle, la codificación con
 * longitudes de las hojas y la idempotencia del cierre contable. Los tres tests
 * existían, pasaban en verde, y **ninguno probaba lo que su nombre decía**. El
 * camino feliz se prueba solo; lo que un atacante rompería hay que romperlo.
 *
 * ## Mutantes equivalentes
 *
 * Una mutación que sobrevive **no siempre es un test que falta**: a veces el
 * cambio no altera nada observable. Cuando eso pase, mídelo antes de escribir un
 * test — y si de verdad es equivalente, apunta por qué en `motivo` en vez de
 * forzar una comprobación que sólo mira el texto de un mensaje.
 */
import { execFileSync } from "node:child_process";
import { copyFileSync, readFileSync, writeFileSync, mkdtempSync } from "node:fs";
import { join, basename } from "node:path";
import { tmpdir } from "node:os";

const D = "src/domain/";

/**
 * Cada entrada: qué se rompe, dónde, y qué pruebas deberían gritar.
 * `equivalente` marca las que se comprobó que no cambian nada observable.
 */
const MUTACIONES = [
  // --- U1 · la semilla como subsidio ---
  { nombre: "U1 bettorStake ignora el modo de la semilla", archivo: `${D}parimutuel.ts`,
    de: 'return pool.seedMode === "subsidio" ? seedStake(pool, id) : 0;',
    a: "return seedStake(pool, id);", tests: ["tests/parimutuel.test.ts"] },
  { nombre: "U1 bettorStake permite un denominador negativo", archivo: `${D}parimutuel.ts`,
    de: "return Math.max(0, outcomeStake(pool, id) - subsidyStake(pool, id));",
    a: "return outcomeStake(pool, id) - subsidyStake(pool, id);", tests: ["tests/parimutuel.test.ts"] },
  { nombre: "U1 la comisión abusiva no se recorta", archivo: `${D}parimutuel.ts`,
    de: "return Math.min(MAX_FEE_BPS, feeBps);", a: "return feeBps;", tests: ["tests/parimutuel.test.ts"] },
  { nombre: "U1 normalizePool comparte el mapa de semilla", archivo: `${D}parimutuel.ts`,
    de: "...(pool.seed ? { seed: { ...pool.seed } } : {}),", a: "...(pool.seed ? { seed: pool.seed } : {}),",
    tests: ["tests/parimutuel.test.ts"] },
  { nombre: "U1 payoutMultiplier no descuenta el subsidio", archivo: `${D}parimutuel.ts`,
    de: "  const sameSide = bettorStake(pool, id) + stake;", a: "  const sameSide = outcomeStake(pool, id) + stake;",
    tests: ["tests/parimutuel.test.ts"] },
  { nombre: "U1 settle no descuenta el subsidio", archivo: `${D}parimutuel.ts`,
    de: "  const winnerStake = bettorStake(pool, winner);", a: "  const winnerStake = outcomeStake(pool, winner);",
    tests: ["tests/parimutuel.test.ts"] },

  // --- U2 · el compensador ---
  { nombre: "U2 el sobrepago ya no se rechaza", archivo: `${D}compensacion.ts`,
    de: "  if (resto < -EPSILON) {", a: "  if (false) {", tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 un pago negativo pasa", archivo: `${D}compensacion.ts`,
    de: "    if (!Number.isFinite(monto) || monto < 0) {", a: "    if (false) {",
    tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 el resto no llega a la casa", archivo: `${D}compensacion.ts`,
    de: "  if (casa > 0) salida[TESORERIA] = (salida[TESORERIA] ?? 0) + casa;",
    a: "  if (reparto.fee > 0) salida[TESORERIA] = reparto.fee;", tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 el polvo de coma flotante crea una pata", archivo: `${D}compensacion.ts`,
    de: "  const restoLimpio = Math.abs(resto) < EPSILON ? 0 : resto;", a: "  const restoLimpio = resto;",
    tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 tesorería entra en los pagos de apuestas", archivo: `${D}compensacion.ts`,
    de: "    if (tenedor !== TESORERIA) pagosDeApuestas[tenedor] = monto;",
    a: "    pagosDeApuestas[tenedor] = monto;", tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 el colateral cero se trata como error", archivo: `${D}compensacion.ts`,
    de: "  if (colateral <= 0) {", a: "  if (false) {", tests: ["tests/compensacion.test.ts"] },
  { nombre: "U2 falta el reparto de un resultado", archivo: `${D}compensacion.ts`,
    de: "      throw new PozoInconsistente(`falta el reparto del resultado ${outcome}`);",
    a: "      continue;", tests: ["tests/compensacion.test.ts"],
    equivalente: "acunar() lo rechaza igual y con un mensaje que también nombra el resultado. Borrar la guarda del todo NO es equivalente: saldría un TypeError, y eso sí lo fija el test" },

  // --- U3 · el asiento del subsidio ---
  { nombre: "U3 asiento() acepta un libro descuadrado", archivo: `${D}contabilidad.ts`,
    de: "  if (Math.abs(suma) > 1e-9) throw new LibroDesbalanceado(suma);", a: "",
    tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 la semilla vuelve a salir de `entrada`", archivo: `${D}contabilidad.ts`,
    de: "{ cuenta: CUENTAS_SISTEMA.capital, monto: -monto },", a: "{ cuenta: CUENTAS_SISTEMA.entrada, monto: -monto },",
    tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 el subsidio no se distingue de la semilla", archivo: `${D}contabilidad.ts`,
    de: '    modo === "subsidio" ? "subsidio" : "semilla",', a: '    "semilla",',
    tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 el fee va a capital en vez de a tesorería", archivo: `${D}contabilidad.ts`,
    de: "    patas.push({ cuenta: CUENTAS_SISTEMA.tesoreria, monto: cierre.fee });",
    a: "    patas.push({ cuenta: CUENTAS_SISTEMA.capital, monto: cierre.fee });",
    tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 lo que nadie reclamó no vuelve al capital", archivo: `${D}contabilidad.ts`,
    de: "  if (cierre.aCapital > 0) {", a: "  if (false) {", tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 un pago de cero crea una pata", archivo: `${D}contabilidad.ts`,
    de: "    if (monto === 0) continue;", a: "", tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 el auditor deja de ver el pozo con saldo", archivo: `${D}contabilidad.ts`,
    de: "    if (saldo !== 0) salida[marketId] = saldo;", a: "", tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 subsidioComprometido cuenta también las semillas", archivo: `${D}contabilidad.ts`,
    de: '    if (entrada.tipo !== "subsidio") continue;', a: "", tests: ["tests/contabilidad.test.ts"] },
  { nombre: "U3 liquidar dos veces paga dos veces", archivo: "server/store.mts",
    de: "    if (yaLiquidado) return { acreditado: 0, comision: 0 };",
    a: "    if (false) return { acreditado: 0, comision: 0 };", tests: ["tests/contabilidad.test.ts"] },

  // --- U4 · presupuesto y freno ---
  { nombre: "U4 el tope abierto deja de frenar", archivo: `${D}presupuesto.ts`,
    de: "  if (topes.abierto !== undefined && trasCrear > topes.abierto) {", a: "  if (false) {",
    tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 el tope por mercado deja de frenar", archivo: `${D}presupuesto.ts`,
    de: "  if (topes.porMercado !== undefined && delCandidato > topes.porMercado) {", a: "  if (false) {",
    tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 la tanda no se cuenta entre sí", archivo: `${D}presupuesto.ts`,
    de: "      aceptados.push(candidato);\n      vivos.push(candidato);", a: "      aceptados.push(candidato);",
    tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 el freno nace desarmado", archivo: `${D}presupuesto.ts`,
    de: "export const TOPES_POR_DEFECTO: Topes = { porMercado: 0, abierto: 0 };",
    a: "export const TOPES_POR_DEFECTO: Topes = {};", tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 los opacos se suman como cero contra el tope", archivo: `${D}presupuesto.ts`,
    de: "    if (opacos.length > 0) {", a: "    if (false) {", tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 un tope mal escrito se lee como NaN", archivo: `${D}presupuesto.ts`,
    de: "    if (!Number.isFinite(valor) || valor < 0) {", a: "    if (false) {",
    tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 subsidioDe cuenta también el modo apuesta", archivo: `${D}presupuesto.ts`,
    de: 'return mercado.modo === "subsidio" ? mercado.semilla : 0;', a: "return mercado.semilla;",
    tests: ["tests/presupuesto.test.ts"] },
  { nombre: "U4 un pozo sin semilla se marca como declarado", archivo: `${D}presupuesto.ts`,
    de: "  const declarada = seed.pool.seed !== undefined;", a: "  const declarada = true;",
    tests: ["tests/presupuesto.test.ts"] },

  // --- U5 · frescura del oráculo ---
  { nombre: "U5 la puerta de frescura deja de existir", archivo: `${D}settlement.ts`,
    de: "  if (!frescura.utilizable) {", a: "  if (false) {", tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 el umbral se vuelve estricto en el límite", archivo: `${D}settlement.ts`,
    de: "    utilizable: umbralHoras === undefined || horas <= umbralHoras,",
    a: "    utilizable: umbralHoras === undefined || horas < umbralHoras,", tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 sin fecha se declara frescura verificada", archivo: `${D}settlement.ts`,
    de: "    return { verificable: false, umbralHoras, utilizable: true };",
    a: "    return { verificable: true, umbralHoras, utilizable: true };", tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 una fecha futura da antigüedad negativa", archivo: `${D}settlement.ts`,
    de: "  const horas = Math.max(0, (now - at) / 3_600_000);", a: "  const horas = (now - at) / 3_600_000;",
    tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 el auditor de frescura mira al revés", archivo: `${D}settlement.ts`,
    de: "        e.frescuraVerificada !== true,", a: "        e.frescuraVerificada === true,",
    tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 el umbral del mercado se ignora", archivo: `${D}settlement.ts`,
    de: "  const umbralHoras = spec.maxAgeHours;", a: "  const umbralHoras = undefined;",
    tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 una lectura vieja conserva el resultado", archivo: `${D}settlement.ts`,
    de: "      observedAt: reading.observedAt,\n      frescuraVerificada: true,",
    a: "      outcome: reading.outcome,\n      observedAt: reading.observedAt,\n      frescuraVerificada: true,",
    tests: ["tests/frescura.test.ts"] },
  { nombre: "U5 `sin_dato` también se juzga por frescura", archivo: `${D}settlement.ts`,
    de: '  if (reading.status === "sin_dato") {', a: "  if (false) {",
    tests: ["tests/frescura.test.ts", "tests/settlement.test.ts"] },

  // --- §3 · ciclo de vida: resolver, y no pagar dos veces tras un redeploy ---
  { nombre: "§3 el redeploy vuelve a pagar el mercado", archivo: "server/store.mts",
    de: '      (a) => a.tipo === "liquidacion" && a.ref === input.marketId,',
    a: "      () => false,", tests: ["tests/servidor.test.ts", "tests/contabilidad.test.ts"] },
  { nombre: "§3 el ciclo no se salta un mercado ya pagado", archivo: "server/ciclo.mts",
    de: '      if (estado.phase === "en_disputa" && isPayable(estado, ahora)) {',
    a: '      if (estado.phase !== "atorado" && isPayable(estado, ahora)) {',
    tests: ["tests/servidor.test.ts"],
    equivalente: "`isPayable` ya comprueba `phase === \"en_disputa\"` por dentro, así que la condición de fuera es redundante. La protección de verdad contra un mercado ya pagado viene de ahí, no de esta línea" },
  // --- §3 · ciclo de vida: que el mercado se pueda resolver ---
  { nombre: "§3 las series pierden su margen de cadencia", archivo: "src/adapters/ownMarkets/catalog.ts",
    de: "      frescuraDias: 100,", a: "", tests: ["tests/frescura.test.ts"] },
  { nombre: "§3 el margen de la serie se vuelve una puerta abierta", archivo: "src/adapters/oracles/seriesOracle.ts",
    de: "      if (ultima.fecha < settlesAt - margen) {", a: "      if (false) {",
    tests: ["tests/frescura.test.ts"] },
  { nombre: "§3 un partido a medias cuenta como resultado", archivo: "src/adapters/oracles/matchOracle.ts",
    de: "      if (!terminado) {", a: "      if (false) {",
    tests: ["tests/fuentes.test.ts"] },

  // --- U6 · el árbol de época ---
  { nombre: "U6 se quita la separación de dominio", archivo: `${D}merkle.ts`,
    de: "const PREFIJO_NODO = 0x01;", a: "const PREFIJO_NODO = 0x00;", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 los campos se concatenan sin longitud", archivo: `${D}merkle.ts`,
    de: "      u32(usuario.length),\n      usuario,\n      u32(hoja.seq),\n      u32(hecho.length),\n      hecho,",
    a: "      usuario,\n      u32(hoja.seq),\n      hecho,", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 la hoja impar se duplica en vez de promoverse", archivo: `${D}merkle.ts`,
    de: "      siguiente.push(i + 1 < nivel.length ? hashNodo(nivel[i], nivel[i + 1]) : nivel[i]);",
    a: "      siguiente.push(i + 1 < nivel.length ? hashNodo(nivel[i], nivel[i + 1]) : hashNodo(nivel[i], nivel[i]));",
    tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 el orden de los hijos deja de importar", archivo: `${D}merkle.ts`,
    de: "  return sha256Hex(\n    concat([new Uint8Array([PREFIJO_NODO]), deHex(izquierdo), deHex(derecho)]),\n  );",
    a: "  const [a, b] = [izquierdo, derecho].sort();\n  return sha256Hex(\n    concat([new Uint8Array([PREFIJO_NODO]), deHex(a), deHex(b)]),\n  );",
    tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 verificar no comprueba el rango del índice", archivo: `${D}merkle.ts`,
    de: "  if (prueba.indice < 0 || prueba.indice >= prueba.hojas) return false;", a: "",
    tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 pruebaDeInclusion acepta un índice fuera del árbol", archivo: `${D}merkle.ts`,
    de: "    throw new Error(`índice fuera del árbol: ${indice} de ${hojas.length} hojas`);",
    a: "    indice = 0;", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 una época vacía devuelve un hash en vez de lanzar", archivo: `${D}merkle.ts`,
    de: '  if (hojas.length === 0) throw new Error("una época vacía no tiene raíz");',
    a: "  if (hojas.length === 0) return sha256Hex(new Uint8Array());", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 el ancla deja de anclar el conteo", archivo: `${D}epoca.ts`,
    de: "  if (hojas.length !== ancla.hojas) {", a: "  if (false) {", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 la secuencia por usuario deja de comprobarse", archivo: `${D}epoca.ts`,
    de: "      if (!vistos.has(n)) huecos.push({ usuario, falta: n });", a: "",
    tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 un duplicado de secuencia no se reporta", archivo: `${D}epoca.ts`,
    de: "    if (vistos.size !== seqs.length) {", a: "    if (false) {", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 verificarAncla no comprueba la raíz", archivo: `${D}epoca.ts`,
    de: "    if (calculada !== ancla.raiz) {", a: "    if (false) {", tests: ["tests/merkle.test.ts"] },
  { nombre: "U6 el ancla no encadena con la anterior", archivo: `${D}epoca.ts`,
    de: "    throw new Error(`la época ${epoca} no sigue a la ${anterior.epoca}`);", a: "",
    tests: ["tests/merkle.test.ts"] },
];

const filtro = process.argv[2]?.toLowerCase();
const aCorrer = filtro
  ? MUTACIONES.filter((m) => m.nombre.toLowerCase().includes(filtro))
  : MUTACIONES;

if (aCorrer.length === 0) {
  console.error(`Ninguna mutación coincide con "${filtro}".`);
  process.exit(1);
}

const respaldos = mkdtempSync(join(tmpdir(), "mutaciones-"));
const resultados = [];

/** Corre vitest y devuelve cuántas pruebas quedaron rojas. */
function correrTests(tests) {
  try {
    execFileSync("npx", ["vitest", "run", ...tests], { encoding: "utf8", stdio: "pipe" });
    return 0;
  } catch (error) {
    const salida = `${error.stdout ?? ""}${error.stderr ?? ""}`;
    const linea = salida.split("\n").find((l) => l.includes("Tests ") && l.includes("failed"));
    return linea ? Number(linea.split("Tests")[1].trim().split(/\s+/)[0]) || -1 : -1;
  }
}

/**
 * La línea base: cuántas rojas hay **sin tocar nada**.
 *
 * Sin esto, el respaldo de «pruébalo contra la suite entera» daría por detectada
 * **cualquier** mutación, porque la suite arrastra rojas conocidas (hoy 6, por
 * el catálogo caducado — `marea/vault/LINEA_BASE.md`). Un arnés que siempre dice
 * que sí es el mismo que no existe, y además esconde los huecos de verdad.
 */
const BASE = correrTests([]);
console.log(`Línea base de la suite: ${BASE} rojas. Una mutación cuenta como detectada si sube de ahí.`);

for (const m of aCorrer) {
  const respaldo = join(respaldos, basename(m.archivo));
  copyFileSync(m.archivo, respaldo);
  const original = readFileSync(m.archivo, "utf8");
  if (!original.includes(m.de)) {
    resultados.push({ ...m, estado: "NO APLICA", detalle: "el patrón ya no está en el archivo" });
    continue;
  }
  writeFileSync(m.archivo, original.replace(m.de, m.a));

  /**
   * Se corren primero los tests que la mutación declara. Si no la ven, se
   * **vuelve a intentar con la suite entera** antes de cantar un hueco.
   *
   * Esa segunda pasada no es por gusto: la primera versión de esto declaró un
   * hueco que no existía —la mutación estaba cubierta, y lo que estaba mal era
   * la lista de archivos de la entrada—. Un arnés que da falsas alarmas se
   * acaba ignorando, y entonces deja de servir justo cuando encuentra algo de
   * verdad. Distinguir «no lo ve nadie» de «apunté al archivo equivocado» es la
   * diferencia entre un hallazgo y ruido.
   */
  let rojas = 0;
  let listaMal = false;
  try {
    rojas = correrTests(m.tests);
    if (rojas === 0) {
      // los tests declarados no la ven: ¿es un hueco, o apunté al archivo malo?
      const enLaSuite = correrTests([]);
      if (enLaSuite > BASE) {
        listaMal = true;
        rojas = enLaSuite - BASE;
      }
    }
  } finally {
    copyFileSync(respaldo, m.archivo);
  }
  resultados.push({
    ...m,
    estado: rojas > 0 ? "detectada" : "SOBREVIVE",
    rojas,
    detalle: listaMal ? `la ve la suite, NO los tests declarados — corrige \`tests\`` : undefined,
  });
}

console.log();
for (const r of resultados) {
  const marca = r.estado === "detectada" ? "  ok" : r.equivalente ? "  ~ " : "  !!";
  const detalle = r.detalle
    ? `${r.rojas} rojas · ${r.detalle}`
    : r.estado === "detectada"
      ? `${r.rojas} rojas`
      : r.equivalente
        ? "equivalente"
        : "SOBREVIVE";
  console.log(`${r.detalle ? "  ?" : marca} ${r.nombre.padEnd(52)} ${detalle}`);
}

const detectadas = resultados.filter((r) => r.estado === "detectada").length;
const equivalentes = resultados.filter((r) => r.estado !== "detectada" && r.equivalente);
const huecos = resultados.filter((r) => r.estado !== "detectada" && !r.equivalente);

console.log(`\n${detectadas}/${resultados.length} detectadas · ${equivalentes.length} equivalentes conocidas · ${huecos.length} huecos`);
for (const r of equivalentes) console.log(`  ~ ${r.nombre}: ${r.equivalente}`);
for (const r of huecos) console.log(`  !! ${r.nombre} — falta un test que lo vea`);
process.exit(huecos.length === 0 ? 0 : 1);
