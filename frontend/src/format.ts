import type { Locale } from "./types";
export function temperature(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "—"
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}°`;
}
export function time(
  value: string | null | undefined,
  timeZone?: string,
  locale?: Locale,
): string {
  return value
    ? new Intl.DateTimeFormat(locale?.language, {
        hour: "2-digit",
        minute: "2-digit",
        hourCycle:
          locale?.time_format === "24"
            ? "h23"
            : locale?.time_format === "12"
              ? "h12"
              : undefined,
        hour12:
          locale?.time_format === "system"
            ? new Intl.DateTimeFormat(undefined, {
                hour: "numeric",
              }).resolvedOptions().hour12
            : undefined,
        timeZone: locale?.time_zone === "local" ? undefined : timeZone,
      }).format(new Date(value))
    : "—";
}
export function localDateTime(value: string | null, timeZone?: string): string {
  if (!value) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(value))
      .map((part) => [part.type, part.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
export function defaultProfile(name = "Default profile"): {
  name: string;
  days: Record<string, { start: string; target: number }[]>;
} {
  return {
    name,
    days: Object.fromEntries(
      ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => [
        day,
        [{ start: "00:00", target: 18 }],
      ]),
    ),
  };
}

/** Weekly starts are wall-clock values, independent of a date or DST offset. */
export function scheduleTime(value: string, locale?: Locale): string {
  return time(`2000-01-01T${value}:00Z`, "UTC", {
    ...locale,
    language:
      locale?.language ?? new Intl.DateTimeFormat().resolvedOptions().locale,
    time_format: locale?.time_format ?? "language",
    time_zone: "server",
  });
}
export function parseScheduleTime(value: string, locale?: Locale): string {
  const trimmed = value.trim().replace(/^(\d):/, "0$1:");
  // Also accept the explicit 24-hour storage notation when typed or pasted.
  if (/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(trimmed)) return trimmed;
  const normalize = (text: string) =>
    text.toLocaleLowerCase(locale?.language).replace(/\s/g, "");
  for (let minute = 0; minute < 1440; minute += 5) {
    const clock = `${Math.floor(minute / 60)
      .toString()
      .padStart(2, "0")}:${(minute % 60).toString().padStart(2, "0")}`;
    if (normalize(scheduleTime(clock, locale)) === normalize(trimmed))
      return clock;
  }
  throw new Error("Enter a valid time on the five-minute grid.");
}
