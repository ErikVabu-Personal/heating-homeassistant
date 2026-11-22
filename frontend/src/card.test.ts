// @vitest-environment jsdom
import { afterEach, describe, it, expect, vi } from "vitest";
import { CentralHeatingCard } from "./card";
import { fixture } from "../demo/fixture";
import type { Hass, Message, Status } from "./types";
const cards: CentralHeatingCard[] = [];
async function settle(card: CentralHeatingCard) {
  for (let i = 0; i < 8; i++) await Promise.resolve();
  await card.updateComplete;
}
function mocked() {
  const unsubscribe = vi.fn();
  const subscribeMessage = vi.fn().mockResolvedValue(unsubscribe);
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
    connection: { subscribeMessage },
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
  return { hass, callWS, subscribeMessage, unsubscribe };
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
afterEach(() => {
  for (const card of cards) card.remove();
  cards.length = 0;
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
