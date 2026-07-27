import { chromium } from "playwright";

const OUT = process.argv[2] ?? "/tmp/marea";
const browser = await chromium.launch({
  executablePath: "/opt/pw-browsers/chromium",
});
const page = await browser.newPage({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 2,
  isMobile: true,
  hasTouch: true,
});
const base = "http://localhost:4173";
const shots = [];

async function shot(name) {
  await page.waitForTimeout(450);
  const overflow = await page.evaluate(() => ({
    doc: document.documentElement.scrollWidth,
    win: window.innerWidth,
  }));
  shots.push({ name, ...overflow });
  await page.screenshot({ path: `${OUT}/${name}.png` });
}

await page.goto(base, { waitUntil: "networkidle" });
await shot("01-splash");
await page.waitForTimeout(1500);
await shot("02-promesa");
await page.getByTestId("onboarding-start").click();
await shot("03-wallet");
await page.getByTestId("onboarding-create-wallet").click();
await page.getByTestId("onboarding-explore").waitFor();
await shot("04-lista");
await page.getByTestId("onboarding-explore").click();
await page.getByTestId("home-screen").waitFor();
await shot("05-feed");
await page.locator("[data-testid=market-card] button").first().click();
await page.getByTestId("market-detail").waitFor();
await shot("06-detalle");
await page.getByTestId("detail-deposit-cta").click();
await page.getByTestId("deposit-sheet").waitFor();
await shot("07-deposito");
await page.keyboard.press("Escape");
await page.waitForTimeout(300);
await page.getByRole("tab", { name: "Portafolio" }).click();
await shot("08-portafolio");
await page.getByRole("tab", { name: "Buscar" }).click();
await shot("09-buscar");
await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
await page.getByRole("tab", { name: "Mercados" }).click();
await shot("10-feed-claro");

console.log(JSON.stringify(shots, null, 1));
await browser.close();
