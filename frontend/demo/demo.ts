import "../src/card";
import { fixture } from "./fixture";
import type { CentralHeatingCard } from "../src/card";
import type { Hass, Message, Room, Profile, Status } from "../src/types";
let status = fixture();
let nextId = 1;
const listeners = new Set<(value: Status) => void>();
function notify() {
  for (const listener of listeners) listener(structuredClone(status));
}
function recalculate() {
  status.global.shadow = status.configuration.shadow;
  status.global.mode = status.configuration.mode;
  for (const [id, room] of Object.entries(status.configuration.rooms)) {
    const override = status.configuration.overrides[id];
    const old = status.rooms[id];
    const mode = status.configuration.mode.value;
    const activeOverride =
      mode === "auto" || mode === "away" ? override : undefined;
    const target =
      mode === "manual"
        ? (old?.target ?? Object.values(old?.trvs ?? {})[0] ?? 18)
        : mode === "summer"
          ? status.configuration.settings.frost_temperature
          : (activeOverride?.target ??
            (mode === "away"
              ? status.configuration.settings.away_temperature
              : 21));
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
      next_change: old?.next_change ?? null,
      next_target: old?.next_target ?? null,
    };
  }
  status.global.demand_count = Object.values(status.rooms).filter(
    (room) => room.demanding,
  ).length;
  status.global.command.heat =
    status.global.demand_count > 0 &&
    status.configuration.mode.value !== "summer";
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
  let savedId: string | undefined;
  if (command === "mode/set") {
    status.configuration.mode = {
      value: message.mode as Status["configuration"]["mode"]["value"],
      until: message.until as string | null,
    };
  } else if (command === "override/set") {
    const room = String(message.room_id);
    status.configuration.overrides[room] = {
      target: Number(message.temperature),
      until:
        message.kind === "next_block"
          ? (status.rooms[room].next_change ??
            new Date(Date.now() + 7 * 86400000).toISOString())
          : new Date(
              Date.now() + Number(message.minutes ?? 120) * 60000,
            ).toISOString(),
      source: "card",
    };
  } else if (command === "override/clear")
    delete status.configuration.overrides[String(message.room_id)];
  else if (command === "room/save") {
    const room = message.room as Room & { id?: string };
    savedId = room.id ?? `room_${nextId++}`;
    const copy = { ...room };
    delete copy.id;
    status.configuration.rooms[savedId] = copy;
  } else if (command === "room/delete") {
    delete status.configuration.rooms[String(message.room_id)];
    delete status.rooms[String(message.room_id)];
    delete status.configuration.overrides[String(message.room_id)];
  } else if (command === "profile/save") {
    const profile = message.profile as Profile & { id?: string };
    savedId = profile.id ?? `profile_${nextId++}`;
    const copy = { ...profile };
    delete copy.id;
    status.configuration.profiles[savedId] = copy;
  } else if (command === "profile/delete")
    delete status.configuration.profiles[String(message.profile_id)];
  else if (command === "settings/save") {
    Object.assign(status.configuration.settings, message.settings ?? {});
    if (message.shadow !== undefined)
      status.configuration.shadow = Boolean(message.shadow);
  } else throw new Error("Unknown demo command");
  recalculate();
  notify();
  return {
    ...structuredClone(status),
    ...(savedId ? { saved_id: savedId } : {}),
  };
}
const hass: Hass = {
  config: { time_zone: "UTC" },
  async callWS<T>(message: Message) {
    return respond(message) as T;
  },
  connection: {
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
const query = new URLSearchParams(location.search);
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
  status = fixture();
  notify();
});
