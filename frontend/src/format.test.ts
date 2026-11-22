import { describe, it, expect } from "vitest";
import { temperature, time, defaultWeek, localDateTime } from "./format";
describe("display and defaults", () => {
  it("formats finite temperatures and unknown values", () => {
    expect(temperature(21.5)).toBe("21.5°");
    expect(temperature(null)).toBe("—");
    expect(temperature(NaN)).toBe("—");
  });
  it("formats times without losing local datetime shape", () => {
    expect(time(null)).toBe("—");
    expect(localDateTime("2026-11-22T10:30:00Z")).toMatch(
      /^2026-11-22T\d\d:\d\d$/,
    );
  });
  it("creates a complete neutral week", () => {
    const week = defaultWeek();
    expect(Object.keys(week.days)).toHaveLength(7);
    expect(week.days.mon).toEqual([{ start: "00:00", target: 18 }]);
    week.days.mon[0].target = 21;
    expect(week.days.tue[0].target).toBe(18);
  });
});

it("uses the HA zone even when browser timezone differs", () => {
  expect(localDateTime("2026-11-22T10:30:00Z", "Europe/Berlin")).toBe(
    "2026-11-22T11:30",
  );
  expect(localDateTime("2026-11-22T10:30:00Z", "America/Los_Angeles")).toBe(
    "2026-11-22T02:30",
  );
});

it("honors HA 24-hour formatting even when its language normally uses 12-hour time", () => {
  expect(
    time("2026-11-22T18:45:00Z", "Europe/Berlin", {
      language: "en-US",
      time_format: "24",
      time_zone: "server",
    }),
  ).toBe("19:45");
});
it("honors HA 12-hour formatting even when its language normally uses 24-hour time", () => {
  expect(
    time("2026-11-22T18:45:00Z", "Europe/Berlin", {
      language: "en-GB",
      time_format: "12",
      time_zone: "server",
    }),
  ).toMatch(/^07:45\s*pm$/i);
});

it("includes an Away end date outside today in HA's zone", async () => {
  const { awayUntilLabel } = await import("./format");
  const locale = { language: "en-GB", time_format: "24" as const };
  const now = new Date("2026-11-22T23:30:00Z");
  expect(awayUntilLabel("2026-11-23T18:00", "Europe/Berlin", locale, now)).toBe(
    "18:00",
  );
  expect(awayUntilLabel("2026-11-24T18:00", "Europe/Berlin", locale, now)).toBe(
    "24 Nov 2026 18:00",
  );
});
