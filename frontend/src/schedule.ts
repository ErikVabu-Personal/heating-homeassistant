import type { Week } from "./types";
export const weekdays = [
  "mon",
  "tue",
  "wed",
  "thu",
  "fri",
  "sat",
  "sun",
] as const;
export const dayNames = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];
export type Block = Week["days"][string][number];
export function minutes(start: string): number {
  if (!/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(start))
    throw new Error("Start time must be HH:MM.");
  const [h, m] = start.split(":").map(Number);
  return h * 60 + m;
}
export function clock(value: number): string {
  return `${Math.floor(value / 60)
    .toString()
    .padStart(2, "0")}:${(value % 60).toString().padStart(2, "0")}`;
}
export function snap(value: number): number {
  if (!Number.isFinite(value)) throw new Error("Choose a valid time.");
  return Math.max(0, Math.min(1435, Math.round(value / 5) * 5));
}
export function validateDay(blocks: Block[]) {
  if (!blocks.length || blocks[0].start !== "00:00")
    throw new Error("Each day must start at 00:00.");
  let previous = -1;
  for (const block of blocks) {
    const at = minutes(block.start);
    if (at % 5) throw new Error("Times must be on the five-minute grid.");
    if (at <= previous)
      throw new Error("Block starts must be strictly increasing.");
    if (
      !Number.isFinite(block.target) ||
      block.target < 5 ||
      block.target > 30 ||
      !Number.isInteger(block.target * 2)
    )
      throw new Error("Temperature must be 5–30° in 0.5° steps.");
    previous = at;
  }
}
export function weekPayload(week: Week) {
  if (
    Object.keys(week.days).length !== 7 ||
    weekdays.some((day) => !week.days[day])
  )
    throw new Error("A week needs all seven days.");
  for (const day of weekdays) validateDay(week.days[day]);
  return { days: structuredClone(week.days) };
}
export function schedulePayload(
  schedule: import("./types").Schedule,
  id?: string,
) {
  if (!schedule.name.trim() || schedule.name.length > 200)
    throw new Error("Enter a schedule name of 1–200 characters.");
  for (const week of Object.values(schedule.rooms)) weekPayload(week);
  return {
    ...(id ? { id } : {}),
    name: schedule.name.trim(),
    rooms: structuredClone(schedule.rooms),
  };
}
export function splitBlock(blocks: Block[], at: number): Block[] {
  const start = clock(snap(at));
  if (blocks.some((b) => b.start === start))
    throw new Error("A block already starts here.");
  const previous = [...blocks].reverse().find((b) => b.start < start);
  if (!previous) throw new Error("The first block stays at 00:00.");
  return [
    ...blocks.map((b) => ({ ...b })),
    { start, target: previous.target },
  ].sort((a, b) => a.start.localeCompare(b.start));
}
export function removeBlock(blocks: Block[], index: number): Block[] {
  if (index <= 0 || index >= blocks.length)
    throw new Error("The first block stays at 00:00.");
  return blocks.filter((_, i) => i !== index).map((b) => ({ ...b }));
}
export function moveBoundary(
  blocks: Block[],
  index: number,
  at: number,
): Block[] {
  if (index <= 0 || index >= blocks.length)
    throw new Error("The first block stays at 00:00.");
  const min = minutes(blocks[index - 1].start) + 5;
  const max =
    index + 1 < blocks.length ? minutes(blocks[index + 1].start) - 5 : 1435;
  const start = clock(Math.max(min, Math.min(max, snap(at))));
  return blocks.map((b, i) => (i === index ? { ...b, start } : { ...b }));
}
export function copyDay(week: Week, from: string, to: string[]): Week {
  const result = structuredClone(week);
  for (const day of to) {
    if (!weekdays.includes(day as (typeof weekdays)[number]))
      throw new Error("Invalid weekday.");
    result.days[day] = structuredClone(week.days[from]);
  }
  return result;
}
export function temperatureStep(value: number, step: number) {
  return Math.max(5, Math.min(30, Math.round(value * 2 + step) / 2));
}
