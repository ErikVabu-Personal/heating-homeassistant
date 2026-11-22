import { LitElement, html, nothing, css } from "lit";
import { styles } from "./styles";
import {
  defaultProfile,
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
  profilePayload,
  splitBlock,
  removeBlock,
  moveBoundary,
  copyDay,
  temperatureStep,
} from "./schedule";
import type { Block } from "./schedule";
import type { Hass, Profile, Status } from "./types";
export class HeatingSchedules extends LitElement {
  static properties = {
    status: { attribute: false },
    hass: { attribute: false },
    writable: { type: Boolean },
    selected: { state: true },
    draft: { state: true },
    error: { state: true },
    saving: { state: true },
    block: { state: true },
    copyFrom: { state: true },
    deleting: { state: true },
  };
  static styles = [
    styles,
    css`
      :host {
        container-type: inline-size;
      }
      .profile-tools {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 16px 0;
      }
      .profile-tools select {
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
      .profile-meta {
        margin: 12px 0;
      }
      .profile-meta p {
        margin: 4px 0;
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
        .profile-tools button {
          flex: 1;
        }
        .edit-panel .form-grid {
          grid-template-columns: 1fr;
        }
      }
    `,
  ];
  status?: Status;
  hass?: Hass;
  writable = false;
  selected = "";
  draft?: Profile;
  error = "";
  saving = false;
  block: { day: string; index: number } | null = null;
  copyFrom: string | null = null;
  deleting = false;
  saveProfile?: (
    profile: ReturnType<typeof profilePayload>,
  ) => Promise<string | undefined>;
  deleteProfile?: (id: string) => Promise<void>;
  private baseline = "";
  private timeInputs = new Map<string, string>();
  private entryId = "";
  protected willUpdate() {
    if (this.entryId !== this.status?.config_entry_id) {
      this.entryId = this.status?.config_entry_id ?? "";
      this.draft = undefined;
      this.selected = "";
      this.block = null;
      this.error = "";
      this.copyFrom = null;
      this.deleting = false;
      this.saving = false;
    }
    if (!this.draft && this.status) {
      const id = Object.keys(this.status.configuration.profiles)[0];
      if (id) this.load(id);
    }
  }
  get dirty() {
    return (
      !!this.draft &&
      (this.timeInputs.size > 0 || JSON.stringify(this.draft) !== this.baseline)
    );
  }
  private load(id: string) {
    const source = this.status?.configuration.profiles[id];
    if (!source) return;
    this.timeInputs.clear();
    this.selected = id;
    this.draft = structuredClone(source);
    this.baseline = JSON.stringify(this.draft);
    this.error = "";
    this.block = null;
    this.deleting = false;
  }
  private newProfile(copy = false) {
    this.timeInputs.clear();
    this.selected = "";
    this.draft =
      copy && this.draft
        ? structuredClone(this.draft)
        : defaultProfile("New profile");
    if (copy) this.draft.name += " copy";
    this.baseline = "";
    this.error = "";
    this.block = null;
    this.deleting = false;
  }
  private clearDayInputs(day: string) {
    for (const key of this.timeInputs.keys())
      if (key.startsWith(`${day}-`)) this.timeInputs.delete(key);
  }
  private change(day: string, blocks: Block[]) {
    if (!this.draft || !this.writable || this.saving) return;
    if (blocks.length !== this.draft.days[day].length) {
      this.clearDayInputs(day);
      if (this.block?.day === day) this.block = null;
    }
    this.draft = { ...this.draft, days: { ...this.draft.days, [day]: blocks } };
    this.error = "";
  }
  private editTime(day: string, index: number, event: Event) {
    const input = event.target as HTMLInputElement;
    const key = `${day}-${index}`;
    try {
      const at = minutes(parseScheduleTime(input.value, this.hass?.locale));
      if (at % 5) throw new Error("Times must be on the five-minute grid.");
      const dayBlocks = this.draft!.days[day];
      const previous = dayBlocks[index - 1]?.start ?? "00:00";
      const next = dayBlocks[index + 1]?.start ?? "24:00";
      const before = next === "24:00" ? 1440 : minutes(next);
      if (index === 0 || at <= minutes(previous) || at >= before)
        throw new Error(
          `Start time must be after ${previous} and before ${next}.`,
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
  private async save() {
    if (!this.draft || !this.writable || this.saving || !this.saveProfile)
      return;
    const entry = this.entryId;
    this.saving = true;
    this.error = "";
    try {
      if (this.timeInputs.size)
        throw new Error("Correct invalid start times before saving.");
      const payload = profilePayload(this.draft, this.selected || undefined);
      const id = await this.saveProfile(payload);
      if (entry !== this.entryId) return;
      this.selected = id || this.selected;
      this.draft = { name: payload.name, days: payload.days };
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
          this.draft!.days[day],
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
    const p = this.draft;
    const profiles = this.status?.configuration.profiles ?? {};
    const rooms = Object.entries(this.status?.configuration.rooms ?? {}).filter(
      ([, r]) => r.profile_id === this.selected,
    );
    const disabled = !this.writable || this.saving;
    const next = rooms
      .map(([id]) => this.status?.rooms[id]?.next_change)
      .filter((x): x is string => !!x)
      .sort((a, b) => Date.parse(a) - Date.parse(b))[0];
    return html`<div class="toolbar">
        <div>
          <h2>Weekly schedules</h2>
          <p class="muted">A comfortable rhythm for every day.</p>
        </div>
        ${this.dirty
          ? html`<span class="badge unsaved" role="status"
              >Unsaved changes</span
            >`
          : html`<span class="badge">Saved profiles</span>`}
      </div>
      <div class="profile-tools">
        <select
          aria-label="Heating profile"
          .value=${this.selected}
          ?disabled=${this.dirty || this.saving}
          @change=${(e: Event) =>
            this.load((e.target as HTMLSelectElement).value)}
        >
          ${!this.selected
            ? html`<option value="">New profile</option>`
            : nothing}
          ${Object.entries(profiles).map(
            ([id, p]) => html`<option value=${id}>${p.name}</option>`,
          )}
        </select>
        <button
          ?disabled=${disabled || this.dirty}
          @click=${() => this.newProfile()}
        >
          Create profile
        </button>
        <button
          ?disabled=${disabled || this.dirty || !p}
          @click=${() => this.newProfile(true)}
        >
          Copy profile
        </button>
      </div>
      ${p
        ? html`<fieldset ?disabled=${disabled}>
              <div class="form-grid">
                <div class="field">
                  <label for="profile-name">Profile name</label
                  ><input
                    id="profile-name"
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
                <div class="profile-meta">
                  <p>
                    <strong>Used by:</strong> ${rooms
                      .map(([, r]) => r.name)
                      .join(", ") || "No rooms assigned"}
                  </p>
                  <small
                    >Next room change:
                    ${next
                      ? time(
                          next,
                          this.hass?.config?.time_zone,
                          this.hass?.locale,
                        )
                      : "No upcoming change"}</small
                  >
                </div>
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
              <div class="week" aria-label="Weekly schedule grid">
                <div class="axis">
                  <span>00:00</span><span>06:00</span><span>12:00</span
                  ><span>18:00</span><span>24:00</span>
                </div>
                ${weekdays.map(
                  (day, i) =>
                    html`<div class="day">
                      <span class="day-label">${dayNames[i]}</span>
                      <div class="track">
                        ${p.days[day].map((b, j) => {
                          const start = minutes(b.start),
                            end =
                              j + 1 < p.days[day].length
                                ? minutes(p.days[day][j + 1].start)
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
                                    p.days[day].map((x, k) =>
                                      k === j
                                        ? {
                                            ...x,
                                            target: temperatureStep(
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
                                  @pointerdown=${(e: PointerEvent) =>
                                    this.drag(e, day, j)}
                                  @keydown=${(e: KeyboardEvent) => {
                                    if (
                                      ["ArrowLeft", "ArrowRight"].includes(
                                        e.key,
                                      )
                                    ) {
                                      e.preventDefault();
                                      this.change(
                                        day,
                                        moveBoundary(
                                          p.days[day],
                                          j,
                                          start +
                                            (e.key === "ArrowRight" ? 5 : -5),
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
                                  : ((e.clientX - rect.left) / rect.width) *
                                    1440;
                              this.change(day, splitBlock(p.days[day], at));
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
                  Five-minute times, half-degree temperatures. Each day starts
                  at 00:00.
                </p>
                ${weekdays.map(
                  (day, i) =>
                    html`<details>
                      <summary>
                        ${dayNames[i]} · ${p.days[day].length} blocks
                      </summary>
                      ${p.days[day].map(
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
                                .value=${this.timeInputs.get(`${day}-${j}`) ??
                                scheduleTime(b.start, this.hass?.locale)}
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
                                    p.days[day].map((x, k) =>
                                      k === j
                                        ? {
                                            ...x,
                                            target: Number(
                                              (e.target as HTMLInputElement)
                                                .value,
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
                                this.change(day, removeBlock(p.days[day], j));
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
                                  p.days[day],
                                  minutes(p.days[day].at(-1)!.start) + 5,
                                ),
                              );
                            })}
                        >
                          Add block</button
                        ><button @click=${() => this.showCopy(day)}>
                          Copy day to…
                        </button>
                      </div>
                    </details>`,
                )}
              </div>
            </fieldset>
            ${this.error
              ? html`<div class="inline-error" role="alert">${this.error}</div>`
              : nothing}
            <div class="actions">
              <button
                class="danger"
                ?disabled=${disabled || !this.selected || this.dirty}
                @click=${() => {
                  this.deleting = true;
                }}
              >
                Delete profile</button
              ><button
                ?disabled=${this.saving || !this.dirty}
                @click=${() => {
                  const id = this.selected || Object.keys(profiles)[0];
                  if (id) this.load(id);
                  else {
                    this.draft = undefined;
                    this.baseline = "";
                  }
                }}
              >
                Discard changes</button
              ><button
                class="primary"
                id="save-profile"
                ?disabled=${disabled || !this.dirty}
                @click=${() => this.save()}
              >
                ${this.saving ? "Saving…" : "Save profile"}
              </button>
            </div>
            ${this.deleting
              ? html`<div class="delete-confirm" role="alert">
                  <h3>Delete ${p.name}?</h3>
                  ${rooms.length
                    ? html`<p>
                        Cannot delete a profile used by:
                        ${rooms.map(([, r]) => r.name).join(", ")}. Assign those
                        rooms to another profile first.
                      </p>`
                    : html`<p>This removes the saved weekly profile.</p>`}
                  <div class="actions">
                    <button
                      @click=${() => {
                        this.deleting = false;
                      }}
                    >
                      Keep profile</button
                    >${!rooms.length
                      ? html`<button
                          class="danger"
                          ?disabled=${disabled}
                          @click=${async () => {
                            if (!this.deleteProfile || disabled) return;
                            this.saving = true;
                            this.error = "";
                            try {
                              await this.deleteProfile(this.selected);
                              this.selected = "";
                              this.draft = undefined;
                              this.deleting = false;
                            } catch (e) {
                              this.error =
                                e instanceof Error ? e.message : String(e);
                            } finally {
                              this.saving = false;
                            }
                          }}
                        >
                          Confirm delete
                        </button>`
                      : nothing}
                  </div>
                </div>`
              : nothing} `
        : html`<div class="empty">
            No profiles yet. Create a profile to plan the week.
          </div>`}
      ${this.copyDialog()}`;
  }
  private blockEditor() {
    if (!this.block || !this.draft) return nothing;
    const { day, index } = this.block;
    const b = this.draft.days[day][index];
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
                this.draft!.days[day].map((x, j) =>
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
            this.change(day, removeBlock(this.draft!.days[day], index));
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
      <p class="muted">Replace the selected days. Save the profile to apply.</p>
      <form
        @submit=${(e: SubmitEvent) => {
          e.preventDefault();
          if (!this.writable || this.saving) return;
          const data = new FormData(e.target as HTMLFormElement);
          for (const day of data.getAll("days").map(String))
            this.clearDayInputs(day);
          this.block = null;
          this.error = "";
          this.draft = copyDay(
            this.draft!,
            this.copyFrom!,
            data.getAll("days").map(String),
          );
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
}
if (!customElements.get("heating-schedules"))
  customElements.define("heating-schedules", HeatingSchedules);
