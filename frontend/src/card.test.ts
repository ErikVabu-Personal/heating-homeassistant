// @vitest-environment jsdom
import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { modeNames } from "./modes";
import { CentralHeatingCard } from "./card";
import { fixture } from "../demo/fixture";
import type { Hass, Message, Status, SubscriptionEvent } from "./types";
const cards: CentralHeatingCard[] = [];
async function settle(card: CentralHeatingCard) {
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await card.updateComplete;
}
function mocked() {
  const unsubscribe = vi.fn();
  let subscriptionCallback: ((event: SubscriptionEvent) => void) | undefined;
  const subscribeMessage = vi.fn(
    async (callback: (event: SubscriptionEvent) => void) => {
      subscriptionCallback = callback;
      return unsubscribe;
    },
  );
  const events = new EventTarget();
  const addEventListener = vi.fn((event: string, listener: EventListener) =>
    events.addEventListener(event, listener),
  );
  const removeEventListener = vi.fn((event: string, listener: EventListener) =>
    events.removeEventListener(event, listener),
  );
  const callWS = vi.fn(async (message: Message) => {
    if (!message.config_entry_id)
      return {
        entries: [
          { entry_id: "entry_a", title: "Boiler A" },
          { entry_id: "entry_b", title: "Boiler B" },
        ],
      };
    return { ...fixture(), config_entry_id: String(message.config_entry_id) };
  });
  const hass = {
    callWS,
    connection: {
      subscribeMessage,
      connected: true,
      addEventListener,
      removeEventListener,
    },
    states: {
      "climate.trv_c": {
        state: "heat",
        attributes: { friendly_name: "Thermostat C" },
      },
      "climate.boiler_a_room_a": {
        state: "heat",
        attributes: { friendly_name: "Virtual room A" },
      },
      "sensor.unrelated": { state: "on", attributes: {} },
    },
    user: { is_admin: true },
    config: { time_zone: "UTC" },
  } as unknown as Hass;
  return {
    hass,
    callWS,
    subscribeMessage,
    unsubscribe,
    events,
    addEventListener,
    removeEventListener,
    emit: (event: SubscriptionEvent) => subscriptionCallback?.(event),
  };
}
async function mount(hass: Hass) {
  const card = new CentralHeatingCard();
  cards.push(card);
  card.setConfig({
    type: "custom:central-heating-card",
    config_entry_id: "entry_a",
  });
  document.body.append(card);
  card.hass = hass;
  await settle(card);
  return card;
}
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.open = true;
    }),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: vi.fn(function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event("close"));
    }),
  });
});
afterEach(() => {
  for (const card of cards) card.remove();
  cards.length = 0;
  vi.useRealTimers();
  vi.restoreAllMocks();
});
describe("card lifecycle and safety", () => {
  it("unsubscribes on disconnect and reconnects when the HA connection changes", async () => {
    const a = mocked(),
      b = mocked();
    const card = await mount(a.hass);
    expect(a.subscribeMessage).toHaveBeenCalledTimes(1);
    card.hass = b.hass;
    await settle(card);
    expect(a.unsubscribe).toHaveBeenCalledTimes(1);
    expect(b.subscribeMessage).toHaveBeenCalledTimes(1);
    card.remove();
    expect(b.unsubscribe).toHaveBeenCalledTimes(1);
  });
  it("ignores writes completed after selecting another config entry", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    let finish!: (value: Status) => void;
    const pending = new Promise<Status>((resolve) => {
      finish = resolve;
    });
    fake.callWS.mockImplementationOnce(() => pending);
    card
      .shadowRoot!.querySelector("form")!
      .dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    await settle(card);
    expect(card.busy).toBe(true);
    card.setConfig({
      type: "custom:central-heating-card",
      config_entry_id: "entry_b",
    });
    await settle(card);
    expect(card.status!.config_entry_id).toBe("entry_b");
    finish({ ...fixture(), config_entry_id: "entry_a" });
    await settle(card);
    expect(card.status!.config_entry_id).toBe("entry_b");
    expect(card.busy).toBe(false);
    expect(card.notice).toBe("");
  });
  it("excludes registry room climates and used TRVs from the picker", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.status = {
      ...fixture(),
      room_entity_ids: ["climate.boiler_a_room_a"],
    };
    card.tab = "Rooms";
    await settle(card);
    const add = Array.from(card.shadowRoot!.querySelectorAll("button")).find(
      (b) => b.textContent?.includes("Add room"),
    )!;
    add.click();
    await settle(card);
    const pickers = Array.from(
      card.shadowRoot!.querySelectorAll<HTMLInputElement>("input[name=trvs]"),
    ).map((input) => input.value);
    expect(pickers).toEqual(["climate.trv_c"]);
  });
  it("shows physical target in manual mode and disables writes for non-admin users", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    const status = fixture();
    status.configuration.mode.value = "manual";
    status.rooms.room_a.desired = null;
    status.rooms.room_a.target = 19;
    card.status = status;
    fake.hass.user = { is_admin: false };
    card.hass = fake.hass;
    await settle(card);
    expect(card.shadowRoot!.textContent).toContain("Target 19°");
    expect(card.shadowRoot!.querySelector("fieldset")!.disabled).toBe(true);
  });
  it("moves focus between tabs with arrow keys", async () => {
    const card = await mount(mocked().hass);
    card
      .shadowRoot!.querySelector("nav")!
      .dispatchEvent(
        new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
      );
    await settle(card);
    expect(card.tab).toBe("Rooms");
    expect(card.shadowRoot!.activeElement?.id).toBe("tab-Rooms");
  });
});

function submit(form: HTMLFormElement) {
  form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
}
function findButton(card: CentralHeatingCard, text: string): HTMLButtonElement {
  const found = Array.from(card.shadowRoot!.querySelectorAll("button")).find(
    (button) => button.textContent?.trim().startsWith(text),
  );
  expect(found, `Button ${text} exists`).toBeTruthy();
  return found!;
}
function writeMessages(fake: ReturnType<typeof mocked>, suffix: string) {
  return fake.callWS.mock.calls
    .map(([message]) => message)
    .filter((message) => message.type === `central_heating/${suffix}`);
}

describe("card payloads and physical thermostat picker", () => {
  it("sends the selected away date picker value without browser-zone conversion", async () => {
    const fake = mocked();
    fake.hass.config = { time_zone: "Europe/Berlin" };
    const card = await mount(fake.hass);
    const mode = card.shadowRoot!.querySelector<HTMLSelectElement>("#mode")!;
    mode.value = "away";
    mode.dispatchEvent(new Event("change", { bubbles: true }));
    card.shadowRoot!.querySelector<HTMLInputElement>("#until")!.value =
      "2026-11-22T18:45";
    submit(mode.form!);
    await settle(card);
    expect(writeMessages(fake, "mode/set")).toEqual([
      {
        type: "central_heating/mode/set",
        config_entry_id: "entry_a",
        mode: "away",
        until: "2026-11-22T18:45",
      },
    ]);
  });
  it("settings save never includes shadow and preserves the knob-sync checkbox value", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.tab = "Settings";
    await settle(card);
    expect(card.shadowRoot!.querySelector("input[name=shadow]")).toBeNull();
    const knob = card.shadowRoot!.querySelector<HTMLInputElement>(
      "input[name=sync_rooms_on_knob_change]",
    )!;
    knob.checked = false;
    submit(knob.form!);
    await settle(card);
    const unchecked = writeMessages(fake, "settings/save").at(-1)!;
    expect(unchecked).not.toHaveProperty("shadow");
    expect(unchecked.settings).toMatchObject({
      sync_rooms_on_knob_change: false,
    });
    knob.checked = true;
    submit(knob.form!);
    await settle(card);
    const checked = writeMessages(fake, "settings/save").at(-1)!;
    expect(checked).not.toHaveProperty("shadow");
    expect(checked.settings).toMatchObject({ sync_rooms_on_knob_change: true });
  });
  it("back to schedule clears the opened room override", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>(
        '[aria-label="Adjust Room B"]',
      )!
      .click();
    await settle(card);
    expect(
      card.shadowRoot!.querySelector<HTMLDialogElement>("#quick-dialog")!.open,
    ).toBe(true);
    findButton(card, "Back to schedule").click();
    await settle(card);
    expect(writeMessages(fake, "override/clear")).toEqual([
      {
        type: "central_heating/override/clear",
        config_entry_id: "entry_a",
        room_id: "room_b",
      },
    ]);
    expect(card.quickRoom).toBeNull();
  });
  it("rounds an off-grid target on open and keeps plus/minus on the half-degree grid", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.status!.rooms.room_a.desired = 20.25;
    card
      .shadowRoot!.querySelector<HTMLButtonElement>(
        '[aria-label="Adjust Room A"]',
      )!
      .click();
    await settle(card);
    expect(card.quickTarget).toBe(20.5);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>(
        '[aria-label="Increase target by half a degree"]',
      )!
      .click();
    await settle(card);
    expect(card.quickTarget).toBe(21);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>(
        '[aria-label="Decrease target by half a degree"]',
      )!
      .click();
    await settle(card);
    expect(card.quickTarget).toBe(20.5);
    submit(
      card.shadowRoot!.querySelector<HTMLFormElement>("#quick-dialog form")!,
    );
    await settle(card);
    expect(writeMessages(fake, "override/set").at(-1)).toMatchObject({
      room_id: "room_a",
      temperature: 20.5,
      kind: "next_block",
    });
  });
  it("creates a default profile before saving the first room", async () => {
    const fake = mocked();
    const empty = fixture();
    empty.configuration.profiles = {};
    empty.configuration.rooms = {};
    empty.configuration.overrides = {};
    empty.rooms = {};
    fake.callWS.mockImplementation(async (message: Message) => {
      if (message.type === "central_heating/profile/save")
        return { ...empty, saved_id: "new_profile" };
      if (message.type === "central_heating/room/save") return empty;
      if (!message.config_entry_id)
        return { entries: [{ entry_id: "entry_a", title: "Boiler A" }] };
      return empty;
    });
    const card = await mount(fake.hass);
    card.tab = "Rooms";
    await settle(card);
    findButton(card, "Add room").click();
    await settle(card);
    card.shadowRoot!.querySelector<HTMLInputElement>("#room-name")!.value =
      "Room C";
    const trv = card.shadowRoot!.querySelector<HTMLInputElement>(
      'input[name=trvs][value="climate.trv_c"]',
    )!;
    trv.checked = true;
    submit(trv.form!);
    await settle(card);
    const saves = fake.callWS.mock.calls
      .map(([message]) => message)
      .filter((message) =>
        ["central_heating/profile/save", "central_heating/room/save"].includes(
          message.type,
        ),
      );
    expect(saves).toHaveLength(2);
    expect(saves[0].type).toBe("central_heating/profile/save");
    const profile = saves[0].profile as {
      days: Record<string, { start: string; target: number }[]>;
    };
    expect(Object.keys(profile.days)).toHaveLength(7);
    expect(profile.days.mon).toEqual([{ start: "00:00", target: 18 }]);
    expect(saves[1]).toMatchObject({
      type: "central_heating/room/save",
      room: {
        name: "Room C",
        trvs: ["climate.trv_c"],
        profile_id: "new_profile",
      },
    });
  });
  it("excludes other-instance used TRVs while retaining missing selected thermostats", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.status = { ...fixture(), used_trv_ids: ["climate.trv_c"] };
    card.status.configuration.rooms.room_a.trvs.push("climate.missing_trv");
    card.tab = "Rooms";
    await settle(card);
    findButton(card, "Edit").click();
    await settle(card);
    const trvs = Array.from(
      card.shadowRoot!.querySelectorAll<HTMLInputElement>("input[name=trvs]"),
    );
    expect(trvs.map((input) => input.value)).not.toContain("climate.trv_c");
    const missing = trvs.find((input) => input.value === "climate.missing_trv");
    expect(missing?.checked).toBe(true);
    expect(missing?.closest("label")?.textContent).toContain("missing");
    submit(missing!.form!);
    await settle(card);
    expect(writeMessages(fake, "room/save").at(-1)).toMatchObject({
      room: { trvs: ["climate.trv_a", "climate.missing_trv"] },
    });
  });
});

describe("explicit shadow control", () => {
  it("never sends shadow-off until confirmed, and cancel changes nothing", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.tab = "Settings";
    await settle(card);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>("#shadow-action")!
      .click();
    await settle(card);
    expect(writeMessages(fake, "settings/save")).toHaveLength(0);
    const dialog =
      card.shadowRoot!.querySelector<HTMLDialogElement>("#shadow-dialog");
    expect(dialog?.open).toBe(true);
    expect(dialog?.textContent).toContain(
      "start sending commands to the boiler",
    );
    card
      .shadowRoot!.querySelector<HTMLButtonElement>("#cancel-shadow")!
      .click();
    await settle(card);
    expect(writeMessages(fake, "settings/save")).toHaveLength(0);
    expect(card.status!.configuration.shadow).toBe(true);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>("#shadow-action")!
      .click();
    await settle(card);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>("#confirm-shadow")!
      .click();
    await settle(card);
    expect(writeMessages(fake, "settings/save")).toEqual([
      {
        type: "central_heating/settings/save",
        config_entry_id: "entry_a",
        shadow: false,
      },
    ]);
  });
  it("enables shadow immediately without a confirmation dialog", async () => {
    const fake = mocked();
    const card = await mount(fake.hass);
    card.status!.configuration.shadow = false;
    card.tab = "Settings";
    await settle(card);
    card
      .shadowRoot!.querySelector<HTMLButtonElement>("#shadow-action")!
      .click();
    await settle(card);
    expect(card.shadowRoot!.querySelector("#shadow-dialog")).toBeNull();
    expect(writeMessages(fake, "settings/save")).toEqual([
      {
        type: "central_heating/settings/save",
        config_entry_id: "entry_a",
        shadow: true,
      },
    ]);
  });
});

describe("heating instance reconnection", () => {
  it("reconnects after the terminal unloaded event and suppresses stale writes meanwhile", async () => {
    vi.useFakeTimers();
    const fake = mocked();
    const card = await mount(fake.hass);
    fake.emit({ unloaded: true });
    await settle(card);
    expect(card.reconnecting).toBe(true);
    expect(card.shadowRoot!.textContent).toContain("Reconnecting");
    expect(card.shadowRoot!.querySelector("fieldset")!.disabled).toBe(true);
    expect(fake.subscribeMessage).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(999);
    expect(fake.subscribeMessage).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(1);
    await settle(card);
    expect(fake.subscribeMessage).toHaveBeenCalledTimes(2);
    expect(card.reconnecting).toBe(false);
  });
  it("handles disconnected/ready events and removes connection listeners on detach", async () => {
    vi.useFakeTimers();
    const fake = mocked();
    const card = await mount(fake.hass);
    fake.hass.connection.connected = false;
    fake.events.dispatchEvent(new Event("disconnected"));
    await settle(card);
    expect(card.reconnecting).toBe(true);
    expect(fake.unsubscribe).toHaveBeenCalledTimes(1);
    fake.hass.connection.connected = true;
    fake.events.dispatchEvent(new Event("ready"));
    await settle(card);
    expect(fake.subscribeMessage).toHaveBeenCalledTimes(2);
    expect(card.reconnecting).toBe(false);
    card.remove();
    expect(fake.removeEventListener.mock.calls.map(([event]) => event)).toEqual(
      ["disconnected", "ready"],
    );
    expect(vi.getTimerCount()).toBe(0);
  });
  it("backs off at 1, 2, 4, 8, 16 and at most 30 seconds, then cancels on detach", async () => {
    vi.useFakeTimers();
    const fake = mocked();
    const card = await mount(fake.hass);
    fake.callWS.mockRejectedValue(new Error("Instance unavailable"));
    fake.emit({ unloaded: true });
    await settle(card);
    let previous = fake.callWS.mock.calls.length;
    for (const delay of [1000, 2000, 4000, 8000, 16000, 30000, 30000]) {
      await vi.advanceTimersByTimeAsync(delay - 1);
      expect(fake.callWS).toHaveBeenCalledTimes(previous);
      await vi.advanceTimersByTimeAsync(1);
      await settle(card);
      expect(fake.callWS).toHaveBeenCalledTimes(previous + 1);
      previous += 1;
    }
    card.remove();
    const detachedCalls = fake.callWS.mock.calls.length;
    expect(vi.getTimerCount()).toBe(0);
    await vi.advanceTimersByTimeAsync(60000);
    expect(fake.callWS).toHaveBeenCalledTimes(detachedCalls);
  });
});

it.each([
  { language: "en-US", time_format: "24" as const, expected: "19:00" },
  { language: "en-GB", time_format: "12" as const, expected: "07:00 pm" },
])(
  "renders override time using HA locale $time_format-hour preference",
  async (locale) => {
    const fake = mocked();
    fake.hass.config = { time_zone: "Europe/Berlin" };
    fake.hass.locale = {
      language: locale.language,
      time_format: locale.time_format,
      time_zone: "server",
    };
    const card = await mount(fake.hass);
    const text = card
      .shadowRoot!.textContent!.replace(/\s+/g, " ")
      .toLowerCase();
    expect(text).toContain(`override until ${locale.expected}`);
  },
);

it("clears a previous away until in the mode/set payload when returning to auto (C06)", async () => {
  const fake = mocked();
  const card = await mount(fake.hass);
  const mode = card.shadowRoot!.querySelector<HTMLSelectElement>("#mode")!;
  card.shadowRoot!.querySelector<HTMLInputElement>("#until")!.value =
    "2026-11-23T18:00";
  mode.value = "auto";
  submit(mode.form!);
  await settle(card);
  expect(writeMessages(fake, "mode/set").at(-1)).toMatchObject({
    mode: "auto",
    until: null,
  });
});
it.each(["away", "summer", "manual"] as const)(
  "room status describes %s instead of schedule comfort",
  async (mode) => {
    const card = await mount(mocked().hass);
    card.status!.configuration.mode.value = mode;
    card.requestUpdate();
    await settle(card);
    expect(card.shadowRoot!.textContent).not.toContain("Comfort on schedule");
    expect(card.shadowRoot!.textContent).toContain(`${modeNames[mode]} ·`);
  },
);
it("unsubscribes on terminal unload before creating the replacement and marks readings stale", async () => {
  vi.useFakeTimers();
  const fake = mocked();
  const card = await mount(fake.hass);
  fake.emit({ unloaded: true });
  await settle(card);
  expect(fake.unsubscribe).toHaveBeenCalledTimes(1);
  expect(
    card.shadowRoot!.querySelector("main")!.classList.contains("stale"),
  ).toBe(true);
  await vi.advanceTimersByTimeAsync(1000);
  await settle(card);
  expect(fake.subscribeMessage).toHaveBeenCalledTimes(2);
  expect(card.reconnecting).toBe(false);
  expect(
    card.shadowRoot!.querySelector("main")!.classList.contains("stale"),
  ).toBe(false);
});

it("preserves unsaved schedule drafts across tab changes", async () => {
  const card = await mount(mocked().hass);
  card.tab = "Schedules";
  await settle(card);
  const editor =
    card.shadowRoot!.querySelector<import("./schedules").HeatingSchedules>(
      "heating-schedules",
    )!;
  await editor.updateComplete;
  const name =
    editor.shadowRoot!.querySelector<HTMLInputElement>("#profile-name")!;
  name.value = "Unsaved profile";
  name.dispatchEvent(new Event("input", { bubbles: true }));
  await editor.updateComplete;
  card.tab = "Overview";
  await settle(card);
  card.tab = "Schedules";
  await settle(card);
  expect(card.shadowRoot!.querySelector("heating-schedules")).toBe(editor);
  expect(editor.draft!.name).toBe("Unsaved profile");
  expect(editor.dirty).toBe(true);
});

it("previews each selected mode and live values before Apply while retaining internal option values", async () => {
  const fake = mocked();
  fake.hass.locale = { language: "en-GB", time_format: "24" };
  const card = await mount(fake.hass);
  card.status!.configuration.settings.away_temperature = 16.5;
  card.status!.configuration.settings.frost_temperature = 7.5;
  card.requestUpdate();
  await settle(card);
  const select = card.shadowRoot!.querySelector<HTMLSelectElement>("#mode")!;
  expect(
    [...select.options].map((o) => [o.value, o.textContent!.trim()]),
  ).toEqual([
    ["auto", "Schedule"],
    ["away", "Away"],
    ["summer", "Heating off"],
    ["manual", "Manual"],
  ]);
  const expected = {
    auto: "Rooms follow their weekly profiles.",
    away: "All rooms at 16.5°.",
    summer: "Boiler heating off, radiators kept at 7.5°. Hot water unaffected.",
    manual:
      "Central Heating doesn't touch the radiators; the boiler still follows their demand.",
  };
  for (const mode of ["manual", "summer", "away", "auto"] as const) {
    select.value = mode;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await settle(card);
    expect(
      card.shadowRoot!.querySelector("#mode-explanation")!.textContent,
    ).toBe(expected[mode]);
  }
  expect(writeMessages(fake, "mode/set")).toEqual([]);
  select.value = "away";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await settle(card);
  const until = card.shadowRoot!.querySelector<HTMLInputElement>("#until")!;
  until.value = "2026-11-23T18:45";
  until.dispatchEvent(new Event("input", { bubbles: true }));
  await settle(card);
  expect(card.shadowRoot!.querySelector("#mode-explanation")!.textContent).toBe(
    "All rooms at 16.5° (until 18:45).",
  );
  until.value = "";
  until.dispatchEvent(new Event("input", { bubbles: true }));
  await settle(card);
  expect(card.shadowRoot!.querySelector("#mode-explanation")!.textContent).toBe(
    "All rooms at 16.5°.",
  );
});
it.each(["auto", "away", "summer", "manual"] as const)(
  "uses the %s display name in the header and room status",
  async (mode) => {
    const card = await mount(mocked().hass);
    card.status!.configuration.mode.value = mode;
    card.requestUpdate();
    await settle(card);
    expect(card.shadowRoot!.querySelector("header")!.textContent).toContain(
      `2 rooms · ${modeNames[mode]}`,
    );
    expect(card.shadowRoot!.querySelector(".room")!.textContent).toContain(
      `${modeNames[mode]} ·`,
    );
  },
);
