import { chromium } from "playwright";

/**
 * Puerta de los primeros diez segundos.
 *
 * Mide lo que le cuesta a un desconocido llegar a algo que pueda tocar, con el
 * mismo estrangulamiento que `npm run perf` — CPU 4× lenta y 1600 kbps. Sin
 * estrangular, cualquier onboarding parece rápido.
 *
 * "Tocable" no es "está en el DOM": el chrome se monta detrás del onboarding, y
 * contar nodos daba cuatro mercados cuando la pantalla tenía cero. Se comprueba
 * con `elementFromPoint`, que es lo que responde a un dedo.
 */

const BASE = process.env.ARRANQUE_BASE ?? "http://127.0.0.1:8100";

const PRESUPUESTO = {
  interacciones: 2,
  ms: 3000,
};

/** Cards que de verdad reciben el toque en su centro. */
const TOCABLES = () => {
  let n = 0;
  for (const c of document.querySelectorAll('[data-testid="market-card"]')) {
    const r = c.getBoundingClientRect();
    if (r.width === 0 || r.bottom < 0 || r.top > innerHeight) continue;
    const y = Math.max(2, Math.min(innerHeight - 2, r.top + r.height / 2));
    const en = document.elementFromPoint(r.left + r.width / 2, y);
    if (en && c.contains(en)) n += 1;
  }
  return n;
};

async function nuevaPagina(browser, { lento }) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
  });
  const page = await ctx.newPage();
  if (lento) {
    const cdp = await ctx.newCDPSession(page);
    await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
    await cdp.send("Network.enable");
    await cdp.send("Network.emulateNetworkConditions", {
      offline: false,
      latency: 150,
      downloadThroughput: (1600 * 1024) / 8,
      uploadThroughput: (750 * 1024) / 8,
    });
  }
  return { ctx, page };
}

async function hastaTocable(page) {
  const t0 = Date.now();
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  let interacciones = 0;
  while (interacciones < 5) {
    if ((await page.evaluate(TOCABLES)) > 0) break;
    const cta = page.locator('[data-testid="onboarding"] button:visible').last();
    if (!(await cta.count())) {
      await page.waitForTimeout(80);
      continue;
    }
    try {
      await cta.click({ timeout: 5000 });
      interacciones += 1;
    } catch {
      await page.waitForTimeout(120);
    }
  }
  await page.waitForFunction(TOCABLES, null, { timeout: 25000 });
  return { interacciones, ms: Date.now() - t0 };
}

const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium",
  args: ["--no-sandbox"],
});

const fallos = [];
console.log("ARRANQUE (navegador real, servidor real)");
console.log("========================================");

// 1 · coste hasta un mercado tocable, con y sin estrangular
for (const lento of [false, true]) {
  const { ctx, page } = await nuevaPagina(browser, { lento });
  const r = await hastaTocable(page);
  // y cuánto cuesta además llegar al feed entero, que es el otro número que
  // importa: el mercado de muestra es tocable desde el primer frame, así que
  // sin esta segunda cifra la medición se vuelve trivial
  const t1 = Date.now();
  let alFeed = r.ms;
  const cta = page.locator('[data-testid="onboarding-start"]');
  if (await cta.count()) {
    await cta.click();
    await page
      .waitForSelector('[data-testid="onboarding"]', { state: "detached", timeout: 10000 })
      .catch(() => {});
    alFeed = r.ms + (Date.now() - t1);
  }
  const etiqueta = lento ? "CPU 4× · 1600 kbps" : "sin estrangular   ";
  console.log(
    `\n${etiqueta} → ${r.interacciones} interacciones · ${r.ms} ms al primer mercado tocable · ${alFeed} ms al feed`,
  );
  if (lento) {
    if (r.interacciones > PRESUPUESTO.interacciones) {
      fallos.push(`${r.interacciones} interacciones, tope ${PRESUPUESTO.interacciones}`);
    }
    if (r.ms > PRESUPUESTO.ms) {
      fallos.push(`${r.ms} ms hasta un mercado tocable, tope ${PRESUPUESTO.ms} ms`);
    }
  }
  await ctx.close();
}

// 2 · el onboarding no reaparece tras recargar.
//     Se completa de verdad primero: el mercado de muestra ya es tocable, así
//     que llegar a "hay algo tocable" no implica haber cerrado el onboarding
{
  const { ctx, page } = await nuevaPagina(browser, { lento: false });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-step="p1"]', { timeout: 15000 });
  await page.locator('[data-testid="onboarding-start"]').click();
  await page.waitForSelector('[data-testid="onboarding"]', { state: "detached", timeout: 10000 });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(700);
  const visible = await page.locator('[data-testid="onboarding"]').count();
  const tocables = await page.evaluate(TOCABLES);
  console.log(
    `\ntras recargar → onboarding visible: ${visible > 0 ? "sí" : "no"} · cards tocables: ${tocables}`,
  );
  if (visible > 0) fallos.push("el onboarding reaparece al recargar");
  if (tocables === 0) fallos.push("tras recargar no hay ningún mercado tocable");
  await ctx.close();
}

// 3 · la primera pantalla trae un mercado real y tocarlo lleva a ese mercado
{
  const { ctx, page } = await nuevaPagina(browser, { lento: false });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-step="p1"]', { timeout: 15000 });
  await page.waitForTimeout(600);
  const muestra = page.locator('[data-testid="onboarding-muestra"] [data-testid="market-card"]');
  const hay = (await muestra.count()) > 0;
  const id = hay ? await muestra.getAttribute("data-market-id") : null;
  console.log(`\nprimera pantalla → mercado de muestra: ${hay ? id : "ninguno"}`);
  if (!hay) {
    fallos.push("la primera pantalla no trae un mercado real");
  } else {
    await muestra.click();
    await page.waitForTimeout(700);
    const detalle = await page.locator('[data-testid="market-detail"]').count();
    console.log(`  tocarlo abre su detalle: ${detalle > 0 ? "sí" : "no"}`);
    if (detalle === 0) fallos.push("tocar el mercado de muestra no abre su detalle");
  }
  await ctx.close();
}

// 4 · con la red cortada la app no se queda en blanco: lo último que cargó se
//     sigue viendo, y lo declara como viejo (UX4)
{
  const { ctx, page } = await nuevaPagina(browser, { lento: false });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-step="p1"]', { timeout: 15000 });
  await page.locator('[data-testid="onboarding-start"]').click();
  await page.waitForFunction(TOCABLES, null, { timeout: 20000 });

  // se corta la red **después** de haber cargado, como se cae en el metro
  await page.route("**/api/**", (ruta) => ruta.abort());
  await ctx.setOffline(true);
  await page.evaluate(() => globalThis.dispatchEvent(new Event("offline")));
  await page.waitForTimeout(900);

  const tocables = await page.evaluate(TOCABLES);
  const aviso = await page.locator('[data-testid="datos-viejos"]').count();
  const enBlanco = await page.evaluate(
    () => document.body.innerText.trim().length < 40,
  );
  console.log(
    `\nred cortada → cards visibles: ${tocables} · aviso de datos viejos: ${aviso > 0 ? "sí" : "no"} · pantalla en blanco: ${enBlanco ? "sí" : "no"}`,
  );
  if (enBlanco) fallos.push("con la red cortada la app se queda en blanco");
  if (tocables === 0) fallos.push("con la red cortada no queda ningún mercado visible");
  if (aviso === 0) {
    fallos.push("con la red cortada no se declara que los datos están viejos");
  }

  // y al volver la red el aviso se va solo, sin pedirle nada al usuario
  await page.unroute("**/api/**");
  await ctx.setOffline(false);
  await page.evaluate(() => globalThis.dispatchEvent(new Event("online")));
  await page.waitForTimeout(1800);
  const avisoDespues = await page.locator('[data-testid="datos-viejos"]').count();
  console.log(
    `red de vuelta   → aviso de datos viejos: ${avisoDespues > 0 ? "sigue" : "se fue"}`,
  );
  if (avisoDespues > 0) {
    fallos.push("al volver la red el aviso de datos viejos no se va solo");
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
