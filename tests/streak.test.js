import { test } from "node:test";
import assert from "node:assert/strict";
import * as S from "../site/streak.js";

const T0 = Date.UTC(2026, 0, 1);
const D = S.DAY;
const t = (start = T0) => S.newTracker({ name: "Porn", startedAt: start }, T0);

test("milestone ladder is the one asked for, in order", () => {
  assert.deepEqual(S.MILESTONES.slice(0, 9).map((m) => m.days), [1, 3, 7, 14, 30, 60, 90, 180, 365]);
  const days = S.MILESTONES.map((m) => m.days);
  assert.deepEqual(days, [...days].sort((a, b) => a - b));
});

test("parts splits a duration", () => {
  assert.deepEqual(S.parts(3 * D + 4 * 3_600_000 + 5 * 60_000 + 6000), { days: 3, hours: 4, minutes: 5, seconds: 6 });
  assert.deepEqual(S.parts(-5), { days: 0, hours: 0, minutes: 0, seconds: 0 });
});

test("reached and next milestone", () => {
  assert.equal(S.reached(D - 1).length, 0);
  assert.deepEqual(S.reached(3 * D).map((m) => m.days), [1, 3]);
  const n = S.next(5 * D);
  assert.equal(n.milestone.days, 7);
  assert.equal(n.progress, 0.5); // halfway from day 3 to day 7
  assert.equal(n.remainingMs, 2 * D);
  assert.equal(S.next(4000 * D), null); // past every milestone
});

test("celebrations fire once per milestone", () => {
  let tr = t();
  assert.deepEqual(S.uncelebrated(tr, T0 + 3 * D).map((m) => m.days), [1, 3]);
  tr = S.markCelebrated(tr, [1, 3]);
  assert.deepEqual(S.uncelebrated(tr, T0 + 3 * D), []);
  assert.deepEqual(S.uncelebrated(tr, T0 + 7 * D).map((m) => m.days), [7]);
});

test("backdated start doesn't flood celebrations", () => {
  const tr = S.withPastCelebrated(S.newTracker({ name: "x", startedAt: T0 - 40 * D }, T0), T0);
  assert.deepEqual(S.uncelebrated(tr, T0), []);
  assert.deepEqual(S.uncelebrated(tr, T0 + 20 * D).map((m) => m.days), [60]);
});

test("start date can't be in the future", () => {
  assert.equal(S.newTracker({ name: "x", startedAt: T0 + D }, T0).startedAt, T0);
});

test("reset keeps history, best streak and the trophy case", () => {
  let tr = S.markCelebrated(t(), [1, 3, 7]);
  tr = S.reset(tr, T0 + 10 * D, "stressful day");
  assert.equal(tr.startedAt, T0 + 10 * D);
  assert.deepEqual(tr.celebrated, []);
  assert.deepEqual(tr.history, [{ start: T0, end: T0 + 10 * D, note: "stressful day" }]);
  const now = T0 + 12 * D;
  assert.equal(S.streakMs(tr, now), 2 * D);
  assert.equal(S.longestMs(tr, now), 10 * D);
  assert.equal(S.totalMs(tr, now), 12 * D);
  assert.deepEqual(S.bestMilestones(tr, now).map((m) => m.days), [1, 3, 7]);
});

test("backup round-trips and rejects junk", () => {
  const state = { trackers: [S.reset(t(), T0 + 5 * D)], settings: { scripture: false } };
  state.trackers[0].rewards = { 7: "new shoes", 999: "not a milestone" };
  const back = S.parseBackup(S.makeBackup(state, T0));
  assert.equal(back.trackers[0].history.length, 1);
  assert.deepEqual(back.trackers[0].rewards, { 7: "new shoes" });
  assert.equal(back.settings.scripture, false);
  assert.throws(() => S.parseBackup("{}"), /Not a Streaks backup/);
  assert.throws(() => S.parseBackup('{"app":"streaks","trackers":[{"startedAt":"soon"}]}'), /bad date/);
  assert.throws(() => S.parseBackup("not json"));
});

test("friendly duration", () => {
  assert.equal(S.fmtDuration(30 * 60_000), "30 min");
  assert.equal(S.fmtDuration(3_600_000), "1 hour");
  assert.equal(S.fmtDuration(D), "1 day");
  assert.equal(S.fmtDuration(14 * D + 5), "14 days");
});

test("every medal explains itself", () => {
  for (const m of S.MILESTONES) assert.ok(m.about && m.about.length > 20, `${m.name} needs an explanation`);
});

// ---- new features (run with TZ=UTC so times of day are predictable) ----
const H = 3_600_000;

test("urges are counted and logged with a time", () => {
  let tr = t();
  tr = S.logUrge(S.logUrge(tr, T0 + H), T0 + 2 * H);
  assert.equal(tr.urges, 2);
  assert.deepEqual(tr.urgeLog.map((u) => u.at), [T0 + H, T0 + 2 * H]);
});

test("time-of-day buckets wrap past midnight", () => {
  assert.equal(S.bucketOf(T0 + 23 * H).key, "night");
  assert.equal(S.bucketOf(T0 + 2 * H).key, "night");
  assert.equal(S.bucketOf(T0 + 8 * H).key, "morning");
  assert.equal(S.bucketOf(T0 + 14 * H).key, "afternoon");
  assert.equal(S.bucketOf(T0 + 19 * H).key, "evening");
});

test("patterns find when slips happen and what notes say", () => {
  let tr = t(T0);
  // three slips: Sat 23:00, Sat 1 week later 23:30, Wed 14:00 (2026-01-03 is a Saturday)
  tr = S.reset(tr, T0 + 2 * D + 23 * H, "bored and late");
  tr = S.reset(tr, T0 + 9 * D + 23.5 * H, "late night, bored scrolling");
  tr = S.reset(tr, T0 + 13 * D + 14 * H, "stressed");
  const p = S.patterns(tr, T0 + 20 * D);
  assert.equal(p.slips, 3);
  assert.deepEqual(p.slipTime, { label: "late at night", count: 2, of: 3 });
  assert.deepEqual(p.slipDay, { day: "Saturday", count: 2, of: 3 });
  assert.deepEqual(p.triggers.map((x) => x.word).sort(), ["bored", "late"]);
  assert.ok(p.averageStreakMs > 0);
  assert.equal(p.beatingAverage, true); // current 6.4 days vs an average of ~4.6
});

test("patterns stay quiet with too little data", () => {
  const p = S.patterns(S.reset(t(), T0 + D, "x"), T0 + 2 * D);
  assert.equal(p.slipTime, null);
  assert.equal(p.slipDay, null);
  assert.deepEqual(p.triggers, []);
});

test("time and money back", () => {
  const tr = { ...t(), perDayMinutes: 90, perDayMoney: 12 };
  const s = S.saved(tr, T0 + 10 * D);
  assert.equal(s.minutes, 900);
  assert.equal(s.money, 120);
  assert.deepEqual(S.saved(t(), T0 + 10 * D), { minutes: null, money: null });
  assert.equal(S.fmtMinutes(45), "45 min");
  assert.equal(S.fmtMinutes(900), "15 hours");
  assert.equal(S.fmtMinutes(60 * 24 * 5), "5 days");
});

test("check-in streak counts consecutive days", () => {
  const c = { "2026-01-01": {}, "2026-01-02": {}, "2026-01-03": {} };
  assert.equal(S.checkinStreak(c, Date.UTC(2026, 0, 3, 20)), 3);
  assert.equal(S.checkinStreak(c, Date.UTC(2026, 0, 4, 9)), 3); // today not done yet: still 3
  assert.equal(S.checkinStreak(c, Date.UTC(2026, 0, 5, 9)), 0); // missed a day
  assert.equal(S.dayKey(Date.UTC(2026, 0, 3, 20)), "2026-01-03");
});

test("verse of the day is stable for a day and changes the next", () => {
  const list = ["a", "b", "c"];
  assert.equal(S.verseOfDay(list, Date.UTC(2026, 0, 3, 1)), S.verseOfDay(list, Date.UTC(2026, 0, 3, 23)));
  assert.notEqual(S.verseOfDay(list, Date.UTC(2026, 0, 3)), S.verseOfDay(list, Date.UTC(2026, 0, 4)));
});

test("calendar files are valid and discreet", () => {
  const ics = S.icsCheckins({ morning: "08:00", evening: "21:30" }, Date.UTC(2026, 0, 3, 10));
  assert.ok(ics.startsWith("BEGIN:VCALENDAR\r\n") && ics.endsWith("END:VCALENDAR\r\n"));
  assert.match(ics, /DTSTART:20260104T080000/); // 8am already passed today: starts tomorrow
  assert.match(ics, /DTSTART:20260103T213000/);
  assert.equal((ics.match(/RRULE:FREQ=DAILY/g) || []).length, 2);
  assert.equal((ics.match(/BEGIN:VALARM/g) || []).length, 2);
  const m = S.icsMilestones([t()], T0 + 2 * D);
  assert.match(m, /SUMMARY:🏅 Streak medal: Three Days/);
  assert.doesNotMatch(m, /Porn/); // discreet by default
  assert.match(S.icsMilestones([t()], T0, false), /free from Porn/);
  assert.ok(S.icsMilestones([{ ...t(), name: "a, b; c" }], T0, false).includes("a\\, b\\; c")); // escaped
});

test("share text can hide what you're quitting", () => {
  assert.equal(S.shareText(t(), T0 + 5 * D, false), "5 days free from porn. Next up: One Week.");
  assert.equal(S.shareText(t(), T0 + 5 * D, true), "5 days on my streak. Next up: One Week.");
});

test("backup v2 keeps check-ins, partner, plan and savings but never the PIN", () => {
  const tr = { ...S.logUrge(t(), T0 + H), plan: ["walk", "call Mike"], perDayMinutes: 60, perDayMoney: 5 };
  const state = { trackers: [tr], checkins: { "2026-01-02": { committed: true, mood: 3, note: "ok" } },
                  settings: { scripture: true, pinHash: "secret", pinSalt: "x", hideName: true, checkin: true,
                              partner: { name: "Mike", phone: "+1 (555) 010-9999" }, morning: "07:30", evening: "22:00" } };
  const text = S.makeBackup(state, T0);
  assert.doesNotMatch(text, /secret/);
  const back = S.parseBackup(text);
  assert.deepEqual(back.trackers[0].plan, ["walk", "call Mike"]);
  assert.equal(back.trackers[0].urgeLog.length, 1);
  assert.equal(back.trackers[0].perDayMinutes, 60);
  assert.deepEqual(back.checkins["2026-01-02"], { committed: true, mood: 3, note: "ok" });
  assert.deepEqual(back.settings.partner, { name: "Mike", phone: "+15550109999" });
  assert.equal(back.settings.morning, "07:30");
  assert.equal(back.settings.hideName, true);
});
