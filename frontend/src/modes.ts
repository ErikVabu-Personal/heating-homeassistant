import { temperature } from "./format";
import type { Mode, Settings } from "./types";
export const modeNames: Record<Mode, string> = {
  schedule: "Schedule",
  away: "Away",
  off: "Off",
  manual: "Manual",
};
export function modeExplanation(
  mode: Mode,
  settings: Settings,
  until?: string,
  scheduleName = "Winter",
): string {
  switch (mode) {
    case "schedule":
      return `Rooms follow the ${scheduleName} schedule.`;
    case "away":
      return `All rooms at ${temperature(settings.away_temperature)}${until ? ` (until ${until})` : ""}.`;
    case "off":
      return `Boiler heating off, radiators kept at ${temperature(settings.frost_temperature)}. Hot water unaffected.`;
    case "manual":
      return "Central Heating doesn't touch the radiators; the boiler still follows their demand.";
  }
}
