import { expect, it } from "vitest";
import { barLayout, houseClock } from "./bars";
it("lays blocks consecutively across exactly one day with no gaps or overlap", () => {
  const bars = barLayout([
    { start: "00:00", target: 18 },
    { start: "06:00", target: 21 },
    { start: "18:00", target: 17 },
  ]);
  expect(bars.map((b) => [b.left, b.width, b.end])).toEqual([
    [0, 25, 360],
    [25, 50, 1080],
    [75, 25, 1440],
  ]);
  expect(bars.reduce((sum, b) => sum + b.width, 0)).toBe(100);
  bars
    .slice(1)
    .forEach((b, i) =>
      expect(b.left).toBeCloseTo(bars[i].left + bars[i].width),
    );
});
it("a single midnight block fills 24 hours", () => {
  expect(barLayout([{ start: "00:00", target: 18 }])).toEqual([
    { start: "00:00", target: 18, end: 1440, left: 0, width: 100 },
  ]);
});
it("five-minute blocks keep their true share at both day edges", () => {
  const bars = barLayout([
    { start: "00:00", target: 18 },
    { start: "00:05", target: 20 },
    { start: "23:55", target: 17 },
  ]);
  expect(bars[0].width).toBeCloseTo(100 / 288);
  expect(bars[2].width).toBeCloseTo(100 / 288);
  expect(bars[2].left + bars[2].width).toBeCloseTo(100);
  expect(bars[0].end).toBe(5);
  expect(bars[2].end).toBe(1440);
});
it("rejects invalid overlapping or missing-midnight input", () => {
  expect(() => barLayout([{ start: "06:00", target: 18 }])).toThrow();
  expect(() =>
    barLayout([
      { start: "00:00", target: 18 },
      { start: "00:00", target: 20 },
    ]),
  ).toThrow();
});
it("uses HA's local day and minute including midnight and DST", () => {
  expect(
    houseClock(new Date("2026-11-22T23:30:00Z"), "Europe/Brussels"),
  ).toEqual({ day: "mon", minute: 30 });
  expect(houseClock(new Date("2026-11-22T00:00:00Z"))).toEqual({
    day: "sun",
    minute: 0,
  });
  expect(
    houseClock(new Date("2026-10-25T00:30:00Z"), "Europe/Brussels"),
  ).toEqual({ day: "sun", minute: 150 });
  expect(
    houseClock(new Date("2026-10-25T01:30:00Z"), "Europe/Brussels"),
  ).toEqual({ day: "sun", minute: 150 });
});
