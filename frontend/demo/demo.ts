import "../src/card";
import { schedulePayload } from "../src/schedule";
import { defaultWeek } from "../src/format";
import { fixture } from "./fixture";
import type { CentralHeatingCard } from "../src/card";
import type { Hass, Message, Room, Schedule, Status } from "../src/types";
const query = new URLSearchParams(location.search);
function demoFixture() {
  const data = fixture();
  if (query.get("rooms") === "9") {
    for (let i = 2; i < 9; i++) {
      const letter = String.fromCharCode(97 + i),
        id = `room_${letter}`;
      data.configuration.rooms[id] = {
        name: `Room ${letter.toUpperCase()}`,
        trvs: [`climate.trv_${letter}`],
        area_id: null,
        enabled: true,
      };
      data.rooms[id] = {
        ...structuredClone(data.rooms.room_a),
        name: `Room ${letter.toUpperCase()}`,
      };
      for (const schedule of Object.values(data.configuration.schedules)) {
        schedule.rooms[id] = structuredClone(
          schedule.rooms[i % 2 ? "room_a" : "room_b"],
        );
        for (const blocks of Object.values(schedule.rooms[id].days))
          for (const block of blocks) block.target += (i % 3) * 0.5;
      }
    }
  }
  return data;
}
let status = demoFixture();
let nextId = 1;
const listeners = new Set<(value: Status) => void>();
const connectionEvents = {
  disconnected: new Set<() => void>(),
  ready: new Set<() => void>(),
};
function notify() {
  for (const listener of listeners) listener(structuredClone(status));
}
const demoNow = new Date("2026-11-22T17:30:00Z");
function roomPlan(value: Status, id: string) {
  const week =
    value.configuration.schedules[value.configuration.active_schedule_id].rooms[
      id
    ];
  const names = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"];
  const today = names[demoNow.getUTCDay()];
  const minute = demoNow.getUTCHours() * 60 + demoNow.getUTCMinutes();
  const target = [...week.days[today]]
    .reverse()
    .find(
      (block) =>
        Number(block.start.slice(0, 2)) * 60 + Number(block.start.slice(3)) <=
        minute,
    )!.target;
  for (let offset = 0; offset <= 7; offset++) {
    const day = new Date(
      Date.UTC(
        demoNow.getUTCFullYear(),
        demoNow.getUTCMonth(),
        demoNow.getUTCDate() + offset,
      ),
    );
    for (const block of week.days[names[day.getUTCDay()]]) {
      const at = new Date(day);
      at.setUTCHours(
        Number(block.start.slice(0, 2)),
        Number(block.start.slice(3)),
      );
      if (at > demoNow && block.target !== target)
        return {
          target,
          next_change: at.toISOString(),
          next_target: block.target,
        };
    }
  }
  return { target, next_change: null, next_target: null };
}
function recalculate() {
  status.global.shadow = status.configuration.shadow;
  status.global.mode = status.configuration.mode;
  for (const [id, room] of Object.entries(status.configuration.rooms)) {
    const override = status.configuration.overrides[id];
    const plan = roomPlan(status, id);
    const old = status.rooms[id];
    const mode = status.configuration.mode.value;
    const activeOverride =
      mode === "schedule" || mode === "away" ? override : undefined;
    const target =
      mode === "manual"
        ? (old?.target ?? Object.values(old?.trvs ?? {})[0] ?? 18)
        : mode === "off"
          ? status.configuration.settings.frost_temperature
          : (activeOverride?.target ??
            (mode === "away"
              ? status.configuration.settings.away_temperature
              : plan.target));
    status.rooms[id] = {
      ...old,
      name: room.name,
      current: old?.current ?? 18,
      desired: mode === "manual" ? null : target,
      target,
      trvs: Object.fromEntries(room.trvs.map((trv) => [trv, target])),
      demanding:
        room.enabled &&
        target - (old?.current ?? 18) >
          status.configuration.settings.hysteresis,
      sync_problem: old?.sync_problem ?? false,
      override_until: activeOverride?.until ?? null,
      next_change: plan.next_change,
      next_target: plan.next_target,
    };
  }
  status.global.demand_count = Object.values(status.rooms).filter(
    (room) => room.demanding,
  ).length;
  status.global.command.heat =
    status.global.demand_count > 0 && status.configuration.mode.value !== "off";
}
function respond(message: Message): unknown {
  const command = message.type.replace("central_heating/", "");
  if (command === "get")
    return message.config_entry_id
      ? structuredClone(status)
      : {
          entries: [
            { entry_id: "demo_entry_a", title: "Demo boiler A" },
            { entry_id: "demo_entry_b", title: "Demo boiler B" },
          ],
        };
  const next = structuredClone(status);
  let savedId: string | undefined;
  if (command === "mode/set") {
    if (message.schedule_id) {
      if (!next.configuration.schedules[String(message.schedule_id)])
        throw new Error("Unknown schedule");
      next.configuration.active_schedule_id = String(message.schedule_id);
    }
    next.configuration.mode = {
      value: message.mode as Status["configuration"]["mode"]["value"],
      until: message.until as string | null,
    };
  } else if (command === "override/set") {
    const id = String(message.room_id);
    next.configuration.overrides[id] = {
      target: Number(message.temperature),
      until:
        message.kind === "next_block"
          ? (next.rooms[id].next_change ??
            new Date(demoNow.getTime() + 7 * 86400000).toISOString())
          : new Date(
              demoNow.getTime() + Number(message.minutes ?? 120) * 60000,
            ).toISOString(),
      source: "card",
      kind: message.kind === "next_block" ? "next_block" : "duration",
    };
  } else if (command === "override/clear")
    delete next.configuration.overrides[String(message.room_id)];
  else if (command === "room/save") {
    const value = message.room as Room & {
      id?: string;
      copy_week_from_room?: string;
    };
    if (
      value.copy_week_from_room &&
      !next.configuration.rooms[value.copy_week_from_room]
    )
      throw new Error("Unknown room");
    savedId = value.id ?? `room_${nextId++}`;
    const copy = { ...value };
    delete copy.id;
    delete copy.copy_week_from_room;
    if (!value.id)
      for (const schedule of Object.values(next.configuration.schedules))
        schedule.rooms[savedId] = value.copy_week_from_room
          ? structuredClone(schedule.rooms[value.copy_week_from_room])
          : defaultWeek();
    next.configuration.rooms[savedId] = copy;
  } else if (command === "room/delete") {
    const id = String(message.room_id);
    delete next.configuration.rooms[id];
    delete next.rooms[id];
    delete next.configuration.overrides[id];
    for (const schedule of Object.values(next.configuration.schedules))
      delete schedule.rooms[id];
  } else if (command === "schedule/save") {
    const value = message.schedule as Schedule & { id?: string };
    schedulePayload(value, value.id);
    if (
      Object.entries(next.configuration.schedules).some(
        ([id, s]) =>
          id !== value.id &&
          s.name.trim().toLowerCase() === value.name.trim().toLowerCase(),
      )
    )
      throw new Error("Schedule names must be unique.");
    savedId = value.id ?? `schedule_${nextId++}`;
    next.configuration.schedules[savedId] = {
      name: value.name,
      rooms: structuredClone(value.rooms),
    };
  } else if (command === "schedule/activate") {
    const id = String(message.schedule_id);
    if (!next.configuration.schedules[id]) throw new Error("Unknown schedule");
    next.configuration.active_schedule_id = id;
  } else if (command === "schedule/delete") {
    const id = String(message.schedule_id);
    if (
      id === next.configuration.active_schedule_id ||
      Object.keys(next.configuration.schedules).length <= 1
    )
      throw new Error("The active or last schedule cannot be deleted.");
    delete next.configuration.schedules[id];
  } else if (command === "settings/save") {
    Object.assign(next.configuration.settings, message.settings ?? {});
    if (message.shadow !== undefined)
      next.configuration.shadow = Boolean(message.shadow);
  } else throw new Error("Unknown demo command");
  for (const [id, override] of Object.entries(next.configuration.overrides)) {
    if (override.kind !== "next_block" || !next.configuration.rooms[id])
      continue;
    const before =
      status.configuration.schedules[status.configuration.active_schedule_id]
        .rooms[id];
    const after =
      next.configuration.schedules[next.configuration.active_schedule_id].rooms[
        id
      ];
    if (
      status.configuration.active_schedule_id !==
        next.configuration.active_schedule_id ||
      JSON.stringify(before) !== JSON.stringify(after)
    )
      override.until =
        roomPlan(next, id).next_change ??
        new Date(demoNow.getTime() + 7 * 86400000).toISOString();
  }
  status = next;
  recalculate();
  notify();
  return {
    ...structuredClone(status),
    ...(savedId ? { saved_id: savedId } : {}),
  };
}
const hass: Hass = {
  config: { time_zone: "UTC" },
  locale: { language: "en-GB", time_format: "24", time_zone: "server" },
  async callWS<T>(message: Message) {
    return respond(message) as T;
  },
  connection: {
    connected: true,
    addEventListener(event, listener) {
      connectionEvents[event].add(listener);
    },
    removeEventListener(event, listener) {
      connectionEvents[event].delete(listener);
    },
    async subscribeMessage<T>(callback: (value: T) => void) {
      const listener = (value: Status) => callback(value as T);
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  },
  states: {
    "climate.trv_a": {
      state: "heat",
      attributes: { friendly_name: "Thermostat A" },
    },
    "climate.trv_b": {
      state: "heat",
      attributes: { friendly_name: "Thermostat B" },
    },
    "climate.trv_c": {
      state: "heat",
      attributes: { friendly_name: "Thermostat C" },
    },
  },
  areas: { area_a: { name: "Area A" }, area_b: { name: "Area B" } },
  user: { is_admin: true },
};
const width = query.get("width") === "390" ? "390px" : "1080px";
document.documentElement.dataset.theme =
  query.get("theme") === "dark" ? "dark" : "light";
document.querySelector<HTMLElement>("#preview")!.style.width = width;
const card = document.querySelector<CentralHeatingCard>(
  "central-heating-card",
)!;
card.setConfig({
  type: "custom:central-heating-card",
  config_entry_id: "demo_entry_a",
});
card.hass = hass;
const selected = query.get("tab");
if (
  selected &&
  ["Overview", "Rooms", "Schedules", "Settings"].includes(selected)
)
  card.tab = selected as typeof card.tab;
document.querySelector<HTMLSelectElement>("#theme")!.value =
  document.documentElement.dataset.theme;
document.querySelector("#theme")!.addEventListener("change", (e) => {
  document.documentElement.dataset.theme = (
    e.target as HTMLSelectElement
  ).value;
});
document.querySelector("#width")!.addEventListener("change", (e) => {
  document.querySelector<HTMLElement>("#preview")!.style.width = (
    e.target as HTMLSelectElement
  ).value;
});
document.querySelector<HTMLSelectElement>("#width")!.value = width;
document.querySelector("#reset")!.addEventListener("click", () => {
  status = demoFixture();
  card.modeDraft = undefined;
  card.modeUntilDraft = undefined;
  card.scheduleDraft = undefined;
  const editor =
    card.shadowRoot?.querySelector<import("../src/schedules").HeatingSchedules>(
      "heating-schedules",
    );
  if (editor) editor.draft = undefined;
  hass.connection.connected = true;
  connectionEvents.ready.forEach((listener) => listener());
  notify();
});

document.querySelector("#simulate-drop")!.addEventListener("click", () => {
  hass.connection.connected = false;
  connectionEvents.disconnected.forEach((listener) => listener());
});
