const BASE = "http://127.0.0.1:8121";
const filas = [];
for (let i = 0; i < 46; i++) {
  const t = Date.now();
  try {
    const r = await fetch(`${BASE}/api/mercados`);
    const j = await r.json();
    const ms = j.markets || j.mercados || j;
    for (const m of ms) {
      if (!/^(btc|eth)-(5m|15m)-/.test(m.id)) continue;
      filas.push({
        t, id: m.id, status: m.status,
        falta: Math.round((Date.parse(m.closesAt) - t) / 1000),
      });
    }
  } catch (e) { filas.push({ t, error: String(e).slice(0, 60) }); }
  await new Promise((r) => setTimeout(r, 10000));
}
console.log(JSON.stringify(filas));
