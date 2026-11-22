import { LitElement, html, nothing, css } from "lit";
import { barLayout, houseClock } from "./bars";
import { styles } from "./styles";
import {
  defaultWeek,
  temperature,
  time,
  scheduleTime,
  parseScheduleTime,
} from "./format";
import {
  weekdays,
  dayNames,
  minutes,
  clock,
  schedulePayload,
  splitBlock,
  removeBlock,
  moveBoundary,
  copyDay,
  temperatureStep,
} from "./schedule";
import type { Block } from "./schedule";
import type { Hass, Schedule, Status } from "./types";
export class HeatingSchedules extends LitElement {
  static properties = {
    view: { state: true },
    overviewDay: { state: true },
    openedDay: { state: true },
    status: { attribute: false },
    hass: { attribute: false },
    writable: { type: Boolean },
    selected: { state: true },
    selectedRoom: { state: true },
    draft: { state: true },
    error: { state: true },
    saving: { state: true },
    block: { state: true },
    copyFrom: { state: true },
    deleting: { state: true },
    creating: { state: true },
    copyRooms: { state: true },
  };
  static styles = [
    styles,
    css`
      :host {
        container-type: inline-size;
      }
      .week-tools {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 16px 0;
      }
      .week-tools select {
        width: auto;
        flex: 1;
        min-width: 130px;
      }
      .week {
        border: 1px solid var(--divider-color);
        border-radius: 12px;
        padding: 16px;
      }
      .axis {
        display: flex;
        justify-content: space-between;
        margin-left: 88px;
        font-size: 12px;
        color: var(--secondary-text-color);
      }
      .day {
        display: grid;
        grid-template-columns: 76px minmax(0, 1fr);
        align-items: center;
        gap: 12px;
        padding: 10px 0;
      }
      .day-label {
        font-weight: 600;
        font-size: 13px;
      }
      .track {
        position: relative;
        height: 70px;
        min-width: 0;
      }
      .schedule-block {
        position: absolute;
        top: 0;
        height: 44px;
        border-radius: 5px;
        padding: 0 3px;
        min-width: 0;
        overflow: hidden;
        border: 1px solid var(--divider-color);
        color: var(--primary-text-color);
      }
      .boundary {
        position: absolute;
        top: 0;
        width: 24px;
        height: 44px;
        padding: 0;
        transform: translateX(-50%);
        cursor: ew-resize;
        background: transparent;
        border: 0;
        touch-action: none;
        z-index: 1;
      }
      .boundary::after {
        content: "";
        display: block;
        height: 25px;
        width: 3px;
        margin: auto;
        background: var(--primary-text-color);
        border-radius: 3px;
      }
      .split-time {
        position: absolute;
        top: 48px;
        width: 100%;
        height: 20px;
        min-height: 20px;
        padding: 0;
        border: 1px dashed var(--divider-color);
        background: var(--secondary-background-color);
        border-radius: 4px;
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      .legend {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        margin: 16px 0;
        font-size: 12px;
      }
      .swatch {
        display: inline-block;
        width: 14px;
        height: 14px;
        border: 1px solid var(--divider-color);
        border-radius: 3px;
        margin-right: 5px;
        vertical-align: middle;
      }
      .edit-panel {
        margin-top: 18px;
        background: var(--secondary-background-color);
      }
      .day-list {
        margin-top: 20px;
      }
      details {
        border-bottom: 1px solid var(--divider-color);
        padding: 8px 0;
      }
      summary {
        cursor: pointer;
        min-height: 44px;
        padding: 10px 0;
        font-weight: 600;
      }
      .block-row {
        display: grid;
        grid-template-columns: 1fr 1fr auto;
        gap: 8px;
        margin: 10px 0;
        align-items: end;
      }
      .block-row .field {
        margin: 0;
        min-width: 0;
      }
      .block-row button {
        padding: 8px;
      }
      .inline-error {
        color: var(--error-color);
        padding: 12px;
        border: 1px solid var(--error-color);
        border-radius: 8px;
        margin-top: 16px;
      }
      .unsaved {
        color: var(--warning-color);
      }
      .week-meta {
        margin: 12px 0;
      }
      .week-meta p {
        margin: 4px 0;
      }
      .schedule-tools {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin: 16px 0;
      }
      .schedule-tools select {
        flex: 1;
        min-width: 140px;
        width: auto;
      }
      .schedule-layout {
        display: grid;
        grid-template-columns: 160px minmax(0, 1fr);
        gap: 20px;
      }
      .room-picker {
        display: flex;
        flex-direction: column;
        gap: 8px;
        align-self: start;
      }
      .room-picker button {
        text-align: left;
      }
      .room-picker [aria-pressed="true"] {
        border-color: var(--primary-color);
        color: var(--primary-color);
        font-weight: 700;
      }
      .week-editor {
        min-width: 0;
      }
      @container (max-width:600px) {
        .schedule-layout {
          grid-template-columns: 1fr;
        }
        .room-picker {
          display: grid;
          grid-template-columns: 1fr 1fr;
        }
      }
      .phone-week {
        display: none;
      }
      .bar-row {
        display: grid;
        grid-template-columns: 120px minmax(0, 1fr);
        gap: 12px;
        align-items: center;
        margin: 8px 0;
      }
      .bar-name {
        overflow-wrap: anywhere;
        font-size: 13px;
        font-weight: 600;
      }
      .bar-button {
        width: 100%;
        min-width: 0;
        height: 44px;
        padding: 0;
        position: relative;
        overflow: hidden;
        border-radius: 6px;
        background: var(--card-background-color);
      }
      .bar-segment {
        position: absolute;
        top: 0;
        bottom: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        white-space: nowrap;
        font-size: 12px;
        border-right: 1px solid var(--divider-color);
      }
      .bar-segment > span {
        position: relative;
        z-index: 2;
        background: inherit;
        padding: 0 2px;
      }
      .bar-axis {
        margin-left: 132px;
        display: flex;
        justify-content: space-between;
        font-size: 11px;
        color: var(--secondary-text-color);
      }
      .now-marker {
        position: absolute;
        top: 0;
        bottom: 0;
        width: 2px;
        background: var(--primary-text-color);
        z-index: 1;
        pointer-events: none;
      }
      .day-overview {
        margin-top: 16px;
      }
      .overview-rows {
        max-height: 640px;
        overflow-y: auto;
        padding: 4px;
      }
      .view-toggle {
        display: flex;
        gap: 8px;
        margin: 16px 0;
      }
      .view-toggle [aria-pressed="true"] {
        border-color: var(--primary-color);
        font-weight: 700;
      }
      @container (max-width:600px) {
        .phone-week {
          display: block;
        }
        .phone-week .bar-row {
          grid-template-columns: 38px minmax(0, 1fr);
          gap: 8px;
        }
        .phone-week .bar-axis {
          margin-left: 46px;
        }
        .day-overview .bar-row {
          grid-template-columns: 72px minmax(0, 1fr);
          gap: 8px;
          margin: 8px 0;
        }
        .day-overview .bar-axis {
          margin-left: 80px;
        }
        .overview-rows {
          max-height: 620px;
        }
        .day-list details {
          display: none;
        }
        .day-list details[open] {
          display: block;
        }
      }
      .toolbar {
        flex-wrap: wrap;
      }
      @container (max-width:600px) {
        .week {
          display: none;
        }
        .block-row {
          grid-template-columns: 1fr 1fr;
        }
        .block-row button {
          grid-column: 2;
        }
        .week-tools button {
          flex: 1;
        }
        .edit-panel .form-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];
  view: "rooms" | "overview" = "rooms";
  overviewDay = "";
  openedDay = "";
  private clockTimer?: ReturnType<typeof setInterval>;
  connectedCallback() {
    super.connectedCallback();
    this.clockTimer = setInterval(() => this.requestUpdate(), 60_000);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.clockTimer);
  }
  status?: Status;
  hass?: Hass;
  writable = false;
  selected = "";
  selectedRoom = "";
  draft?: Schedule;
  error = "";
  saving = false;
  block: { day: string; index: number } | null = null;
  copyFrom: string | null = null;
  deleting = false;
  creating = false;
  copyRooms = false;
  saveSchedule?: (
    schedule: ReturnType<typeof schedulePayload>,
  ) => Promise<string | undefined>;
  deleteSchedule?: (id: string) => Promise<void>;
  activateSchedule?: (id: string) => Promise<void>;
  private baseline = "";
  private serverSnapshot = "";
  private newSource = "";
  private entryId = "";
  private timeInputs = new Map<string, string>();
  protected willUpdate() {
    if (this.entryId !== this.status?.config_entry_id) {
      this.entryId = this.status?.config_entry_id ?? "";
      this.draft = undefined;
      this.selected = "";
      this.selectedRoom = "";
      this.view = "rooms";
      this.overviewDay = "";
      this.openedDay = "";
      this.block = null;
      this.error = "";
      this.copyFrom = null;
      this.deleting = false;
      this.saving = false;
      this.creating = false;
      this.copyRooms = false;
      this.timeInputs.clear();
    }
    if (!this.draft && this.status)
      this.load(this.status.configuration.active_schedule_id);
    if (this.draft && this.status && !this.saving) {
      const config = this.status.configuration;
      if (this.selected && !config.schedules[this.selected]) {
        if (!this.dirty) this.load(config.active_schedule_id);
        return;
      }
      const source = this.selected
        ? config.schedules[this.selected]
        : {
            name: (JSON.parse(this.baseline) as Schedule).name,
            rooms: Object.fromEntries(
              Object.keys(config.rooms).map((id) => [
                id,
                config.schedules[this.newSource]?.rooms[id] ?? defaultWeek(),
              ]),
            ),
          };
      if (source && JSON.stringify(source) !== this.serverSnapshot) {
        if (!this.dirty) this.load(this.selected);
        else {
          const baseline = JSON.parse(this.baseline) as Schedule;
          const rooms = { ...this.draft.rooms };
          for (const id of Object.keys(rooms)) {
            if (!(id in source.rooms)) {
              delete rooms[id];
              delete baseline.rooms[id];
            }
          }
          for (const [id, week] of Object.entries(source.rooms)) {
            // Refresh untouched weeks as well as newly added rooms.
            if (
              JSON.stringify(rooms[id]) === JSON.stringify(baseline.rooms[id])
            ) {
              rooms[id] = structuredClone(week);
              baseline.rooms[id] = structuredClone(week);
            }
          }
          const name =
            this.draft.name === baseline.name ? source.name : this.draft.name;
          if (this.draft.name === baseline.name) baseline.name = source.name;
          this.draft = { ...this.draft, name, rooms };
          this.baseline = JSON.stringify(baseline);
          this.serverSnapshot = JSON.stringify(source);
          if (!(this.selectedRoom in rooms)) {
            this.selectedRoom = Object.keys(rooms)[0] ?? "";
            this.timeInputs.clear();
            this.block = null;
            this.error = "";
          }
        }
      }
    }
  }
  get week() {
    return this.draft?.rooms[this.selectedRoom] ?? defaultWeek();
  }
  get dirty() {
    return (
      !!this.draft &&
      (!this.selected ||
        this.timeInputs.size > 0 ||
        JSON.stringify(this.draft) !== this.baseline)
    );
  }
  private load(id: string) {
    const source = this.status?.configuration.schedules[id];
    if (!source) return;
    this.timeInputs.clear();
    this.selected = id;
    this.draft = structuredClone(source);
    this.baseline = JSON.stringify(this.draft);
    this.serverSnapshot = JSON.stringify(source);
    if (!this.status?.configuration.rooms[this.selectedRoom])
      this.selectedRoom =
        Object.keys(this.status?.configuration.rooms ?? {})[0] ?? "";
    this.error = "";
    this.block = null;
    this.deleting = false;
  }
  private async save() {
    if (!this.draft || !this.writable || this.saving || !this.saveSchedule)
      return;
    const entry = this.entryId;
    this.saving = true;
    this.error = "";
    try {
      if (this.timeInputs.size)
        throw new Error("Correct invalid start times before saving.");
      const payload = schedulePayload(this.draft, this.selected || undefined);
      const saved = structuredClone(this.draft);
      if (this.selected) {
        const baseline = JSON.parse(this.baseline) as Schedule;
        payload.rooms = Object.fromEntries(
          Object.entries(payload.rooms).filter(
            ([id, week]) =>
              JSON.stringify(week) !== JSON.stringify(baseline.rooms[id]),
          ),
        );
      }
      const id = await this.saveSchedule(payload);
      if (entry !== this.entryId) return;
      this.selected = id || this.selected;
      this.draft = { ...saved, name: payload.name };
      this.baseline = JSON.stringify(this.draft);
    } catch (e) {
      if (entry === this.entryId)
        this.error = e instanceof Error ? e.message : String(e);
    } finally {
      if (entry === this.entryId) this.saving = false;
    }
  }
  private async showCopy(day: string) {
    this.copyFrom = day;
    await this.updateComplete;
    this.renderRoot.querySelector<HTMLDialogElement>("#copy-day")?.showModal();
  }
  private async showDialog(kind: "create" | "rooms") {
    if (kind === "create") this.creating = true;
    else this.copyRooms = true;
    await this.updateComplete;
    this.renderRoot
      .querySelector<HTMLDialogElement>(
        kind === "create" ? "#create-schedule" : "#copy-rooms",
      )
      ?.showModal();
  }
  private async activate() {
    if (!this.activateSchedule || !this.writable || this.saving || this.dirty)
      return;
    this.saving = true;
    this.error = "";
    try {
      await this.activateSchedule(this.selected);
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    } finally {
      this.saving = false;
    }
  }
  private clearDayInputs(day: string) {
    for (const key of this.timeInputs.keys())
      if (key.startsWith(`${day}-`)) this.timeInputs.delete(key);
  }
  private change(day: string, blocks: Block[]) {
    if (!this.draft || !this.writable || this.saving) return;
    if (blocks.length !== this.week.days[day].length) {
      this.clearDayInputs(day);
      if (this.block?.day === day) this.block = null;
    }
    this.draft = {
      ...this.draft,
      rooms: {
        ...this.draft.rooms,
        [this.selectedRoom]: {
          days: { ...this.week.days, [day]: blocks },
        },
      },
    };
    this.error = "";
  }
  private editTime(day: string, index: number, event: Event) {
    const input = event.target as HTMLInputElement;
    const key = `${day}-${index}`;
    try {
      const at = minutes(parseScheduleTime(input.value, this.hass?.locale));
      if (at % 5) throw new Error("Times must be on the five-minute grid.");
      const dayBlocks = this.week.days[day];
      const previous = dayBlocks[index - 1]?.start ?? "00:00";
      const next = dayBlocks[index + 1]?.start ?? "24:00";
      const before = next === "24:00" ? 1440 : minutes(next);
      if (index === 0 || at <= minutes(previous) || at >= before)
        throw new Error(
          `Start time must be after ${scheduleTime(previous, this.hass?.locale)}${next === "24:00" ? "" : ` and before ${scheduleTime(next, this.hass?.locale)}`}.`,
        );
      const blocks = dayBlocks.map((block, i) =>
        i === index ? { ...block, start: clock(at) } : block,
      );
      this.timeInputs.delete(key);
      this.change(day, blocks);
    } catch (error) {
      this.timeInputs.set(key, input.value);
      this.error = error instanceof Error ? error.message : String(error);
    }
  }
  private attempt(action: () => void) {
    try {
      action();
      this.error = "";
    } catch (e) {
      this.error = e instanceof Error ? e.message : String(e);
    }
  }
  private color(target: number) {
    const weight = Math.max(12, Math.min(65, (target - 5) * 2.2));
    return `color-mix(in srgb, var(--${target < 19 ? "primary" : "warning"}-color) ${weight}%, var(--card-background-color))`;
  }
  private drag(event: PointerEvent, day: string, index: number) {
    if (!this.writable || this.saving) return;
    event.preventDefault();
    const handle = event.currentTarget as HTMLButtonElement;
    const rect = handle.parentElement!.getBoundingClientRect();
    handle.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => {
      if (e.pointerId !== event.pointerId) return;
      this.change(
        day,
        moveBoundary(
          this.week.days[day],
          index,
          ((e.clientX - rect.left) / rect.width) * 1440,
        ),
      );
    };
    const end = (e: PointerEvent) => {
      if (e.pointerId !== event.pointerId) return;
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", end);
      handle.removeEventListener("pointercancel", end);
      handle.removeEventListener("lostpointercapture", end);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", end);
    handle.addEventListener("pointercancel", end);
    handle.addEventListener("lostpointercapture", end);
  }
  render() {
    const p = this.draft,
      week = this.week;
    const schedules = this.status?.configuration.schedules ?? {};
    const rooms = Object.entries(this.status?.configuration.rooms ?? {});
    const disabled = !this.writable || this.saving;
    const active =
      this.selected === this.status?.configuration.active_schedule_id;
    const protectedDelete = active || Object.keys(schedules).length <= 1;
    const deleteReason =
      Object.keys(schedules).length <= 1
        ? "The last schedule cannot be deleted."
        : active
          ? "The active schedule cannot be deleted. Activate another schedule first."
          : "";
    const missing = !!this.selected && !schedules[this.selected];
    const next = this.status?.rooms[this.selectedRoom]?.next_change;
    return html`<div class="toolbar">
        <div>
          <h2>Schedules</h2>
          <p class="muted">One plan for the house. A week for every room.</p>
        </div>
        ${this.dirty
          ? html`<span class="badge unsaved" role="status"
              >Unsaved changes</span
            >`
          : nothing}
        ${active ? html`<span class="badge">Active schedule</span>` : nothing}
      </div>
      <div class="schedule-tools">
        <select
          aria-label="Schedule"
          .value=${this.selected}
          ?disabled=${this.dirty || this.saving}
          @change=${(e: Event) =>
            this.load((e.target as HTMLSelectElement).value)}
        >
          ${missing
            ? html`<option value=${this.selected} selected>
                Deleted · ${p?.name}
              </option>`
            : nothing}
          ${!this.selected
            ? html`<option value="">New schedule</option>`
            : nothing}
          ${Object.entries(schedules).map(
            ([id, s]) =>
              html`<option value=${id} ?selected=${id === this.selected}>
                ${s.name}
              </option>`,
          )}
        </select>
        <button
          ?disabled=${disabled || this.dirty}
          @click=${() => this.showDialog("create")}
        >
          Create
        </button>
        <button
          ?disabled=${disabled || !p}
          @click=${() =>
            this.renderRoot
              .querySelector<HTMLInputElement>("#schedule-name")
              ?.focus()}
        >
          Rename
        </button>
        <button
          ?disabled=${disabled || this.dirty || !this.selected || active}
          @click=${() => this.activate()}
        >
          Activate
        </button>
        <button
          class="danger"
          ?disabled=${disabled ||
          this.dirty ||
          !this.selected ||
          protectedDelete}
          aria-describedby=${deleteReason ? "delete-reason" : nothing}
          @click=${() => {
            this.deleting = true;
          }}
        >
          Delete
        </button>
      </div>
      ${deleteReason
        ? html`<p id="delete-reason" class="muted">${deleteReason}</p>`
        : nothing}
      ${missing
        ? html`<p role="status">
            This schedule was deleted on another device. Discard changes to open
            the active schedule.
          </p>`
        : nothing}
      ${p
        ? html`<fieldset>
              <div class="field">
                <label for="schedule-name">Schedule name</label
                ><input
                  id="schedule-name"
                  ?disabled=${disabled}
                  maxlength="200"
                  .value=${p.name}
                  @input=${(e: Event) => {
                    this.draft = {
                      ...p,
                      name: (e.target as HTMLInputElement).value,
                    };
                  }}
                />
              </div>
              <div class="view-toggle" aria-label="Schedule view">
                <button
                  aria-pressed=${this.view === "rooms"}
                  @click=${() => {
                    this.view = "rooms";
                  }}
                >
                  Rooms
                </button>
                <button
                  aria-pressed=${this.view === "overview"}
                  @click=${() => {
                    this.view = "overview";
                  }}
                >
                  Overview
                </button>
              </div>
              ${this.overview()}
              <div class="schedule-layout" ?hidden=${this.view !== "rooms"}>
                <div class="room-picker" aria-label="Rooms in schedule">
                  ${rooms.map(
                    ([id, room]) =>
                      html`<button
                        aria-pressed=${this.selectedRoom === id}
                        ?disabled=${this.timeInputs.size > 0}
                        @click=${() => {
                          this.selectedRoom = id;
                          this.block = null;
                          this.timeInputs.clear();
                          this.error = "";
                        }}
                      >
                        ${room.name}
                      </button>`,
                  )}
                </div>
                <div class="week-editor">
                  <fieldset>
                    ${this.selectedRoom
                      ? html`<div class="toolbar">
                            <div>
                              <h3>
                                ${this.status?.configuration.rooms[
                                  this.selectedRoom
                                ]?.name}
                              </h3>
                              <small
                                >${active
                                  ? `Next change: ${time(next, this.hass?.config?.time_zone, this.hass?.locale)}`
                                  : "Activate this schedule to use these weeks."}</small
                              >
                            </div>
                            <button
                              ?disabled=${disabled}
                              @click=${() => this.showDialog("rooms")}
                            >
                              Copy this room’s week to…
                            </button>
                          </div>
                          <div class="legend" aria-label="Temperature legend">
                            ${[10, 18, 21, 25].map(
                              (t) =>
                                html`<span
                                  ><span
                                    class="swatch"
                                    style=${`background:${this.color(t)}`}
                                  ></span
                                  >${temperature(t)}</span
                                >`,
                            )}
                          </div>
                          <div class="phone-week" aria-label="Weekly day bars">
                            <p class="muted">
                              Tap a day to edit its times and temperatures.
                            </p>
                            ${this.barAxis()}
                            ${weekdays.map(
                              (day, i) =>
                                html`<div class="bar-row">
                                  <span class="bar-name"
                                    >${dayNames[i].slice(0, 3)}</span
                                  >
                                  ${this.readBar(
                                    week.days[day],
                                    dayNames[i],
                                    () => this.openDay(day),
                                    undefined,
                                    `day-${day}`,
                                  )}
                                </div>`,
                            )}
                          </div>
                          <fieldset ?disabled=${disabled}>
                            <div class="week" aria-label="Weekly schedule grid">
                              <div class="axis">
                                <span>00:00</span><span>06:00</span
                                ><span>12:00</span><span>18:00</span
                                ><span>24:00</span>
                              </div>
                              ${weekdays.map(
                                (day, i) =>
                                  html`<div class="day">
                                    <span class="day-label"
                                      >${dayNames[i]}</span
                                    >
                                    <div class="track">
                                      ${week.days[day].map((b, j) => {
                                        const start = minutes(b.start),
                                          end =
                                            j + 1 < week.days[day].length
                                              ? minutes(
                                                  week.days[day][j + 1].start,
                                                )
                                              : 1440;
                                        return html` <button
                                            class="schedule-block"
                                            style=${`left:${start / 14.4}%;width:${(end - start) / 14.4}%;background:${this.color(b.target)}`}
                                            aria-label=${`${dayNames[i]} ${b.start} to ${clock(end)} · ${temperature(b.target)}. Arrow keys change temperature.`}
                                            @click=${() => {
                                              this.block = { day, index: j };
                                            }}
                                            @keydown=${(e: KeyboardEvent) => {
                                              if (
                                                [
                                                  "ArrowUp",
                                                  "ArrowDown",
                                                  "ArrowLeft",
                                                  "ArrowRight",
                                                ].includes(e.key)
                                              ) {
                                                e.preventDefault();
                                                this.change(
                                                  day,
                                                  week.days[day].map((x, k) =>
                                                    k === j
                                                      ? {
                                                          ...x,
                                                          target:
                                                            temperatureStep(
                                                              x.target,
                                                              [
                                                                "ArrowUp",
                                                                "ArrowRight",
                                                              ].includes(e.key)
                                                                ? 1
                                                                : -1,
                                                            ),
                                                        }
                                                      : x,
                                                  ),
                                                );
                                              }
                                            }}
                                          >
                                            ${temperature(b.target)}
                                          </button>
                                          ${j
                                            ? html`<button
                                                class="boundary"
                                                style=${`left:${start / 14.4}%`}
                                                aria-label=${`Move ${dayNames[i]} boundary at ${b.start}`}
                                                @pointerdown=${(
                                                  e: PointerEvent,
                                                ) => this.drag(e, day, j)}
                                                @keydown=${(
                                                  e: KeyboardEvent,
                                                ) => {
                                                  if (
                                                    [
                                                      "ArrowLeft",
                                                      "ArrowRight",
                                                    ].includes(e.key)
                                                  ) {
                                                    e.preventDefault();
                                                    this.change(
                                                      day,
                                                      moveBoundary(
                                                        week.days[day],
                                                        j,
                                                        start +
                                                          (e.key ===
                                                          "ArrowRight"
                                                            ? 5
                                                            : -5),
                                                      ),
                                                    );
                                                  }
                                                }}
                                              ></button>`
                                            : nothing}`;
                                      })}
                                      <button
                                        class="split-time"
                                        aria-label=${`Split ${dayNames[i]} at a point on the timeline`}
                                        @click=${(e: MouseEvent) =>
                                          this.attempt(() => {
                                            const rect = (
                                              e.currentTarget as HTMLElement
                                            ).getBoundingClientRect();
                                            const at =
                                              e.detail === 0
                                                ? 720
                                                : ((e.clientX - rect.left) /
                                                    rect.width) *
                                                  1440;
                                            this.change(
                                              day,
                                              splitBlock(week.days[day], at),
                                            );
                                          })}
                                      >
                                        + Tap timeline to split
                                      </button>
                                    </div>
                                  </div>`,
                              )}
                            </div>
                            ${this.blockEditor()}
                            <div class="day-list">
                              <h3>Edit times & copy days</h3>
                              <p class="muted">
                                Five-minute times, half-degree temperatures.
                                Each day starts at 00:00.
                              </p>
                              ${weekdays.map(
                                (day, i) =>
                                  html`<details
                                    id=${`day-${day}`}
                                    @toggle=${(e: Event) => {
                                      if ((e.target as HTMLDetailsElement).open)
                                        this.openedDay = day;
                                      else if (this.openedDay === day)
                                        this.openedDay = "";
                                    }}
                                  >
                                    <summary>
                                      ${dayNames[i]} · ${week.days[day].length}
                                      blocks
                                    </summary>
                                    ${week.days[day].map(
                                      (b, j) =>
                                        html`<div class="block-row">
                                          <div class="field">
                                            <label for=${`start-${day}-${j}`}
                                              >Start time</label
                                            ><input
                                              id=${`start-${day}-${j}`}
                                              aria-invalid=${this.timeInputs.has(
                                                `${day}-${j}`,
                                              )}
                                              type="text"
                                              inputmode="text"
                                              .value=${this.timeInputs.get(
                                                `${day}-${j}`,
                                              ) ??
                                              scheduleTime(
                                                b.start,
                                                this.hass?.locale,
                                              )}
                                              ?disabled=${!j}
                                              @change=${(e: Event) =>
                                                this.editTime(day, j, e)}
                                            />
                                          </div>
                                          <div class="field">
                                            <label for=${`target-${day}-${j}`}
                                              >Temperature °C</label
                                            ><input
                                              id=${`target-${day}-${j}`}
                                              type="number"
                                              min="5"
                                              max="30"
                                              step="0.5"
                                              .value=${String(b.target)}
                                              @change=${(e: Event) =>
                                                this.change(
                                                  day,
                                                  week.days[day].map((x, k) =>
                                                    k === j
                                                      ? {
                                                          ...x,
                                                          target: Number(
                                                            (
                                                              e.target as HTMLInputElement
                                                            ).value,
                                                          ),
                                                        }
                                                      : x,
                                                  ),
                                                )}
                                            />
                                          </div>
                                          <button
                                            ?disabled=${!j}
                                            @click=${() => {
                                              this.change(
                                                day,
                                                removeBlock(week.days[day], j),
                                              );
                                              this.block = null;
                                            }}
                                          >
                                            Remove<span class="sr-only">
                                              ${dayNames[i]} ${b.start}</span
                                            >
                                          </button>
                                        </div>`,
                                    )}
                                    <div class="actions">
                                      <button
                                        @click=${() =>
                                          this.attempt(() => {
                                            this.change(
                                              day,
                                              splitBlock(
                                                week.days[day],
                                                minutes(
                                                  week.days[day].at(-1)!.start,
                                                ) + 5,
                                              ),
                                            );
                                          })}
                                      >
                                        Add block</button
                                      ><button
                                        @click=${() => this.showCopy(day)}
                                      >
                                        Copy day to…
                                      </button>
                                    </div>
                                  </details>`,
                              )}
                            </div>
                          </fieldset> `
                      : html`<div class="empty">
                          Add a room to set up its week in every schedule.
                        </div>`}
                  </fieldset>
                </div>
              </div>
            </fieldset>
            ${this.error
              ? html`<div class="inline-error" role="alert">${this.error}</div>`
              : nothing}
            <div class="actions">
              <button
                ?disabled=${this.saving || !this.dirty}
                @click=${() =>
                  this.load(
                    (this.status!.configuration.schedules[this.selected]
                      ? this.selected
                      : "") || this.status!.configuration.active_schedule_id,
                  )}
              >
                Discard changes</button
              ><button
                id="save-schedule"
                class="primary"
                ?disabled=${disabled || !this.dirty || missing}
                @click=${() => this.save()}
              >
                ${this.saving ? "Saving…" : "Save schedule"}
              </button>
            </div>
            ${this.deleting
              ? html`<div class="delete-confirm" role="alert">
                  <h3>Delete ${p.name}?</h3>
                  <p>
                    ${protectedDelete
                      ? Object.keys(schedules).length <= 1
                        ? "The last schedule cannot be deleted."
                        : "The active schedule cannot be deleted. Activate another schedule first."
                      : "This removes all room weeks in this schedule."}
                  </p>
                  <div class="actions">
                    <button
                      @click=${() => {
                        this.deleting = false;
                      }}
                    >
                      Keep schedule</button
                    >${!protectedDelete
                      ? html`<button
                          class="danger"
                          ?disabled=${disabled}
                          @click=${async () => {
                            if (!this.deleteSchedule || disabled) return;
                            const entry = this.entryId;
                            this.saving = true;
                            try {
                              await this.deleteSchedule(this.selected);
                              if (entry === this.entryId) {
                                this.draft = undefined;
                                this.deleting = false;
                              }
                            } catch (e) {
                              if (entry === this.entryId)
                                this.error =
                                  e instanceof Error ? e.message : String(e);
                            } finally {
                              if (entry === this.entryId) this.saving = false;
                            }
                          }}
                        >
                          Confirm delete
                        </button>`
                      : nothing}
                  </div>
                </div>`
              : nothing} `
        : nothing}
      ${this.copyDialog()}${this.createDialog()}${this.copyRoomsDialog()}`;
  }
  private barAxis() {
    return html`<div class="bar-axis" aria-hidden="true">
      <span>00:00</span><span>06</span><span>12</span><span>18</span
      ><span>24:00</span>
    </div>`;
  }
  private async openDay(day: string) {
    this.openedDay = day;
    await this.updateComplete;
    for (const details of this.renderRoot.querySelectorAll<HTMLDetailsElement>(
      ".day-list details",
    ))
      details.open = details.id === `day-${day}`;
    const panel = this.renderRoot.querySelector<HTMLDetailsElement>(
      `#day-${day}`,
    );
    panel?.scrollIntoView?.({ block: "nearest", behavior: "instant" });
    panel?.querySelector<HTMLElement>("summary")?.focus();
  }
  private readBar(
    blocks: Block[],
    label: string,
    action: () => void,
    now?: number,
    controls?: string,
  ) {
    let layout: ReturnType<typeof barLayout>;
    try {
      layout = barLayout(blocks);
    } catch {
      return html`<span class="muted"
        >Correct this day’s values to preview its bar.</span
      >`;
    }
    return html`<button
      class="bar-button"
      aria-label=${`${label}: ${layout.map((b) => `${b.start}–${clock(b.end)} ${temperature(b.target)}`).join(", ")}. Open day editor.`}
      aria-controls=${controls ?? nothing}
      aria-expanded=${controls
        ? String(this.openedDay === controls.slice(4))
        : nothing}
      @click=${action}
    >
      ${layout.map(
        (b) =>
          html`<span
            class="bar-segment"
            title=${`${b.start}–${clock(b.end)} · ${temperature(b.target)}`}
            style=${`left:${b.left}%;width:${b.width}%;background:${this.color(b.target)}`}
          >
            ${b.width >= 14
              ? html`<span>${temperature(b.target)}</span>`
              : nothing}
          </span>`,
      )}
      ${now !== undefined
        ? html`<span
            class="now-marker"
            style=${`left:${now / 14.4}%`}
            title=${`Now · ${clock(now)}`}
          ></span>`
        : nothing}
    </button>`;
  }
  private overview() {
    const clockNow = houseClock(new Date(), this.hass?.config?.time_zone);
    const day = this.overviewDay || clockNow.day;
    const now =
      this.selected === this.status?.configuration.active_schedule_id &&
      day === clockNow.day
        ? clockNow.minute
        : undefined;
    return html`<section
      class="day-overview"
      ?hidden=${this.view !== "overview"}
      aria-label="Whole-house day overview"
    >
      <div class="field">
        <label for="overview-day">Day</label
        ><select
          id="overview-day"
          .value=${day}
          @change=${(e: Event) => {
            this.overviewDay = (e.target as HTMLSelectElement).value;
          }}
        >
          ${weekdays.map(
            (key, i) =>
              html`<option value=${key} ?selected=${key === day}>
                ${dayNames[i]}
              </option>`,
          )}
        </select>
      </div>
      <p class="muted">
        ${this.draft?.name} · Tap a room to open its
        week.${now !== undefined
          ? ` Now ${clock(now)} (Home Assistant time).`
          : ""}
      </p>
      <div class="legend" aria-label="Temperature legend">
        ${[10, 18, 21, 25].map(
          (t) =>
            html`<span
              ><span
                class="swatch"
                style=${`background:${this.color(t)}`}
              ></span
              >${temperature(t)}</span
            >`,
        )}
      </div>
      ${this.barAxis()}
      <div class="overview-rows">
        ${Object.entries(this.status?.configuration.rooms ?? {}).map(
          ([id, room]) =>
            html`<div class="bar-row" data-room=${id}>
              <span class="bar-name">${room.name}</span>
              ${this.readBar(
                this.draft?.rooms[id]?.days[day] ?? defaultWeek().days[day],
                room.name,
                () => {
                  if (this.timeInputs.size) {
                    this.error =
                      "Correct invalid start times before switching rooms.";
                    return;
                  }
                  this.selectedRoom = id;
                  this.block = null;
                  this.view = "rooms";
                  void this.openDay(day);
                },
                now,
              )}
            </div>`,
        )}
      </div>
    </section>`;
  }
  private blockEditor() {
    if (!this.block || !this.draft) return nothing;
    const { day, index } = this.block;
    const b = this.week.days[day][index];
    if (!b) return nothing;
    return html`<section
      class="panel edit-panel"
      aria-label="Edit schedule block"
    >
      <div class="toolbar">
        <h3>
          ${dayNames[weekdays.indexOf(day as (typeof weekdays)[number])]} ·
          ${b.start}
        </h3>
        <button
          aria-label="Close block editor"
          @click=${() => {
            this.block = null;
          }}
        >
          Close
        </button>
      </div>
      <div class="form-grid">
        <div class="field">
          <label for="block-start">Start time</label
          ><input
            id="block-start"
            aria-invalid=${this.timeInputs.has(`${day}-${index}`)}
            type="text"
            inputmode="text"
            .value=${this.timeInputs.get(`${day}-${index}`) ??
            scheduleTime(b.start, this.hass?.locale)}
            ?disabled=${!index}
            @change=${(e: Event) => this.editTime(day, index, e)}
          />
        </div>
        <div class="field">
          <label for="block-target">Temperature °C</label
          ><input
            id="block-target"
            type="number"
            min="5"
            max="30"
            step="0.5"
            .value=${String(b.target)}
            @change=${(e: Event) =>
              this.change(
                day,
                this.week.days[day].map((x, j) =>
                  j === index
                    ? {
                        ...x,
                        target: Number((e.target as HTMLInputElement).value),
                      }
                    : x,
                ),
              )}
          />
        </div>
      </div>
      <div class="actions">
        <button
          ?disabled=${!index}
          @click=${() => {
            this.change(day, removeBlock(this.week.days[day], index));
            this.block = null;
          }}
        >
          Remove block</button
        ><button @click=${() => this.showCopy(day)}>Copy day to…</button>
      </div>
    </section>`;
  }
  private copyDialog() {
    if (!this.copyFrom) return nothing;
    return html`<dialog
      id="copy-day"
      @close=${() => {
        this.copyFrom = null;
      }}
    >
      <h2>
        Copy
        ${dayNames[
          weekdays.indexOf(this.copyFrom as (typeof weekdays)[number])
        ]}
        to…
      </h2>
      <p class="muted">Replace the selected days. Save the week to apply.</p>
      <form
        @submit=${(e: SubmitEvent) => {
          e.preventDefault();
          if (!this.writable || this.saving) return;
          const data = new FormData(e.target as HTMLFormElement);
          for (const day of data.getAll("days").map(String))
            this.clearDayInputs(day);
          this.block = null;
          this.error = "";
          this.draft = {
            ...this.draft!,
            rooms: {
              ...this.draft!.rooms,
              [this.selectedRoom]: copyDay(
                this.week,
                this.copyFrom!,
                data.getAll("days").map(String),
              ),
            },
          };
          this.renderRoot
            .querySelector<HTMLDialogElement>("#copy-day")
            ?.close();
        }}
      >
        <fieldset ?disabled=${!this.writable || this.saving}>
          ${weekdays.map(
            (day, i) =>
              html`<label class="check"
                ><input
                  type="checkbox"
                  name="days"
                  value=${day}
                  ?disabled=${day === this.copyFrom}
                />${dayNames[i]}</label
              >`,
          )}
        </fieldset>
        <div class="actions">
          <button
            type="button"
            @click=${() =>
              this.renderRoot
                .querySelector<HTMLDialogElement>("#copy-day")
                ?.close()}
          >
            Cancel</button
          ><button
            class="primary"
            ?disabled=${!this.writable || this.saving}
            type="submit"
          >
            Copy selected days
          </button>
        </div>
      </form>
    </dialog>`;
  }
  private createDialog() {
    if (!this.creating) return nothing;
    return html`<dialog
      id="create-schedule"
      @close=${() => {
        this.creating = false;
      }}
    >
      <h2>Create schedule</h2>
      <p class="muted">
        Copy a whole-house plan or start every room at 18° all day.
      </p>
      <form
        @submit=${(e: SubmitEvent) => {
          e.preventDefault();
          if (!this.writable || this.saving) return;
          const data = new FormData(e.target as HTMLFormElement);
          const source = String(data.get("source"));
          this.selected = "";
          this.timeInputs.clear();
          this.block = null;
          this.draft = {
            name: String(data.get("name")).trim(),
            rooms: source
              ? structuredClone(
                  this.status!.configuration.schedules[source].rooms,
                )
              : Object.fromEntries(
                  Object.keys(this.status!.configuration.rooms).map((id) => [
                    id,
                    defaultWeek(),
                  ]),
                ),
          };
          this.newSource = source;
          this.baseline = JSON.stringify(this.draft);
          this.serverSnapshot = "";
          this.error = "";
          this.renderRoot
            .querySelector<HTMLDialogElement>("#create-schedule")
            ?.close();
        }}
      >
        <fieldset ?disabled=${!this.writable || this.saving}>
          <div class="field">
            <label for="new-schedule-name">Schedule name</label
            ><input
              id="new-schedule-name"
              name="name"
              required
              maxlength="200"
              placeholder="New schedule"
            />
          </div>
          <div class="field">
            <label for="schedule-source">Start from</label
            ><select
              id="schedule-source"
              name="source"
              .value=${this.status?.configuration.active_schedule_id ?? ""}
            >
              ${Object.entries(this.status?.configuration.schedules ?? {}).map(
                ([id, s]) =>
                  html`<option
                    value=${id}
                    ?selected=${id ===
                    this.status?.configuration.active_schedule_id}
                  >
                    ${s.name}
                  </option>`,
              )}
              <option value="">Blank · 18° all day</option>
            </select>
          </div>
          <div class="actions">
            <button
              type="button"
              @click=${() =>
                this.renderRoot
                  .querySelector<HTMLDialogElement>("#create-schedule")
                  ?.close()}
            >
              Cancel</button
            ><button type="submit" class="primary">Create draft</button>
          </div>
        </fieldset>
      </form>
    </dialog>`;
  }
  private copyRoomsDialog() {
    if (!this.copyRooms) return nothing;
    return html`<dialog
      id="copy-rooms"
      @close=${() => {
        this.copyRooms = false;
      }}
    >
      <h2>Copy this room’s week to…</h2>
      <p class="muted">
        Replace the selected room weeks in ${this.draft?.name}. Save the
        schedule to apply.
      </p>
      <form
        @submit=${(e: SubmitEvent) => {
          e.preventDefault();
          if (!this.writable || this.saving) return;
          const data = new FormData(e.target as HTMLFormElement);
          const rooms = { ...this.draft!.rooms };
          for (const id of data.getAll("rooms").map(String))
            rooms[id] = structuredClone(this.week);
          this.draft = { ...this.draft!, rooms };
          this.renderRoot
            .querySelector<HTMLDialogElement>("#copy-rooms")
            ?.close();
        }}
      >
        <fieldset ?disabled=${!this.writable || this.saving}>
          ${Object.entries(this.status?.configuration.rooms ?? {}).map(
            ([id, room]) =>
              html`<label class="check"
                ><input
                  name="rooms"
                  type="checkbox"
                  value=${id}
                  ?disabled=${id === this.selectedRoom}
                />${room.name}</label
              >`,
          )}
          <div class="actions">
            <button
              type="button"
              @click=${() =>
                this.renderRoot
                  .querySelector<HTMLDialogElement>("#copy-rooms")
                  ?.close()}
            >
              Cancel</button
            ><button class="primary" type="submit">Copy selected rooms</button>
          </div>
        </fieldset>
      </form>
    </dialog>`;
  }
}
if (!customElements.get("heating-schedules"))
  customElements.define("heating-schedules", HeatingSchedules);
