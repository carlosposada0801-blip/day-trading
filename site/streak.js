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
    rewards: {}, history: [], celebrated: [], urges: 0, urgeLog: [], plan: [],
    perDayMinutes: 0, perDayMoney: 0,
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
    urgeLog: (t.urgeLog ?? []).filter((u) => Number.isFinite(u?.at)).map((u) => ({ at: u.at })),
    plan: (t.plan ?? []).map((x) => String(x).slice(0, 120)).slice(0, 12),
    perDayMinutes: Math.max(0, Number(t.perDayMinutes) || 0),
    perDayMoney: Math.max(0, Number(t.perDayMoney) || 0),
  }));
  const set = data.settings ?? {};
  const time = (v, d) => (/^\d{2}:\d{2}$/.test(v ?? "") ? v : d);
  const checkins = {};
  Object.entries(data.checkins ?? {}).forEach(([k, v]) => {
    if (/^\d{4}-\d{2}-\d{2}$/.test(k) && v && typeof v === "object") {
      checkins[k] = { committed: !!v.committed, mood: Number.isInteger(v.mood) && v.mood >= 0 && v.mood < 5 ? v.mood : null,
                      note: String(v.note ?? "").slice(0, 300) };
    }
  });
  return {
    trackers, checkins,
    settings: {
      scripture: set.scripture !== false, checkin: set.checkin !== false, hideName: set.hideName !== false,
      partner: set.partner ? { name: String(set.partner.name ?? "").slice(0, 40), phone: String(set.partner.phone ?? "").replace(/[^\d+]/g, "").slice(0, 20) } : null,
      morning: time(set.morning, "08:00"), evening: time(set.evening, "21:00"),
    },
  };
}

export function makeBackup(state, now = Date.now()) {
  const { pinHash, pinSalt, onboarded, ...settings } = state.settings; // never export the PIN
  return JSON.stringify({ app: "streaks", version: 2, exportedAt: now, trackers: state.trackers,
                          checkins: state.checkins || {}, settings }, null, 2);
}

export function fmtDuration(ms) {
  const p = parts(ms);
  if (p.days >= 1) return `${p.days} day${p.days === 1 ? "" : "s"}`;
  if (p.hours >= 1) return `${p.hours} hour${p.hours === 1 ? "" : "s"}`;
  return `${p.minutes} min`;
}

// ---------- urges ----------
export function logUrge(t, now) {
  return { ...t, urges: (t.urges || 0) + 1, urgeLog: [...(t.urgeLog || []), { at: now }].slice(-500) };
}

// ---------- patterns ----------
export const BUCKETS = [
  { key: "morning", label: "in the morning", from: 5, to: 12 },
  { key: "afternoon", label: "in the afternoon", from: 12, to: 17 },
  { key: "evening", label: "in the evening", from: 17, to: 22 },
  { key: "night", label: "late at night", from: 22, to: 29 }, // 22:00–04:59
];
export const bucketOf = (ms) => {
  const h = new Date(ms).getHours();
  const hh = h < 5 ? h + 24 : h;
  return BUCKETS.find((b) => hh >= b.from && hh < b.to);
};
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const STOP = new Set("a an and the to of in on at it i me my was is im i'm just so but or for with after got had felt feel really very then because this that be been".split(" "));

function top(counts) {
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
  return entries.length ? { key: entries[0][0], count: entries[0][1] } : null;
}

/** What tends to come before slips and urges. Needs a few events to say anything. */
export function patterns(t, now) {
  const slips = (t.history || []).map((r) => r.end);
  const urges = (t.urgeLog || []).map((u) => u.at);
  const timeOf = (list) => {
    if (list.length < 2) return null;
    const c = {};
    list.forEach((ms) => { const b = bucketOf(ms).key; c[b] = (c[b] || 0) + 1; });
    const tp = top(c);
    return { label: BUCKETS.find((b) => b.key === tp.key).label, count: tp.count, of: list.length };
  };
  let day = null;
  if (slips.length >= 2) {
    const c = {};
    slips.forEach((ms) => { const d = WEEKDAYS[new Date(ms).getDay()]; c[d] = (c[d] || 0) + 1; });
    const tp = top(c);
    if (tp.count >= 2) day = { day: tp.key, count: tp.count, of: slips.length };
  }
  const words = {};
  (t.history || []).forEach((r) => {
    new Set(String(r.note || "").toLowerCase().match(/[a-z']{3,}/g) || []).forEach((w) => {
      if (!STOP.has(w)) words[w] = (words[w] || 0) + 1;
    });
  });
  const triggers = Object.entries(words).filter(([, n]) => n >= 2).sort((a, b) => b[1] - a[1]).slice(0, 4)
    .map(([word, count]) => ({ word, count }));
  const runs = (t.history || []).map((r) => r.end - r.start);
  return {
    slips: slips.length, urges: urges.length,
    slipTime: timeOf(slips), urgeTime: timeOf(urges), slipDay: day, triggers,
    averageStreakMs: runs.length ? runs.reduce((a, b) => a + b, 0) / runs.length : null,
    beatingAverage: runs.length ? streakMs(t, now) > runs.reduce((a, b) => a + b, 0) / runs.length : null,
  };
}

// ---------- time & money back ----------
export function saved(t, now) {
  const days = totalMs(t, now) / DAY;
  return {
    minutes: t.perDayMinutes > 0 ? days * t.perDayMinutes : null,
    money: t.perDayMoney > 0 ? days * t.perDayMoney : null,
  };
}
export function fmtMinutes(min) {
  if (min < 60) return `${Math.round(min)} min`;
  const h = min / 60;
  return h < 48 ? `${Math.round(h)} hours` : `${Math.round(h / 24)} days`;
}

// ---------- daily check-in ----------
export const dayKey = (ms) => {
  const d = new Date(ms);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
/** Consecutive days (ending today, or yesterday if today isn't done yet) with any check-in. */
export function checkinStreak(checkins, now) {
  let n = 0;
  const d = new Date(now);
  d.setHours(12, 0, 0, 0);
  if (!checkins[dayKey(d.getTime())]) d.setDate(d.getDate() - 1);
  while (checkins[dayKey(d.getTime())]) { n++; d.setDate(d.getDate() - 1); }
  return n;
}
export const MOODS = ["😣", "🙁", "😐", "🙂", "😄"];

// ---------- verse of the day ----------
export const verseOfDay = (list, now) => {
  const d = new Date(now);
  const n = Math.floor(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY);
  return list[n % list.length];
};

// ---------- calendar reminders (.ics) ----------
const icsText = (s) => String(s).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/[,;]/g, (c) => "\\" + c);
const icsLocal = (d) => `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, "0")}${String(d.getDate()).padStart(2, "0")}T`
  + `${String(d.getHours()).padStart(2, "0")}${String(d.getMinutes()).padStart(2, "0")}00`;
const icsUtc = (ms) => new Date(ms).toISOString().replace(/[-:]/g, "").replace(/\.\d{3}/, "");

function calendar(events, now) {
  const lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Streaks//EN", "CALSCALE:GREGORIAN"];
  events.forEach((e) => {
    lines.push("BEGIN:VEVENT", `UID:${e.uid}`, `DTSTAMP:${icsUtc(now)}`, `DTSTART:${icsLocal(e.start)}`,
      `DURATION:PT${e.minutes || 5}M`, `SUMMARY:${icsText(e.title)}`, `DESCRIPTION:${icsText(e.body)}`);
    if (e.rrule) lines.push(`RRULE:${e.rrule}`);
    lines.push("BEGIN:VALARM", "ACTION:DISPLAY", `DESCRIPTION:${icsText(e.title)}`, "TRIGGER:PT0M", "END:VALARM", "END:VEVENT");
  });
  lines.push("END:VCALENDAR");
  return lines.join("\r\n") + "\r\n";
}

/** Daily check-in reminders. Titles are deliberately discreet: calendars get seen. */
export function icsCheckins({ morning = "08:00", evening = "21:00" } = {}, now = Date.now()) {
  const at = (hhmm) => {
    const [h, m] = hhmm.split(":").map(Number);
    const d = new Date(now);
    d.setHours(h, m, 0, 0);
    if (d.getTime() <= now) d.setDate(d.getDate() + 1);
    return d;
  };
  return calendar([
    { uid: `streaks-morning@streaks`, start: at(morning), rrule: "FREQ=DAILY", title: "Streaks: morning check-in",
      body: "Open Streaks and commit to today." },
    { uid: `streaks-evening@streaks`, start: at(evening), rrule: "FREQ=DAILY", title: "Streaks: how did today go?",
      body: "Open Streaks and check in for tonight." },
  ], now);
}

/** The day each upcoming medal unlocks, for every streak. */
export function icsMilestones(trackers, now = Date.now(), discreet = true) {
  const events = [];
  trackers.forEach((t) => {
    MILESTONES.filter((m) => t.startedAt + m.days * DAY > now).slice(0, 6).forEach((m) => {
      const start = new Date(t.startedAt + m.days * DAY);
      events.push({ uid: `streaks-${t.id}-${m.days}@streaks`, start, minutes: 15,
        title: discreet ? `🏅 Streak medal: ${m.name}` : `🏅 ${m.name} free from ${t.name}`,
        body: `You reach ${m.name} today. Open Streaks to claim your medal.` });
    });
  });
  return calendar(events, now);
}

// ---------- sharing ----------
export function shareText(t, now, hideName) {
  const p = parts(streakMs(t, now));
  const what = hideName ? "on my streak" : `free from ${t.name.toLowerCase()}`;
  const n = next(streakMs(t, now));
  return `${p.days} ${p.days === 1 ? "day" : "days"} ${what}.${n ? ` Next up: ${n.milestone.name}.` : ""}`;
}
