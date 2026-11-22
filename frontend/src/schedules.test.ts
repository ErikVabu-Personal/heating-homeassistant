// @vitest-environment jsdom
import { it, expect, vi, afterEach, beforeEach } from "vitest";
import { HeatingSchedules } from "./schedules";
import { fixture } from "../demo/fixture";
const editors: HeatingSchedules[] = [];
async function tick(e: HeatingSchedules) {
  for (let i = 0; i < 5; i++) await Promise.resolve();
  await e.updateComplete;
}
async function mount() {
  const e = new HeatingSchedules();
  editors.push(e);
  e.status = fixture();
  e.writable = true;
  e.saveProfile = vi.fn().mockResolvedValue("profile_a");
  e.deleteProfile = vi.fn().mockResolvedValue(undefined);
  document.body.append(e);
  await tick(e);
  return e;
}
function button(e: HeatingSchedules, text: string) {
  const b = [...e.shadowRoot!.querySelectorAll("button")].find((b) =>
    b.textContent?.trim().startsWith(text),
  );
  expect(b).toBeTruthy();
  return b!;
}
function input(
  e: HeatingSchedules,
  id: string,
  value: string,
  event = "change",
) {
  const el = e.shadowRoot!.querySelector<HTMLInputElement>(id)!;
  el.value = value;
  el.dispatchEvent(new Event(event, { bubbles: true }));
}
beforeEach(() => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = true;
    },
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: function (this: HTMLDialogElement) {
      this.open = false;
      this.dispatchEvent(new Event("close"));
    },
  });
});
afterEach(() => {
  editors.forEach((e) => e.remove());
  editors.length = 0;
  vi.restoreAllMocks();
});
it("holds local edits during status pushes, saves explicitly and preserves payload identity", async () => {
  const e = await mount();
  input(e, "#profile-name", "Profile renamed", "input");
  await tick(e);
  expect(e.dirty).toBe(true);
  expect(e.saveProfile).not.toHaveBeenCalled();
  e.status = fixture();
  await tick(e);
  expect(e.draft!.name).toBe("Profile renamed");
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).toHaveBeenCalledWith({ ...e.draft, id: "profile_a" });
  expect(e.dirty).toBe(false);
});
it("keyboard edits targets, boundary arrows snap times, and never saves on edits", async () => {
  const e = await mount();
  const b = e.shadowRoot!.querySelector<HTMLButtonElement>(".schedule-block")!;
  b.dispatchEvent(
    new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }),
  );
  await tick(e);
  expect(e.draft!.days.mon[0].target).toBe(18.5);
  const handle = e.shadowRoot!.querySelector<HTMLButtonElement>(".boundary")!;
  handle.dispatchEvent(
    new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
  );
  await tick(e);
  expect(e.draft!.days.mon[1].start).toBe("06:05");
  expect(e.saveProfile).not.toHaveBeenCalled();
});
it("pointer dragging moves a boundary on the snapped grid", async () => {
  const e = await mount();
  const handle = e.shadowRoot!.querySelector<HTMLButtonElement>(".boundary")!;
  handle.setPointerCapture = vi.fn();
  handle.parentElement!.getBoundingClientRect = () =>
    ({ left: 0, width: 1440 }) as DOMRect;
  const pointer = (type: string, x: number) =>
    Object.assign(new Event(type, { bubbles: true, cancelable: true }), {
      pointerId: 1,
      clientX: x,
    });
  handle.dispatchEvent(pointer("pointerdown", 360));
  handle.dispatchEvent(pointer("pointermove", 424));
  handle.dispatchEvent(pointer("pointerup", 424));
  await tick(e);
  expect(e.draft!.days.mon[1].start).toBe("07:05");
  expect(e.saveProfile).not.toHaveBeenCalled();
});
it("copies checked days in the draft and leaves unchecked days untouched", async () => {
  const e = await mount();
  e.shadowRoot!.querySelector<HTMLButtonElement>(".schedule-block")!.click();
  await tick(e);
  button(e, "Copy day to").click();
  await tick(e);
  const checkbox = e.shadowRoot!.querySelector<HTMLInputElement>(
    "input[name=days][value=sat]",
  )!;
  checkbox.checked = true;
  checkbox.form!.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  await tick(e);
  expect(e.draft!.days.sat).toEqual(e.draft!.days.mon);
  expect(e.draft!.days.sun[1].start).toBe("08:00");
  expect(e.dirty).toBe(true);
  expect(e.saveProfile).not.toHaveBeenCalled();
});
it("shows schedule and API validation inline without discarding edits", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "20.25");
  await tick(e);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).not.toHaveBeenCalled();
  expect(e.shadowRoot!.querySelector("[role=alert]")!.textContent).toContain(
    "0.5",
  );
  input(e, "#target-mon-0", "20.5");
  e.saveProfile = vi
    .fn()
    .mockRejectedValue(new Error("API validation: profile conflict"));
  await tick(e);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.shadowRoot!.querySelector("[role=alert]")!.textContent).toContain(
    "API validation",
  );
  expect(e.dirty).toBe(true);
});
it("creates and copies new identities, discards safely, and shows room references on refused deletion", async () => {
  const e = await mount();
  button(e, "Delete profile").click();
  await tick(e);
  expect(e.shadowRoot!.querySelector(".delete-confirm")!.textContent).toContain(
    "Room A, Room B",
  );
  expect(
    [...e.shadowRoot!.querySelectorAll("button")].some((b) =>
      b.textContent?.includes("Confirm delete"),
    ),
  ).toBe(false);
  button(e, "Keep profile").click();
  button(e, "Copy profile").click();
  await tick(e);
  expect(e.selected).toBe("");
  expect(e.draft!.name).toBe("Profile A copy");
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).toHaveBeenCalledWith(
    expect.not.objectContaining({ id: expect.anything() }),
  );
});
it("narrow list supports time, temperature, add/remove and discarding without writes", async () => {
  const e = await mount();
  input(e, "#start-mon-1", "07:15");
  await tick(e);
  expect(e.draft!.days.mon[1].start).toBe("07:15");
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-0")!.disabled,
  ).toBe(true);
  button(e, "Add block").click();
  await tick(e);
  expect(e.draft!.days.mon.at(-1)!.start).toBe("22:05");
  input(e, "#target-mon-1", "22.5");
  await tick(e);
  expect(e.draft!.days.mon[1].target).toBe(22.5);
  const remove = [
    ...e.shadowRoot!.querySelectorAll<HTMLButtonElement>(".block-row button"),
  ][1];
  remove.click();
  await tick(e);
  expect(e.draft!.days.mon.some((b) => b.start === "07:15")).toBe(false);
  button(e, "Discard changes").click();
  await tick(e);
  expect(e.dirty).toBe(false);
  expect(e.saveProfile).not.toHaveBeenCalled();
});
it("clears a draft on entry change and refuses save when read-only", async () => {
  const e = await mount();
  input(e, "#profile-name", "Draft", "input");
  await tick(e);
  e.status = { ...fixture(), config_entry_id: "other" };
  await tick(e);
  expect(e.dirty).toBe(false);
  expect(e.draft!.name).toBe("Profile A");
  e.writable = false;
  await tick(e);
  expect(button(e, "Save profile").disabled).toBe(true);
});

it("uses HA's time format for editable starts and blocks saving an invalid raw time", async () => {
  const e = await mount();
  e.hass = {
    locale: { language: "en-GB", time_format: "24" },
  } as import("./types").Hass;
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-0")!.value,
  ).toBe("00:00");
  input(e, "#start-mon-1", "07:13");
  input(e, "#profile-name", "Renamed", "input");
  await tick(e);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).not.toHaveBeenCalled();
  expect(e.error).toContain("invalid start times");
  input(e, "#start-mon-1", "07:15");
  await tick(e);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).toHaveBeenCalled();
  e.hass = {
    locale: { language: "en-US", time_format: "12" },
  } as import("./types").Hass;
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-1")!.value,
  ).toContain("AM");
  input(e, "#start-mon-1", "08:15 AM");
  await tick(e);
  expect(e.draft!.days.mon[1].start).toBe("08:15");
});
