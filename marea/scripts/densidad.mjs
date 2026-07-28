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

    const enteras = cards.filter((c) => {
      const b = c.getBoundingClientRect();
      return b.top >= 0 && b.bottom <= window.innerHeight - alturaTabs;
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

    return {
      enteras,
      envueltos,
      totalCards: cards.length,
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

await browser.close();

console.log("DENSIDAD (navegador real, servidor real)");
console.log("========================================");
for (const r of reporte) {
  console.log(`\n${r.ancho}×844:`);
  console.log(`  cards enteras       ${r.enteras}  (presupuesto ${PRESUPUESTO.cardsVisibles} a 390px)`);
  console.log(`  alto de card        ${r.altoCard} px`);
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
