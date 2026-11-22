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
  e.saveSchedule = vi.fn().mockResolvedValue("winter");
  e.deleteSchedule = vi.fn().mockResolvedValue(undefined);
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
  input(e, "#schedule-name", "Week renamed", "input");
  await tick(e);
  expect(e.dirty).toBe(true);
  expect(e.saveSchedule).not.toHaveBeenCalled();
  e.status = fixture();
  await tick(e);
  expect(e.draft!.name).toBe("Week renamed");
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith({
    name: "Week renamed",
    rooms: {},
    id: "winter",
  });
  expect(e.dirty).toBe(false);
});
it("keyboard edits targets, boundary arrows snap times, and never saves on edits", async () => {
  const e = await mount();
  const b = e.shadowRoot!.querySelector<HTMLButtonElement>(".schedule-block")!;
  b.dispatchEvent(
    new KeyboardEvent("keydown", { key: "ArrowUp", bubbles: true }),
  );
  await tick(e);
  expect(e.week.days.mon[0].target).toBe(18.5);
  const handle = e.shadowRoot!.querySelector<HTMLButtonElement>(".boundary")!;
  handle.dispatchEvent(
    new KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }),
  );
  await tick(e);
  expect(e.week.days.mon[1].start).toBe("06:05");
  expect(e.saveSchedule).not.toHaveBeenCalled();
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
  expect(e.week.days.mon[1].start).toBe("07:05");
  expect(e.saveSchedule).not.toHaveBeenCalled();
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
  expect(e.week.days.sat).toEqual(e.week.days.mon);
  expect(e.week.days.sun[1].start).toBe("08:00");
  expect(e.dirty).toBe(true);
  expect(e.saveSchedule).not.toHaveBeenCalled();
});
it("shows schedule and API validation inline without discarding edits", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "20.25");
  await tick(e);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).not.toHaveBeenCalled();
  expect(e.shadowRoot!.querySelector("[role=alert]")!.textContent).toContain(
    "0.5",
  );
  input(e, "#target-mon-0", "20.5");
  e.saveSchedule = vi
    .fn()
    .mockRejectedValue(new Error("API validation: week conflict"));
  await tick(e);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.shadowRoot!.querySelector("[role=alert]")!.textContent).toContain(
    "API validation",
  );
  expect(e.dirty).toBe(true);
});
it("refuses active deletion and creates a copied schedule as a new unsaved identity", async () => {
  const e = await mount();
  expect(button(e, "Delete").disabled).toBe(true);
  expect(e.shadowRoot!.querySelector("#delete-reason")!.textContent).toContain(
    "active schedule",
  );
  button(e, "Create").click();
  await tick(e);
  const name =
    e.shadowRoot!.querySelector<HTMLInputElement>("#new-schedule-name")!;
  name.value = "Autumn copy";
  name.form!.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  await tick(e);
  expect(e.selected).toBe("");
  expect(e.draft!.name).toBe("Autumn copy");
  expect(e.draft!.rooms).toEqual(
    e.status!.configuration.schedules.winter.rooms,
  );
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith(
    expect.not.objectContaining({ id: expect.anything() }),
  );
});
it("narrow list supports time, temperature, add/remove and discarding without writes", async () => {
  const e = await mount();
  input(e, "#start-mon-1", "07:15");
  await tick(e);
  expect(e.week.days.mon[1].start).toBe("07:15");
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-0")!.disabled,
  ).toBe(true);
  button(e, "Add block").click();
  await tick(e);
  expect(e.week.days.mon.at(-1)!.start).toBe("22:05");
  input(e, "#target-mon-1", "22.5");
  await tick(e);
  expect(e.week.days.mon[1].target).toBe(22.5);
  const remove = [
    ...e.shadowRoot!.querySelectorAll<HTMLButtonElement>(".block-row button"),
  ][1];
  remove.click();
  await tick(e);
  expect(e.week.days.mon.some((b) => b.start === "07:15")).toBe(false);
  button(e, "Discard changes").click();
  await tick(e);
  expect(e.dirty).toBe(false);
  expect(e.saveSchedule).not.toHaveBeenCalled();
});
it("clears a draft on entry change and refuses save when read-only", async () => {
  const e = await mount();
  input(e, "#schedule-name", "Draft", "input");
  await tick(e);
  e.status = { ...fixture(), config_entry_id: "other" };
  await tick(e);
  expect(e.dirty).toBe(false);
  expect(e.draft!.name).toBe("Winter");
  e.writable = false;
  await tick(e);
  expect(button(e, "Save schedule").disabled).toBe(true);
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
  input(e, "#schedule-name", "Renamed", "input");
  await tick(e);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).not.toHaveBeenCalled();
  expect(e.error).toContain("invalid start times");
  input(e, "#start-mon-1", "07:15");
  await tick(e);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalled();
  e.hass = {
    locale: { language: "en-US", time_format: "12" },
  } as import("./types").Hass;
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-mon-1")!.value,
  ).toContain("AM");
  input(e, "#start-mon-1", "08:15 AM");
  await tick(e);
  expect(e.week.days.mon[1].start).toBe("08:15");
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
    expect(e.week.days.mon[3].start).toBe("17:00");
    expect(e.error).toContain("must be after 09:00 and before 22:00");
    button(e, "Save schedule").click();
    await tick(e);
    expect(e.saveSchedule).not.toHaveBeenCalled();
    input(e, id, "05:00");
    await tick(e);
    expect(e.week.days.mon[3].start).toBe("17:00");
    expect(e.error).toContain("must be after 09:00 and before 22:00");
    input(e, id, "18:05");
    await tick(e);
    expect(e.week.days.mon[3].start).toBe("18:05");
    button(e, "Save schedule").click();
    await tick(e);
    expect(e.saveSchedule).toHaveBeenCalled();
  },
);
it("removing a rejected row clears its remembered input and allows saving other changes", async () => {
  const e = await mount();
  input(e, "#schedule-name", "Keep this edit", "input");
  input(e, "#start-mon-3", "nonsense");
  await tick(e);
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    "details:first-of-type .block-row button",
  )[3].click();
  await tick(e);
  expect(e.week.days.mon).toHaveLength(4);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith(
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
  expect(e.week.days.mon[2].start).toBe("17:00");
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#start-tue-2")!.value,
  ).toBe("invalid Tuesday");
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).not.toHaveBeenCalled();
  input(e, "#start-tue-2", "10:00");
  await tick(e);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalled();
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
      input(e, "#schedule-name", "Copied Monday", "input");
    }
    await tick(e);
    button(e, "Save schedule").click();
    await tick(e);
    expect(e.saveSchedule).toHaveBeenCalled();
  },
);
it("disables schedule selection for unsaved edits, including rejected typed input (E05)", async () => {
  const e = await mount();
  const selector = () =>
    e.shadowRoot!.querySelector<HTMLSelectElement>('[aria-label="Schedule"]')!;
  expect(selector().disabled).toBe(false);
  input(e, "#schedule-name", "Renamed", "input");
  await tick(e);
  expect(selector().disabled).toBe(true);
  button(e, "Discard changes").click();
  await tick(e);
  expect(selector().disabled).toBe(false);
  input(e, "#start-mon-2", "nonsense");
  await tick(e);
  expect(selector().disabled).toBe(true);
});
it("shows the selected room’s next absolute change through the autumn DST fold", async () => {
  const e = await mount();
  e.hass = {
    config: { time_zone: "UTC" },
    locale: { language: "en-GB", time_format: "24" },
  } as import("./types").Hass;
  e.status!.rooms.room_a.next_change = "2026-10-25T02:10:00+01:00";
  e.status!.rooms.room_b.next_change = "2026-10-25T02:50:00+02:00";
  e.requestUpdate();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector(".week-editor .toolbar")!.textContent,
  ).toContain("01:10");
  button(e, "Room B").click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector(".week-editor .toolbar")!.textContent,
  ).toContain("00:50");
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
    expect(e.week.days.mon[1].start).toBe("06:30");
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

it("selects a whole-house schedule and a room, preserving edits in both room weeks", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "19");
  await tick(e);
  button(e, "Room B").click();
  await tick(e);
  expect(e.week.days.mon[0].target).toBe(17);
  input(e, "#target-mon-0", "20");
  await tick(e);
  button(e, "Room A").click();
  await tick(e);
  expect(e.week.days.mon[0].target).toBe(19);
  expect(e.draft!.rooms.room_b.days.mon[0].target).toBe(20);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith(
    expect.objectContaining({
      id: "winter",
      rooms: expect.objectContaining({
        room_a: expect.anything(),
        room_b: expect.anything(),
      }),
    }),
  );
});
it("copies only checked room weeks in the selected schedule, with independent copies and explicit saving", async () => {
  const e = await mount();
  const updated = structuredClone(e.status!);
  updated.configuration.rooms.room_c = {
    ...updated.configuration.rooms.room_b,
    name: "Room C",
    trvs: ["climate.trv_c"],
  };
  for (const schedule of Object.values(updated.configuration.schedules))
    schedule.rooms.room_c = structuredClone(schedule.rooms.room_b);
  e.status = updated;
  await tick(e);
  const unchecked = structuredClone(e.draft!.rooms.room_c);
  input(e, "#target-mon-0", "22");
  await tick(e);
  button(e, "Copy this room").click();
  await tick(e);
  const check = e.shadowRoot!.querySelector<HTMLInputElement>(
    "input[name=rooms][value=room_b]",
  )!;
  check.checked = true;
  check.form!.dispatchEvent(
    new Event("submit", { bubbles: true, cancelable: true }),
  );
  await tick(e);
  expect(e.draft!.rooms.room_c).toEqual(unchecked);
  expect(e.draft!.rooms.room_b).toEqual(e.draft!.rooms.room_a);
  expect(e.saveSchedule).not.toHaveBeenCalled();
  input(e, "#target-mon-0", "23");
  await tick(e);
  expect(e.draft!.rooms.room_b.days.mon[0].target).toBe(22);
  expect(
    e.status!.configuration.schedules.autumn.rooms.room_b.days.mon[0].target,
  ).toBe(18);
});
it.each(["active", "blank"])(
  "creates a schedule from %s with every room seeded",
  async (source) => {
    const e = await mount();
    e.status!.configuration.active_schedule_id = "autumn";
    e.requestUpdate();
    await tick(e);
    button(e, "Create").click();
    await tick(e);
    const select =
      e.shadowRoot!.querySelector<HTMLSelectElement>("#schedule-source")!;
    expect(select.value).toBe("autumn");
    if (source === "blank") select.value = "";
    const name =
      e.shadowRoot!.querySelector<HTMLInputElement>("#new-schedule-name")!;
    name.value = "New plan";
    name.form!.dispatchEvent(
      new Event("submit", { bubbles: true, cancelable: true }),
    );
    await tick(e);
    expect(Object.keys(e.draft!.rooms)).toEqual(["room_a", "room_b"]);
    if (source === "active")
      expect(e.draft!.rooms).toEqual(
        e.status!.configuration.schedules.autumn.rooms,
      );
    else
      expect(e.draft!.rooms.room_a.days.mon).toEqual([
        { start: "00:00", target: 18 },
      ]);
    expect(e.saveSchedule).not.toHaveBeenCalled();
    expect(e.dirty).toBe(true);
  },
);
it("activation is explicit and blocked while unsaved; inactive schedules may be deleted", async () => {
  const e = await mount();
  e.activateSchedule = vi.fn().mockResolvedValue(undefined);
  const select = e.shadowRoot!.querySelector<HTMLSelectElement>(
    "[aria-label=Schedule]",
  )!;
  select.value = "autumn";
  select.dispatchEvent(new Event("change", { bubbles: true }));
  await tick(e);
  expect(e.selected).toBe("autumn");
  button(e, "Activate").click();
  await tick(e);
  expect(e.activateSchedule).toHaveBeenCalledWith("autumn");
  input(e, "#schedule-name", "Renamed", "input");
  await tick(e);
  expect(button(e, "Activate").disabled).toBe(true);
  button(e, "Discard changes").click();
  await tick(e);
  button(e, "Delete").click();
  await tick(e);
  button(e, "Confirm delete").click();
  await tick(e);
  expect(e.deleteSchedule).toHaveBeenCalledWith("autumn");
});

it("lets read-only users inspect other room weeks while editing and activation stay disabled", async () => {
  const e = await mount();
  e.writable = false;
  await tick(e);
  const room = button(e, "Room B");
  expect(room.matches(":disabled")).toBe(false);
  room.click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_b");
  expect(e.week.days.mon[0].target).toBe(17);
  expect(
    e
      .shadowRoot!.querySelector<HTMLInputElement>("#target-mon-0")!
      .matches(":disabled"),
  ).toBe(true);
  expect(button(e, "Activate").disabled).toBe(true);
  expect(button(e, "Save schedule").disabled).toBe(true);
});

it.each([false, true])(
  "loads server-seeded added rooms while dirty=%s without inventing defaults",
  async (dirty) => {
    const e = await mount();
    button(e, "Room B").click();
    await tick(e);
    if (dirty) {
      input(e, "#target-mon-0", "23");
      await tick(e);
    }
    const status = structuredClone(e.status!);
    status.configuration.rooms.room_c = {
      ...status.configuration.rooms.room_a,
      name: "Room C",
      trvs: ["climate.trv_c"],
    };
    for (const schedule of Object.values(status.configuration.schedules))
      schedule.rooms.room_c = structuredClone(schedule.rooms.room_a);
    e.status = status;
    await tick(e);
    expect(e.selectedRoom).toBe("room_b");
    expect(e.dirty).toBe(dirty);
    button(e, "Room C").click();
    await tick(e);
    expect(e.week).toEqual(status.configuration.schedules.winter.rooms.room_a);
    if (dirty) {
      button(e, "Save schedule").click();
      await tick(e);
      expect(e.saveSchedule).toHaveBeenCalledWith(
        expect.objectContaining({ rooms: { room_b: expect.anything() } }),
      );
    }
  },
);
it("drops deleted rooms during unsaved edits and saves surviving edits without Discard", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "23");
  await tick(e);
  const status = structuredClone(e.status!);
  delete status.configuration.rooms.room_b;
  for (const schedule of Object.values(status.configuration.schedules))
    delete schedule.rooms.room_b;
  e.status = status;
  await tick(e);
  expect(e.draft!.rooms).not.toHaveProperty("room_b");
  expect(e.dirty).toBe(true);
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith(
    expect.objectContaining({ rooms: { room_a: expect.anything() } }),
  );
  expect(e.draft!.rooms.room_a.days.mon[0].target).toBe(23);
  expect(e.error).toBe("");
  expect(e.dirty).toBe(false);
});
it.each([false, true])(
  "preserves another device's Room A change when saving Room B, dirty=%s",
  async (dirty) => {
    const e = await mount();
    button(e, "Room B").click();
    await tick(e);
    if (dirty) {
      input(e, "#target-mon-0", "23");
      await tick(e);
    }
    const server = structuredClone(e.status!);
    server.configuration.schedules.winter.rooms.room_a.days.mon[0].target = 25;
    e.status = structuredClone(server);
    await tick(e);
    expect(e.selectedRoom).toBe("room_b");
    if (!dirty) {
      expect(e.draft!.rooms.room_a.days.mon[0].target).toBe(25);
      expect(e.dirty).toBe(false);
      input(e, "#target-mon-0", "23");
      await tick(e);
    }
    e.saveSchedule = vi.fn(async (payload) => {
      Object.assign(server.configuration.schedules.winter.rooms, payload.rooms);
      return "winter";
    });
    button(e, "Save schedule").click();
    await tick(e);
    expect(e.saveSchedule).toHaveBeenCalledWith(
      expect.objectContaining({ rooms: { room_b: expect.anything() } }),
    );
    expect(
      server.configuration.schedules.winter.rooms.room_a.days.mon[0].target,
    ).toBe(25);
    expect(
      server.configuration.schedules.winter.rooms.room_b.days.mon[0].target,
    ).toBe(23);
  },
);
it("disables every room picker while a typed time is invalid, then restores navigation (S11)", async () => {
  const e = await mount();
  input(e, "#start-mon-1", "invalid");
  await tick(e);
  const rooms = [
    ...e.shadowRoot!.querySelectorAll<HTMLButtonElement>(".room-picker button"),
  ];
  expect(rooms.length).toBe(2);
  expect(rooms.every((b) => b.disabled)).toBe(true);
  button(e, "Room B").click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_a");
  input(e, "#start-mon-1", "07:15");
  await tick(e);
  expect(button(e, "Room B").disabled).toBe(false);
  button(e, "Room B").click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_b");
});
it("visibly disables deleting the last schedule with a reason", async () => {
  const e = await mount();
  const status = structuredClone(e.status!);
  delete status.configuration.schedules.autumn;
  delete status.configuration.schedules.spring;
  e.status = status;
  await tick(e);
  expect(button(e, "Delete").disabled).toBe(true);
  expect(button(e, "Delete").getAttribute("aria-describedby")).toBe(
    "delete-reason",
  );
  expect(e.shadowRoot!.querySelector("#delete-reason")!.textContent).toContain(
    "last schedule",
  );
});

it.each([false, true])(
  "recovers when the open schedule is deleted elsewhere, dirty=%s",
  async (dirty) => {
    const e = await mount();
    const select = e.shadowRoot!.querySelector<HTMLSelectElement>(
      "[aria-label=Schedule]",
    )!;
    select.value = "autumn";
    select.dispatchEvent(new Event("change"));
    await tick(e);
    if (dirty) {
      input(e, "#target-mon-0", "23");
      await tick(e);
    }
    const status = structuredClone(e.status!);
    delete status.configuration.schedules.autumn;
    e.status = status;
    await tick(e);
    if (dirty) {
      expect(e.draft!.rooms.room_a.days.mon[0].target).toBe(23);
      expect(e.shadowRoot!.textContent).toContain("deleted on another device");
      expect(button(e, "Save schedule").disabled).toBe(true);
      button(e, "Discard changes").click();
      await tick(e);
    }
    expect(e.selected).toBe("winter");
    expect(e.draft!.name).toBe("Winter");
    expect(e.dirty).toBe(false);
    expect(button(e, "Create").disabled).toBe(false);
  },
);
it("refreshes remote rename and untouched room while retaining local room edits (N09/N06)", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "23");
  await tick(e);
  const status = structuredClone(e.status!);
  status.configuration.schedules.winter.name = "Cold";
  status.configuration.schedules.winter.rooms.room_b.days.mon[0].target = 25;
  e.status = status;
  await tick(e);
  expect(e.draft!.name).toBe("Cold");
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#schedule-name")!.value,
  ).toBe("Cold");
  expect(e.week.days.mon[0].target).toBe(23);
  button(e, "Room B").click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#target-mon-0")!.value,
  ).toBe("25");
  expect(e.dirty).toBe(true);
});
it("moves selected room when it is deleted, preserving other edits (N12)", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "23");
  await tick(e);
  button(e, "Room B").click();
  await tick(e);
  input(e, "#start-mon-1", "invalid");
  await tick(e);
  const status = structuredClone(e.status!);
  delete status.configuration.rooms.room_b;
  for (const s of Object.values(status.configuration.schedules))
    delete s.rooms.room_b;
  e.status = status;
  await tick(e);
  expect(e.selectedRoom).toBe("room_a");
  expect(e.week.days.mon[0].target).toBe(23);
  expect(e.error).toBe("");
  button(e, "Save schedule").click();
  await tick(e);
  expect(e.saveSchedule).toHaveBeenCalledWith(
    expect.objectContaining({ rooms: { room_a: expect.anything() } }),
  );
});
it("shows server updates received during an in-flight save afterwards (N14)", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "23");
  await tick(e);
  let finish!: (id: string) => void;
  e.saveSchedule = vi.fn(
    () =>
      new Promise<string>((resolve) => {
        finish = resolve;
      }),
  );
  button(e, "Save schedule").click();
  await tick(e);
  const status = structuredClone(e.status!);
  status.configuration.schedules.winter.name = "Cold";
  status.configuration.schedules.winter.rooms.room_a.days.mon[0].target = 23;
  status.configuration.schedules.winter.rooms.room_b.days.mon[0].target = 25;
  e.status = status;
  await tick(e);
  expect(e.saving).toBe(true);
  finish("winter");
  await tick(e);
  expect(e.draft).toEqual(status.configuration.schedules.winter);
  expect(e.dirty).toBe(false);
  button(e, "Room B").click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLInputElement>("#target-mon-0")!.value,
  ).toBe("25");
});
it.each(["winter", ""])(
  "reconciles room membership in a new draft seeded from %s",
  async (source) => {
    const e = await mount();
    button(e, "Create").click();
    await tick(e);
    const name =
      e.shadowRoot!.querySelector<HTMLInputElement>("#new-schedule-name")!;
    name.value = "New plan";
    e.shadowRoot!.querySelector<HTMLSelectElement>("#schedule-source")!.value =
      source;
    name.form!.dispatchEvent(new Event("submit", { cancelable: true }));
    await tick(e);
    input(e, "#target-mon-0", "23");
    await tick(e);
    const status = structuredClone(e.status!);
    delete status.configuration.rooms.room_b;
    status.configuration.rooms.room_c = {
      ...status.configuration.rooms.room_a,
      name: "Room C",
      trvs: ["climate.trv_c"],
    };
    for (const s of Object.values(status.configuration.schedules)) {
      delete s.rooms.room_b;
      s.rooms.room_c = structuredClone(s.rooms.room_a);
    }
    e.status = status;
    await tick(e);
    expect(e.draft!.rooms).not.toHaveProperty("room_b");
    expect(e.draft!.rooms.room_a.days.mon[0].target).toBe(23);
    expect(e.draft!.rooms.room_c.days.mon).toEqual(
      source
        ? status.configuration.schedules.winter.rooms.room_c.days.mon
        : [{ start: "00:00", target: 18 }],
    );
    expect(e.dirty).toBe(true);
    button(e, "Save schedule").click();
    await tick(e);
    expect(e.saveSchedule).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "New plan",
        rooms: { room_a: expect.anything(), room_c: expect.anything() },
      }),
    );
  },
);

it("renders seven phone day bars and tapping opens that day's existing editor without saving", async () => {
  const e = await mount();
  const bars = [
    ...e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
      ".phone-week .bar-button",
    ),
  ];
  expect(bars).toHaveLength(7);
  expect(bars[0].getAttribute("aria-label")).toContain("Monday");
  expect(e.shadowRoot!.querySelector("#day-mon")!.hasAttribute("open")).toBe(
    false,
  );
  bars[0].click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLDetailsElement>("#day-mon")!.open,
  ).toBe(true);
  expect(bars[0].getAttribute("aria-expanded")).toBe("true");
  input(e, "#target-mon-0", "23");
  await tick(e);
  expect(e.week.days.mon[0].target).toBe(23);
  bars[1].click();
  await tick(e);
  expect(
    e.shadowRoot!.querySelector<HTMLDetailsElement>("#day-mon")!.open,
  ).toBe(false);
  expect(
    e.shadowRoot!.querySelector<HTMLDetailsElement>("#day-tue")!.open,
  ).toBe(true);
  expect(e.saveSchedule).not.toHaveBeenCalled();
});
it("keeps five-minute blocks at their true width without a colliding text label", async () => {
  const e = await mount();
  const status = structuredClone(e.status!);
  status.configuration.schedules.winter.rooms.room_a.days.mon = [
    { start: "00:00", target: 18 },
    { start: "00:05", target: 21 },
  ];
  e.status = status;
  await tick(e);
  const segment = e.shadowRoot!.querySelector<HTMLElement>(
    ".phone-week .bar-segment",
  )!;
  expect(segment.style.width).toBe(`${100 / 288}%`);
  expect(segment.textContent!.trim()).toBe("");
  expect(segment.title).toContain("00:00–00:05 · 18°");
});
it("overview follows room order and selected day, and opens the tapped room without edits", async () => {
  const e = await mount();
  button(e, "Overview").click();
  await tick(e);
  expect(e.view).toBe("overview");
  const rows = [
    ...e.shadowRoot!.querySelectorAll<HTMLElement>(".overview-rows .bar-row"),
  ];
  expect(rows.map((r) => r.dataset.room)).toEqual(["room_a", "room_b"]);
  const day = e.shadowRoot!.querySelector<HTMLSelectElement>("#overview-day")!;
  day.value = "sat";
  day.dispatchEvent(new Event("change"));
  await tick(e);
  expect(
    e
      .shadowRoot!.querySelector(".overview-rows .bar-button")!
      .getAttribute("aria-label"),
  ).toContain("08:00");
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    ".overview-rows .bar-button",
  )[1].click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_b");
  expect(e.view).toBe("rooms");
  expect(
    e.shadowRoot!.querySelector<HTMLDetailsElement>("#day-sat")!.open,
  ).toBe(true);
  expect(e.dirty).toBe(false);
  expect(e.saveSchedule).not.toHaveBeenCalled();
});
it("now markers appear only for the active schedule on today in HA's zone and refresh each minute", async () => {
  vi.useFakeTimers();
  try {
    vi.setSystemTime(new Date("2026-11-22T23:30:00Z"));
    const e = await mount();
    e.hass = {
      config: { time_zone: "Europe/Brussels" },
    } as import("./types").Hass;
    button(e, "Overview").click();
    await tick(e);
    expect(
      e.shadowRoot!.querySelector<HTMLSelectElement>("#overview-day")!.value,
    ).toBe("mon");
    expect(e.shadowRoot!.querySelectorAll(".now-marker")).toHaveLength(2);
    expect(
      e.shadowRoot!.querySelector<HTMLElement>(".now-marker")!.style.left,
    ).toBe(`${30 / 14.4}%`);
    await vi.advanceTimersByTimeAsync(60_000);
    await tick(e);
    expect(
      e.shadowRoot!.querySelector<HTMLElement>(".now-marker")!.style.left,
    ).toBe(`${31 / 14.4}%`);
    e.overviewDay = "sun";
    await tick(e);
    expect(e.shadowRoot!.querySelectorAll(".now-marker")).toHaveLength(0);
    e.overviewDay = "mon";
    const select = e.shadowRoot!.querySelector<HTMLSelectElement>(
      "[aria-label=Schedule]",
    )!;
    select.value = "autumn";
    select.dispatchEvent(new Event("change"));
    await tick(e);
    expect(e.shadowRoot!.querySelectorAll(".now-marker")).toHaveLength(0);
    e.remove();
    expect(vi.getTimerCount()).toBe(0);
  } finally {
    vi.useRealTimers();
  }
});
it("escapes malicious room names in the overview", async () => {
  const e = await mount();
  const status = structuredClone(e.status!);
  status.configuration.rooms.room_a.name = '<img src=x onerror="alert(1)">';
  e.status = status;
  e.view = "overview";
  await tick(e);
  expect(e.shadowRoot!.querySelector(".overview-rows img")).toBeNull();
  expect(
    e.shadowRoot!.querySelector(".overview-rows .bar-name")!.textContent,
  ).toBe(status.configuration.rooms.room_a.name);
});
it("lets read-only users open phone days and overview rows while controls stay disabled", async () => {
  const e = await mount();
  e.writable = false;
  await tick(e);
  const bar = e.shadowRoot!.querySelector<HTMLButtonElement>(
    ".phone-week .bar-button",
  )!;
  expect(bar.matches(":disabled")).toBe(false);
  bar.click();
  await tick(e);
  expect(
    e
      .shadowRoot!.querySelector<HTMLInputElement>("#target-mon-0")!
      .matches(":disabled"),
  ).toBe(true);
  button(e, "Overview").click();
  await tick(e);
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    ".overview-rows .bar-button",
  )[1].click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_b");
  expect(e.dirty).toBe(false);
});

it("overview navigation cannot bypass an invalid typed time or discard a room draft", async () => {
  const e = await mount();
  input(e, "#target-mon-0", "23");
  input(e, "#start-mon-1", "invalid");
  await tick(e);
  button(e, "Overview").click();
  await tick(e);
  e.shadowRoot!.querySelectorAll<HTMLButtonElement>(
    ".overview-rows .bar-button",
  )[1].click();
  await tick(e);
  expect(e.selectedRoom).toBe("room_a");
  expect(e.error).toContain("Correct invalid start times");
  button(e, "Rooms").click();
  await tick(e);
  expect(e.week.days.mon[0].target).toBe(23);
  expect(e.dirty).toBe(true);
  expect(e.saveSchedule).not.toHaveBeenCalled();
});
