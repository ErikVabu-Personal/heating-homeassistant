import { it, expect } from "vitest";
import { modeNames, modeExplanation } from "./modes";
import { fixture } from "../demo/fixture";
it("maps internal values to the approved labels and exact explanations with live values", () => {
  const settings = {
    ...fixture().configuration.settings,
    away_temperature: 16.5,
    frost_temperature: 7.5,
  };
  expect(modeNames).toEqual({
    auto: "Schedule",
    away: "Away",
    summer: "Heating off",
    manual: "Manual",
  });
  expect(modeExplanation("auto", settings)).toBe(
    "Rooms follow their weekly profiles.",
  );
  expect(modeExplanation("away", settings)).toBe("All rooms at 16.5°.");
  expect(modeExplanation("away", settings, "18:45")).toBe(
    "All rooms at 16.5° (until 18:45).",
  );
  expect(modeExplanation("summer", settings)).toBe(
    "Boiler heating off, radiators kept at 7.5°. Hot water unaffected.",
  );
  expect(modeExplanation("manual", settings)).toBe(
    "Central Heating doesn't touch the radiators; the boiler still follows their demand.",
  );
});
