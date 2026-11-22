import { describe, it, expect } from "vitest";
import cases from "../../tests/fixtures/schedule_contract.json";
import {
  splitBlock,
  removeBlock,
  moveBoundary,
  copyDay,
  snap,
  profilePayload,
  temperatureStep,
} from "./schedule";
import { defaultProfile } from "./format";
import type { Profile } from "./types";
describe("weekly schedule contract shared with the real websocket API", () => {
  it.each(cases)("$name", ({ valid, profile }) => {
    if (valid) expect(profilePayload(profile as Profile)).toEqual(profile);
    else expect(() => profilePayload(profile as Profile)).toThrow();
  });
  it("splits, moves, copies with independent days, and produces the shared save payload", () => {
    let p = structuredClone(cases[0].profile) as Profile;
    p.days.mon = splitBlock(p.days.mon, 721);
    p.days.mon = moveBoundary(p.days.mon, 1, 364);
    p = copyDay(p, "mon", ["sat"]);
    expect(profilePayload(p)).toEqual(cases[1].profile);
    p.days.sat[0].target = 19;
    expect(p.days.mon[0].target).toBe(18);
  });
  it("merges removed blocks into the previous one and fixes the midnight rule", () => {
    const blocks = cases[0].profile.days.mon;
    expect(removeBlock(blocks, 1)).toEqual([blocks[0], blocks[2]]);
    expect(() => removeBlock(blocks, 0)).toThrow("00:00");
    expect(() => moveBoundary(blocks, 0, 20)).toThrow("00:00");
    expect(() => splitBlock(blocks, 0)).toThrow();
    expect(blocks).toHaveLength(3);
  });
  it("snaps to five minutes and clamps moves between neighbours", () => {
    expect([0, 2, 3, 1439, 1440, -1].map(snap)).toEqual([
      0, 0, 5, 1435, 1435, 0,
    ]);
    const blocks = cases[0].profile.days.mon;
    expect(moveBoundary(blocks, 1, -10)[1].start).toBe("00:05");
    expect(moveBoundary(blocks, 1, 1400)[1].start).toBe("21:55");
    expect(moveBoundary(blocks, 2, 1440)[2].start).toBe("23:55");
    expect(() => snap(NaN)).toThrow();
    expect(() => splitBlock(blocks, 360)).toThrow();
  });
  it("bounds keyboard temperatures, strips names and includes IDs only for updates", () => {
    expect(temperatureStep(21, 1)).toBe(21.5);
    expect(temperatureStep(5, -1)).toBe(5);
    expect(temperatureStep(30, 1)).toBe(30);
    expect(profilePayload(defaultProfile("  Profile A  "), "a")).toMatchObject({
      id: "a",
      name: "Profile A",
    });
    expect(profilePayload(defaultProfile())).not.toHaveProperty("id");
    expect(() => profilePayload(defaultProfile(" "))).toThrow();
  });
});
