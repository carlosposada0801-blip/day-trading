// Fetches chapter text for each translation. Every translation has an ordered
// list of sources; the first one that returns verses wins. Downloaded chapters
// are kept in IndexedDB so anything you've read once works offline.
import * as db from "./storage.js";

export const TRANSLATIONS = {
  NIV: "New International Version",
  NLT: "New Living Translation",
  ASV: "American Standard Version",
};

const bolls = (code) => ({
  url: (b, c) => `https://bolls.life/get-text/${code}/${b}/${c}/`,
  parse: (data) => (Array.isArray(data) ? data : []).map((v) => ({ v: v.verse, t: clean(v.text) })),
});

const getbible = (code) => ({
  url: (b, c) => `https://api.getbible.net/v2/${code}/${b}/${c}.json`,
  parse: (data) => (data && Array.isArray(data.verses) ? data.verses : []).map((v) => ({ v: v.verse, t: clean(v.text) })),
});

const SOURCES = {
  NIV: [bolls("NIV"), bolls("NIV2011")],
  NLT: [bolls("NLT")],
  ASV: [bolls("ASV"), getbible("asv")],
};

// Strip Strong's numbers, footnote markers and any other markup.
function clean(html) {
  const s = String(html || "")
    .replace(/<S>[\s\S]*?<\/S>/gi, "")
    .replace(/<sup>[\s\S]*?<\/sup>/gi, "")
    .replace(/<br\s*\/?>/gi, " ");
  const text = new DOMParser().parseFromString(s, "text/html").body.textContent || "";
  return text.replace(/\s+/g, " ").trim();
}

export async function getChapter(tr, book, chapter) {
  const key = `${tr}|${book}|${chapter}`;
  const cached = await db.get("text", key).catch(() => null);
  if (cached && cached.length) return cached;

  let lastErr;
  for (const src of SOURCES[tr]) {
    try {
      const res = await fetch(src.url(book, chapter));
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const verses = src.parse(await res.json()).filter((v) => v.t);
      if (verses.length) {
        db.put("text", key, verses).catch(() => {});
        return verses;
      }
      lastErr = new Error("No verses returned");
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr || new Error("Could not load chapter");
}
