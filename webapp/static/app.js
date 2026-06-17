/* FQ Mini App — frontend. Vanilla JS, sin framework.
   Auth: manda Telegram.WebApp.initData en cada request (cabecera). El rol y el
   filtrado los decide el servidor; aqui solo pintamos lo que llega. */
"use strict";

const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
const INIT_DATA = tg ? (tg.initData || "") : "";

if (tg) {
  try { tg.ready(); tg.expand(); } catch (e) {}
}

const GLYPH = { long: "▲", short: "▼" }; // ▲ ▼

// ---------------------------------------------------------------- API
async function api(path) {
  const res = await fetch(path, {
    headers: { "X-Telegram-Init-Data": INIT_DATA },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const err = new Error(body.error || ("HTTP " + res.status));
    err.status = res.status;
    throw err;
  }
  return res.json();
}

// ---------------------------------------------------------------- helpers
const $ = (sel) => document.querySelector(sel);
function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
}
function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function num(x, dmax) {
  if (x === null || x === undefined || isNaN(x)) return "—";
  return Number(x).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: dmax === undefined ? 2 : dmax });
}
function price(x) {
  if (x === null || x === undefined) return "—";
  const a = Math.abs(x);
  const d = a >= 100 ? 2 : a >= 1 ? 3 : 5;
  return num(x, d);
}
function rmult(x) {
  if (x === null || x === undefined) return "—";
  return (x >= 0 ? "+" : "") + Number(x).toFixed(2) + "R";
}
function pct(x, d) {
  if (x === null || x === undefined) return "—";
  return (x * 100).toFixed(d === undefined ? 0 : d) + "%";
}
function pf(x) {
  if (x === null || x === undefined) return "—";
  if (!isFinite(x)) return "∞";
  return Number(x).toFixed(2);
}
function usd(x) {
  if (x === null || x === undefined) return "—";
  return "$" + Number(x).toLocaleString("en-US", { maximumFractionDigits: 0 });
}
function ago(iso) {
  if (!iso) return "";
  const t = Date.parse(iso);
  if (isNaN(t)) return "";
  const s = (Date.now() - t) / 1000;
  if (s < 60) return "hace " + Math.floor(s) + "s";
  if (s < 3600) return "hace " + Math.floor(s / 60) + "m";
  if (s < 86400) return "hace " + Math.floor(s / 3600) + "h";
  return "hace " + Math.floor(s / 86400) + "d";
}
function dur(iso) {
  if (!iso) return "—";
  const s = iso;
  if (s < 60) return s + "s";
  if (s < 3600) return Math.floor(s / 60) + "m";
  return Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
}

const WIN = new Set(["tp1", "tp2", "tp3", "tp4"]);

// ---------------------------------------------------------------- state
let ME = null;
let CURRENT = null;

const TABS_CLIENT = [
  { id: "signals", label: "Senales", render: renderClientSignals },
  { id: "results", label: "Resultados", render: renderResults },
  { id: "account", label: "Mi cuenta", render: renderAccount },
];
const TABS_ADMIN = [
  { id: "signals", label: "Senales", render: renderAdminSignals },
  { id: "health", label: "Motor", render: renderEngine },
  { id: "subs", label: "Suscriptores", render: renderSubs },
];

function tabs() { return ME && ME.is_admin ? TABS_ADMIN : TABS_CLIENT; }

// ---------------------------------------------------------------- boot
async function boot() {
  try {
    ME = await api("/api/me");
  } catch (e) {
    return fail(e);
  }
  renderWho();
  renderTabs();
  const wanted = tabs().find((t) => t.id === wantedView());
  select(wanted ? wanted.id : tabs()[0].id);
}

// Vista pedida por deep-link. Un boton web_app abre la URL directa, asi que el
// destino llega por location.search (?startapp=); los deep-links t.me lo dan en
// start_param; el hash cubre la navegacion interna.
function wantedView() {
  if (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) return tg.initDataUnsafe.start_param;
  try {
    const q = new URLSearchParams(location.search);
    if (q.get("startapp")) return q.get("startapp");
    if (q.get("view")) return q.get("view");
  } catch (e) {}
  if (location.hash) return location.hash.slice(1);
  return null;
}

function fail(e) {
  const v = $("#view");
  clear(v);
  if (e && e.status === 401) {
    v.appendChild(el("div", "banner", "Abre esta app desde el bot de Telegram para identificarte."));
  } else {
    v.appendChild(el("div", "empty error", "No se pudo cargar: " + (e && e.message ? e.message : e)));
  }
}

function renderWho() {
  const who = $("#who");
  clear(who);
  const role = ME.role || "free";
  const cls = role === "admin" ? "admin" : (role === "vip" || role === "trial") ? "vip" : "";
  who.appendChild(el("span", "pill " + cls, role.toUpperCase()));
  if (ME.first_name) who.appendChild(el("span", "sig-time", ME.first_name));
  if (ME.days_remaining !== null && ME.days_remaining !== undefined && role !== "admin") {
    who.appendChild(el("span", "sig-time", "· " + ME.days_remaining + "d restantes"));
  }
}

function renderTabs() {
  const bar = $("#tabs");
  clear(bar);
  tabs().forEach((t) => {
    const b = el("button", "tab", t.label);
    b.dataset.id = t.id;
    b.onclick = () => select(t.id);
    bar.appendChild(b);
  });
}

function select(id) {
  CURRENT = id;
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.id === id);
  });
  try { location.hash = id; } catch (e) {}
  const tab = tabs().find((t) => t.id === id) || tabs()[0];
  const v = $("#view");
  clear(v);
  v.appendChild(el("div", "loading", "Cargando…"));
  tab.render(v).catch((e) => fail(e));
}

function header(v, title) {
  const wrap = el("div");
  wrap.style.display = "flex";
  wrap.style.justifyContent = "space-between";
  wrap.style.alignItems = "center";
  wrap.appendChild(el("div", "section-title", title));
  const btn = el("button", "refresh", "Actualizar");
  btn.onclick = () => select(CURRENT);
  wrap.appendChild(btn);
  v.appendChild(wrap);
}

// ---------------------------------------------------------------- signal card
function progressSteps(progress) {
  const done = new Set((progress || []).map((p) => p.event));
  const steps = el("div", "progress");
  ["tp1", "tp2", "tp3"].forEach((tp, i) => {
    const hit = done.has(tp + "_hit");
    steps.appendChild(el("span", "step" + (hit ? " done" : ""), "TP" + (i + 1) + (hit ? " ✓" : "")));
  });
  if (done.has("be_suggested")) steps.appendChild(el("span", "step done", "SL→BE"));
  return steps;
}

function levelsGrid(s, progress) {
  const done = new Set((progress || []).map((p) => p.event));
  const grid = el("div", "levels");
  const add = (k, val, cls) => {
    const row = el("div", "lvl");
    row.appendChild(el("span", "k", k));
    row.appendChild(el("span", "v" + (cls ? " " + cls : ""), val));
    grid.appendChild(row);
  };
  add("Entry", price(s.entry_price));
  add("SL", price(s.sl), "sl");
  add("TP1", price(s.tp1), done.has("tp1_hit") ? "hit" : "");
  add("TP2", price(s.tp2), done.has("tp2_hit") ? "hit" : "");
  add("TP3", price(s.tp3), done.has("tp3_hit") ? "hit" : "");
  add("TP4", price(s.tp4), "");
  return grid;
}

function signalCard(s, opts) {
  opts = opts || {};
  const card = el("div", "card accent-left");
  const head = el("div", "sig-head");
  const dir = (s.direction || "").toLowerCase();
  const dirEl = el("div", "sig-dir " + dir);
  dirEl.appendChild(el("span", "glyph", GLYPH[dir] || ""));
  dirEl.appendChild(document.createTextNode((dir === "short" ? "SHORT" : "LONG") + " · SOL/USDT"));
  head.appendChild(dirEl);

  if (s.status === "closed") {
    const win = WIN.has(s.outcome);
    head.appendChild(el("span", "pill " + (win ? "win" : "loss"),
      (s.outcome || "").toUpperCase() + " " + rmult(s.pnl_r)));
  } else {
    head.appendChild(el("span", "pill open", "ABIERTA"));
  }
  card.appendChild(head);
  card.appendChild(el("div", "sig-time", ago(s.ts_emitted)));

  if (s.locked) {
    const lk = el("div", "locked");
    lk.appendChild(el("div", "lock", "◉"));
    lk.appendChild(el("div", null, "Niveles exclusivos para VIP"));
    card.appendChild(lk);
    return card;
  }

  card.appendChild(levelsGrid(s, s.progress));
  if (s.status === "open") card.appendChild(progressSteps(s.progress));

  if (opts.admin) {
    const ax = el("div", "progress");
    if (s.p_master_final !== undefined && s.p_master_final !== null)
      ax.appendChild(el("span", "step", "P " + num(s.p_master_final, 2)));
    if (s.kappa_evo !== undefined && s.kappa_evo !== null)
      ax.appendChild(el("span", "step", "κ " + num(s.kappa_evo, 2)));
    if (s.session) ax.appendChild(el("span", "step", s.session));
    if (s.tier) ax.appendChild(el("span", "step", s.tier));
    card.appendChild(ax);
  }
  return card;
}

// ---------------------------------------------------------------- views: client
async function renderClientSignals(v) {
  const data = await api("/api/signals");
  clear(v);
  header(v, "Senales");
  const list = (data.signals || []);
  if (!list.length) { v.appendChild(el("div", "empty", "Sin senales todavia.")); return; }
  if (data.locked) {
    v.appendChild(el("div", "banner",
      "Tier free: ves direccion y resultados. Hazte VIP para ver entry, SL y TPs en vivo."));
  }
  list.forEach((s) => v.appendChild(signalCard(s)));
}

async function renderResults(v) {
  const data = await api("/api/track-record");
  clear(v);
  header(v, "Track record");
  const s = data.summary;
  if (!s) { v.appendChild(el("div", "empty", "Aun no hay cierres registrados.")); return; }
  v.appendChild(windowStats("Ultimos 30 dias", s.w30));
  v.appendChild(windowStats("Ultimos 90 dias", s.w90));
  v.appendChild(windowStats("Total", s.total));
  if (s.longest_streak) {
    const c = el("div", "card");
    c.appendChild(kv("Mejor racha ganadora", s.longest_streak + " seguidas"));
    v.appendChild(c);
  }
}

function windowStats(title, w) {
  const card = el("div", "card");
  card.appendChild(el("div", "section-title", title));
  if (!w || !w.n) { card.appendChild(el("div", "empty", "Sin datos.")); return card; }
  const grid = el("div", "stat-grid");
  grid.appendChild(stat("Win rate", pct(w.win_rate), w.win_rate >= 0.5 ? "pos" : ""));
  grid.appendChild(stat("Expectancy", rmult(w.expectancy), w.expectancy >= 0 ? "pos" : "neg"));
  grid.appendChild(stat("Profit factor", pf(w.profit_factor)));
  grid.appendChild(stat("Cerradas", w.n));
  card.appendChild(grid);
  return card;
}

async function renderAccount(v) {
  clear(v);
  header(v, "Mi cuenta");
  const card = el("div", "card accent-left");
  card.appendChild(kv("Nombre", ME.first_name || "—"));
  card.appendChild(kv("Plan", (ME.role || "free").toUpperCase()));
  if (ME.days_remaining !== null && ME.days_remaining !== undefined)
    card.appendChild(kv("Dias restantes", ME.days_remaining));
  v.appendChild(card);
  if (ME.role === "free" || ME.role === "trial") {
    v.appendChild(el("div", "banner",
      "Activa VIP desde el bot para senales en vivo con entry, SL y TPs."));
  }
}

// ---------------------------------------------------------------- views: admin
async function renderAdminSignals(v) {
  const data = await api("/api/admin/signals");
  clear(v);
  header(v, "Senales (motor)");
  const open = data.open || [];
  const recent = data.recent || [];
  v.appendChild(el("div", "section-title", "Abiertas (" + open.length + ")"));
  if (!open.length) v.appendChild(el("div", "empty", "Ninguna abierta."));
  open.forEach((s) => v.appendChild(signalCard(s, { admin: true })));
  v.appendChild(el("div", "section-title", "Recientes"));
  recent.forEach((s) => v.appendChild(signalCard(s, { admin: true })));
}

async function renderEngine(v) {
  const [ov, st] = await Promise.all([api("/api/admin/overview"), api("/api/admin/stats")]);
  clear(v);
  header(v, "Salud del motor");

  const hc = el("div", "card");
  const h = ov.health || {};
  ["vip", "public", "maintenance", "web"].forEach((c) => {
    if (!h[c]) return;
    const row = el("div", "row");
    const left = el("div", "name");
    const dotcls = !h[c].seen ? "idle" : h[c].stale ? "bad" : "ok";
    left.innerHTML = '<span class="dot ' + dotcls + '"></span>' + c;
    row.appendChild(left);
    row.appendChild(el("div", "meta", h[c].seen ? ("latido " + dur(Math.floor(h[c].age_seconds))) : "sin latido"));
    hc.appendChild(row);
  });
  v.appendChild(hc);

  const counts = el("div", "stat-grid three");
  counts.appendChild(stat("Abiertas", ov.open_count));
  counts.appendChild(stat("Cerradas", ov.signals_closed));
  counts.appendChild(stat("Total", ov.signals_total));
  v.appendChild(counts);

  const g = st.global;
  if (g && g.n) {
    v.appendChild(el("div", "section-title", "Desempeno global"));
    const grid = el("div", "stat-grid");
    grid.appendChild(stat("Win rate", pct(g.win_rate), g.win_rate >= 0.5 ? "pos" : ""));
    grid.appendChild(stat("Expectancy", rmult(g.expectancy_r), g.expectancy_r >= 0 ? "pos" : "neg"));
    grid.appendChild(stat("Profit factor", pf(g.profit_factor)));
    grid.appendChild(stat("Muestras", g.n));
    v.appendChild(grid);

    if (g.tier_summary && Object.keys(g.tier_summary).length) {
      const tc = el("div", "card");
      tc.appendChild(el("div", "section-title", "Por tier"));
      Object.keys(g.tier_summary).forEach((t) => {
        const d = g.tier_summary[t];
        tc.appendChild(kv(t + " (" + d.n + ")", pct(d.win_rate) + " · " + rmult(d.expectancy)));
      });
      v.appendChild(tc);
    }
  }
}

async function renderSubs(v) {
  const data = await api("/api/admin/subs");
  clear(v);
  header(v, "Suscriptores");
  const s = data.stats;
  if (s) {
    const grid = el("div", "stat-grid three");
    grid.appendChild(stat("Total", s.users_total));
    grid.appendChild(stat("VIP activos", s.active_vips, "pos"));
    grid.appendChild(stat("Trials", s.users_trial));
    v.appendChild(grid);
    const rev = el("div", "stat-grid");
    rev.appendChild(stat("Ingresos (30d)", usd(s.revenue_30d), "pos"));
    rev.appendChild(stat("Ingresos total", usd(s.revenue_total)));
    v.appendChild(rev);
  }

  const pend = data.pending_payments || [];
  if (pend.length) {
    const pc = el("div", "card");
    pc.appendChild(el("div", "section-title", "Pagos pendientes (" + pend.length + ")"));
    pend.forEach((p) => pc.appendChild(kv((p.method || "?") + " · " + (p.chat_id || ""), usd(p.amount_usd))));
    v.appendChild(pc);
  }

  const users = data.recent_users || [];
  if (users.length) {
    const uc = el("div", "card");
    uc.appendChild(el("div", "section-title", "Ultimos usuarios"));
    users.forEach((u) => {
      const row = el("div", "row");
      row.appendChild(el("div", "name", (u.first_name || u.username || u.chat_id) +
        '  <span class="pill ' + (u.tier || "") + '">' + (u.tier || "free") + "</span>"));
      row.appendChild(el("div", "meta", ago(u.last_seen_at)));
      uc.appendChild(row);
    });
    v.appendChild(uc);
  }
}

// ---------------------------------------------------------------- small builders
function stat(label, value, cls) {
  const s = el("div", "stat");
  s.appendChild(el("div", "label", label));
  s.appendChild(el("div", "value" + (cls ? " " + cls : ""), value));
  return s;
}
function kv(k, val) {
  const row = el("div", "kv");
  row.appendChild(el("span", "k", k));
  row.appendChild(el("span", "v", val));
  return row;
}

boot();
