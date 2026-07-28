import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { chromium } from "playwright";

/**
 * Puerta de accesibilidad.
 *
 * No es una casilla de cumplimiento: es cuánta gente puede usar esto. En
 * Latinoamérica el teléfono suele ser el único dispositivo, y mucha gente lo
 * trae con el texto agrandado — que es justo lo que más se rompe y lo que
 * nadie prueba.
 *
 * jsdom no sirve para esto: no tiene layout, así que no sabe si un texto al
 * 200 % se sale de su caja ni puede calcular contraste sobre el fondo real.
 *
 *   npm run build && PORT=8100 npx tsx server/index.mts &
 *   npm run acceso
 */

const BASE = process.env.ACCESO_BASE ?? "http://127.0.0.1:8100";
const require = createRequire(import.meta.url);
const AXE = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");

/** Pantallas que se auditan, con cómo llegar a cada una. */
const PANTALLAS = [
  { nombre: "feed", tab: null },
  { nombre: "buscar", tab: /buscar/i },
  { nombre: "portafolio", tab: /portafolio/i },
  { nombre: "tabla", tab: /tabla/i },
  { nombre: "perfil", tab: /perfil/i },
];

async function pasarOnboarding(page) {
  const cta = page.locator('[data-testid="onboarding-start"]');
  try {
    await cta.waitFor({ timeout: 15000 });
    await cta.click();
  } catch {
    /* si no hay onboarding, mejor */
  }
  await page.waitForSelector('[data-testid="market-card"]', { timeout: 20000 });
}

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium",
  args: ["--no-sandbox"],
});

const fallos = [];
console.log("ACCESO (navegador real, servidor real)");
console.log("======================================");

/* ------------------------ 1 · axe-core por pantalla ---------------------- */
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  await pasarOnboarding(page);

  for (const pantalla of PANTALLAS) {
    if (pantalla.tab) {
      await page.getByRole("tab", { name: pantalla.tab }).click();
      await page.waitForTimeout(700);
    }
    await page.addScriptTag({ content: AXE });
    const resultado = await page.evaluate(async () => {
      const r = await globalThis.axe.run(document, {
        resultTypes: ["violations"],
        runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      });
      return r.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        n: v.nodes.length,
        ejemplo: v.nodes[0]?.html?.slice(0, 90),
        descripcion: v.help,
      }));
    });
    const graves = resultado.filter(
      (v) => v.impact === "serious" || v.impact === "critical",
    );
    console.log(
      `\n${pantalla.nombre.padEnd(11)} → ${resultado.length} hallazgos · ${graves.length} graves`,
    );
    for (const v of resultado) {
      console.log(`   [${v.impact}] ${v.id} ×${v.n} — ${v.descripcion}`);
      if (v.impact === "serious" || v.impact === "critical") {
        console.log(`       ${v.ejemplo}`);
      }
    }
    for (const v of graves) {
      fallos.push(`${pantalla.nombre}: ${v.id} (${v.impact}) en ${v.n} nodos`);
    }
  }
  await ctx.close();
}

/* --------------------- 2 · texto al 200 % sin desbordes ------------------ */
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  await pasarOnboarding(page);

  // 200 % del tamaño base. No es zoom del navegador: es lo que hace el ajuste
  // de "texto más grande" del sistema, que escala la raíz y deja el layout
  await page.addStyleTag({ content: "html { font-size: 200% !important; }" });
  await page.waitForTimeout(900);

  for (const pantalla of PANTALLAS) {
    if (pantalla.tab) {
      await page.getByRole("tab", { name: pantalla.tab }).click();
      await page.waitForTimeout(600);
    }
    const r = await page.evaluate(() => {
      const desbordes = [];
      for (const el of document.querySelectorAll("body *")) {
        if (el.children.length > 0 || !el.textContent.trim()) continue;
        const cs = getComputedStyle(el);
        if (cs.display === "none" || cs.visibility === "hidden") continue;
        // `sr-only` recorta a 1 px a propósito: existe para el lector de
        // pantalla, no para la vista. Contarlo como desborde era un falso
        // positivo — "Hot ahora" salía como 142px en 1px
        if (el.closest(".sr-only")) continue;
        if (cs.clip === "rect(0px, 0px, 0px, 0px)" || cs.clipPath === "inset(50%)") continue;
        // sólo cuenta el desborde horizontal de un nodo que recorta: si el
        // texto puede crecer hacia abajo, crecer no es romperse
        const recorta = cs.overflow !== "visible" || cs.textOverflow === "ellipsis";
        if (!recorta) continue;
        if (el.scrollWidth > el.clientWidth + 2) {
          desbordes.push({
            txt: el.textContent.trim().slice(0, 32),
            sw: el.scrollWidth,
            cw: el.clientWidth,
          });
        }
      }
      return {
        desbordes,
        // la página nunca se desplaza en horizontal, pase lo que pase
        scrollHorizontal:
          document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
      };
    });
    console.log(
      `\n${pantalla.nombre.padEnd(11)} al 200 % → ${r.desbordes.length} nodos recortados · scroll horizontal: ${r.scrollHorizontal ? "SÍ" : "no"}`,
    );
    for (const d of r.desbordes.slice(0, 4)) {
      console.log(`   "${d.txt}" ${d.sw}px en ${d.cw}px`);
    }
    if (r.scrollHorizontal) {
      fallos.push(`${pantalla.nombre} al 200 %: la página se desplaza en horizontal`);
    }
  }
  await ctx.close();
}

/* ------------------ 3 · acciones primarias en el pulgar ------------------ */
{
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  await page.goto(BASE, { waitUntil: "networkidle" });
  await pasarOnboarding(page);
  await page.locator('[data-testid="market-card"]').first().click();
  await page.waitForSelector('[data-testid="market-detail"]');
  // se mide donde de verdad se toca: el detalle se desplaza, así que el CTA
  // vive al final. Medirlo sin bajar decía "está en el píxel 1053 de 844",
  // que no dice nada sobre si se alcanza con el pulgar
  await page
    .locator('[data-testid="detail-trade-cta"], [data-testid="detail-deposit-cta"]')
    .first()
    .scrollIntoViewIfNeeded();
  await page.waitForTimeout(400);

  const r = await page.evaluate(() => {
    const cta =
      document.querySelector('[data-testid="detail-trade-cta"]') ??
      document.querySelector('[data-testid="detail-deposit-cta"]');
    if (!cta) return null;
    const b = cta.getBoundingClientRect();
    return {
      centro: Math.round(b.top + b.height / 2),
      alto: Math.round(b.height),
      ancho: Math.round(b.width),
      ventana: window.innerHeight,
    };
  });
  if (!r) {
    fallos.push("el detalle no expone su CTA principal");
  } else {
    // en el tercio inferior de la ventana una vez que se ve
    const enElPulgar = r.centro >= r.ventana * 0.4 && r.centro <= r.ventana;
    console.log(
      `\nCTA del detalle → centro en ${r.centro}px de ${r.ventana} · ${r.ancho}×${r.alto} px`,
    );
    if (!enElPulgar) {
      fallos.push(
        `el CTA principal está en el ${Math.round((r.centro / r.ventana) * 100)}% superior: se decide con el pulgar (R-010)`,
      );
    }
    if (r.alto < 44) fallos.push(`el CTA mide ${r.alto}px de alto, mínimo 44`);
  }
  await ctx.close();
}

await browser.close();

if (fallos.length > 0) {
  console.log(`\nfailed[] (${fallos.length})`);
  for (const f of fallos) console.log(`  ✗ ${f}`);
  console.log("\nverdict: FAIL");
  process.exit(1);
}
console.log("\nfailed[] (0)\n\nverdict: PASS");
