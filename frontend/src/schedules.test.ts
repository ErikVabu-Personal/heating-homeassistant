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

it.each(["list", "block"])(
  "rejects out-of-order typed times in the %s editor without clamping (E01)",
  async (editor) => {
    const e = await mount();
    e.hass = {
      locale: { language: "en-GB", time_format: "24" },
    } as import("./types").Hass;
    await tick(e);
    if (editor === "block") {
      e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
        ".schedule-block",
      )[3].click();
      await tick(e);
    }
    const id = editor === "list" ? "#start-mon-3" : "#block-start";
    input(e, id, "23:00");
    await tick(e);
    expect(e.draft!.days.mon[3].start).toBe("17:00");
    expect(e.error).toContain("must be after 09:00 and before 22:00");
    button(e, "Save profile").click();
    await tick(e);
    expect(e.saveProfile).not.toHaveBeenCalled();
    input(e, id, "05:00");
    await tick(e);
    expect(e.draft!.days.mon[3].start).toBe("17:00");
    expect(e.error).toContain("must be after 09:00 and before 22:00");
    input(e, id, "18:05");
    await tick(e);
    expect(e.draft!.days.mon[3].start).toBe("18:05");
    button(e, "Save profile").click();
    await tick(e);
    expect(e.saveProfile).toHaveBeenCalled();
  },
);
it("removing a rejected row clears its remembered input and allows saving other changes", async () => {
  const e = await mount();
  input(e, "#profile-name", "Keep this edit", "input");
  input(e, "#start-mon-3", "nonsense");
  await tick(e);
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    "details:first-of-type .block-row button",
  )[3].click();
  await tick(e);
  expect(e.draft!.days.mon).toHaveLength(4);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).toHaveBeenCalledWith(
    expect.objectContaining({ name: "Keep this edit" }),
  );
  expect(e.error).toBe("");
});
it("removing a row above rejected text restores the correct row times and keeps other days' errors", async () => {
  const e = await mount();
  input(e, "#start-mon-3", "nonsense");
  input(e, "#start-tue-2", "invalid Tuesday");
  await tick(e);
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    "details:first-of-type .block-row button",
  )[1].click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-2")!.value,
  ).not.toBe("nonsense");
  expect(e.draft!.days.mon[2].start).toBe("17:00");
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-tue-2")!.value,
  ).toBe("invalid Tuesday");
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).not.toHaveBeenCalled();
  input(e, "#start-tue-2", "10:00");
  await tick(e);
  button(e, "Save profile").click();
  await tick(e);
  expect(e.saveProfile).toHaveBeenCalled();
});
it.each(["split", "copy"])(
  "%s clears rejected inputs for the structurally changed day",
  async (action) => {
    const e = await mount();
    input(e, "#start-mon-3", "nonsense");
    await tick(e);
    if (action === "split") button(e, "Add block").click();
    else {
      // Copy Tuesday to Monday, replacing the rejected row with valid schedule data.
      e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
        ".schedule-block",
      )[5].click();
      await tick(e);
      button(e, "Copy day to").click();
      await tick(e);
      const check = e.shadowRoot!.querySelector<HTMLInputElement>(
        "input[name=days][value=mon]",
      )!;
      check.checked = true;
      check.form!.dispatchEvent(
        new Event("submit", { bubbles: true, cancelable: true }),
      );
      input(e, "#profile-name", "Copied Monday", "input");
    }
    await tick(e);
    button(e, "Save profile").click();
    await tick(e);
    expect(e.saveProfile).toHaveBeenCalled();
  },
);
it("disables profile selection for unsaved edits, including rejected typed input (E05)", async () => {
  const e = await mount();
  const selector = () =>
    e.shadowRoot!.querySelector<HTMLSelectElement>(
      '[aria-label="Heating profile"]',
    )!;
  expect(selector().disabled).toBe(false);
  input(e, "#profile-name", "Renamed", "input");
  await tick(e);
  expect(selector().disabled).toBe(true);
  button(e, "Discard changes").click();
  await tick(e);
  expect(selector().disabled).toBe(false);
  input(e, "#start-mon-2", "nonsense");
  await tick(e);
  expect(selector().disabled).toBe(true);
});
it("chooses next room change by absolute time through the autumn DST fold", async () => {
  const e = await mount();
  e.hass = {
    config: { time_zone: "UTC" },
    locale: { language: "en-GB", time_format: "24" },
  } as import("./types").Hass;
  e.status!.rooms.room_a.next_change = "2026-10-25T02:10:00+01:00";
  e.status!.rooms.room_b.next_change = "2026-10-25T02:50:00+02:00";
  e.requestUpdate();
  await tick(e);
  expect(e.shadowRoot!.querySelector(".profile-meta")!.textContent).toContain(
    "00:50",
  );
});
it.each([
  ["24", "6:30"],
  ["12", "6:30 AM"],
] as const)(
  "accepts a one-digit hour in a %s h locale",
  async (format, value) => {
    const e = await mount();
    e.hass = {
      locale: {
        language: format === "24" ? "en-GB" : "en-US",
        time_format: format,
      },
    } as import("./types").Hass;
    await tick(e);
    input(e, "#start-mon-1", value);
    await tick(e);
    expect(e.draft!.days.mon[1].start).toBe("06:30");
    expect(e.error).toBe("");
  },
);

it.each(["12", "24"] as const)(
  "formats neighbour rejection bounds in the %s h locale, with no midnight upper bound",
  async (time_format) => {
    const e = await mount();
    e.hass = {
      locale: { language: "en-GB", time_format },
    } as import("./types").Hass;
    await tick(e);
    input(e, "#start-mon-3", "23:00");
    await tick(e);
    expect(e.error).toBe(
      time_format === "12"
        ? "Start time must be after 09:00 am and before 10:00 pm."
        : "Start time must be after 09:00 and before 22:00.",
    );
    input(e, "#start-mon-4", "16:00");
    await tick(e);
    expect(e.error).toBe(
      time_format === "12"
        ? "Start time must be after 05:00 pm."
        : "Start time must be after 17:00.",
    );
    expect(e.error).not.toContain("24:00");
  },
);
