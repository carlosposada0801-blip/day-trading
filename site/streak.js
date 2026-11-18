// Pure streak logic, shared by the app and the tests. No DOM, no storage.

export const DAY = 86_400_000;

// Rewards ladder. Tier sets the medal's look.
export const MILESTONES = [
  { days: 1, name: "First Day", tier: "bronze",
    about: "The first 24 hours are often the hardest. You just proved you can go a full day without it." },
  { days: 3, name: "Three Days", tier: "bronze",
    about: "Cravings tend to be strongest in the first few days. Getting through them is a real win, not a small one." },
  { days: 7, name: "One Week", tier: "bronze",
    about: "A full week: every weekday, a weekend, late nights. You've now faced each kind of day without giving in." },
  { days: 14, name: "Two Weeks", tier: "silver",
    about: "Around here many people notice urges coming less often and fading faster. Keep using what's working." },
  { days: 30, name: "One Month", tier: "silver",
    about: "A whole month. The new routine is starting to feel normal instead of forced. This is a big one." },
  { days: 60, name: "Two Months", tier: "gold",
    about: "A well-known study found new habits took about 66 days on average to feel automatic (anywhere from 18 to 254 days). You're right in that zone." },
  { days: 90, name: "Three Months", tier: "gold",
    about: "Ninety days is a milestone many recovery programs celebrate. Look back at who you were on day one." },
  { days: 180, name: "Six Months", tier: "platinum",
    about: "Half a year. This isn't a streak you're protecting anymore. It's becoming who you are." },
  { days: 365, name: "One Year", tier: "platinum",
    about: "A full year: every season, holiday and hard week faced and won. Very few people get here. You did." },
  { days: 730, name: "Two Years", tier: "diamond",
    about: "Two years free. Your story can now help someone who's on day one." },
  { days: 1095, name: "Three Years", tier: "diamond",
    about: "Three years. The old habit is a chapter you closed, not a fight you're still in." },
  { days: 1825, name: "Five Years", tier: "diamond",
    about: "Five years. Half a decade of choosing the harder, better thing." },
  { days: 3650, name: "Ten Years", tier: "diamond",
    about: "Ten years. A decade. Legendary." },
];

export const PRESETS = [
  { name: "Porn", emoji: "🛡️" },
  { name: "Social media", emoji: "📵" },
  { name: "Alcohol", emoji: "🍺" },
  { name: "Nicotine", emoji: "🚭" },
  { name: "Weed", emoji: "🌿" },
  { name: "Gaming", emoji: "🎮" },
  { name: "Junk food", emoji: "🍔" },
  { name: "Gambling", emoji: "🎲" },
];

export function parts(ms) {
  ms = Math.max(0, ms);
  return {
    days: Math.floor(ms / DAY),
    hours: Math.floor((ms % DAY) / 3_600_000),
    minutes: Math.floor((ms % 3_600_000) / 60_000),
    seconds: Math.floor((ms % 60_000) / 1000),
  };
}

export const streakMs = (t, now) => Math.max(0, now - t.startedAt);

export const reached = (ms) => MILESTONES.filter((m) => ms >= m.days * DAY);

/** The next milestone, and progress toward it from the previous one (0..1). */
export function next(ms) {
  const i = MILESTONES.findIndex((m) => ms < m.days * DAY);
  if (i === -1) return null;
  const from = i === 0 ? 0 : MILESTONES[i - 1].days * DAY;
  const to = MILESTONES[i].days * DAY;
  return { milestone: MILESTONES[i], progress: (ms - from) / (to - from), remainingMs: to - ms };
}

/** Milestones the current streak has reached that haven't been celebrated yet. */
export function uncelebrated(t, now) {
  const seen = new Set(t.celebrated || []);
  return reached(streakMs(t, now)).filter((m) => !seen.has(m.days));
}

export function markCelebrated(t, days) {
  return { ...t, celebrated: [...new Set([...(t.celebrated || []), ...days])] };
}

/** Start over: the finished streak goes into history, a new one starts now. */
export function reset(t, now, note = "") {
  const run = { start: t.startedAt, end: now, note: String(note).slice(0, 500) };
  return { ...t, history: [...(t.history || []), run], startedAt: now, celebrated: [] };
}

export function longestMs(t, now) {
  return Math.max(streakMs(t, now), ...(t.history || []).map((r) => r.end - r.start), 0);
}

export function totalMs(t, now) {
  return streakMs(t, now) + (t.history || []).reduce((s, r) => s + Math.max(0, r.end - r.start), 0);
}

/** Every milestone ever reached on any streak (the trophy case keeps them after a reset). */
export function bestMilestones(t, now) {
  return reached(longestMs(t, now));
}

export function newTracker({ name, emoji = "⭐", startedAt, why = "" }, now = Date.now()) {
  const id = (globalThis.crypto?.randomUUID?.() ?? String(now) + Math.random().toString(16).slice(2));
  return {
    id, name: String(name).trim().slice(0, 40) || "My streak", emoji: String(emoji).slice(0, 8) || "⭐",
    startedAt: Math.min(startedAt ?? now, now), createdAt: now, why: String(why).slice(0, 500),
    rewards: {}, history: [], celebrated: [], urges: 0,
  };
}

/** Milestones the tracker already passed when it was created (a backdated start) are
 *  marked celebrated, so adding "clean for 40 days" doesn't fire five popups at once. */
export function withPastCelebrated(t, now) {
  return markCelebrated(t, reached(streakMs(t, now)).map((m) => m.days));
}

/** Validate a backup file before trusting it. Throws on anything malformed. */
export function parseBackup(text) {
  const data = JSON.parse(text);
  if (!data || data.app !== "streaks" || !Array.isArray(data.trackers)) throw new Error("Not a Streaks backup file");
  const num = (v) => (Number.isFinite(v) ? v : (() => { throw new Error("Backup has a bad date"); })());
  const trackers = data.trackers.map((t) => ({
    id: String(t.id), name: String(t.name ?? "").slice(0, 40), emoji: String(t.emoji ?? "⭐").slice(0, 8),
    startedAt: num(t.startedAt), createdAt: num(t.createdAt ?? t.startedAt), why: String(t.why ?? "").slice(0, 500),
    rewards: Object.fromEntries(Object.entries(t.rewards ?? {}).filter(([k]) => MILESTONES.some((m) => String(m.days) === k))
      .map(([k, v]) => [k, String(v).slice(0, 120)])),
    history: (t.history ?? []).map((r) => ({ start: num(r.start), end: num(r.end), note: String(r.note ?? "").slice(0, 500) })),
    celebrated: (t.celebrated ?? []).filter(Number.isFinite),
    urges: Number.isFinite(t.urges) ? t.urges : 0,
  }));
  return { trackers, settings: { scripture: data.settings?.scripture !== false } };
}

export function makeBackup(state, now = Date.now()) {
  return JSON.stringify({ app: "streaks", version: 1, exportedAt: now, trackers: state.trackers,
                          settings: { scripture: state.settings.scripture } }, null, 2);
}

export function fmtDuration(ms) {
  const p = parts(ms);
  if (p.days >= 1) return `${p.days} day${p.days === 1 ? "" : "s"}`;
  if (p.hours >= 1) return `${p.hours} hour${p.hours === 1 ? "" : "s"}`;
  return `${p.minutes} min`;
}
