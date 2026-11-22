/** Shared 24-hour geometry for read-only schedule bars. */
import { minutes, validateDay, weekdays, type Block } from "./schedule";
export function barLayout(blocks: Block[]) {
  validateDay(blocks);
  return blocks.map((block, index) => {
    const start = minutes(block.start);
    const end =
      index + 1 < blocks.length ? minutes(blocks[index + 1].start) : 1440;
    return {
      ...block,
      end,
      left: (start / 1440) * 100,
      width: ((end - start) / 1440) * 100,
    };
  });
}
export function houseClock(now: Date, zone = "UTC") {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(now);
  const part = (key: string) => parts.find((p) => p.type === key)!.value;
  return {
    day: part("weekday").toLowerCase() as (typeof weekdays)[number],
    minute: Number(part("hour")) * 60 + Number(part("minute")),
  };
}
