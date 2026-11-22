import { describe, it, expect } from "vitest";
import cases from "../../tests/fixtures/schedule_contract.json";
import {
  splitBlock,
  removeBlock,
  moveBoundary,
  copyDay,
  snap,
  weekPayload,
  schedulePayload,
  temperatureStep,
} from "./schedule";
import { defaultWeek } from "./format";
import type { Week } from "./types";
describe("weekly schedule contract shared with the real websocket API", () => {
  it.each(cases)("$name", ({ valid, week }) => {
    if (valid) expect(weekPayload(week as Week)).toEqual(week);
    else expect(() => weekPayload(week as Week)).toThrow();
  });
  it("splits, moves, copies with independent days, and produces the shared save payload", () => {
    let p = structuredClone(cases[0].week) as Week;
    p.days.mon = splitBlock(p.days.mon, 721);
    p.days.mon = moveBoundary(p.days.mon, 1, 364);
    p = copyDay(p, "mon", ["sat"]);
    expect(weekPayload(p)).toEqual(cases[1].week);
    p.days.sat[0].target = 19;
    expect(p.days.mon[0].target).toBe(18);
  });
  it("merges removed blocks into the previous one and fixes the midnight rule", () => {
    const blocks = cases[0].week.days.mon;
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
    const blocks = cases[0].week.days.mon;
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
    expect(
      schedulePayload(
        { name: "  Winter  ", rooms: { room_a: defaultWeek() } },
        "a",
      ),
    ).toMatchObject({ id: "a", name: "Winter" });
    expect(weekPayload(defaultWeek())).not.toHaveProperty("id");
    expect(() => schedulePayload({ name: " ", rooms: {} })).toThrow();
  });
});

it("seeded per-room editor fuzz keeps 16000 operations valid across independent whole-house plans", () => {
  let seed = 42;
  const random = (n: number) => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed % n;
  };
  for (let plan = 0; plan < 80; plan++) {
    const schedule = {
      name: `Schedule ${plan}`,
      rooms: { room_a: defaultWeek(), room_b: defaultWeek() },
    };
    for (let step = 0; step < 200; step++) {
      const room = random(2) ? "room_a" : "room_b";
      const day = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][random(7)];
      const blocks = schedule.rooms[room].days[day];
      const op = random(5);
      try {
        if (op === 0)
          schedule.rooms[room].days[day] = splitBlock(blocks, random(1440));
        if (op === 1 && blocks.length > 1)
          schedule.rooms[room].days[day] = removeBlock(
            blocks,
            1 + random(blocks.length - 1),
          );
        if (op === 2 && blocks.length > 1)
          schedule.rooms[room].days[day] = moveBoundary(
            blocks,
            1 + random(blocks.length - 1),
            random(1440),
          );
        if (op === 3)
          schedule.rooms[room].days[day] = blocks.map((b, i) =>
            i === random(blocks.length)
              ? { ...b, target: 5 + random(51) * 0.5 }
              : b,
          );
        if (op === 4)
          schedule.rooms[room] = copyDay(schedule.rooms[room], day, [
            ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][random(7)],
          ]);
      } catch (error) {
        expect((error as Error).message).toMatch(/already|00:00/);
      }
      expect(() => schedulePayload(schedule)).not.toThrow();
    }
  }
});
