import { chromium } from "playwright";

/**
 * Puerta de densidad del feed.
 *
 * jsdom no tiene layout: no mide alturas, no envuelve texto y no sabe que
 * `Sí · paga 1.8×` cae en dos líneas a 390 px. Esto sólo se ve en un navegador
 * de verdad, y por eso la puerta vive aquí y no en la suite de unidad.
 *
 * Se mide contra el servidor real, no contra el preview: la diferencia entre
 * los dos ya nos costó 1.3 s de LCP una vez (R-055).
 *
 *   npm run build && PORT=8100 npx tsx server/index.mts &
 *   npm run densidad
 */

const BASE = process.env.DENSIDAD_BASE ?? "http://127.0.0.1:8100";

/** Presupuestos. Se abren bajando el error, nunca bajando el umbral. */
const PRESUPUESTO = {
  /** Cards visibles enteras dentro de la ventana, sobre la barra de pestañas. */
  cardsVisibles: 4,
  /** Nodos de texto de la card que caen en más de una línea. */
  envolturas: 0,
  /** El nodo de probabilidad no puede encoger para ganar densidad (R-004). */
  probabilidadMinPx: 30,
  /**
   * Cromo antes del **primer bloque de producto**, sea el carrusel de
   * destacados o la primera card. Header + tira de categorías y nada más: el
   * carrusel no es cromo, es contenido, y tiene su propio presupuesto abajo.
   */
  topeCromoPx: 130,
  /** La banda de destacados, con sus puntos. */
  topeCarruselPx: 200,
  /**
   * Alto máximo **por variante**. Sin esto el gate medía sólo la primera card
   * y una normal gorda pasaba escondida detrás del promedio: cada tipo tiene
   * su techo y cada tipo lo defiende solo.
   *
   * De dónde salen los números. El mínimo aritmético de la card, con la
   * probabilidad en 44 px (R-004, congelado en `tokens.lock.json`) y el título
   * en dos líneas:
   *
   *   py 8+8 (16) + badges 18 + título 2×21 (42) + decisión 34 + barra 3
   *   + meta 15 + 4 huecos de 3 (12) = 140 px
   *
   * Bajar de ahí exige romper R-004 o clampear el título a una línea, y
   * ninguna de las dos se paga por densidad.
   *
   * Medido a 390 px: `default` = 143 px. Los techos son ése más el margen que
   * cada variante puede gastar de verdad:
   *
   *  - `edge` puede llevar el badge de Edge a una segunda línea de la fila de
   *    decisión: +18 px, que es lo que mide esa línea.
   *  - `live` no añade filas —su badge cabe en la fila 1— así que va con el
   *    mismo techo que `default`.
   *  - `compact` clampea el título a una línea: −19 px.
   *
   * A 320 px la fila de decisión envuelve **por diseño**: el contenido real
   * pide ~310 px y el ancho interior es 292, y comprimir no es amputar (R-063,
   * vault/CARD_SPEC.md). Por eso hay dos tablas y no una con excepciones: cada
   * clase de ancho declara su techo y lo defiende sola.
   */
  altoPorVariante: {
    /** >= 360 px, donde la fila de decisión cabe en una línea. */
    normal: { default: 148, edge: 166, live: 148, compact: 130 },
    /** < 360 px, donde la fila de decisión envuelve por diseño. */
    angosto: { default: 182, edge: 200, live: 182, compact: 164 },
  },
};

/** Anchos que importan: lo que se rompe primero es el chico. */
const ANCHOS = [320, 390, 430];

async function pasarOnboarding(page) {
  for (let i = 0; i < 8; i += 1) {
    const cta = page
      .locator(
        '[data-testid="onboarding-skip"], [data-testid="onboarding-cta"], [data-testid="p0-cta"], button:has-text("Empezar"), button:has-text("Explorar"), button:has-text("Entendido"), button:has-text("Continuar")',
      )
      .first();
    if ((await cta.count()) && (await cta.isVisible())) {
      await cta.click();
      await page.waitForTimeout(300);
    } else break;
  }
  await page.waitForSelector('[data-testid="market-card"]', { timeout: 20000 });
}

async function medir(page) {
  return page.evaluate(() => {
    const tabs = document.querySelector("nav");
    const alturaTabs = tabs ? tabs.getBoundingClientRect().height : 0;
    const cabecera = document.querySelector("header");
    const alturaCabecera = cabecera ? cabecera.getBoundingClientRect().height : 0;
    const cards = [...document.querySelectorAll('[data-testid="market-card"]')];

    /**
     * Cuántos mercados caben de una vez **en la lista**.
     *
     * Se mide desde el primer mercado, no desde el borde de la pantalla: la
     * banda de destacados se recorre una vez y se va, y contarla aquí haría
     * que un carrusel más alto se leyera como lista menos densa. Lo que este
     * presupuesto protege es el ritmo vertical del feed, y ese ritmo empieza
     * donde empieza el feed. La cabecera sí resta: es sticky y sigue ocupando
     * sitio mientras se recorre la lista.
     */
    const ventanaLista = window.innerHeight - alturaTabs - alturaCabecera;
    const inicio = cards[0]?.getBoundingClientRect().top ?? 0;
    const enteras = cards.filter((c) => {
      const b = c.getBoundingClientRect();
      return b.top - inicio >= 0 && b.bottom - inicio <= ventanaLista;
    }).length;

    /**
     * Un nodo envuelve si su texto ocupa más de una caja de línea.
     *
     * No se puede medir con `scrollWidth`: un texto que salta de línea crece
     * en alto, no en ancho, y la comprobación ingenua da cero siempre.
     *
     * Tampoco sirve dividir el alto del nodo entre su `line-height`: en cuanto
     * un badge lleva alto fijo y `leading-none` —18 px de caja para 11 px de
     * línea— la división da 1.6 y redondea a dos líneas. Esa versión marcaba
     * "HOT" y "LATAM" como envueltos sin que nada envolviera.
     *
     * `Range.getClientRects()` da una caja por fragmento de texto, ignorando
     * padding y altura fija. Pero devuelve **una caja por nodo de texto**,
     * no por línea: la fila de meta se arma con tres expresiones distintas
     * —pozo, participantes, cierre— y daba tres cajas en una sola línea.
     * Las líneas de verdad son las tapas distintas, así que se cuentan ésas.
     */
    const envueltos = [];
    for (const card of cards.slice(0, 8)) {
      for (const el of card.querySelectorAll("div,span,p")) {
        if (el.children.length > 0 || !el.textContent.trim()) continue;
        // el título del mercado sí puede ocupar dos líneas: es su diseño
        if (el.closest("h3")) continue;
        const rango = document.createRange();
        rango.selectNodeContents(el);
        const tapas = new Set();
        for (const caja of rango.getClientRects()) {
          if (caja.width > 0 || caja.height > 0) tapas.add(Math.round(caja.top));
        }
        rango.detach?.();
        const lineas = tapas.size;
        if (lineas > 1) {
          envueltos.push({ texto: el.textContent.trim().slice(0, 34), lineas });
        }
      }
    }

    const prob = document.querySelector('[data-role="probability"]');
    const primera = cards[0]?.getBoundingClientRect();

    // el alto real por variante: el peor caso de cada tipo, no el promedio ni
    // el de la primera card. Una normal gorda ya no se esconde detrás de una
    // viva, que era exactamente el agujero
    const porVariante = {};
    for (const card of cards) {
      const tipo = card.getAttribute("data-variant") ?? "default";
      const alto = Math.round(card.getBoundingClientRect().height);
      const actual = porVariante[tipo];
      if (!actual || alto > actual.max) {
        porVariante[tipo] = { max: alto, n: (actual?.n ?? 0) + 1 };
      } else {
        actual.n += 1;
      }
    }

    // cromo = lo que hay antes del primer bloque de producto. El carrusel
    // cuenta como producto, no como cromo
    const carrusel = document.querySelector('[data-testid="featured-carousel"]');
    const cajaCarrusel = carrusel?.getBoundingClientRect();
    const primerProducto = cajaCarrusel ?? primera;

    return {
      enteras,
      envueltos,
      totalCards: cards.length,
      altoCard: primera ? Math.round(primera.height) : 0,
      porVariante,
      cromo: primerProducto ? Math.round(primerProducto.top) : 0,
      altoCarrusel: cajaCarrusel ? Math.round(cajaCarrusel.height) : 0,
      topePrimeraCard: primera ? Math.round(primera.top) : 0,
      probabilidadPx: prob ? Math.round(parseFloat(getComputedStyle(prob).fontSize)) : 0,
      altoDocumento: Math.round(document.documentElement.scrollHeight),
    };
  });
}

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium",
  args: ["--no-sandbox"],
});

const fallos = [];
const reporte = [];

for (const ancho of ANCHOS) {
  const page = await browser.newPage({
    viewport: { width: ancho, height: 844 },
    deviceScaleFactor: 2,
  });
  await page.goto(BASE, { waitUntil: "networkidle" });
  await pasarOnboarding(page);
  const m = await medir(page);
  reporte.push({ ancho, ...m });

  // el presupuesto de densidad se exige en el ancho de referencia; en 320 px
  // basta con que no se rompa el texto, que es lo que de verdad se degrada
  if (ancho === 390) {
    if (m.enteras < PRESUPUESTO.cardsVisibles) {
      fallos.push(
        `${ancho}px: ${m.enteras} cards enteras en la lista, se piden ${PRESUPUESTO.cardsVisibles}`,
      );
    }
    if (m.cromo > PRESUPUESTO.topeCromoPx) {
      fallos.push(
        `${ancho}px: ${m.cromo}px de cromo antes del primer bloque de producto, tope ${PRESUPUESTO.topeCromoPx}px`,
      );
    }
    if (m.altoCarrusel > PRESUPUESTO.topeCarruselPx) {
      fallos.push(
        `${ancho}px: la banda de destacados mide ${m.altoCarrusel}px, tope ${PRESUPUESTO.topeCarruselPx}px`,
      );
    }
  }

  /**
   * El techo por variante se exige en **todos** los anchos. Es la regla que
   * más barato se rompe: basta con que una etiqueta larga envuelva a 320 px
   * para que un tipo de card engorde sin que nadie lo note en el ancho de
   * referencia.
   */
  const topes = PRESUPUESTO.altoPorVariante[ancho < 360 ? "angosto" : "normal"];
  for (const [tipo, { max, n }] of Object.entries(m.porVariante)) {
    const tope = topes[tipo];
    if (tope === undefined) {
      fallos.push(`${ancho}px: variante "${tipo}" sin techo declarado (${n} cards)`);
      continue;
    }
    if (max > tope) {
      fallos.push(
        `${ancho}px: la card "${tipo}" más alta mide ${max}px, tope ${tope}px (${n} en pantalla)`,
      );
    }
  }
  if (m.envueltos.length > PRESUPUESTO.envolturas) {
    fallos.push(
      `${ancho}px: ${m.envueltos.length} nodos envueltos (${m.envueltos
        .slice(0, 3)
        .map((e) => `"${e.texto}"`)
        .join(", ")})`,
    );
  }
  if (m.probabilidadPx < PRESUPUESTO.probabilidadMinPx) {
    fallos.push(
      `${ancho}px: la probabilidad bajó a ${m.probabilidadPx}px, mínimo ${PRESUPUESTO.probabilidadMinPx}px — la densidad no se compra degradando la jerarquía (R-004)`,
    );
  }
  await page.close();
}

/**
 * El esqueleto tiene que medir **exactamente** lo que va a reemplazar. Uno que
 * no mide igual es un salto de layout disfrazado: se ve bien en una captura y
 * empuja la página cuando llegan los datos.
 */
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  await cdp.send("Network.enable");
  // red muy lenta a propósito: sin esto el esqueleto no llega a verse
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 400,
    downloadThroughput: (400 * 1024) / 8,
    uploadThroughput: (400 * 1024) / 8,
  });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });

  let esqueleto = null;
  try {
    await page.waitForSelector('[data-testid="list-skeleton"]', { timeout: 12000 });
    esqueleto = await page.evaluate(() => {
      const s = document.querySelector('[data-testid="list-skeleton"]');
      const piezas = s ? [...s.children] : [];
      if (piezas.length === 0) return null;
      const a = piezas[0].getBoundingClientRect();
      // el hueco real se mide entre dos vecinos: `space-y-*` usa margen, no
      // `rowGap`, y leer `rowGap` daba 0 en los dos lados — la comprobación
      // pasaba sin comparar nada
      const b = piezas[1]?.getBoundingClientRect();
      return {
        alto: Math.round(a.height),
        hueco: b ? Math.round(b.top - a.bottom) : 0,
      };
    });
  } catch {
    /* si no llegó a pintarse, no se inventa una medición */
  }

  await pasarOnboarding(page);
  const real = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('[data-testid="market-card"]')];
    if (cards.length === 0) return { alto: 0, hueco: 0 };
    const a = cards[0].getBoundingClientRect();
    const b = cards[1]?.getBoundingClientRect();
    return {
      alto: Math.round(a.height),
      hueco: b ? Math.round(b.top - a.bottom) : 0,
    };
  });

  reporte.push({ esqueleto, real });
  if (!esqueleto) {
    console.log("\n(el esqueleto no llegó a pintarse: no se mide lo que no se vio)");
  } else {
    const dAlto = Math.abs(esqueleto.alto - real.alto);
    const dHueco = Math.abs(esqueleto.hueco - real.hueco);
    if (dAlto > 2) {
      fallos.push(
        `el esqueleto mide ${esqueleto.alto}px y la card ${real.alto}px: ${dAlto}px de salto`,
      );
    }
    if (dHueco > 2) {
      fallos.push(
        `el hueco del esqueleto es ${esqueleto.hueco}px y el del feed ${real.hueco}px`,
      );
    }
  }
  await ctx.close();
}

/**
 * Las imágenes del feed (escudos) no pueden empujar el layout ni la pintada.
 * Una imagen sin `width`/`height` reserva cero espacio y desplaza todo lo que
 * tiene debajo cuando llega — es la forma más común de subir el CLS sin verlo.
 */
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  await pasarOnboarding(page);

  const imgs = await page.evaluate(() => {
    const salida = [];
    for (const img of document.querySelectorAll('[data-testid="market-card"] img')) {
      salida.push({
        src: img.getAttribute("src")?.slice(0, 60) ?? "",
        ancho: img.getAttribute("width"),
        alto: img.getAttribute("height"),
        lazy: img.getAttribute("loading"),
      });
    }
    return salida;
  });
  const sinMedidas = imgs.filter((i) => !i.ancho || !i.alto);
  const sinLazy = imgs.filter((i) => i.lazy !== "lazy");
  reporte.push({ imagenes: imgs.length, sinMedidas: sinMedidas.length, sinLazy: sinLazy.length });

  if (sinMedidas.length > 0) {
    fallos.push(
      `${sinMedidas.length} imágenes del feed sin width/height: reservan cero y empujan el layout`,
    );
  }
  if (sinLazy.length > 0) {
    fallos.push(`${sinLazy.length} imágenes del feed sin loading="lazy"`);
  }
  await ctx.close();
}

await browser.close();

console.log("DENSIDAD (navegador real, servidor real)");
console.log("========================================");
for (const r of reporte) {
  if (r.imagenes !== undefined) {
    console.log("\nimágenes del feed:");
    console.log(`  total ${r.imagenes} · sin medidas ${r.sinMedidas} · sin lazy ${r.sinLazy}`);
    continue;
  }
  if (r.esqueleto !== undefined) {
    console.log("\nesqueleto vs card real:");
    console.log(
      `  esqueleto  ${r.esqueleto ? `${r.esqueleto.alto} px · hueco ${r.esqueleto.hueco} px` : "no se pintó"}`,
    );
    console.log(`  card real  ${r.real.alto} px · hueco ${r.real.hueco} px`);
    continue;
  }
  console.log(`\n${r.ancho}×844:`);
  console.log(`  cards enteras       ${r.enteras}  (presupuesto ${PRESUPUESTO.cardsVisibles} a 390px)`);
  console.log(`  alto de card        ${r.altoCard} px`);
  const topesDe = PRESUPUESTO.altoPorVariante[r.ancho < 360 ? "angosto" : "normal"];
  for (const [tipo, { max, n }] of Object.entries(r.porVariante)) {
    const tope = topesDe[tipo];
    console.log(
      `    · ${tipo.padEnd(8)} máx ${String(max).padStart(3)} px  (tope ${tope ?? "—"}) · ${n} en pantalla`,
    );
  }
  console.log(`  cromo previo        ${r.cromo} px  (tope ${PRESUPUESTO.topeCromoPx})`);
  console.log(`  banda destacados    ${r.altoCarrusel} px  (tope ${PRESUPUESTO.topeCarruselPx})`);
  console.log(`  nodos envueltos     ${r.envueltos.length}  (presupuesto ${PRESUPUESTO.envolturas})`);
  for (const e of r.envueltos.slice(0, 4)) console.log(`      · "${e.texto}" → ${e.lineas} líneas`);
  console.log(`  probabilidad        ${r.probabilidadPx} px  (mínimo ${PRESUPUESTO.probabilidadMinPx})`);
  console.log(`  documento           ${r.altoDocumento} px para ${r.totalCards} mercados`);
}

if (fallos.length > 0) {
  console.log(`\nfailed[] (${fallos.length})`);
  for (const f of fallos) console.log(`  ✗ ${f}`);
  console.log("\nverdict: FAIL");
  process.exit(1);
}
console.log("\nfailed[] (0)\n\nverdict: PASS");
