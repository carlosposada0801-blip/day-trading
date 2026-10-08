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
const compactMoney = (n) => (n < 0 ? "-$" : "$") + Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(Math.abs(n));

// Per-browser preferences. Storage can be blocked (private mode), so every access is guarded.
const pref = {
  get(k, d = null) { try { const v = localStorage.getItem("sd." + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("sd." + k, JSON.stringify(v)); } catch { /* ignore */ } },
};

let selected = pref.get("selected");
let sigRows = [];
let sortKey = pref.get("sortKey", "score"), sortAsc = pref.get("sortAsc", false);

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (r.status === 401) { location.href = "/login"; throw new Error("Logged out"); }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || r.statusText);
  return body;
}

function toast(msg, isError = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.toggle("error", isError);
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), isError ? 6000 : 3000);
}
const fail = (e) => toast(e.message, true);

function scoreBar(score) {
  const w = Math.abs(score) / 2; // 100 -> 50% of bar
  const color = score >= 0 ? "var(--up)" : "var(--down)";
  const left = score >= 0 ? 50 : 50 - w;
  return `<span class="bar"><i style="left:${left}%;width:${w}%;background:${color}"></i></span>`;
}

const comp = (v) => (v == null ? `<span class="flat">—</span>` : `<span class="${cls(v)}">${v > 0 ? "+" : ""}${v.toFixed(2)}</span>`);

const SORTERS = {
  ticker: (s) => s.ticker, price: (s) => s.price ?? -Infinity, day: (s) => s.change_pct ?? -Infinity,
  score: (s) => s.score, stance: (s) => s.score, conf: (s) => s.confidence,
  news: (s) => s.components.news ?? -9, social: (s) => s.components.social ?? -9,
  momentum: (s) => s.components.momentum ?? -9, insiders: (s) => s.components.insiders ?? -9,
  funds: (s) => s.components.funds ?? -9, congress: (s) => s.components.congress ?? -9,
};

async function loadSignals() {
  sigRows = await api("/api/signals");
  renderSignals();
}

function renderSignals() {
  const key = SORTERS[sortKey] ? sortKey : "score";
  const rows = [...sigRows].sort((a, b) => {
    const x = SORTERS[key](a), y = SORTERS[key](b);
    return (x < y ? -1 : x > y ? 1 : 0) * (sortAsc ? 1 : -1);
  });
  document.querySelectorAll("#signals th[data-key]").forEach((th) => {
    th.classList.toggle("sorted", th.dataset.key === key);
    th.classList.toggle("asc", th.dataset.key === key && sortAsc);
    th.setAttribute("aria-sort", th.dataset.key === key ? (sortAsc ? "ascending" : "descending") : "none");
  });
  $("#signals tbody").innerHTML = rows.map((s) => `
    <tr data-t="${esc(s.ticker)}" tabindex="0" class="${s.ticker === selected ? "sel" : ""}">
      <td><b>${esc(s.ticker)}</b></td>
      <td>${s.price == null ? "—" : "$" + fmt(s.price)}</td>
      <td class="${cls(s.change_pct)}">${s.change_pct == null ? "—" : (s.change_pct > 0 ? "+" : "") + fmt(s.change_pct) + "%"}</td>
      <td>${fmt(s.score, 1)}${scoreBar(s.score)}</td>
      <td class="stance ${s.stance === "bullish" ? "up" : s.stance === "bearish" ? "down" : "flat"}">${s.stance}</td>
      <td>${comp(s.components.news)}</td><td>${comp(s.components.social)}</td>
      <td>${comp(s.components.momentum)}</td><td>${comp(s.components.insiders)}</td>
      <td>${comp(s.components.funds)}</td><td>${comp(s.components.congress)}</td>
      <td>${Math.round(s.confidence * 100)}%</td>
    </tr>`).join("");
  document.querySelectorAll("#signals tbody tr").forEach((tr) => {
    tr.addEventListener("click", () => showDetail(tr.dataset.t).catch(fail));
    tr.addEventListener("keydown", (e) => { if (e.key === "Enter") showDetail(tr.dataset.t).catch(fail); });
  });
}

function linePath(values, w, h, pad = 3) {
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const xy = values.map((v, i) => [(i / (values.length - 1)) * w, h - pad - ((v - min) / span) * (h - 2 * pad)]);
  return { xy, pts: xy.map(([x, y]) => `${x},${y}`).join(" ") };
}

function sparkline(closes) {
  if (closes.length < 2) return "";
  const { pts } = linePath(closes, 260, 48);
  const color = closes.at(-1) >= closes[0] ? "var(--up)" : "var(--down)";
  return `<polyline fill="none" stroke="${color}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" points="${pts}"/>`;
}

// Crosshair + tooltip for a line chart. labelFn(i) returns the tooltip text for point i.
function attachHover(wrap, svg, values, w, h, labelFn) {
  wrap.querySelector(".hover-tip")?.remove();
  if (values.length < 2) return;
  const { xy } = linePath(values, w, h);
  const tip = document.createElement("div");
  tip.className = "hover-tip";
  tip.hidden = true;
  wrap.appendChild(tip);
  const ns = "http://www.w3.org/2000/svg";
  const vline = document.createElementNS(ns, "line");
  vline.setAttribute("stroke", "var(--muted)"); vline.setAttribute("stroke-width", "1");
  vline.setAttribute("vector-effect", "non-scaling-stroke"); vline.setAttribute("y1", 0); vline.setAttribute("y2", h);
  const dot = document.createElementNS(ns, "circle");
  dot.setAttribute("r", 4); dot.setAttribute("fill", "var(--text)"); dot.setAttribute("stroke", "var(--card)"); dot.setAttribute("stroke-width", 2);
  vline.style.display = dot.style.display = "none";
  svg.append(vline, dot);
  const move = (clientX) => {
    const r = svg.getBoundingClientRect();
    const i = Math.max(0, Math.min(values.length - 1, Math.round(((clientX - r.left) / r.width) * (values.length - 1))));
    const [x, y] = xy[i];
    vline.setAttribute("x1", x); vline.setAttribute("x2", x);
    dot.setAttribute("cx", x); dot.setAttribute("cy", y);
    vline.style.display = dot.style.display = "";
    tip.hidden = false;
    tip.textContent = labelFn(i);
    tip.style.left = `${(x / w) * r.width}px`;
    tip.style.top = `${(y / h) * r.height}px`;
  };
  const hide = () => { tip.hidden = true; vline.style.display = dot.style.display = "none"; };
  svg.onpointermove = (e) => move(e.clientX);
  svg.onpointerleave = hide;
}

function closeDetail() {
  selected = null;
  pref.set("selected", null);
  $("#detail").hidden = true;
  document.querySelectorAll("#signals tbody tr").forEach((tr) => tr.classList.remove("sel"));
}

async function showDetail(ticker, scroll = true) {
  selected = ticker;
  pref.set("selected", ticker);
  document.querySelectorAll("#signals tbody tr").forEach((tr) => tr.classList.toggle("sel", tr.dataset.t === ticker));
  const d = await api(`/api/ticker/${encodeURIComponent(ticker)}`);
  const s = d.signal;
  $("#detail").hidden = false;
  $("#d-title").innerHTML = `${esc(ticker)} <span class="${s.stance === "bullish" ? "up" : s.stance === "bearish" ? "down" : "flat"}">${fmt(s.score, 1)} · ${s.stance}</span>`;
  $("#d-spark").innerHTML = sparkline(d.closes);
  attachHover($("#d-spark-wrap"), $("#d-spark"), d.closes, 260, 48,
    (i) => `${d.dates[i] ? new Date(d.dates[i] + "T12:00").toLocaleDateString([], { month: "short", day: "numeric" }) + " · " : ""}$${fmt(d.closes[i])}`);
  $("#d-news").innerHTML = d.news.map((a) => `
    <li><span class="dot" style="background:var(--${cls(a.sentiment)})"></span>
      <a href="${esc(safeUrl(a.url))}" target="_blank" rel="noopener">${esc(a.title)}</a>
      <div class="meta">${esc(a.source)} · ${ago(a.published)} · sentiment ${a.sentiment.toFixed(2)}</div></li>`).join("") || `<li class="meta">No headlines</li>`;
  $("#d-social").innerHTML = d.social.map((p) => `
    <li><span class="dot" style="background:var(--${cls(p.sentiment)})"></span>
      <a href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener">${esc(p.text.slice(0, 180))}</a>
      <div class="meta">${esc(p.platform)} · ${esc(p.author)} · ▲${p.score}${p.label ? " · " + p.label : ""} · ${ago(p.created)}</div></li>`).join("") || `<li class="meta">No posts</li>`;
  $("#d-funds").innerHTML = d.funds.map(fundRow).join("") || `<li class="meta">No tracked fund holds this</li>`;
  $("#d-insiders").innerHTML = d.insiders.map((t) => `
    <li><b>${esc(t.insider)}</b> <span class="meta">${esc(t.title)}</span>
      <span class="${t.code === "P" ? "up" : "down"}">${t.code === "P" ? "bought" : "sold"}</span>
      <div class="meta">${fmt(t.shares, 0)} sh @ $${fmt(t.price)} = ${money(t.value)} · ${esc(t.date)}</div></li>`).join("") || `<li class="meta">No open-market insider trades</li>`;
  $("#d-congress").innerHTML = d.congress.map((t) => `
    <li><b>${esc(t.member)}</b> <span class="meta">${esc(t.chamber)}</span>
      <span class="${t.side === "buy" ? "up" : "down"}">${t.side === "buy" ? "bought" : "sold"}</span>
      <div class="meta">${money(t.amount_low).replace(".00", "")}–${money(t.amount_high).replace(".00", "")} · traded ${esc(t.traded)} · disclosed ${esc(t.disclosed)}</div></li>`).join("") || `<li class="meta">No disclosed trades</li>`;
  if (scroll) $("#detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function fundRow(m) {
  const verb = m.prev_shares === 0 ? "opened" : m.shares === 0 ? "exited" : m.change > 0 ? "added" : m.change < 0 ? "trimmed" : "held";
  const pct = m.prev_shares ? ` (${m.change > 0 ? "+" : ""}${fmt((m.change / m.prev_shares) * 100, 0)}%)` : "";
  return `<li><b>${esc(m.fund)}</b> <span class="${cls(m.change)}">${verb}</span> ${esc(m.ticker)}${pct}
    <div class="meta">${fmt(m.shares, 0)} sh · ${compactMoney(m.value_usd)} · period ${esc(m.period)}</div></li>`;
}

async function loadSide() {
  const [trend, funds, src, cfg] = await Promise.all([api("/api/trending"), api("/api/funds"), api("/api/sources"), api("/api/config")]);
  $("#trending").innerHTML = trend.map((t) => `<li><b>${esc(t.ticker)}</b> · ${t.mentions} mentions · <span class="${cls(t.sentiment)}">${t.sentiment.toFixed(2)}</span></li>`).join("") || `<li class="meta">No data</li>`;
  $("#funds").innerHTML = funds.slice(0, 15).map(fundRow).join("") || `<li class="meta">No data</li>`;
  $("#mode").textContent = cfg.demo_mode ? "DEMO DATA" : "LIVE";
  $("#ai").hidden = !cfg.ai_sentiment;
  $("#ai").title = cfg.ai_model ? `Headlines and posts scored by ${cfg.ai_model}` : "";
  const a = cfg.alerts;
  $("#alert-rules").textContent = a.enabled
    ? `Checks every ${a.every_min} min. Fires when a score moves ${a.delta}+ points or turns bullish/bearish.${a.push ? " Push notifications on." : " Set ALERT_WEBHOOK_URL for phone push."}`
    : "Background alerts are off (ALERTS_ENABLED=0).";
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

let lastAlertId = null;
async function loadAlerts() {
  const { alerts, unseen } = await api("/api/alerts");
  badge.alerts = unseen;
  updateTitle();
  $("#unseen").textContent = unseen;
  $("#bell").classList.toggle("has", unseen > 0);
  $("#alerts").innerHTML = alerts.slice(0, 20).map((x) => `
    <li class="${x.seen ? "" : "unseen"}"><span class="${x.kind === "flip" ? "" : cls(x.score - (x.prev_score ?? x.score))}">${esc(x.message)}</span>
      <div class="meta">${ago(x.ts)}</div></li>`).join("") || `<li class="meta">No alerts yet. They appear as scores move over time.</li>`;
  const newest = alerts[0]?.id ?? 0;
  if (lastAlertId !== null && newest > lastAlertId && "Notification" in window && Notification.permission === "granted") {
    alerts.filter((x) => x.id > lastAlertId).forEach((x) => new Notification("Signal Desk", { body: x.message }));
  }
  lastAlertId = newest;
}

const pct = (v) => (v == null ? "—" : `<span class="${cls(v)}">${v > 0 ? "+" : ""}${fmt(v, 2)}%</span>`);
function btBlock(title, r) {
  if (!r.n) return `<div><h3>${title}</h3><p class="meta">Not enough data yet.</p></div>`;
  return `<div><h3>${title}</h3>
    <div class="bt-row"><span>Samples</span><b>${r.n}</b></div>
    <div class="bt-row" title="Rank correlation between score and forward return. Above ~0.05 is meaningful for markets."><span>IC</span><b class="${cls(r.ic ?? 0)}">${r.ic ?? "—"}</b></div>
    <div class="bt-row" title="How often bullish/bearish calls got the direction right"><span>Hit rate</span><b>${r.hit_rate == null ? "—" : Math.round(r.hit_rate * 100) + "%"} <span class="meta">(${r.calls})</span></b></div>
    <div class="bt-row"><span>Avg after bullish</span>${pct(r.avg_fwd_return_pct.bullish)}</div>
    <div class="bt-row"><span>Avg after neutral</span>${pct(r.avg_fwd_return_pct.neutral)}</div>
    <div class="bt-row"><span>Avg after bearish</span>${pct(r.avg_fwd_return_pct.bearish)}</div>
    <div class="bt-row"><span>Long − short</span>${pct(r.long_short_pct)}</div></div>`;
}
async function loadBacktest() {
  const b = await api(`/api/backtest?horizon=${$("#horizon").value}`);
  $("#backtest").innerHTML = `<div class="bt-grid">${btBlock("Full score (recorded)", b.track_record)}${btBlock("Momentum, past year", b.momentum)}</div>
    <p class="note">${b.snapshots} score snapshots recorded so far; the full-score track record fills in as the app runs. No trading costs included.${b.demo ? " <b>Demo data: these numbers mean nothing.</b>" : ""}</p>`;
}

let apState = null;
async function loadAutopilot() {
  const a = await api("/api/autopilot");
  apState = a;
  const st = $("#ap-state");
  st.textContent = a.running ? "RUNNING" : "OFF";
  st.className = "pill " + (a.running ? "on" : "off");
  $("#ap-broker").textContent = a.broker === "robinhood" ? "Robinhood Agentic account" : "Practice account (pretend money)";
  const btn = $("#ap-toggle");
  btn.textContent = a.running ? "Stop autopilot" : "Start autopilot";
  btn.classList.toggle("stop", a.running);
  btn.disabled = !a.running && !a.ready;
  btn.title = !a.running && !a.ready ? "Fix the red items below first" : "";
  $("#ap-practice").hidden = a.broker !== "sim";

  const acct = a.account;
  const profitPct = a.profit != null && a.net_deposits ? (a.profit / a.net_deposits) * 100 : null;
  $("#ap-kpis").innerHTML = !acct ? `<p class="meta">Can't reach the account right now. See the checklist.</p>` : `
    <div><div class="meta">You've put in</div><div class="v">${a.net_deposits == null ? "—" : money(a.net_deposits)}</div>
      <div class="sub">deposits minus withdrawals</div></div>
    <div><div class="meta">Worth now</div><div class="v">${money(acct.equity)}</div></div>
    <div><div class="meta">Profit</div><div class="v ${cls(a.profit ?? 0)}">${a.profit == null ? "—" : (a.profit >= 0 ? "+" : "") + money(a.profit)}</div>
      <div class="sub">${profitPct == null ? "" : (profitPct >= 0 ? "+" : "") + fmt(profitPct) + "%"}</div></div>
    <div><div class="meta">Ready to withdraw</div><div class="v">${money(a.reserved || 0)}</div>
      <div class="sub">${a.reserved > 0 ? (a.broker === "robinhood" ? "Withdraw in the Robinhood app" : "Use Withdraw below") : `set aside once you're up ${a.plan.profit_pull_trigger_pct}%`}</div>
      ${a.reserved > 0 ? `<button id="ap-release" title="Put this money back to work instead">Keep it invested</button>` : ""}</div>`;
  $("#ap-release")?.addEventListener("click", async () => {
    if (!confirm("Put the set-aside profit back to work instead of withdrawing it?")) return;
    await post("/api/autopilot/release"); loadAutopilot();
  });

  const al = a.allocation;
  if (al) {
    const parts = [["core", `Core (${a.plan.core_symbol})`, al.core], ["sat", "Signal trades", al.satellites],
                   ["cash", "Cash", al.cash], ["aside", "Set aside for you", al.set_aside]];
    const total = parts.reduce((s, p) => s + p[2], 0) || 1;
    const shown = parts.filter((p) => p[2] > 0.5);
    $("#ap-alloc").innerHTML = `<div class="stack" role="img" aria-label="${shown.map((p) => `${p[1]} ${Math.round((p[2] / total) * 100)}%`).join(", ")}">
        ${shown.map((p) => `<i class="seg-${p[0]}" style="flex:${p[2]}" title="${esc(p[1])}: ${money(p[2])}"></i>`).join("")}</div>
      <div class="legend">${parts.map((p) => `<span><i class="sw seg-${p[0]}"></i>${esc(p[1])} <b>${money(p[2])}</b> ${Math.round((p[2] / total) * 100)}%</span>`).join("")}</div>`;
  } else $("#ap-alloc").innerHTML = "";

  const pl = a.plan;
  $("#ap-plan").innerHTML = `
    ${pl.core_pct > 0 ? `<b>${pl.core_pct}%</b> in ${esc(pl.core_symbol)} (a broad index fund), rebalanced when it drifts ${pl.rebalance_band_pct}%.<br>` : "No core fund: everything follows signals.<br>"}
    <b>${Math.max(0, 100 - pl.core_pct - pl.cash_reserve_pct)}%</b> traded by the signal rules · <b>${pl.cash_reserve_pct}%</b> kept as cash.<br>
    New deposits are found automatically and invested in steps of up to ${money(pl.core_max_order_usd).replace(".00", "")}.<br>
    Once you're up <b>${pl.profit_pull_trigger_pct}%</b>, <b>${pl.profit_pull_share_pct}%</b> of the profit is set aside as cash and you're notified to withdraw it.
    ${pl.weekly_summary ? "<br>Weekly summary to your phone after Friday's close." : ""}`;
  $("#ap-checks").innerHTML = a.checks.map((c) => `<li>
      <span class="mark ${c.ok ? "ok" : c.level === "block" ? "bad" : "warn"}">${c.ok ? "✓" : c.level === "block" ? "✕" : "!"}</span>
      <span>${esc(c.text)}${c.fix ? `<span class="fix">${esc(c.fix)}</span>` : ""}</span></li>`).join("");
}

const post = (path, body) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
let tstate = null;

async function loadTrader() {
  const t = await api("/api/trading");
  tstate = t;
  badge.proposals = t.proposals.length;
  updateTitle();
  $("#header-stop").hidden = t.kill_switch || t.mode === "off";
  document.querySelectorAll(".seg button").forEach((b) => b.classList.toggle("on", b.dataset.mode === t.mode));
  $("#broker").value = t.broker;
  const kill = $("#kill");
  kill.textContent = t.kill_switch ? "Resume (kill switch on)" : "STOP ALL TRADING";
  kill.classList.toggle("resume", t.kill_switch);
  const s = t.last_summary;
  $("#trader-status").textContent = `Market ${t.market_open ? "open" : "closed"}` +
    (t.last_cycle ? ` · last run ${ago(t.last_cycle)}` : "") + (s?.skipped ? ` · ${s.skipped}` : s?.error ? ` · ${s.error}` : "");
  const rh = t.robinhood;
  $("#rh").innerHTML = t.broker !== "robinhood" ? "Practice account: simulated fills against your paper portfolio. No real money."
    : rh.login_url ? `Sign in to Robinhood to finish connecting: <a href="${esc(safeUrl(rh.login_url))}" target="_blank" rel="noopener">open Robinhood login</a>`
    : rh.connected ? `Robinhood connected (${rh.tools.length} tools). Orders go only to your Agentic account. <button id="rh-disc">Disconnect</button>`
    : `Robinhood not connected. <button id="rh-conn">Connect Robinhood</button>${rh.last_connect?.error ? ` <span class="down">${esc(rh.last_connect.error)}</span>` : ""}${rh.connecting ? " Connecting…" : ""}`;
  $("#rh-conn")?.addEventListener("click", async () => {
    const r = await post("/api/broker/robinhood/connect");
    if (r.login_url) window.open(r.login_url, "_blank", "noopener");
    loadTrader();
  });
  $("#rh-disc")?.addEventListener("click", async () => { await post("/api/broker/robinhood/disconnect"); loadTrader(); });
  $("#proposals").innerHTML = t.proposals.map((p) => `
    <li><b class="${p.side === "buy" ? "up" : "down"}">${p.side.toUpperCase()}</b> ${fmt(p.qty, 0)} <b>${esc(p.ticker)}</b> @ ~$${fmt(p.price)}
      <div class="meta">${esc(p.reasons.join("; "))} · expires ${ago(p.expires).replace(" ago", "")}</div>
      <div class="prop"><button class="buy" data-ok="${p.proposal_id}">Approve</button><button data-no="${p.proposal_id}">Reject</button></div></li>`).join("")
    || `<li class="meta">${t.mode === "approve" ? "Nothing waiting. Ideas appear here during market hours." : "Switch to “Ask me first” to approve each trade."}</li>`;
  document.querySelectorAll("[data-ok]").forEach((b) => b.addEventListener("click", async () => {
    try { const d = await post(`/api/trading/proposals/${b.dataset.ok}/approve`); toast(`${d.side} ${d.ticker}: ${d.status}`); } catch (e) { fail(e); }
    loadTrader(); loadPaper();
  }));
  document.querySelectorAll("[data-no]").forEach((b) => b.addEventListener("click", async () => {
    await post(`/api/trading/proposals/${b.dataset.no}/reject`); loadTrader();
  }));
  $("#journal tbody").innerHTML = t.decisions.map((d) => `<tr>
    <td>${new Date(d.ts).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
    <td><b>${esc(d.ticker)}</b></td><td class="${d.side === "buy" ? "up" : "down"}">${d.side}</td><td>${fmt(d.qty, 0)}</td>
    <td>${d.fill_price ? "$" + fmt(d.fill_price) : d.limit_price ? "lim $" + fmt(d.limit_price) : "$" + fmt(d.price)}</td>
    <td class="st-${esc(d.status)}">${esc(d.status)}</td><td>${esc([...d.reasons, d.detail].filter(Boolean).join(" · "))}</td></tr>`).join("")
    || `<tr><td colspan="7" class="meta">No decisions yet.</td></tr>`;
  const r = t.rules;
  $("#rules").innerHTML = `Buy: score ≥ ${r.entry.min_score}, confidence ≥ ${Math.round(r.entry.min_confidence * 100)}%, ${r.sizing.position_pct}% per position, max ${r.sizing.max_positions}.<br>
    Sell: −${r.exit.stop_loss_pct}% stop, +${r.exit.take_profit_pct}% target, score &lt; ${r.exit.exit_score_below}, or ${r.exit.max_hold_days} days${r.exit.close_at_eod ? ", and everything before the close" : ""}.<br>
    Limits: ${r.risk.daily_loss_limit_pct}% daily loss, ${r.risk.max_trades_per_day} trades/day, $${fmt(r.risk.max_order_usd, 0)}/order,
    ${r.risk.max_day_trades_per_5d < 0 ? "no day-trade cap" : r.risk.max_day_trades_per_5d + " day trades per 5 days"}${r.risk.avoid_wash_sales ? ", wash-sale guard" : ""}. Limit orders only.`;
}

function curveSvg(curve) {
  if (!curve || curve.length < 2) return "";
  const { pts } = linePath(curve, 600, 80);
  return `<div class="chart-wrap" id="curve-wrap"><svg id="curve" viewBox="0 0 600 80" preserveAspectRatio="none" aria-label="Strategy equity curve"><polyline fill="none" stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round" points="${pts}"/></svg></div>`;
}

async function loadSim() {
  const r = await api(`/api/trading/backtest?source=${$("#sim-source").value}`);
  if (!r.total_return_pct && r.total_return_pct !== 0) {
    $("#sim").innerHTML = `<p class="meta">Not enough history yet (${r.days} days).</p>`;
    return;
  }
  $("#sim").innerHTML = `<div class="sim-stats">
      <div><span class="meta">Strategy</span><b class="${cls(r.total_return_pct)}">${r.total_return_pct > 0 ? "+" : ""}${fmt(r.total_return_pct)}%</b></div>
      <div><span class="meta">Holding SPY</span><b>${r.benchmark_return_pct == null ? "—" : (r.benchmark_return_pct > 0 ? "+" : "") + fmt(r.benchmark_return_pct) + "%"}</b></div>
      <div><span class="meta">Worst drop</span><b class="down">${fmt(r.max_drawdown_pct)}%</b></div>
      <div><span class="meta">Trades</span><b>${r.trades}</b></div>
      <div><span class="meta">Winners</span><b>${r.win_rate == null ? "—" : Math.round(r.win_rate * 100) + "%"}</b></div>
      <div><span class="meta">Avg trade</span><b class="${cls(r.avg_trade_pct ?? 0)}">${r.avg_trade_pct == null ? "—" : fmt(r.avg_trade_pct) + "%"}</b></div>
    </div>${curveSvg(r.curve)}
    <p class="note">${esc(r.from)} to ${esc(r.to)}, your current rules, ${r.cost_bps_per_side} bps cost per trade side.
      ${r.beats_benchmark === false ? "<b>Did not beat simply holding SPY.</b>" : r.beats_benchmark ? "Beat holding SPY over this period (one period proves little)." : ""}
      ${r.demo ? " <b>Demo data: meaningless.</b>" : ""}</p>`;
  if ($("#curve")) attachHover($("#curve-wrap"), $("#curve"), r.curve, 600, 80,
    (i) => `${r.dates[i]} · ${money(r.curve[i])} (${r.curve[i] >= r.curve[0] ? "+" : ""}${fmt((r.curve[i] / r.curve[0] - 1) * 100)}%)`);
}

const badge = { alerts: 0, proposals: 0 };
function updateTitle() {
  const n = badge.alerts + badge.proposals;
  document.title = n ? `(${n}) Signal Desk` : "Signal Desk";
}

let lastUpdated = null, refreshing = false, paused = pref.get("paused", false);
function renderUpdated() {
  const el = $("#updated");
  if (paused) { el.textContent = "Auto-refresh paused"; el.classList.add("stale"); return; }
  if (!lastUpdated) { el.textContent = ""; return; }
  const s = Math.round((Date.now() - lastUpdated) / 1000);
  el.textContent = `Updated ${s < 60 ? s + "s" : Math.round(s / 60) + "m"} ago`;
  el.classList.toggle("stale", s > 180);
}

async function refresh() {
  if (refreshing) return;
  refreshing = true;
  const btn = $("#refresh");
  btn.disabled = true;
  btn.classList.add("loading");
  try {
    await Promise.all([loadSignals(), loadSide(), loadPaper(), loadAlerts(), loadTrader(), loadAutopilot()]);
    if (selected) await showDetail(selected, false).catch(closeDetail);  // e.g. a remembered ticker that no longer resolves
    lastUpdated = Date.now();
  } catch (e) { fail(e); }
  finally {
    refreshing = false;
    btn.disabled = false;
    btn.classList.remove("loading");
    renderUpdated();
  }
}

// ---- theme ----
const THEMES = ["system", "light", "dark"];
function applyTheme(t) {
  if (t === "system") document.documentElement.removeAttribute("data-theme");
  else document.documentElement.setAttribute("data-theme", t);
  try { t === "system" ? localStorage.removeItem("theme") : localStorage.setItem("theme", t); } catch { /* ignore */ }
  const btn = $("#theme");
  btn.textContent = { system: "Auto", light: "Light", dark: "Dark" }[t];
  btn.title = `Theme: ${t === "system" ? "follows your device" : t} (t to switch)`;
}
let theme = (() => { try { return localStorage.getItem("theme") || "system"; } catch { return "system"; } })();
applyTheme(theme);
function cycleTheme() {
  theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
  applyTheme(theme);
  toast(`Theme: ${theme}`);
}

// ---- watchlist editor ----
function renderWatchlistEditor() {
  const tickers = sigRows.map((s) => s.ticker).sort();
  $("#wl-editor").innerHTML = tickers.map((t) => `<span class="chip">${esc(t)}<button data-rm="${esc(t)}" aria-label="Remove ${esc(t)}" title="Remove">×</button></span>`).join("")
    + `<form id="wl-add"><input id="wl-input" placeholder="Add ticker" aria-label="Add ticker" maxlength="10"></form>`;
  document.querySelectorAll("[data-rm]").forEach((b) => b.addEventListener("click", () => saveWatchlist(tickers.filter((x) => x !== b.dataset.rm))));
  $("#wl-add").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("#wl-input").value.trim().toUpperCase();
    if (t) saveWatchlist([...tickers, t]);
  });
}
async function saveWatchlist(tickers) {
  try {
    await api("/api/watchlist", { method: "PUT", headers: { "content-type": "application/json" }, body: JSON.stringify({ tickers }) });
    await loadSignals();
    renderWatchlistEditor();
    $("#wl-input")?.focus();
  } catch (e) { fail(e); }
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
  } catch (err) { fail(err); }
});
$("#reset").addEventListener("click", async () => {
  if (!confirm("Reset the paper account? All simulated trades will be deleted.")) return;
  await api("/api/paper/reset", { method: "POST" });
  loadPaper();
});
$("#refresh").addEventListener("click", refresh);
$("#horizon").addEventListener("change", () => loadBacktest().catch(fail));
$("#run-alerts").addEventListener("click", async () => {
  const r = await api("/api/alerts/run", { method: "POST" });
  toast(r.new.length ? `${r.new.length} new alert(s)` : "Scores recorded, no new alerts");
  loadAlerts(); loadBacktest();
});
$("#bell").addEventListener("click", async () => {
  if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  await api("/api/alerts/seen", { method: "POST" });
  loadAlerts();
  $("#alerts-card").scrollIntoView({ behavior: "smooth" });
});
document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", async () => {
  const mode = b.dataset.mode;
  if (mode === "auto" && !confirm(`Turn on fully automatic trading on the ${$("#broker").selectedOptions[0].text}? Orders will be placed without asking you.`)) return;
  try { await post("/api/trading/mode", { mode, broker: $("#broker").value }); } catch (e) { fail(e); }
  loadTrader();
}));
$("#broker").addEventListener("change", async () => {
  try { await post("/api/trading/mode", { mode: "off", broker: $("#broker").value }); toast("Broker changed; autotrader set to Off"); } catch (e) { fail(e); }
  loadTrader();
});
$("#kill").addEventListener("click", async () => {
  if (tstate?.kill_switch) { await post("/api/trading/resume"); toast("Kill switch released. Autotrader is Off until you pick a mode."); }
  else { const r = await post("/api/trading/kill"); toast(r.message); }
  loadTrader();
});
$("#run-trader").addEventListener("click", async () => {
  try {
    const r = await post("/api/trading/run");
    toast(r.skipped || r.error || `${r.actions.length} action(s)`);
  } catch (e) { fail(e); }
  loadTrader(); loadPaper();
});
$("#sim-source").addEventListener("change", () => loadSim().catch(fail));
document.querySelectorAll("#signals thead th").forEach((th, i) => {
  const key = ["ticker", "price", "day", "score", "stance", "news", "social", "momentum", "insiders", "funds", "congress", "conf"][i];
  th.dataset.key = key;
  th.classList.add("sortable");
  th.tabIndex = 0;
  const sort = () => {
    sortAsc = sortKey === key ? !sortAsc : key === "ticker";
    sortKey = key;
    pref.set("sortKey", sortKey); pref.set("sortAsc", sortAsc);
    renderSignals();
  };
  th.addEventListener("click", sort);
  th.addEventListener("keydown", (e) => { if (e.key === "Enter") sort(); });
});
$("#close-detail").addEventListener("click", closeDetail);
$("#ap-toggle").addEventListener("click", async () => {
  try {
    if (apState?.running) {
      await post("/api/autopilot/stop");
      toast("Autopilot stopped. Nothing will be bought or sold until you start it again.");
    } else {
      const live = apState?.broker === "robinhood";
      if (!confirm(live
        ? "Start autopilot on your Robinhood Agentic account? It will buy and sell with real money without asking you, within your strategy.toml limits."
        : "Start autopilot on the practice account? It will trade pretend money automatically.")) return;
      await post("/api/autopilot/start");
      toast("Autopilot running.");
    }
  } catch (e) { fail(e); }
  loadAutopilot(); loadTrader();
});
$("#ap-transfer").addEventListener("submit", async (e) => {
  e.preventDefault();
  const amount = Number($("#ap-amount").value) * Number(e.submitter.dataset.dir);
  try {
    await post("/api/paper/transfer", { amount });
    toast(`${amount > 0 ? "Deposited" : "Withdrew"} ${money(Math.abs(amount))} (practice). Autopilot picks it up on its next run.`);
  } catch (err) { fail(err); }
  loadAutopilot(); loadPaper();
});
$("#theme").addEventListener("click", cycleTheme);
$("#help").addEventListener("click", () => $("#keys").showModal());
$("#header-stop").addEventListener("click", () => $("#kill").click());
$("#search").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("#search-input").value.trim().toUpperCase();
  if (!t) return;
  $("#search-input").value = "";
  $("#search-input").blur();
  showDetail(t).catch(fail);
});
$("#edit-wl").addEventListener("click", () => {
  const ed = $("#wl-editor");
  ed.hidden = !ed.hidden;
  $("#edit-wl").setAttribute("aria-expanded", String(!ed.hidden));
  $("#edit-wl").textContent = ed.hidden ? "Edit watchlist" : "Done";
  if (!ed.hidden) { renderWatchlistEditor(); $("#wl-input").focus(); }
});

function moveSelection(step) {
  const rows = [...document.querySelectorAll("#signals tbody tr[data-t]")];
  if (!rows.length) return;
  const i = rows.findIndex((r) => r.dataset.t === selected);
  const next = rows[Math.max(0, Math.min(rows.length - 1, i < 0 ? 0 : i + step))];
  next.focus();
  showDetail(next.dataset.t, false).catch(fail);
}

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName) || e.target.isContentEditable;
  if (e.key === "Escape") {
    if (typing) e.target.blur();
    else if (!$("#keys").open && selected) closeDetail();
    return;
  }
  if (typing || e.metaKey || e.ctrlKey || e.altKey || $("#keys").open) return;
  const actions = {
    "/": () => $("#search-input").focus(),
    r: refresh,
    t: cycleTheme,
    j: () => moveSelection(1),
    k: () => moveSelection(-1),
    a: () => $("#alerts-card").scrollIntoView({ behavior: "smooth" }),
    g: () => $("#trader").scrollIntoView({ behavior: "smooth" }),
    p: () => { paused = !paused; pref.set("paused", paused); renderUpdated(); toast(paused ? "Auto-refresh paused" : "Auto-refresh on"); if (!paused) refresh(); },
    "?": () => $("#keys").showModal(),
  };
  const fn = actions[e.key];
  if (fn) { e.preventDefault(); fn(); }
});

// Refresh every minute, but not while the tab is hidden; catch up as soon as it's visible again.
setInterval(() => { if (!paused && !document.hidden) refresh(); }, 60_000);
setInterval(renderUpdated, 5_000);
document.addEventListener("visibilitychange", () => {
  if (!document.hidden && !paused && (!lastUpdated || Date.now() - lastUpdated > 60_000)) refresh();
});

refresh();
loadBacktest().catch(fail);
loadSim().catch(fail);
