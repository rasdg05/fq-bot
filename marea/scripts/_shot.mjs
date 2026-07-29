import { chromium } from "playwright";
const b = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
for (const tema of ["dark", "light"]) {
  const p = await b.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true });
  await p.goto("http://127.0.0.1:8100/", { waitUntil: "networkidle" });
  await p.evaluate((t) => document.documentElement.setAttribute("data-theme", t), tema);
  for (let i = 0; i < 10; i++) {
    const cta = p.locator('[data-testid="onboarding-skip"], [data-testid="onboarding-cta"], [data-testid="p0-cta"], button:has-text("Ver los mercados"), button:has-text("Empezar"), button:has-text("Explorar"), button:has-text("Entendido"), button:has-text("Continuar")').first();
    if ((await cta.count()) && (await cta.isVisible())) { await cta.click(); await p.waitForTimeout(250); } else break;
  }
  await p.waitForSelector('[data-testid="home-screen"]', { timeout: 15000 });
  await p.evaluate((t) => document.documentElement.setAttribute("data-theme", t), tema);
  await p.waitForTimeout(700);
  await p.screenshot({ path: `${process.argv[2]}/feed-${tema}.png` });
  await p.close();
}
await b.close();
