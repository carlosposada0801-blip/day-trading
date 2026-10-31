import { BOOKS, bookName, chapterCount } from "./books.js";
import { TRANSLATIONS, getChapter } from "./bible.js";
import { InkLayer, bboxOf } from "./ink.js";
import * as db from "./storage.js";

const PAGE_W = 1000;
const BASE_SPACE = 360;   // blank writing area under every chapter
const SPACE_STEP = 600;   // how much "Add writing space" adds

const PEN_COLORS = ["#2b2620", "#1d4f91", "#a3261b", "#2f6b34", "#6a3ea1", "#b8860b"];
const HL_COLORS = ["#ffe14d", "#a6e57f", "#ff9fcf", "#8fd3ff", "#ffbf66", "#c9b3ff"];

const $ = (id) => document.getElementById(id);
const els = {
  book: $("book"), chapter: $("chapter"), prev: $("prev"), next: $("next"),
  translations: $("translations"), tools: $("tools"), swatches: $("swatches"), size: $("size"),
  undo: $("undo"), redo: $("redo"), menuBtn: $("menuBtn"), menu: $("menu"),
  pencilOnly: $("pencilOnly"), addSpace: $("addSpace"), clearPage: $("clearPage"),
  exportBtn: $("exportBtn"), importFile: $("importFile"),
  stage: $("stage"), pageWrap: $("pageWrap"), page: $("page"), title: $("title"), trName: $("trName"),
  text: $("text"), space: $("space"), ink: $("ink"), status: $("status"),
};

// ---- persisted settings -------------------------------------------------------

const settings = Object.assign({
  tr: "NIV", book: 43, chapter: 1, tool: "read", pencilOnly: true,
  pen: { color: PEN_COLORS[0], size: 3 },
  hl: { color: HL_COLORS[0], size: 6 },
  erase: { size: 4 },
}, JSON.parse(localStorage.getItem("margin.settings") || "{}"));
const saveSettings = () => localStorage.setItem("margin.settings", JSON.stringify(settings));

// ---- page state ---------------------------------------------------------------

const ink = new InkLayer(els.ink, PAGE_W);
let pageKey = "";
let extraSpace = 0;
let undoStack = [];
let redoStack = [];
let scale = 1;
let loadToken = 0;

// ---- toolbar setup ------------------------------------------------------------

for (const [i, [name]] of BOOKS.entries()) els.book.add(new Option(name, i + 1));

for (const code of Object.keys(TRANSLATIONS)) {
  const b = document.createElement("button");
  b.textContent = code;
  b.title = TRANSLATIONS[code];
  b.dataset.tr = code;
  b.onclick = () => go(code, settings.book, settings.chapter);
  els.translations.appendChild(b);
}

function fillChapters() {
  els.chapter.innerHTML = "";
  for (let c = 1; c <= chapterCount(settings.book); c++) els.chapter.add(new Option(`Chapter ${c}`, c));
  els.chapter.value = settings.chapter;
}

els.book.onchange = () => go(settings.tr, +els.book.value, 1);
els.chapter.onchange = () => go(settings.tr, settings.book, +els.chapter.value);
els.prev.onclick = () => step(-1);
els.next.onclick = () => step(1);

function step(dir) {
  let { book, chapter } = settings;
  chapter += dir;
  if (chapter < 1) { if (book === 1) return; book--; chapter = chapterCount(book); }
  if (chapter > chapterCount(book)) { if (book === 66) return; book++; chapter = 1; }
  go(settings.tr, book, chapter);
}

els.tools.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-tool]");
  if (b) setTool(b.dataset.tool);
});

function setTool(tool) {
  settings.tool = tool;
  saveSettings();
  for (const b of els.tools.children) b.classList.toggle("on", b.dataset.tool === tool);
  document.body.classList.toggle("drawing", tool !== "read");
  document.body.classList.toggle("erasing", tool === "erase");
  renderSwatches();
}

function renderSwatches() {
  const tool = settings.tool;
  els.swatches.innerHTML = "";
  els.swatches.hidden = !(tool === "pen" || tool === "hl");
  els.size.parentElement.hidden = tool === "read";
  if (tool === "read") return;
  els.size.value = settings[tool].size;
  if (els.swatches.hidden) return;
  for (const color of tool === "pen" ? PEN_COLORS : HL_COLORS) {
    const b = document.createElement("button");
    b.style.background = color;
    b.setAttribute("aria-label", `Color ${color}`);
    b.classList.toggle("on", settings[tool].color === color);
    b.onclick = () => { settings[tool].color = color; saveSettings(); renderSwatches(); };
    els.swatches.appendChild(b);
  }
}

els.size.oninput = () => {
  if (settings.tool === "read") return;
  settings[settings.tool].size = +els.size.value;
  saveSettings();
};

els.pencilOnly.onchange = () => {
  settings.pencilOnly = els.pencilOnly.checked;
  document.body.classList.toggle("anyInput", !settings.pencilOnly);
  saveSettings();
};

els.menuBtn.onclick = (e) => { e.stopPropagation(); els.menu.hidden = !els.menu.hidden; };
document.addEventListener("pointerdown", (e) => {
  if (!els.menu.hidden && !els.menu.contains(e.target) && e.target !== els.menuBtn) els.menu.hidden = true;
});

// ---- loading a chapter --------------------------------------------------------

async function go(tr, book, chapter) {
  Object.assign(settings, { tr, book, chapter });
  saveSettings();
  els.book.value = book;
  fillChapters();
  for (const b of els.translations.children) b.classList.toggle("on", b.dataset.tr === tr);
  els.prev.disabled = book === 1 && chapter === 1;
  els.next.disabled = book === 66 && chapter === chapterCount(66);
  els.title.textContent = `${bookName(book)} ${chapter}`;
  els.trName.textContent = TRANSLATIONS[tr];
  document.title = `${bookName(book)} ${chapter} (${tr}) — Margin`;

  const token = ++loadToken;
  pageKey = `${tr}|${book}|${chapter}`;
  undoStack = []; redoStack = [];
  updateUndo();
  ink.setStrokes([]);
  els.text.innerHTML = `<p class="loading">Loading ${bookName(book)} ${chapter}…</p>`;
  layout();
  window.scrollTo(0, 0);

  const [saved, verses] = await Promise.all([
    db.get("ink", pageKey).catch(() => null),
    getChapter(tr, book, chapter).catch((err) => ({ err })),
  ]);
  if (token !== loadToken) return; // user already moved on

  if (verses.err) {
    els.text.innerHTML = `<div class="error">Couldn't load this chapter${navigator.onLine ? "" : " — you appear to be offline"}.<br>
      <small>${escapeHtml(verses.err.message || "")}</small><br><button id="retry">Try again</button></div>`;
    $("retry").onclick = () => go(tr, book, chapter);
  } else {
    renderVerses(verses, chapter);
  }

  extraSpace = saved?.extra || 0;
  const strokes = (saved?.strokes || []).map((s) => ({ ...s, bbox: bboxOf(s) }));
  layout(strokes);
  ink.setStrokes(strokes);
}

function renderVerses(verses, chapter) {
  const p = document.createElement("p");
  verses.forEach(({ v, t }, i) => {
    const span = document.createElement("span");
    span.className = "v";
    span.dataset.v = v;
    if (i === 0 && v === 1) {
      span.innerHTML = `<span class="ch">${chapter}</span>`;
    } else {
      span.innerHTML = `<sup>${v}</sup>`;
    }
    span.append(t + " ");
    p.appendChild(span);
  });
  els.text.replaceChildren(p);
}

// Sizes the page to its content and scales it to fit the screen.
function layout(strokes = ink.strokes) {
  const avail = els.stage.clientWidth - 24;
  scale = Math.max(0.3, Math.min(1.25, avail / PAGE_W));
  els.page.style.transform = `scale(${scale})`;

  const contentH = els.space.offsetTop;
  let space = BASE_SPACE + extraSpace;
  const lowest = strokes.reduce((m, s) => Math.max(m, s.bbox[3]), 0);
  if (lowest + 120 > contentH + space) space = lowest + 120 - contentH;
  els.space.style.height = space + "px";

  const h = contentH + space;
  els.pageWrap.style.width = PAGE_W * scale + "px";
  els.pageWrap.style.height = h * scale + "px";
  if (ink.height !== h) ink.setHeight(h);
}

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => layout(), 120);
});

// ---- saving -------------------------------------------------------------------

let saveTimer;
function scheduleSave() {
  const key = pageKey;
  const strokes = ink.strokes.map(({ bbox, ...s }) => s);
  const extra = extraSpace;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    const op = strokes.length || extra ? db.put("ink", key, { strokes, extra, updated: Date.now() }) : db.del("ink", key);
    op.catch(() => toast("Couldn't save your notes on this device."));
  }, 400);
}

// ---- drawing with Apple Pencil -----------------------------------------------

let active = null; // { id, stroke | erased[] }

// iPad Safari: stop the Pencil from scrolling the page, so it always draws.
els.ink.addEventListener("touchstart", (e) => {
  if (settings.tool === "read") return;
  const t = e.changedTouches[0];
  if (!settings.pencilOnly || (t && t.touchType === "stylus")) e.preventDefault();
}, { passive: false });
els.ink.addEventListener("touchmove", (e) => {
  if (active) e.preventDefault();
}, { passive: false });

function toPage(e) {
  const r = els.page.getBoundingClientRect();
  const s = r.width / PAGE_W;
  const p = e.pointerType === "pen" ? e.pressure || 0.5 : 0.5;
  return [(e.clientX - r.left) / s, (e.clientY - r.top) / s, p];
}

els.ink.addEventListener("pointerdown", (e) => {
  const tool = settings.tool;
  if (tool === "read" || active) return;
  if (settings.pencilOnly && e.pointerType === "touch") return; // finger: let it scroll
  if (e.pointerType === "mouse" && e.button !== 0) return;
  e.preventDefault();
  els.ink.setPointerCapture(e.pointerId);
  els.menu.hidden = true;

  if (tool === "erase") {
    active = { id: e.pointerId, erased: [] };
    erase(e);
  } else {
    const conf = settings[tool];
    const stroke = {
      id: Math.random().toString(36).slice(2, 10),
      tool,
      color: conf.color,
      w: tool === "hl" ? 8 + conf.size * 3.2 : 0.8 + conf.size * 0.75,
      pts: [],
    };
    active = { id: e.pointerId, stroke };
    ink.begin(stroke);
    ink.extend([toPage(e)]);
  }
});

els.ink.addEventListener("pointermove", (e) => {
  if (!active || e.pointerId !== active.id) return;
  e.preventDefault();
  const events = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
  if (active.erased) { for (const ev of events.length ? events : [e]) erase(ev); return; }
  ink.extend((events.length ? events : [e]).map(toPage));
});

function finish(e) {
  if (!active || e.pointerId !== active.id) return;
  if (active.erased) {
    if (active.erased.length) record({ type: "remove", strokes: active.erased });
  } else {
    const s = ink.end();
    if (s) {
      record({ type: "add", strokes: [s] });
      if (s.bbox[3] > ink.height - 200) layout();
    }
  }
  active = null;
}
els.ink.addEventListener("pointerup", finish);
els.ink.addEventListener("pointercancel", finish);

function erase(e) {
  const [x, y] = toPage(e);
  const r = 4 + settings.erase.size * 3;
  active.erased.push(...ink.eraseAt(x, y, r));
}

// ---- undo / redo --------------------------------------------------------------

function record(action) {
  undoStack.push(action);
  if (undoStack.length > 200) undoStack.shift();
  redoStack = [];
  updateUndo();
  scheduleSave();
}

function apply(action, reverse) {
  const adding = (action.type === "add") !== reverse;
  if (adding) {
    ink.strokes.push(...action.strokes);
  } else {
    const ids = new Set(action.strokes.map((s) => s.id));
    ink.strokes = ink.strokes.filter((s) => !ids.has(s.id));
  }
  for (const s of action.strokes) ink.redrawRegion(s.bbox);
}

els.undo.onclick = () => {
  const a = undoStack.pop();
  if (!a) return;
  apply(a, true); redoStack.push(a); updateUndo(); scheduleSave();
};
els.redo.onclick = () => {
  const a = redoStack.pop();
  if (!a) return;
  apply(a, false); undoStack.push(a); updateUndo(); scheduleSave();
};
function updateUndo() {
  els.undo.disabled = !undoStack.length;
  els.redo.disabled = !redoStack.length;
}

// ---- menu actions -------------------------------------------------------------

els.addSpace.onclick = () => {
  extraSpace += SPACE_STEP;
  layout();
  scheduleSave();
  els.menu.hidden = true;
  toast("Added more writing space at the bottom of the page.");
};

els.clearPage.onclick = () => {
  if (!ink.strokes.length) { els.menu.hidden = true; return; }
  if (!confirm("Erase all of your handwriting on this page? (You can undo this.)")) return;
  record({ type: "remove", strokes: [...ink.strokes] });
  ink.setStrokes([]);
  els.menu.hidden = true;
};

els.exportBtn.onclick = async () => {
  await flushSave();
  const data = { app: "margin-bible", version: 1, exported: new Date().toISOString(), ink: await db.entries("ink") };
  const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `margin-notes-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
  els.menu.hidden = true;
};

els.importFile.onchange = async () => {
  const file = els.importFile.files[0];
  els.importFile.value = "";
  if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.app !== "margin-bible" || !Array.isArray(data.ink)) throw new Error("Not a Margin backup file");
    if (!confirm(`Restore notes for ${data.ink.length} page(s)? Pages in the backup will replace what's on this device.`)) return;
    for (const [key, value] of data.ink) await db.put("ink", key, value);
    els.menu.hidden = true;
    toast(`Restored ${data.ink.length} page(s).`);
    go(settings.tr, settings.book, settings.chapter);
  } catch (err) {
    toast(`Couldn't restore: ${err.message}`);
  }
};

function flushSave() {
  return new Promise((r) => setTimeout(r, 450));
}

// ---- misc ---------------------------------------------------------------------

let toastTimer;
function toast(msg) {
  els.status.textContent = msg;
  els.status.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (els.status.hidden = true), 3500);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key.toLowerCase() === "z") { e.preventDefault(); (e.shiftKey ? els.redo : els.undo).click(); }
  else if (e.key === "ArrowLeft") step(-1);
  else if (e.key === "ArrowRight") step(1);
});

if ("serviceWorker" in navigator && location.protocol !== "file:") {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

// ---- start ----------------------------------------------------------------------

els.pencilOnly.checked = settings.pencilOnly;
document.body.classList.toggle("anyInput", !settings.pencilOnly);
setTool(settings.tool);
go(settings.tr, settings.book, settings.chapter);
