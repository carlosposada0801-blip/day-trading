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
