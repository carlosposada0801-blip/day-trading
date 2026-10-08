const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const cls = (v) => (v > 0.05 ? "up" : v < -0.05 ? "down" : "flat");
const fmt = (n, d = 2) => (n == null ? "—" : Number(n).toLocaleString(undefined, { minimumFractionDigits: d, maximumFractionDigits: d }));
const money = (n) => (n < 0 ? "-$" : "$") + fmt(Math.abs(n));
const ago = (iso) => {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  return m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};
const safeUrl = (u) => (/^https?:\/\//.test(u) ? u : "#");

let selected = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 3000);
}

function scoreBar(score) {
  const w = Math.abs(score) / 2; // 100 -> 50% of bar
  const color = score >= 0 ? "var(--up)" : "var(--down)";
  const left = score >= 0 ? 50 : 50 - w;
  return `<span class="bar"><i style="left:${left}%;width:${w}%;background:${color}"></i></span>`;
}

const comp = (v) => (v == null ? `<span class="flat">—</span>` : `<span class="${cls(v)}">${v > 0 ? "+" : ""}${v.toFixed(2)}</span>`);

async function loadSignals() {
  const rows = await api("/api/signals");
  $("#signals tbody").innerHTML = rows.map((s) => `
    <tr data-t="${esc(s.ticker)}" class="${s.ticker === selected ? "sel" : ""}">
      <td><b>${esc(s.ticker)}</b></td>
      <td>${s.price == null ? "—" : "$" + fmt(s.price)}</td>
      <td class="${cls(s.change_pct)}">${s.change_pct == null ? "—" : (s.change_pct > 0 ? "+" : "") + fmt(s.change_pct) + "%"}</td>
      <td>${fmt(s.score, 1)}${scoreBar(s.score)}</td>
      <td class="stance ${s.stance === "bullish" ? "up" : s.stance === "bearish" ? "down" : "flat"}">${s.stance}</td>
      <td>${comp(s.components.news)}</td><td>${comp(s.components.social)}</td>
      <td>${comp(s.components.funds)}</td><td>${comp(s.components.momentum)}</td>
      <td>${Math.round(s.confidence * 100)}%</td>
    </tr>`).join("");
  document.querySelectorAll("#signals tbody tr").forEach((tr) => tr.addEventListener("click", () => showDetail(tr.dataset.t)));
}

function sparkline(closes) {
  if (closes.length < 2) return "";
  const min = Math.min(...closes), max = Math.max(...closes), span = max - min || 1;
  const pts = closes.map((c, i) => `${(i / (closes.length - 1)) * 200},${38 - ((c - min) / span) * 36}`).join(" ");
  const color = closes.at(-1) >= closes[0] ? "var(--up)" : "var(--down)";
  return `<polyline fill="none" stroke="${color}" stroke-width="1.5" points="${pts}"/>`;
}

async function showDetail(ticker) {
  selected = ticker;
  document.querySelectorAll("#signals tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.t === ticker));
  const d = await api(`/api/ticker/${encodeURIComponent(ticker)}`);
  const s = d.signal;
  $("#detail").hidden = false;
  $("#d-title").innerHTML = `${esc(ticker)} <span class="${s.stance === "bullish" ? "up" : s.stance === "bearish" ? "down" : "flat"}">${fmt(s.score, 1)} · ${s.stance}</span>`;
  $("#d-spark").innerHTML = sparkline(d.closes);
  $("#d-news").innerHTML = d.news.map((a) => `
    <li><span class="dot" style="background:var(--${cls(a.sentiment)})"></span>
      <a href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener">${esc(a.title)}</a>
      <div class="meta">${esc(a.source)} · ${ago(a.published)} · sentiment ${a.sentiment.toFixed(2)}</div></li>`).join("") || `<li class="meta">No headlines</li>`;
  $("#d-social").innerHTML = d.social.map((p) => `
    <li><span class="dot" style="background:var(--${cls(p.sentiment)})"></span>
      <a href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener">${esc(p.text.slice(0, 180))}</a>
      <div class="meta">${esc(p.platform)} · ${esc(p.author)} · ▲${p.score}${p.label ? " · " + p.label : ""} · ${ago(p.created)}</div></li>`).join("") || `<li class="meta">No posts</li>`;
  $("#d-funds").innerHTML = d.funds.map(fundRow).join("") || `<li class="meta">No tracked fund holds this</li>`;
  $("#detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function fundRow(m) {
  const verb = m.prev_shares === 0 ? "opened" : m.shares === 0 ? "exited" : m.change > 0 ? "added" : m.change < 0 ? "trimmed" : "held";
  const pct = m.prev_shares ? ` (${m.change > 0 ? "+" : ""}${fmt((m.change / m.prev_shares) * 100, 0)}%)` : "";
  return `<li><b>${esc(m.fund)}</b> <span class="${cls(m.change)}">${verb}</span> ${esc(m.ticker)}${pct}
    <div class="meta">${fmt(m.shares, 0)} sh · ${money(m.value_usd).replace(".00", "")} · period ${esc(m.period)}</div></li>`;
}

async function loadSide() {
  const [trend, funds, src, cfg] = await Promise.all([api("/api/trending"), api("/api/funds"), api("/api/sources"), api("/api/config")]);
  $("#trending").innerHTML = trend.map((t) => `<li><b>${esc(t.ticker)}</b> · ${t.mentions} mentions · <span class="${cls(t.sentiment)}">${t.sentiment.toFixed(2)}</span></li>`).join("") || `<li class="meta">No data</li>`;
  $("#funds").innerHTML = funds.slice(0, 15).map(fundRow).join("") || `<li class="meta">No data</li>`;
  $("#mode").textContent = cfg.demo_mode ? "DEMO DATA" : "LIVE";
  $("#sources").innerHTML = Object.entries(src.sources).map(([k, v]) => `<span class="${v.ok ? "" : "bad"}" title="${esc(v.error || "ok")}">${v.ok ? "●" : "○"} ${esc(k)}</span>`).join(" &nbsp; ");
}

async function loadPaper() {
  const p = await api("/api/paper");
  $("#paper").innerHTML = `
    <div class="kpis">
      <div class="kpi"><div class="meta">Equity</div><div class="v">${money(p.equity)}</div></div>
      <div class="kpi"><div class="meta">Cash</div><div class="v">${money(p.cash)}</div></div>
      <div class="kpi"><div class="meta">Total P&amp;L</div><div class="v ${cls(p.total_pnl)}">${money(p.total_pnl)} (${fmt(p.total_pnl_pct)}%)</div></div>
      <div class="kpi"><div class="meta">Realized</div><div class="v ${cls(p.realized_pnl)}">${money(p.realized_pnl)}</div></div>
    </div>
    <ul class="feed">${p.positions.map((x) => `<li><b>${esc(x.ticker)}</b> ${fmt(x.qty, 2)} @ $${fmt(x.avg_cost)} → $${fmt(x.last)}
      <span class="${cls(x.unrealized)}" style="float:right">${money(x.unrealized)}</span></li>`).join("") || `<li class="meta">No open positions. Pick a ticker above to paper trade.</li>`}</ul>`;
}

async function refresh() {
  try {
    await Promise.all([loadSignals(), loadSide(), loadPaper()]);
    if (selected) await showDetail(selected);
  } catch (e) { toast(e.message); }
}

$("#trade").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!selected) return;
  const side = e.submitter.dataset.side;
  try {
    const o = await api("/api/paper/order", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ ticker: selected, side, qty: Number($("#t-qty").value) }) });
    toast(`Paper ${o.side} ${o.qty} ${o.ticker} @ $${fmt(o.price)}`);
    loadPaper();
  } catch (err) { toast(err.message); }
});
$("#reset").addEventListener("click", async () => {
  if (!confirm("Reset the paper account? All simulated trades will be deleted.")) return;
  await api("/api/paper/reset", { method: "POST" });
  loadPaper();
});
$("#refresh").addEventListener("click", refresh);
refresh();
setInterval(refresh, 60_000);
