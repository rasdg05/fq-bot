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
  cardsVisibles: 5,
  /** Alto de la card de una pregunta, borde incluido. Medido, no estimado. */
  altoCardMaxPx: 116,
  /**
   * La card viva lleva una fila que la normal no tiene: el precio de ahora con
   * su variación. Es la razón de ser del formato, así que se le presupuestan
   * esos píxeles y se le exige no pasarse ni uno más.
   */
  altoCardVivaMaxPx: 124,
  /** Nodos de texto de la card que caen en más de una línea. */
  envolturas: 0,
  /** El nodo de probabilidad no puede encoger para ganar densidad (R-004). */
  probabilidadMinPx: 30,
  /** Cromo antes del primer mercado. */
  topePrimeraCardPx: 130,
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
    const cards = [...document.querySelectorAll('[data-testid="market-card"]')];

    // entera = se ve completa, también de lado. Sin la comprobación
    // horizontal, las tarjetas del carrusel que están fuera de pantalla a la
    // derecha se contaban como visibles y el número subía a 15 sin que nadie
    // viera 15 mercados: la puerta se volvía más fácil sola
    const enteras = cards.filter((c) => {
      const b = c.getBoundingClientRect();
      return (
        b.top >= 0 &&
        b.bottom <= window.innerHeight - alturaTabs &&
        b.left >= 0 &&
        b.right <= window.innerWidth
      );
    }).length;

    // un nodo envuelve si su alto pasa de una línea de su propio line-height.
    // No se puede medir con scrollWidth: un texto que salta de línea crece en
    // alto, no en ancho, y la comprobación ingenua da cero siempre
    const envueltos = [];
    for (const card of cards.slice(0, 8)) {
      for (const el of card.querySelectorAll("div,span,p")) {
        if (el.children.length > 0 || !el.textContent.trim()) continue;
        // el título del mercado sí puede ocupar dos líneas: es su diseño
        if (el.closest("h3")) continue;
        const cs = getComputedStyle(el);
        let lh = parseFloat(cs.lineHeight);
        if (!Number.isFinite(lh)) lh = parseFloat(cs.fontSize) * 1.2;
        const lineas = Math.round(el.getBoundingClientRect().height / lh);
        if (lineas > 1) {
          envueltos.push({ texto: el.textContent.trim().slice(0, 34), lineas });
        }
      }
    }

    const prob = document.querySelector('[data-role="probability"]');
    const primera = cards[0]?.getBoundingClientRect();
    // cada tipo de card se mide contra su propio presupuesto: mezclarlos deja
    // pasar una card normal gorda escondida detrás de una viva
    const norm = cards.find((c) => c.getAttribute("data-variant") !== "live");
    const viva = cards.find((c) => c.getAttribute("data-variant") === "live");

    return {
      enteras,
      envueltos,
      totalCards: cards.length,
      altoNormal: norm ? Math.round(norm.getBoundingClientRect().height) : 0,
      altoViva: viva ? Math.round(viva.getBoundingClientRect().height) : 0,
      altoCard: primera ? Math.round(primera.height) : 0,
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
        `${ancho}px: ${m.enteras} cards enteras, se piden ${PRESUPUESTO.cardsVisibles}`,
      );
    }
    // el alto de la card es el presupuesto que multiplica: se ve 29 veces en
    // una pantalla, así que un píxel de más se paga 29 veces
    if (m.altoNormal > PRESUPUESTO.altoCardMaxPx) {
      fallos.push(
        `${ancho}px: la card normal mide ${m.altoNormal}px y el tope es ${PRESUPUESTO.altoCardMaxPx}px`,
      );
    }
    if (m.altoViva > PRESUPUESTO.altoCardVivaMaxPx) {
      fallos.push(
        `${ancho}px: la card viva mide ${m.altoViva}px y el tope es ${PRESUPUESTO.altoCardVivaMaxPx}px`,
      );
    }
    if (m.topePrimeraCard > PRESUPUESTO.topePrimeraCardPx) {
      fallos.push(
        `${ancho}px: ${m.topePrimeraCard}px de cromo antes del primer mercado, tope ${PRESUPUESTO.topePrimeraCardPx}px`,
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
    // sólo las de la lista vertical: el esqueleto representa **esa** lista, y
    // dos tarjetas del carrusel van una al lado de la otra, así que el hueco
    // entre ellas es negativo y no dice nada del salto de layout
    const cards = [...document.querySelectorAll('[data-testid="market-card"]')].filter(
      (c) => !c.closest('[data-testid="carrusel-item"]'),
    );
    if (cards.length === 0) return { alto: 0, hueco: 0 };
    // el esqueleto reemplaza a la card normal: la viva no existe hasta que el
    // ticker responde, y compararlo con ella medía dos cosas distintas
    const normales = cards.filter((c) => c.getAttribute("data-variant") !== "live");
    const a = (normales[0] ?? cards[0]).getBoundingClientRect();
    const b = (normales[1] ?? cards[1])?.getBoundingClientRect();
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
  console.log(
    `  alto de card        normal ${r.altoNormal || "—"} px · viva ${r.altoViva || "—"} px`,
  );
  console.log(`  cromo previo        ${r.topePrimeraCard} px  (tope ${PRESUPUESTO.topePrimeraCardPx})`);
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
