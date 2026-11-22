import type { Configuration, Status } from "../src/types";
import { defaultWeek } from "../src/format";
const configuration: Configuration = {
  settings: {
    frost_temperature: 16,
    hysteresis: 0.3,
    away_temperature: 15,
    override_default: "next_block",
    override_minutes: 120,
    sync_rooms_on_knob_change: true,
    retry_seconds: 300,
  },
  mode: { value: "schedule", until: null },
  shadow: true,
  active_schedule_id: "winter",
  schedules: {
    winter: {
      name: "Winter",
      rooms: {
        room_a: {
          days: Object.fromEntries(
            ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day, i) => [
              day,
              [
                { start: "00:00", target: 18 },
                { start: i < 5 ? "06:00" : "08:00", target: 21 },
                { start: "09:00", target: 18.5 },
                { start: "17:00", target: 21 },
                { start: "22:00", target: 18 },
              ],
            ]),
          ),
        },
        room_b: {
          days: Object.fromEntries(
            ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((day) => [
              day,
              [
                { start: "00:00", target: 17 },
                { start: "07:00", target: 20 },
                { start: "22:00", target: 17 },
              ],
            ]),
          ),
        },
      },
    },
    autumn: {
      name: "Autumn",
      rooms: { room_a: defaultWeek(), room_b: defaultWeek() },
    },
    spring: {
      name: "Spring",
      rooms: { room_a: defaultWeek(), room_b: defaultWeek() },
    },
  },
  rooms: {
    room_a: {
      name: "Room A",
      trvs: ["climate.trv_a"],
      area_id: "area_a",
      enabled: true,
    },
    room_b: {
      name: "Room B",
      trvs: ["climate.trv_b"],
      area_id: null,
      enabled: true,
    },
  },
  overrides: {
    room_b: { target: 22, until: "2026-11-22T18:00:00Z", source: "card" },
  },
};
export function fixture(): Status {
  return structuredClone({
    config_entry_id: "demo_entry_a",
    configuration,
    global: {
      demand_count: 1,
      virtual_temp: 19.4,
      virtual_temp_raw: 19.4,
      virtual_setpoint: 21,
      command: { heat: true, room_temperature: 19.4, setpoint: 21 },
      last_sent: "2026-11-22T16:30:00Z",
      shadow: true,
      mode: configuration.mode,
    },
    rooms: {
      room_a: {
        name: "Room A",
        current: 19.4,
        desired: 21,
        trvs: { "climate.trv_a": 21 },
        demanding: true,
        sync_problem: false,
        override_until: null,
        next_change: "2026-11-22T22:00:00Z",
        next_target: 18,
      },
      room_b: {
        name: "Room B",
        current: 21.8,
        desired: 22,
        trvs: { "climate.trv_b": 20 },
        demanding: false,
        sync_problem: true,
        override_until: "2026-11-22T18:00:00Z",
        next_change: "2026-11-22T22:00:00Z",
        next_target: 18,
      },
    },
  });
}
