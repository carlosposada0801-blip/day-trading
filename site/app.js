import * as S from "./streak.js";

// ---------- storage (this device only) ----------
const KEY = "streaks.v1";
const load = () => {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const d = JSON.parse(raw);
      return { trackers: d.trackers ?? [], settings: { scripture: true, ...d.settings } };
    }
  } catch { /* storage blocked or corrupt: start fresh */ }
  return { trackers: [], settings: { scripture: true } };
};
let state = load();
function save() {
  try { localStorage.setItem(KEY, JSON.stringify(state)); }
  catch { toast("Couldn't save on this device. Export a backup from Settings."); }
}
navigator.storage?.persist?.().catch(() => {}); // ask the browser not to clear our data

// ---------- helpers ----------
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const now = () => Date.now();
const byId = (id) => state.trackers.find((t) => t.id === id);
const plural = (n, w) => `${n} ${w}${n === 1 ? "" : "s"}`;
const fmtDate = (ms) => new Date(ms).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.remove("show"), 2800);
}

// Scripture encouragement (KJV, public domain). Shown when the setting is on.
const VERSES = [
  ["There hath no temptation taken you but such as is common to man: but God is faithful, who will not suffer you to be tempted above that ye are able; but will with the temptation also make a way to escape, that ye may be able to bear it.", "1 Corinthians 10:13"],
  ["I can do all things through Christ which strengtheneth me.", "Philippians 4:13"],
  ["Blessed is the man that endureth temptation: for when he is tried, he shall receive the crown of life, which the Lord hath promised to them that love him.", "James 1:12"],
  ["For God hath not given us the spirit of fear; but of power, and of love, and of a sound mind.", "2 Timothy 1:7"],
  ["But they that wait upon the LORD shall renew their strength; they shall mount up with wings as eagles; they shall run, and not be weary; and they shall walk, and not faint.", "Isaiah 40:31"],
  ["It is of the LORD's mercies that we are not consumed, because his compassions fail not. They are new every morning: great is thy faithfulness.", "Lamentations 3:22–23"],
  ["And be not conformed to this world: but be ye transformed by the renewing of your mind.", "Romans 12:2"],
  ["Wherewithal shall a young man cleanse his way? by taking heed thereto according to thy word.", "Psalm 119:9"],
];
const COMEBACK = [
  ["For a just man falleth seven times, and riseth up again.", "Proverbs 24:16"],
  ["If we confess our sins, he is faithful and just to forgive us our sins, and to cleanse us from all unrighteousness.", "1 John 1:9"],
  ["It is of the LORD's mercies that we are not consumed, because his compassions fail not. They are new every morning: great is thy faithfulness.", "Lamentations 3:22–23"],
];
const pick = (list) => list[Math.floor(Math.random() * list.length)];
const verseHtml = (list = VERSES) => {
  if (!state.settings.scripture) return "";
  const [text, ref] = pick(list);
  return `<blockquote class="verse">“${esc(text)}”<cite>${esc(ref)} (KJV)</cite></blockquote>`;
};

// ---------- graphics ----------
const TIER = { bronze: ["#f0b27a", "#a8622e"], silver: ["#f3f6f9", "#8f9aa6"], gold: ["#ffe08a", "#c98a12"],
               platinum: ["#d4f6ff", "#3fa9d6"], diamond: ["#e9dcff", "#7a4dff"] };
document.body.insertAdjacentHTML("afterbegin", `<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>
  <linearGradient id="ringGrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b6cff"/><stop offset="1" stop-color="#3fd0ff"/></linearGradient>
  ${Object.entries(TIER).map(([k, [a, b]]) => `<radialGradient id="tier-${k}" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></radialGradient>`).join("")}
  <radialGradient id="tier-locked" cx="35%" cy="30%" r="80%"><stop offset="0" stop-color="#3a3a42"/><stop offset="1" stop-color="#1c1c22"/></radialGradient>
</defs></svg>`);

function medal(m, locked = false, cls = "") {
  const fill = locked ? "url(#tier-locked)" : `url(#tier-${m.tier})`;
  const label = m.days >= 365 ? `${m.days / 365}Y` : String(m.days);
  const ribbon = locked ? "#2a2a31" : m.tier === "bronze" ? "#7a3f1a" : m.tier === "silver" ? "#4b5560" : m.tier === "gold" ? "#8a5a00" : m.tier === "platinum" ? "#1d5f80" : "#4a2aa8";
  return `<svg class="${cls}" viewBox="0 0 64 64" role="img" aria-label="${esc(m.name)} medal${locked ? " (locked)" : ""}">
    <path d="M20 4h10l6 18h-10z" fill="${ribbon}"/><path d="M44 4H34l-6 18h10z" fill="${ribbon}" opacity=".85"/>
    <circle cx="32" cy="38" r="22" fill="${fill}"/>
    <circle cx="32" cy="38" r="17" fill="none" stroke="rgba(255,255,255,.35)" stroke-width="1.5"/>
    ${locked ? `<path d="M27 38v-3a5 5 0 0 1 10 0v3" fill="none" stroke="#6b6b75" stroke-width="2"/><rect x="25" y="38" width="14" height="10" rx="2" fill="#6b6b75"/>`
             : `<text x="32" y="44" text-anchor="middle" font-size="${label.length > 2 ? 14 : 17}" font-weight="800" fill="rgba(0,0,0,.72)" font-family="-apple-system,Segoe UI,sans-serif">${label}</text>`}
  </svg>`;
}

function ring(size, stroke, progress, inner) {
  const r = (size - stroke) / 2, c = 2 * Math.PI * r;
  return `<div class="ring-wrap" style="width:${size}px;height:${size}px">
    <svg class="ring" width="${size}" height="${size}" aria-hidden="true">
      <circle class="track" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"/>
      <circle class="bar" cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke-width="${stroke}"
        stroke-dasharray="${c}" stroke-dashoffset="${c * (1 - Math.min(1, Math.max(0, progress)))}" data-c="${c}"/>
    </svg>
    <div class="ring-label">${inner}</div>
  </div>`;
}

function nextText(ms) {
  const n = S.next(ms);
  if (!n) return "Every medal earned. Legendary.";
  return `${n.milestone.name} in ${S.fmtDuration(n.remainingMs) === "0 min" ? "under a minute" : S.fmtDuration(n.remainingMs)}`;
}

// ---------- home list ----------
function renderList() {
  const list = $("#list");
  if (!state.trackers.length) {
    list.innerHTML = `<div class="empty">
      <h2>Start your first streak</h2>
      <p>Pick what you're quitting. The clock starts now and medals unlock at 1, 3, 7, 14, 30 days and beyond.</p>
      <div class="chips">${S.PRESETS.map((p, i) => `<button class="chip" data-preset="${i}">${p.emoji} ${esc(p.name)}</button>`).join("")}
        <button class="chip" data-preset="-1">＋ Something else</button></div>
    </div>`;
    list.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => {
      const p = S.PRESETS[+b.dataset.preset];
      openEditor(null, p ? { name: p.name, emoji: p.emoji } : {});
    }));
    $("#add").hidden = true;
    return;
  }
  $("#add").hidden = false;
  const t0 = now();
  list.innerHTML = state.trackers.map((t) => {
    const ms = S.streakMs(t, t0), p = S.parts(ms), n = S.next(ms);
    const earned = S.reached(ms);
    return `<button class="card" data-open="${esc(t.id)}" aria-label="${esc(t.name)}: ${plural(p.days, "day")}">
      <div class="card-name"><span class="emoji">${esc(t.emoji)}</span>${esc(t.name)}</div>
      <div class="big num" data-days="${esc(t.id)}">${p.days}<small>${p.days === 1 ? "day" : "days"}</small></div>
      <div class="clock num" data-clock="${esc(t.id)}">${pad(p.hours)}:${pad(p.minutes)}:${pad(p.seconds)}</div>
      ${ring(76, 7, n ? n.progress : 1, `<b class="num" data-pct="${esc(t.id)}">${n ? Math.floor(n.progress * 100) : 100}%</b><span>next</span>`)}
      <div class="card-next"><span data-next="${esc(t.id)}">${esc(nextText(ms))}</span>
        <span class="card-medals">${earned.slice(-4).map((m) => medal(m)).join("")}</span></div>
    </button>`;
  }).join("");
  list.querySelectorAll("[data-open]").forEach((b) => b.addEventListener("click", () => openDetail(b.dataset.open)));
}

// ---------- detail ----------
let detailId = null;
function renderDetail() {
  const t = byId(detailId);
  if (!t) return closeSheet();
  const t0 = now(), ms = S.streakMs(t, t0), p = S.parts(ms), n = S.next(ms);
  const best = S.longestMs(t, t0), bestMs = S.bestMilestones(t, t0).map((m) => m.days);
  const el = $("#detail");
  el.innerHTML = `<div class="sheet-inner">
    <div class="sheet-top"><button class="icon-btn back" data-close aria-label="Back">‹</button>
      <h2 id="detail-title">${esc(t.emoji)} ${esc(t.name)}</h2>
      <button class="icon-btn" id="edit-tracker" aria-label="Edit">✎</button></div>
    <div class="hero">
      ${ring(230, 12, n ? n.progress : 1, `<b class="num" data-days="${esc(t.id)}">${p.days}</b><span>${p.days === 1 ? "day" : "days"} free</span>`)}
      <div class="hero-clock num" data-clock="${esc(t.id)}">${pad(p.hours)}h ${pad(p.minutes)}m ${pad(p.seconds)}s</div>
      <div class="hero-next" data-next="${esc(t.id)}">${esc(nextText(ms))}</div>
      <p class="explain" style="margin:10px 0 0">The ring fills as you get closer to your next medal.</p>
    </div>
    <div class="section row">
      <button class="btn primary" id="urge-btn">I'm struggling</button>
    </div>

    <div class="section"><h3>Why I'm doing this</h3>
      <div class="panel">${t.why ? `<div class="why">${esc(t.why)}</div>` : `<div class="why-empty">Add your reason. You'll see it when it's hard.</div>`}</div></div>

    <div class="section"><h3>Stats</h3><div class="stats">
      <div class="stat"><b class="num">${S.fmtDuration(ms)}</b><span>Current streak</span><em>Since your last reset.</em></div>
      <div class="stat"><b class="num">${S.fmtDuration(best)}</b><span>Best streak</span><em>Your longest run ever. A slip never lowers it.</em></div>
      <div class="stat"><b class="num">${S.fmtDuration(S.totalMs(t, t0))}</b><span>Total time free</span><em>Every streak added together.</em></div>
      <div class="stat"><b class="num">${t.urges || 0}</b><span>Urges beaten</span><em>Times you tapped "I'm struggling" and made it through.</em></div>
    </div></div>

    <div class="section"><h3>Medals</h3>
      <p class="explain">Each medal unlocks when your current streak reaches it. Medals you earned on an earlier streak stay in your case. Tap one to see what it means.</p>
      <div class="trophies">
      ${S.MILESTONES.map((m) => {
        const got = ms >= m.days * S.DAY, everGot = bestMs.includes(m.days), isNext = n && n.milestone.days === m.days;
        const reward = t.rewards?.[m.days];
        const sub = got ? "Earned" : isNext ? `in ${S.fmtDuration(m.days * S.DAY - ms)}` : everGot ? "Earned before" : plural(m.days, "day");
        return `<button class="trophy ${got || everGot ? "" : "locked"} ${isNext ? "current" : ""}" data-medal="${m.days}" data-status="${esc(sub)}">
          ${medal(m, !(got || everGot))}<div class="t-name">${esc(m.name)}</div><div class="t-sub">${esc(sub)}</div>
          ${reward ? `<div class="t-reward">🎁 ${esc(reward)}</div>` : ""}</button>`;
      }).join("")}
    </div></div>

    <div class="section"><h3>History</h3>
      <p class="explain">Every streak you've had. A reset ends the current one here, along with any note you left.</p>
      <div class="panel">
      <ul class="history">
        <li><div><b>Current</b><div class="h-note">since ${fmtDate(t.startedAt)}</div></div><div class="num">${S.fmtDuration(ms)}</div></li>
        ${[...(t.history || [])].reverse().map((r) => `<li><div>${fmtDate(r.start)} → ${fmtDate(r.end)}${r.note ? `<div class="h-note">${esc(r.note)}</div>` : ""}</div>
          <div class="num">${S.fmtDuration(r.end - r.start)}</div></li>`).join("")}
      </ul>
      ${(t.history || []).length ? "" : `<p class="hint">No resets yet. Keep it that way.</p>`}
    </div></div>

    <div class="section" id="reset-area">
      <button class="btn danger" id="reset-open">I slipped: reset to zero</button>
    </div>
  </div>`;
  el.querySelector("[data-close]").addEventListener("click", closeSheet);
  $("#edit-tracker").addEventListener("click", () => openEditor(t.id));
  $("#urge-btn").addEventListener("click", () => openUrge(t.id));
  $("#reset-open").addEventListener("click", () => showResetConfirm(t));
  el.querySelectorAll("[data-medal]").forEach((b) => b.addEventListener("click", () =>
    showMedalInfo(t, S.MILESTONES.find((m) => m.days === +b.dataset.medal), b.dataset.status, b.classList.contains("locked"))));
}

function showMedalInfo(t, m, status, locked) {
  const reward = t.rewards?.[m.days];
  $("#medal-info-card").innerHTML = `${medal(m, locked, "medal")}
    <h2>${esc(m.name)}</h2>
    <div class="status">${esc(plural(m.days, "day"))} · ${esc(locked && status === plural(m.days, "day") ? "Locked" : status)}</div>
    <p class="about">${locked ? "<b>When you get here:</b> " : ""}${esc(m.about)}</p>
    ${reward ? `<div class="reward">🎁 Your reward: <b>${esc(reward)}</b></div>` : `<p class="hint">Tip: set a reward for this medal with ✎ Edit.</p>`}
    <button class="btn" id="medal-info-ok">Close</button>`;
  $("#medal-info").hidden = false;
  $("#medal-info-ok").focus();
  const close = () => { $("#medal-info").hidden = true; };
  $("#medal-info-ok").addEventListener("click", close);
  $("#medal-info").onclick = (e) => { if (e.target.id === "medal-info") close(); };
}

function showResetConfirm(t) {
  $("#reset-area").innerHTML = `<div class="panel">
    <p style="margin:0 0 4px;font-weight:650">A slip isn't the end.</p>
    <p class="hint" style="margin:0 0 12px">Your best streak, your medals and your history all stay. The clock starts again from now.</p>
    ${verseHtml(COMEBACK)}
    <label class="field"><span>What happened? (optional, only you see this)</span>
      <textarea id="reset-note" maxlength="500" placeholder="e.g. late night, bored, stressed"></textarea></label>
    <div class="row" style="margin-top:12px"><button class="btn" id="reset-cancel">Cancel</button>
      <button class="btn danger" id="reset-go">Reset</button></div></div>`;
  $("#reset-note").focus();
  $("#reset-cancel").addEventListener("click", renderDetail);
  $("#reset-go").addEventListener("click", () => {
    const i = state.trackers.findIndex((x) => x.id === t.id);
    state.trackers[i] = S.reset(state.trackers[i], now(), $("#reset-note").value);
    save();
    renderDetail(); renderList();
    toast("Day one. You've got this.");
  });
}

// ---------- editor ----------
const toLocalInput = (ms) => { const d = new Date(ms); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 16); };

function openEditor(id, preset = {}) {
  const t = id ? byId(id) : null;
  const el = $("#editor");
  const startedAt = t ? t.startedAt : now();
  el.innerHTML = `<div class="sheet-inner">
    <div class="sheet-top"><button class="icon-btn back" data-close aria-label="Cancel">‹</button>
      <h2 id="editor-title">${t ? "Edit streak" : "New streak"}</h2><span class="icon-btn"></span></div>
    ${t ? "" : `<div class="chips" style="justify-content:flex-start;margin-top:6px">${S.PRESETS.map((p, i) =>
      `<button class="chip" data-pick="${i}" aria-pressed="${preset.name === p.name}">${p.emoji} ${esc(p.name)}</button>`).join("")}</div>`}
    <div class="name-row">
      <label class="field"><span>Icon</span><input type="text" id="f-emoji" class="emoji-input" maxlength="8" value="${esc(t?.emoji ?? preset.emoji ?? "⭐")}" aria-label="Icon (emoji)"></label>
      <label class="field"><span>What are you quitting?</span><input type="text" id="f-name" maxlength="40" value="${esc(t?.name ?? preset.name ?? "")}" placeholder="e.g. Porn, Instagram, Vaping"></label>
    </div>
    ${t ? `<label class="field"><span>Streak started</span><input type="datetime-local" id="f-start" value="${toLocalInput(startedAt)}" max="${toLocalInput(now())}"></label>
           <p class="hint">Changing this rewrites the current streak only.</p>`
        : `<div class="field"><span style="display:block;font-size:13px;color:var(--muted);margin-bottom:6px">When did you last do it?</span>
           <div class="seg" role="group"><button data-when="now" aria-pressed="true">Just now</button><button data-when="past" aria-pressed="false">Earlier</button></div>
           <input type="datetime-local" id="f-start" value="${toLocalInput(startedAt)}" max="${toLocalInput(now())}" hidden style="margin-top:10px"></div>`}
    <label class="field"><span>Why are you doing this?</span>
      <textarea id="f-why" maxlength="500" placeholder="Who you want to be. What you'll get back. You'll see this when it's hard.">${esc(t?.why ?? "")}</textarea></label>
    <details class="section" ${t && Object.keys(t.rewards || {}).length ? "open" : ""}><summary>🎁 Set rewards for milestones</summary>
      <p class="hint">Promise yourself something. It shows on the medal and when you earn it.</p>
      ${S.MILESTONES.slice(0, 9).map((m) => `<div class="reward-row"><span>${esc(m.name)}</span>
        <input type="text" data-reward="${m.days}" maxlength="120" value="${esc(t?.rewards?.[m.days] ?? "")}" placeholder="e.g. new shoes" aria-label="Reward for ${esc(m.name)}"></div>`).join("")}
    </details>
    <div class="section"><button class="btn primary" id="f-save">${t ? "Save" : "Start streak"}</button></div>
    ${t ? `<div class="section"><button class="btn ghost danger" id="f-delete">Delete this streak</button></div>` : ""}
  </div>`;
  el.querySelector("[data-close]").addEventListener("click", closeSheet);
  el.querySelectorAll("[data-pick]").forEach((b) => b.addEventListener("click", () => {
    const p = S.PRESETS[+b.dataset.pick];
    $("#f-name").value = p.name; $("#f-emoji").value = p.emoji;
    el.querySelectorAll("[data-pick]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  }));
  el.querySelectorAll("[data-when]").forEach((b) => b.addEventListener("click", () => {
    el.querySelectorAll("[data-when]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    $("#f-start").hidden = b.dataset.when === "now";
  }));
  $("#f-save").addEventListener("click", () => {
    const name = $("#f-name").value.trim();
    if (!name) { $("#f-name").focus(); return toast("Give it a name"); }
    const startInput = $("#f-start");
    const useInput = t || !startInput.hidden;
    let start = useInput && startInput.value ? new Date(startInput.value).getTime() : now();
    if (!Number.isFinite(start) || start > now()) start = now();
    const rewards = {};
    el.querySelectorAll("[data-reward]").forEach((i) => { if (i.value.trim()) rewards[i.dataset.reward] = i.value.trim(); });
    if (t) {
      const i = state.trackers.findIndex((x) => x.id === t.id);
      let upd = { ...t, name, emoji: $("#f-emoji").value.trim() || "⭐", why: $("#f-why").value.trim(), rewards };
      if (start !== t.startedAt) upd = S.withPastCelebrated({ ...upd, startedAt: start, celebrated: [] }, now());
      state.trackers[i] = upd;
    } else {
      const tr = S.withPastCelebrated(S.newTracker({ name, emoji: $("#f-emoji").value.trim(), startedAt: start, why: $("#f-why").value.trim() }), now());
      tr.rewards = rewards;
      state.trackers.push(tr);
    }
    save();
    closeSheet();
    renderList();
    if (detailId) renderDetail();
    const days = S.parts(now() - start).days;
    toast(t ? "Saved" : days ? `Saved: ${plural(days, "day")} and counting.` : "Streak started. Day one.");
  });
  $("#f-delete")?.addEventListener("click", () => {
    if (!confirm(`Delete “${t.name}” and all its history? This can't be undone.`)) return;
    state.trackers = state.trackers.filter((x) => x.id !== t.id);
    save();
    detailId = null;
    closeAllSheets();
    renderList();
    toast("Deleted");
  });
  openSheet(el);
  if (!t && !preset.name) setTimeout(() => $("#f-name").focus(), 50);
}

// ---------- urge help ----------
let urgeTimer = null;
function openUrge(id) {
  const t = byId(id);
  const el = $("#urge");
  let left = 90;
  el.innerHTML = `<div class="sheet-inner">
    <div class="sheet-top"><button class="icon-btn back" data-close aria-label="Close">‹</button><h2>Ride it out</h2><span class="icon-btn"></span></div>
    <div class="breathe"><div class="orb" id="orb"></div><div class="phase" id="phase">Breathe in</div></div>
    <div class="urge-timer num" id="urge-left">1:30</div>
    <p class="urge-copy">Urges rise, peak and pass, often within 15–30 minutes. Breathe with the circle: slow breathing, with a longer breath out, calms your body down so the urge loses its grip. You don't have to act on it.</p>
    ${t.why ? `<div class="panel"><div class="hint" style="margin:0 0 6px">Your reason</div><div class="why">${esc(t.why)}</div></div>` : ""}
    ${verseHtml()}
    <div class="urge-actions">
      <button class="btn primary" id="urge-won">I made it through</button>
      <button class="btn ghost" data-close>Close</button>
    </div>
  </div>`;
  el.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", closeSheet));
  $("#urge-won").addEventListener("click", () => {
    const i = state.trackers.findIndex((x) => x.id === id);
    state.trackers[i] = { ...state.trackers[i], urges: (state.trackers[i].urges || 0) + 1 };
    save();
    closeSheet();
    if (detailId) renderDetail();
    toast(`Urge beaten. That's ${plural(state.trackers[i].urges, "win")}.`);
  });
  const orb = $("#orb"), phase = $("#phase");
  let step = 0;
  const cycle = [["in", "Breathe in", 4], ["hold", "Hold", 4], ["out", "Breathe out", 6]];
  const runPhase = () => {
    const [cls, label, secs] = cycle[step % 3];
    orb.className = "orb " + cls;
    phase.textContent = label;
    step++;
    urgeTimer = setTimeout(runPhase, secs * 1000);
  };
  runPhase();
  const tick = setInterval(() => {
    left = Math.max(0, left - 1);
    $("#urge-left") && ($("#urge-left").textContent = left ? `${Math.floor(left / 60)}:${pad(left % 60)}` : "You did it. Breathe normally.");
    if (!left) clearInterval(tick);
  }, 1000);
  el._cleanup = () => { clearTimeout(urgeTimer); clearInterval(tick); };
  openSheet(el);
}

// ---------- settings ----------
function renderSettings() {
  const el = $("#settings");
  const locked = !!state.settings.pinHash;
  el.innerHTML = `<div class="sheet-inner">
    <div class="sheet-top"><button class="icon-btn back" data-close aria-label="Back">‹</button><h2 id="settings-title">Settings</h2><span class="icon-btn"></span></div>
    <div class="section"><div class="panel">
      <div class="setting"><div><b>Scripture encouragement</b><p>A Bible verse when you're struggling, slip, or earn a medal.</p></div>
        <button class="switch" role="switch" id="s-scripture" aria-checked="${state.settings.scripture}" aria-label="Scripture encouragement"></button></div>
      <div class="setting"><div><b>PIN lock</b><p>Ask for a PIN when the app opens or after a minute away.</p></div>
        <button class="switch" role="switch" id="s-pin" aria-checked="${locked}" aria-label="PIN lock"></button></div>
    </div></div>
    <div class="section"><h3>Your data</h3><div class="panel">
      <p class="hint" style="margin:0 0 12px">Everything stays on this device. Nothing is uploaded anywhere. Save a backup now and then so you don't lose your streaks if you clear your browser or switch phones.</p>
      <div class="row"><button class="btn" id="s-export">Save backup</button><button class="btn" id="s-import">Restore backup</button></div>
      <input type="file" id="s-file" accept="application/json,.json" hidden>
      <button class="btn ghost danger" id="s-wipe" style="margin-top:10px">Erase everything</button>
    </div></div>
    <div class="section"><h3>Help</h3><div class="panel">
      <button class="btn" id="s-howto">How Streaks works</button>
      <div class="faq" style="margin-top:8px">
        <details><summary>What counts as a streak?</summary><p>The time since you last did the thing you're quitting. It counts up on its own, every second, even while the app is closed.</p></details>
        <details><summary>What happens if I slip?</summary><p>Open the streak and tap “I slipped: reset to zero”. The clock starts over, but your best streak, every medal you've earned and your history all stay. You can add a private note about what happened to spot patterns later.</p></details>
        <details><summary>How do medals and rewards work?</summary><p>Medals unlock at 1, 3 and 7 days, 2 weeks, 1, 2, 3 and 6 months, then 1, 2, 3, 5 and 10 years. When you reach one, you get a celebration. Set your own reward for any medal (✎ Edit on a streak) and it shows on the medal and in the celebration.</p></details>
        <details><summary>What does “I'm struggling” do?</summary><p>It guides you through 90 seconds of slow breathing and shows your reason for quitting. If you get through the urge, tap “I made it through” and it's counted under Urges beaten.</p></details>
        <details><summary>Will it remind me or notify me?</summary><p>Not while it's closed. It's a website saved to your home screen, so it can't send notifications. Celebrations show up the next time you open it.</p></details>
        <details><summary>Where is my data? Is it private?</summary><p>Only on this phone, in this browser. Nothing is uploaded and there's no account. Turn on the PIN lock to keep others out. Clearing your browser data or deleting the app from your home screen erases it, so save a backup now and then.</p></details>
        <details><summary>How do I move to a new phone?</summary><p>Tap Save backup here, send the file to yourself, then open Streaks on the new phone and tap Restore backup.</p></details>
        <details><summary>Can I fix the start date?</summary><p>Yes. Open the streak, tap ✎ and change “Streak started”. It only changes the current streak.</p></details>
      </div>
    </div></div>
    <p class="hint" style="text-align:center;margin-top:24px">Tip: add this page to your home screen to use it like an app, offline too.</p>
  </div>`;
  el.querySelector("[data-close]").addEventListener("click", closeSheet);
  $("#s-scripture").addEventListener("click", (e) => {
    state.settings.scripture = !state.settings.scripture;
    e.currentTarget.setAttribute("aria-checked", String(state.settings.scripture));
    save();
  });
  $("#s-pin").addEventListener("click", () => {
    if (state.settings.pinHash) {
      delete state.settings.pinHash; delete state.settings.pinSalt;
      save(); renderSettings(); toast("PIN lock off");
    } else {
      setPin();
    }
  });
  $("#s-howto").addEventListener("click", () => showWelcome());
  $("#s-export").addEventListener("click", exportBackup);
  $("#s-import").addEventListener("click", () => $("#s-file").click());
  $("#s-file").addEventListener("change", importBackup);
  $("#s-wipe").addEventListener("click", () => {
    if (!confirm("Erase every streak, medal and setting on this device?")) return;
    if (!confirm("Really erase everything? This can't be undone.")) return;
    wipe();
  });
}
function wipe() {
  state = { trackers: [], settings: { scripture: true } };
  save(); closeAllSheets(); renderList(); toast("Erased");
}

async function exportBackup() {
  const text = S.makeBackup(state);
  const name = `streaks-backup-${new Date().toISOString().slice(0, 10)}.json`;
  const file = new File([text], name, { type: "application/json" });
  if (navigator.canShare?.({ files: [file] })) {
    try { await navigator.share({ files: [file], title: "Streaks backup" }); return; } catch { /* fall through to download */ }
  }
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(file), download: name });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  toast("Backup saved");
}

async function importBackup(e) {
  const f = e.target.files?.[0];
  e.target.value = "";
  if (!f) return;
  try {
    const data = S.parseBackup(await f.text());
    if (!confirm(`Replace what's on this device with the backup (${plural(data.trackers.length, "streak")})?`)) return;
    state = { trackers: data.trackers, settings: { ...state.settings, scripture: data.settings.scripture } };
    save(); closeAllSheets(); renderList(); toast("Backup restored");
  } catch (err) {
    toast(`Couldn't restore: ${err.message}`);
  }
}

// ---------- PIN lock ----------
async function hashPin(pin, salt) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}:${pin}`));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
let pinMode = null; // "unlock" | "set1" | "set2"
let pinBuf = "", pinFirst = "";
function showLock(mode) {
  pinMode = mode; pinBuf = ""; pinFirst = mode === "set2" ? pinFirst : "";
  $("#lock").hidden = false;
  $(".lock-title").textContent = mode === "unlock" ? "Enter PIN" : mode === "set1" ? "Choose a 4-digit PIN" : "Enter it again";
  $("#lock-err").textContent = "";
  drawDots();
  const keys = [1, 2, 3, 4, 5, 6, 7, 8, 9, mode === "unlock" ? "Forgot?" : "Cancel", 0, "⌫"];
  $("#keypad").innerHTML = keys.map((k) => `<button class="${typeof k === "string" && k.length > 1 ? "text" : ""}" data-k="${k}" aria-label="${k === "⌫" ? "Delete" : k}">${k}</button>`).join("");
  $("#keypad").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => pinKey(b.dataset.k)));
}
const drawDots = () => { $("#pin-dots").innerHTML = [0, 1, 2, 3].map((i) => `<i class="${i < pinBuf.length ? "on" : ""}"></i>`).join(""); };
function pinFail(msg) {
  $("#lock-err").textContent = msg;
  const inner = $(".lock-inner"); inner.classList.remove("shake"); void inner.offsetWidth; inner.classList.add("shake");
  navigator.vibrate?.(80);
  pinBuf = ""; drawDots();
}
async function pinKey(k) {
  if (k === "⌫") { pinBuf = pinBuf.slice(0, -1); return drawDots(); }
  if (k === "Cancel") { $("#lock").hidden = true; return; }
  if (k === "Forgot?") {
    if (confirm("Without the PIN the only way in is to erase everything on this device. Erase and start over?")) {
      wipe(); $("#lock").hidden = true;
    }
    return;
  }
  if (pinBuf.length >= 4) return;
  pinBuf += k; drawDots();
  if (pinBuf.length < 4) return;
  if (pinMode === "unlock") {
    if (await hashPin(pinBuf, state.settings.pinSalt) === state.settings.pinHash) { $("#lock").hidden = true; lastHidden = null; }
    else pinFail("Wrong PIN");
  } else if (pinMode === "set1") {
    pinFirst = pinBuf; showLock("set2");
  } else {
    if (pinBuf !== pinFirst) { showLock("set1"); return pinFail("Didn't match. Try again."); }
    const salt = crypto.getRandomValues(new Uint32Array(2)).join("-");
    state.settings.pinSalt = salt;
    state.settings.pinHash = await hashPin(pinBuf, salt);
    save(); $("#lock").hidden = true; renderSettings(); toast("PIN lock on");
  }
}
function setPin() {
  if (!crypto.subtle) return toast("PIN lock needs the app opened over https");
  showLock("set1");
}
let lastHidden = null;
document.addEventListener("visibilitychange", () => {
  if (document.hidden) lastHidden = now();
  else if (state.settings.pinHash && lastHidden && now() - lastHidden > 60_000) showLock("unlock");
});

// ---------- celebration ----------
const queue = [];
let celebrating = false;
function checkMilestones() {
  const t0 = now();
  state.trackers.forEach((t, i) => {
    const fresh = S.uncelebrated(t, t0);
    if (!fresh.length) return;
    state.trackers[i] = S.markCelebrated(t, fresh.map((m) => m.days));
    queue.push({ t, m: fresh[fresh.length - 1] }); // celebrate the biggest one reached
    save();
  });
  if (!celebrating && queue.length && $("#lock").hidden) celebrate(queue.shift());
}
function celebrate({ t, m }) {
  celebrating = true;
  const reward = t.rewards?.[m.days];
  const n = S.MILESTONES.find((x) => x.days > m.days);
  $("#celebrate-card").innerHTML = `${medal(m, false, "medal")}
    <h2>${esc(m.name)}!</h2>
    <p>${esc(t.emoji)} ${esc(t.name)}: ${plural(m.days, "day")} free.</p>
    <p style="color:var(--text);margin:12px 0">${esc(m.about)}</p>
    ${reward ? `<div class="reward">🎁 You promised yourself: <b>${esc(reward)}</b>. Go get it.</div>` : ""}
    ${verseHtml()}
    ${n ? `<p class="hint">Next medal: ${esc(n.name)}</p>` : ""}
    <button class="btn primary" id="celebrate-ok">Keep going</button>`;
  $("#celebrate").hidden = false;
  navigator.vibrate?.([60, 40, 120]);
  confetti();
  $("#celebrate-ok").focus();
  $("#celebrate-ok").addEventListener("click", () => {
    $("#celebrate").hidden = true;
    celebrating = false;
    renderList(); if (detailId) renderDetail();
    if (queue.length) setTimeout(() => celebrate(queue.shift()), 250);
  });
}
function confetti() {
  if (reduceMotion) return;
  const c = $("#confetti"), ctx = c.getContext("2d");
  const W = (c.width = innerWidth * devicePixelRatio), H = (c.height = innerHeight * devicePixelRatio);
  const colors = ["#8b6cff", "#3fd0ff", "#f4c14f", "#ffffff", "#3ddc97", "#ff7ab6"];
  const bits = Array.from({ length: 160 }, () => ({
    x: W / 2, y: H * 0.42, vx: (Math.random() - 0.5) * 22 * devicePixelRatio, vy: (-Math.random() * 18 - 6) * devicePixelRatio,
    s: (4 + Math.random() * 6) * devicePixelRatio, r: Math.random() * 6, vr: (Math.random() - 0.5) * 0.3, col: colors[(Math.random() * colors.length) | 0],
  }));
  const end = performance.now() + 2800;
  const frame = (ts) => {
    ctx.clearRect(0, 0, W, H);
    bits.forEach((b) => {
      b.vy += 0.5 * devicePixelRatio; b.vx *= 0.99; b.x += b.vx; b.y += b.vy; b.r += b.vr;
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.r); ctx.fillStyle = b.col; ctx.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2); ctx.restore();
    });
    if (ts < end) requestAnimationFrame(frame); else ctx.clearRect(0, 0, W, H);
  };
  requestAnimationFrame(frame);
}

// ---------- welcome walkthrough ----------
function showWelcome() {
  const slides = [
    { art: ring(120, 10, 0.62, `<b class="num" style="font-size:30px">12</b><span>days</span>`),
      title: "Count your free days",
      body: `<p>Add what you're quitting: porn, social media, anything. A clock counts every day, hour and second since the last time.</p>
             <p>Started a while ago? You can set an earlier start date.</p>` },
    { art: S.MILESTONES.filter((m) => [1, 7, 30, 90, 365].includes(m.days)).map((m) => medal(m)).join(""),
      title: "Earn medals",
      body: `<p>Medals unlock at 1, 3 and 7 days, 2 weeks, 1, 2, 3 and 6 months, and on up to 10 years. Each one comes with a celebration and a note on why it matters.</p>
             <p>Promise yourself a reward for any medal and it shows up when you earn it.</p>` },
    { art: `<div class="breathe" style="width:120px;height:120px;margin:0"><div class="orb in"></div></div>`,
      title: "When it gets hard",
      body: `<ul><li><b>I'm struggling:</b> a 90-second breathing guide, your reason for quitting${state.settings.scripture ? " and a Bible verse" : ""}. Urges pass.</li>
             <li><b>If you slip:</b> reset and start again. Your best streak, medals and history all stay. A slip isn't the end.</li></ul>` },
    { art: `<svg viewBox="0 0 64 64" aria-hidden="true"><rect x="14" y="28" width="36" height="28" rx="6" fill="#8b6cff"/><path d="M22 28v-8a10 10 0 0 1 20 0v8" fill="none" stroke="#3fd0ff" stroke-width="5"/></svg>`,
      title: "Private to you",
      body: `<ul><li>Everything stays <b>on this phone</b>. No account, nothing uploaded.</li>
             <li>Add a <b>PIN lock</b> in Settings to keep others out.</li>
             <li>Save a <b>backup</b> now and then so you never lose your streaks.</li>
             <li>Add Streaks to your <b>home screen</b> to use it like an app.</li></ul>` },
  ];
  let i = 0;
  const el = $("#welcome");
  const draw = () => {
    const sl = slides[i], last = i === slides.length - 1;
    el.innerHTML = `<div class="welcome-inner">
      <button class="welcome-skip" id="w-skip">${last ? "" : "Skip"}</button>
      <div class="slide" aria-live="polite"><div class="art">${sl.art}</div><h2>${sl.title}</h2>${sl.body}</div>
      <div class="dots" aria-hidden="true">${slides.map((_, k) => `<i class="${k === i ? "on" : ""}"></i>`).join("")}</div>
      <div class="row">${i ? `<button class="btn" id="w-back">Back</button>` : ""}
        <button class="btn primary" id="w-next">${last ? "Let's go" : "Next"}</button></div>
    </div>`;
    $("#w-next").addEventListener("click", () => (last ? done() : (i++, draw())));
    $("#w-back")?.addEventListener("click", () => { i--; draw(); });
    $("#w-skip").addEventListener("click", done);
    $("#w-next").focus();
  };
  const done = () => { el.hidden = true; state.settings.onboarded = true; save(); };
  el.hidden = false;
  draw();
}

// ---------- sheets & back button ----------
const stack = [];
function openSheet(el) {
  if (!stack.includes(el)) { stack.push(el); history.pushState({ sheet: el.id }, ""); }
  el.hidden = false;
  el.scrollTop = 0;
}
function hideTop() {
  const el = stack.pop();
  if (!el) return;
  el._cleanup?.(); el._cleanup = null;
  el.hidden = true;
  if (el.id === "detail") detailId = null;
}
let ignorePops = 0;
function closeSheet() { if (stack.length) history.back(); }
function closeAllSheets() {
  const n = stack.length;
  if (!n) return;
  while (stack.length) hideTop();
  ignorePops++; // one popstate arrives for the jump below; the sheets are already hidden
  history.go(-n);
}
addEventListener("popstate", () => {
  if (ignorePops) { ignorePops--; return; }
  hideTop();
});
addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!$("#medal-info").hidden) { $("#medal-info").hidden = true; return; }
  if (stack.length && $("#celebrate").hidden) closeSheet();
});

function openDetail(id) { detailId = id; renderDetail(); openSheet($("#detail")); }
$("#add").addEventListener("click", () => openEditor(null));
$("#open-settings").addEventListener("click", () => { renderSettings(); openSheet($("#settings")); });

// ---------- live clock ----------
function tick() {
  const t0 = now();
  state.trackers.forEach((t) => {
    const ms = S.streakMs(t, t0), p = S.parts(ms), n = S.next(ms);
    document.querySelectorAll(`[data-clock="${CSS.escape(t.id)}"]`).forEach((el) => {
      el.textContent = el.closest(".hero") ? `${pad(p.hours)}h ${pad(p.minutes)}m ${pad(p.seconds)}s` : `${pad(p.hours)}:${pad(p.minutes)}:${pad(p.seconds)}`;
    });
    document.querySelectorAll(`[data-days="${CSS.escape(t.id)}"]`).forEach((el) => {
      if (el.firstChild && el.firstChild.nodeType === 3 && el.firstChild.nodeValue !== String(p.days)) el.firstChild.nodeValue = String(p.days);
    });
    document.querySelectorAll(`[data-next="${CSS.escape(t.id)}"]`).forEach((el) => { el.textContent = nextText(ms); });
    document.querySelectorAll(`[data-pct="${CSS.escape(t.id)}"]`).forEach((el) => { el.textContent = `${n ? Math.floor(n.progress * 100) : 100}%`; });
  });
  document.querySelectorAll(".ring .bar").forEach((bar) => {
    const wrap = bar.closest(".card, .hero");
    const id = wrap?.querySelector("[data-days]")?.dataset.days;
    const t = id && byId(id);
    if (!t) return;
    const n = S.next(S.streakMs(t, t0));
    bar.setAttribute("stroke-dashoffset", String(+bar.dataset.c * (1 - (n ? n.progress : 1))));
  });
  checkMilestones();
}

// ---------- start ----------
renderList();
if (!state.settings.onboarded && !state.trackers.length) showWelcome();
if (state.settings.pinHash) showLock("unlock");
tick();
setInterval(tick, 1000);
if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
