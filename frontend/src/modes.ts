import { temperature } from "./format";
import type { Mode, Settings } from "./types";
export const modeNames: Record<Mode, string> = {
  auto: "Schedule",
  away: "Away",
  summer: "Heating off",
  manual: "Manual",
};
export function modeExplanation(
  mode: Mode,
  settings: Settings,
  until?: string,
): string {
  switch (mode) {
    case "auto":
      return "Rooms follow their weekly profiles.";
    case "away":
      return `All rooms at ${temperature(settings.away_temperature)}${until ? ` (until ${until})` : ""}.`;
    case "summer":
      return `Boiler heating off, radiators kept at ${temperature(settings.frost_temperature)}. Hot water unaffected.`;
    case "manual":
      return "Central Heating doesn't touch the radiators; the boiler still follows their demand.";
  }
}
