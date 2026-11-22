# Central Heating: design (v1)

**Status:** implementation in progress; PR 2 review decisions incorporated.

## 1. Goal

One Home Assistant integration that does three things:
- controls a central-heating boiler from the demand of per-room radiator thermostats (TRVs);
- runs whole-house schedules with a separate week for every room;
- ships its own dashboard card to set up and run both.

It replaces a hand-written YAML package (a room group, template sensors, a filter sensor, two `input_number`
helpers and three automations), the Scheduler integration and its card, and a summer/winter `input_select`.

### Not in v1
- **Flow-temperature optimisation:** weather or room compensation of the boiler's water temperature. It's a
  likely v2 feature, which is why the boiler connection is kept separate (§5.3).
- **Domestic hot water:** the boiler controller keeps handling it on its own.
- **Other heaters,** such as air conditioners or heat pumps.
- **More than one boiler per instance.** Several instances are allowed (one per boiler), but nothing coordinates
  them.

### Alternatives considered
- **Versatile Thermostat with the Scheduler card:** still two integrations, and Versatile Thermostat doesn't drive
  a controller through a single virtual room temperature and setpoint (§5.1).
- **Keeping the package:** it works, but its logic is spread over six places, its tuning helpers can't really be
  tuned, and the schedules can't express different times per weekday without being copied.

## 2. Terms

| Term | Meaning |
|---|---|
| TRV | A physical radiator `climate` entity reporting current and target temperatures. |
| Room | A named group of physical TRVs sharing a target. |
| Schedule | A user-created whole-house week plan, for example Winter, Autumn or Spring. Exactly one is active. |
| Room week | Each room's seven days inside each schedule. Each day has ordered blocks starting at 00:00. |
| Block | A start time and target, effective until the next block. Starts are on a five-minute grid; targets are 5–30° in 0.5° steps. |
| Override | A temporary room target, with next-change or duration expiry, that wins over its scheduled target in Schedule/Away. |
| Mode | Schedule (`schedule`), Away (`away`), Off (`off`) or Manual (`manual`). |
| Demand | A TRV whose target exceeds current temperature by more than hysteresis. |
| Boiler adapter | Sends one computed command to the boiler controller; DIYLESS MQTT is the first adapter. |

## 3. Behaviour that must match the current package

The boiler logic below is an exact port of the package it replaces, so that shadow mode (§9) can compare the two
directly. Section 5 gives the full rules.

| Item | Package today | v1 |
|---|---|---|
| Recalculation | every 10 s (trigger template) | every 10 s, and on every TRV state change |
| Demand | `target − current > hysteresis` (raw floats) | the same, but **rounded** (§5.1). The raw float version counts a room exactly at `target − hysteresis` as demand: `21.0 − 20.7 = 0.30000000000000071`, which is more than `0.3`. |
| Virtual temperature (raw) | the mean of the demanding TRVs; with none demanding, the mean of all available TRVs | the same |
| Smoothing | HA `filter`: outlier (window 4, radius 1.5), then low-pass (time constant 30 samples, precision 2) | the same outlier step, then a **time-based** low-pass (§5.2). Within ±0.1 °C of the package is accepted in shadow mode. |
| Virtual setpoint | the maximum target among the demanding TRVs (1 decimal); with none, the frost setpoint | the same |
| Boiler mode | `heat` if demand > 0, else `off` | the same, plus forced boiler `off` in Off mode |
| Sending | on change, plus every 30 s | the same |
| Controller temperature source | `tempSource = 1` at start-up and every 6 h | the same |
| Frost setpoint, hysteresis | YAML `input_number` with `initial:`, so read-only and reset on every restart | stored settings, editable in the card and as `number` entities, kept across restarts |

## 4. Architecture

```
            TRV states ──────────────┐
                                     ▼
 card ⇄ websocket API ⇄ ┌──────────────────────────┐
 services ─────────────▶│  engine (per config entry)│──▶ climate.set_temperature on TRVs
                        │  ├ demand (pure)          │
                        │  ├ smoothing (pure)       │
                        │  ├ schedule (pure)        │
                        │  └ overrides, mode        │
                        └────────────┬─────────────┘
                                     │ BoilerCommand
                                     ▼
                        boiler adapter (DIYLESS MQTT) ──▶ mqtt.publish
                                     │
                        entities: room climates, mode select, sensors, numbers, shadow switch
```

- **Pure logic modules** (`demand.py`, `smoothing.py`, `schedule.py`) have no Home Assistant imports and are
  unit-tested on their own.
- **The engine** wires the pure logic to Home Assistant: state listeners, timers, storage, the adapter and
  entities.
- **Configuration is split in two:**
  - the config flow holds only the boiler adapter and its connection details;
  - rooms, schedules, mode and tuning settings live in a `Store` and are edited through the card (websocket API)
    or services.

## 5. Boiler control

### 5.1 Demand, virtual temperature and setpoint
For each TRV in any enabled room, with `c` = `current_temperature` and `t` = target (`temperature`).
Anything that isn't a finite number (an int, a float or a numeric string, excluding booleans) counts as missing.

- **Demanding:** `c` and `t` are both available, and `round(t − c, 2) > round(hysteresis, 2)`.
- `demand_count` is the number of demanding TRVs.
- **`virtual_temp_raw`:**
  - the mean of `c` over the demanding TRVs, if there are any;
  - otherwise the mean of `c` over all TRVs where `c` is available;
  - otherwise unknown.
  - Rounded to 2 decimals.
- **`virtual_setpoint`:** `round(max(t of demanding TRVs), 1)` if there are any, otherwise `frost_temperature`.

Defaults: `hysteresis` 0.3 °C (allowed 0.1–1.0, step 0.1); `frost_temperature` 16 °C (allowed 5–18, step 0.5).

### 5.2 Smoothing
`virtual_temp` = smoothed `virtual_temp_raw`. The low-pass filter is time-based, so it doesn't depend on how often
the raw value happens to change.

1. **Outlier rejection:** sample only when the raw virtual temperature changes, as HA `filter` did.
   Repeated raw values retain the previous accepted low-pass input; the time-based low-pass still updates on
   every recalculation. Keep a window of the last 4 changed raw values, rejected ones included; a value is only
   rejected once the window is full. If a new value differs from the previous window's median by more than
   1.5 °C, use the median instead for the low-pass input, while storing the raw sample in the window.
2. **Low-pass:** `y ← y + (x − y) · (1 − e^(−Δt/τ))`, with τ = 300 s and Δt the seconds since the last update. The
   first value initialises `y`. Rounded to 2 decimals. The engine passes a monotonic clock; a negative Δt
   is treated as zero, retaining `y` and updating the timestamp.
3. **Unknown raw value:** smoothing state is kept, and nothing is sent (§5.4).

### 5.3 Boiler adapter
```python
@dataclass(frozen=True)
class BoilerCommand:
    heat: bool                  # demand_count > 0 and mode != "off"
    room_temperature: float | None   # virtual_temp; None when unknown
    setpoint: float             # virtual_setpoint

class BoilerAdapter(Protocol):
    last_success: bool           # whether the latest operation was delivered
    async def async_start(self) -> None: ...
    async def async_apply(self, cmd: BoilerCommand, *, keepalive: bool) -> None: ...
    async def async_stop(self, *, unloading: bool) -> None: ...
```
Recalculation and publishing do nothing until `hass.state is CoreState.running`.
The engine builds a `BoilerCommand` on every recalculation and calls `async_apply` when the command changes, and
every 30 s with `keepalive=True`.

**v1 adapter: `diyless_mqtt`.** Topic prefix default: `diyless_thermostat/cmnd/things/thermostat/properties`, no
trailing slash. It's configurable.

| When | Topic (under the prefix) | Payload |
|---|---|---|
| Start, then every 6 h | `tempSource` | `1` |
| Change or keep-alive, if `room_temperature` is known | `temperature` | `room_temperature`, 2 decimals |
| Change or keep-alive | `targetTemperature` | `setpoint`, 1 decimal |
| Change or keep-alive | `mode` | `heat` or `off` |

- **Delivery:** QoS 0, retain false, the same as the package.
- **Before sending:** check that the MQTT integration is loaded. If it isn't, log once per unavailable transition and raise a Repairs issue,
  instead of failing.
- **Unloading:** when the config entry is unloaded or removed (not when Home Assistant shuts down), and shadow mode
  is off, send `mode = off` once. A controller left with a stale temperature and setpoint must not keep heating.
  Nothing is sent on shutdown, because a restart resumes within seconds.

### 5.4 Shadow mode
- A `switch` entity, stored; **on by default when an entry is created.**
- While it's on, the adapter is never called. The command that would have been sent is shown on the
  `binary_sensor` and in diagnostics.
- Shadow mode doesn't change schedule writes to TRVs; `manual` mode does that (§6.2). During migration, use
  shadow mode together with `manual` mode, so a new install changes nothing until it's switched on.

## 6. Rooms, schedules, modes and overrides

### 6.1 Data model (Store version 1, minor version 4)

```jsonc
{
  "shadow": true,
  "settings": {"frost_temperature": 16, "hysteresis": 0.3, "away_temperature": 15,
    "override_default": "next_block", "override_minutes": 120,
    "sync_rooms_on_knob_change": true, "retry_seconds": 300},
  "mode": {"value": "manual", "until": null},
  "active_schedule_id": "winter",
  "schedules": {
    "winter": {"name": "Winter", "rooms": {
      "room_a": {"days": {"mon": [{"start": "00:00", "target": 18}],
        "tue": [...], "wed": [...], "thu": [...], "fri": [...], "sat": [...], "sun": [...]}}
    }}
  },
  "rooms": {"room_a": {"name": "Room A", "trvs": ["climate.trv_a"], "area_id": null, "enabled": true}},
  "overrides": {"room_a": {"target": 22, "until": "2027-01-01T18:00:00+00:00", "source": "card", "kind": "next_block"}}
}
```

Every schedule has exactly one validated week for every room. At least one schedule exists, even with no rooms;
new installs start with an empty Winter. Schedule names are non-empty and unique after trimming/case-folding.
Room/schedule identities remain stable across renames. A physical TRV can belong to only one room across instances.
The active or last schedule cannot be deleted. A new room gets 00:00 →18° in every schedule, or copies another
room's week separately inside each schedule. Deleting a room removes all its weeks and override.

Minor-version migration converts existing profiles into one active Winter: each room's week is a detached copy
of its former profile's days. It removes profiles/profile_id, preserves room IDs, names, TRVs, area/enabled flags,
settings, shadow and overrides (including kind/expiry/source), and maps auto→schedule and summer→off. Empty installs
also receive Winter. Missing references or invalid weeks fail validation before a migrated Store can be saved.
Legacy overrides without a recorded kind retain their expiry as duration. A generic four-profile/nine-room fixture,
multi-TRV rooms and both active override kinds exercise the pure conversion and HA's migration callback/reload.
Read-only ownership lookups convert old files only in memory and reject future minor versions without writing.

All configuration updates build and validate a detached complete candidate before one serialized Store save.
HA logs disk-write failures; the validated in-memory snapshot may advance without surviving a restart.
Removing an entry removes its own Store and repair issue.

### 6.2 Modes and active schedule

| Name | Stored/select value | Radiators | Boiler |
|---|---|---|---|
| Schedule | `schedule` | Override, otherwise the room's active-schedule block | Follows demand |
| Away | `away` | Override, otherwise away temperature | Follows demand |
| Off | `off` | Frost temperature | Always off; hot water unaffected |
| Manual | `manual` | No writes | Follows existing TRV demand |

Services and websocket mode/set accept auto and summer as aliases and immediately store schedule and off.
Away's optional end is interpreted in HA's server zone when no offset is supplied; expiry returns to schedule.
Mode select options contain only the four new values, with translated states. A separate Active schedule select
contains schedule names and activates by name; its options/current state follow creates, renames and deletes.
set_schedule accepts a name or ID. Activation is permitted in any mode, preserving Manual and shadow guarantees.

The card explains the selected mode before Apply. Schedule says “Rooms follow the {name} schedule” and shows a
schedule selector; Apply sends mode plus schedule_id atomically. Away shows its live temperature and optional end,
including the date when the end isn't today in HA's zone. Off names the frost temperature and leaves hot water
unaffected. Manual leaves radiator targets alone while the boiler follows demand. Header: “9 rooms · Schedule · Winter”.

### 6.3 Applying targets to TRVs

Inactive schedule edits and schedule renames do not apply room targets or change active overrides. All other
existing room triggers remain. Manual never writes TRVs; shadow plus Manual never sends TRV or boiler commands.

- **Desired target for a room:** given by the mode table in §6.2. In `manual` mode there's none.
- **Re-apply only on these triggers:**
  - at every block start of enabled room weeks in the active schedule only (`async_track_point_in_time` on the next start, then reschedule);
  - when the mode changes;
  - when an override is set, cleared or expires;
  - when rooms or settings are saved; when the active schedule changes; or when an active room week is edited (only affected rooms);
  - once after Home Assistant has started;
  - when a TRV comes back online (apply its room);
  - on the retry timers below.
  The 10 s tick and ordinary TRV state events recalculate the boiler, without applying room targets.
- **Writing:** gated on `CoreState.running`. For each TRV whose target differs, call
  `climate.set_temperature` with `temperature`. Add `hvac_mode: heat` only if it is in another mode and supports
  heat. A TRV deliberately switched off stays off until the next room trigger; then restore heat if supported,
  even when its target is already equal. Only a transition into `off` starts the pause; attribute-only reports
  while off do not cancel an in-flight heat command. While off it does not contribute to demand.
- **Boiler isolation:** calculate/send the boiler first. Room failures cannot skip that update. TRV service calls
  use `blocking=False`, outside the boiler lock; confirmation and retry logic handles slow radio devices.
- **Pending commands:** per TRV retain unconfirmed `(value, time, previous value, Context)` commands, with our own Context
  on service calls. `last_commanded` is diagnostics only. See §6.4 for confirmation. If the reported target
  already equals the desired target but an older command for another target is in flight, enqueue the desired
  target behind it; retain the older command for echo recognition.
- **Normal triggers and retry budgets:** an unchanged desired target preserves an existing pending command and
  its retry counter; a TRV with `sync_problem` is not retried for that same target on normal triggers. A changed
  desired target starts a new retry budget. Successful synchronization clears the problem; `apply_now` explicitly
  restarts the budget. Applying targets always reschedules the next boundary in `finally`, even after an error.
- **Retry:** after `retry_seconds` (default 300 s), check the desired target is unchanged and no foreign change
  occurred. Retry at most 3 times. After the fourth retry interval (the retry window), clear unconfirmed
  commands, set `sync_problem`, log a warning, and raise a Repairs issue. Successful synchronization clears it.
- **TRV back online:** when a TRV goes from `unavailable` or `unknown` to available, re-apply its room.
- **`apply_now`:** a manual retry in writing modes: rewrite every available TRV, including already-correct,
  pending and problem TRVs, reset retry counters and clear previous repair issues. With knob sync off, this
  explicitly writes the room target, including any active knob override, to every TRV. Manual mode writes nothing.

### 6.4 Overrides
- **From the card or a service:** a target, plus either `next_block` (until the room's next target change) or a
  number of minutes. "Until the next change" means the next effective block start whose target differs from
  the currently scheduled target, skipping equal-target blocks across midnight and days. If the entire week
  has one target, the override expires after seven elapsed days. The stored `next_block` option keeps its name.
- **From a TRV knob, only in Schedule/Away:**
  - A report equal to any pending command with one of our pending command Contexts is **provisional**: HA
    may have reported the command optimistically. Keep pending commands and stale guards. Only a matching
    report with a foreign Context, or the retry check finding the target in place, releases them. Normal room
    triggers do not confirm an optimistic value. An equal target while still off cannot confirm a command
    that must restore supported heat mode.
  - A matching foreign-Context report confirms a command only when its target or HVAC mode actually changes.
    Attribute-only reports (for example, a new room temperature while HA still shows our optimistic target)
    cannot confirm it. Confirmation drops that command and all older commands; retain newer unconfirmed
    commands. A real report identical to the optimistic state emits no state-change event; the retry check
    then confirms it. Contexts are stored per command so late optimistic echoes of older commands remain
    provisional too.
  - Each pending command records its previous target and HVAC mode. A report equal to a previous target, or
    a transition back to a previous HVAC mode, is stale/optimistic: ignore it while that command is pending.
    In particular, an optimistic heat restore followed by the device's old `off` report must retain the pending
    command and its retry rather than start a user pause. A real knob turn back to that old value or mode
    inside the retry window is indistinguishable and gets corrected by the retry.
  - Any other target change is a knob change. Round to 0.5 and clamp to 5–30. If it equals the room target
    without an override (active week in Schedule, away temperature in away), clear the override if one exists (no Store
    save when there is nothing to clear); otherwise create or
    update it with `settings.override_default`. With `sync_rooms_on_knob_change` on, apply it to the other TRVs.
  - Confirmed commands and commands outside the retry window never mask later knob changes.
- **Schedule edits and activation:** next-change overrides recompute against the affected room's active week.
  Switching the active schedule counts as an edit for all rooms, even when weeks happen to be identical.
  Editing an active room week affects only that room; duration overrides keep their expiry. Inactive edits and
  renames affect no overrides. Refresh the stored active-week snapshot after recomputation so a constant week's
  seven-day cap cannot slide on later re-applies. Kind is persisted independently of later default-setting changes.
- **Expiry:** an override expires at its `until`, or when it's cleared. The
  room then goes back to the desired target.
- **Off/Manual:** knob changes are not tracked or immediately reverted.

## 7. Entities

All unique IDs are `<entry_id>_<key>`. Boiler entity names are translated; room names come from the Store; there are no hard-coded entity IDs.

| Platform | Entity | Notes |
|---|---|---|
| `climate` | one per room | `current_temperature` = the mean of the room's available TRVs; `target_temperature` = the desired target (or the TRVs' target in `manual`). `hvac_modes: [heat]`. `hvac_action: heating` while the room is demanding. `set_temperature` sets an override with the default length. Attributes: `schedule` (the active schedule name), `scheduled_target`, `next_change`, `next_target`, `override_until`, `demanding`, `trvs`, `sync_problem`. |
| `select` | mode | `schedule`, `away`, `off`, `manual` |
| `select` | active schedule | schedule names; selecting one activates it |
| `switch` | shadow mode | §5.4 |
| `sensor` | demand count, virtual temperature, virtual temperature (raw), virtual setpoint | °C where it applies, with `state_class: measurement` |
| `binary_sensor` | boiler call | on when the computed command has `heat = true`. Attributes: the last command and `shadow`. Send timing is diagnostics-only to avoid recorder churn. |
| `number` | frost temperature, hysteresis, away temperature | write to `settings` |

The room attributes `next_change` and `next_target` describe the next effective target change from §6.4,
not merely the next block start; both are `None` when the schedule has no target change. `override_until` is `None` unless an unexpired override
applies in the current mode. Room climates accept `set_hvac_mode(heat)` as a no-op and reject off-grid targets
with `ServiceValidationError`. A small feature-detected property bridge uses the native-temperature API in
2026.11 and the original API in 2026.10, without triggering 2026.11 deprecations.

**Diagnostics:** settings, rooms, schedules, active_schedule_id, mode, overrides, the last command and the timing of sends. No
credentials are involved.

## 8. Services and websocket API

Services are registered once and resolve the loaded instance via config_entry_id per call.

| Service | Fields |
|---|---|
| set_mode | mode: schedule/away/off/manual, aliases auto/summer; optional until for Away |
| set_schedule | schedule: name or ID |
| set_override | room climate entity, temperature, optional minutes |
| clear_override | room climate entity |
| apply_now | explicit retry of all room targets in a writing mode |

Websocket reads require any logged-in user; every write checks admin status on each call. Voluptuous validates
wire shapes; configuration commands validate the whole detached candidate before a single save. Invalid inputs
never partly apply. Commands are instance-scoped by config_entry_id.

| Command | Fields/behaviour |
|---|---|
| get | without instance: entries and room_entity_ids; with instance: full status |
| subscribe | initial status then changed snapshots, at most once a second |
| schedule/save | schedule: name, optional existing id, optional rooms mapping room_id→{days}; create fills default weeks, update merges supplied room weeks atomically |
| schedule/delete | schedule_id; active/last deletion refused |
| schedule/activate | schedule_id |
| room/save | room: optional existing id, name, trvs, optional area_id/enabled; optional copy_week_from_room only on create |
| room/delete | room_id; removes all its weeks, entity-registry record and override |
| settings/save | partial settings, optional shadow; one validated update |
| mode/set | mode, optional until; optional schedule_id only in Schedule mode, applied together atomically |
| override/set | room_id, temperature, optional kind and minutes; next_block cannot include minutes |
| override/clear | room_id |

There are no profile commands. Successful creates/updates return status and saved_id. Full status contains
configuration (schedules, active_schedule_id, rooms, settings, overrides, shadow and mode), global demand/virtual
values/command/last_sent, and rooms with current/desired/reported targets, demanding/sync_problem, override_until,
next_change and next_target from the active room week. It also includes actual registry room_entity_ids and
used_trv_ids across configured instances for the physical-TRV picker. Virtual Central Heating climates and TRVs
owned by another instance are rejected under a shared assignment lock. Unreadable other-instance storage warns
and skips for status/ordinary controls; room/save fails closed. Ownership reads never migrate/write other stores.

One unload hook drains the engine's subscription cleanup set. Disconnect/unsubscribe cancels listeners/timers;
unload sends {unloaded:true} then leaves an inert no-op record until the client acknowledges unsubscribe_events
or closes its socket. The card releases it before capped-backoff resubscription; generation checks discard late
callbacks. Unchanged status snapshots are silent. No control actions are authorized by a subscription.

## 9. Card

Lit/TypeScript, bundled with rollup to a committed local central-heating-card.js. The integration registers its
static path once and calls frontend.add_extra_js_url with the bundle's SHA content hash. No external scripts,
fonts, assets or requests. Card type custom:central-heating-card has an instance picker. HA theme variables,
locale/time-format preferences and 390px layouts are supported. Date pickers use HA's server zone; Away explanations
include a date outside today. An unload/disconnected socket greys out stale readings, disables writes and retries
with 1/2/4/8/16/30-second capped backoff; removal cancels subscriptions/timers/listeners.

- Overview: mode name/explanation updates before Apply. Schedule reveals a whole-house schedule selector;
  Apply sends both in one atomic mode/set. Successful Apply clears selection drafts. Away until shows/hides with
  the selected mode. Boiler demand and room comfort, sync errors and overrides remain visible.
- Schedules: choose a whole-house schedule, active badge, Create (copy an existing schedule, defaulting to active,
  or blank 18° weeks for all rooms), Rename, protected Delete and explicit Activate. Select a room to edit its
  week using the existing 7-row/24-hour coloured grid or narrow day-list fallback. Copy this room's week to checked
  rooms in the selected schedule; Copy day remains. Explicit per-schedule Save/Discard; local drafts survive status
  pushes/tab changes. Unsaved changes block schedule selection/activation. Room navigation retains edits for all rooms.
  Typed times validate strictly between neighbours with localized errors, while pointer/keyboard boundary moves clamp
  on the five-minute grid. Midnight is fixed. Focusable blocks use half-degree arrow keys. Structural day changes
  clear rejected row inputs. API validation errors stay inline. A seeded per-room editor fuzz test preserves validation.
- Rooms: name, physical TRVs, area/enabled; Add room offers Start its weeks from an existing room or 18° all day.
  No profile association. Missing assigned TRVs remain shown and selected until removed; used/virtual TRVs are excluded.
- Settings: frost, hysteresis, Away temperature, default override length, knob sync and retry interval. Shadow is
  a separate action: turning off requires the in-card “Central Heating will start sending commands to the boiler
  controller” confirmation. Turning on is immediate. Save settings never changes shadow.

The demo uses generic schedules Winter/Autumn/Spring and invented rooms only. CI validates TypeScript, lint,
Vitest, lockfile, pinned checksum-verified Node22 and byte-identical card/demo rebuilds. Shared room-week fixtures
run through TypeScript validation and the real authenticated schedule/save API.

## 10. Repository layout

```
custom_components/central_heating/
  __init__.py  manifest.json  const.py  config_flow.py  strings.json  translations/en.json
  engine.py  storage.py  websocket.py  services.py  services.yaml  diagnostics.py
  demand.py  smoothing.py  schedule.py                      # pure, no HA imports
  boiler/__init__.py  boiler/base.py  boiler/diyless_mqtt.py
  climate.py  select.py  switch.py  sensor.py  binary_sensor.py  number.py
  frontend/central-heating-card.js                          # built bundle (committed)
frontend/                                                   # card source: src/, package.json, rollup.config.mjs
tests/                                                      # pytest + pytest-homeassistant-custom-component
docs/DESIGN.md
hacs.json  README.md  .gitignore
.forgejo/workflows/ci.yml
```

**`manifest.json`:**
- `domain: central_heating`, `name: Central Heating`, `config_flow: true`, `iot_class: calculated`;
- `dependencies: ["http", "frontend", "websocket_api"]`, `after_dependencies: ["mqtt"]`. MQTT stays optional, so
  that later adapters don't need it;
- `codeowners`, `documentation` and `version` in the same style as the other `cc-homeassistant` integrations;
- no `requirements`.

**`hacs.json`:** `{"name": "Central Heating", "render_readme": true}`.

**Config flow:** step `user` takes a name, the boiler adapter (only `diyless_mqtt` in v1) and the MQTT topic prefix.
It aborts with a clear message if MQTT isn't set up. The options flow edits the prefix. Duplicate effective prefixes are rejected; an unchanged prefix does not reload
the entry (reloading can send `mode=off`). Prefix validation runs inside the step so form schemas serialize.

## 11. Testing

**Pure logic** (plain pytest):
- **Demand:**
  - the float edge case: target 21.0, current 20.7, hysteresis 0.3 is **not** demand;
  - unavailable values are skipped;
  - an empty room list.
- **Virtual temperature:** with demand, without demand, nothing available.
- **Setpoint:** the maximum among demanding TRVs, and the frost fallback.
- **Smoothing:** outlier replacement, time-based convergence (Δt independence), unknown input.
- **Schedule:**
  - the current block and the next block start across midnight and weekday changes;
  - daylight-saving changes in both directions, coinciding starts and skipped dates;
  - next-target-change lookup across equal-target blocks, midnight and weekdays;
  - a constant week's seven-day override cap, and a change deferred by a DST gap to the following week;
  - every validation rule.
- **Golden test:** feed the same TRV fixtures to a Python copy of the package's templates and to `demand.py`. The
  results must be identical, apart from the documented rounding fix.

**Integration** (`pytest-homeassistant-custom-component`, pinned to a current Home Assistant release):
- the config flow, including when MQTT is missing;
- the entities created from a Store fixture;
- **MQTT** with `mqtt_mock`: the exact topics and payloads; a send on change; the 30 s keep-alive; `tempSource` at
  start; **nothing sent in shadow mode**; Off forces boiler `off`; `mode = off` on unload;
- schedule writes at a block start (with a frozen clock), with no write when the target is already correct;
- retry and `sync_problem`; a knob change becomes an override; override expiry; a TRV coming back online;
- websocket: an admin can write, a non-admin can't, and a bad input changes nothing;
- the services.

**CI** (Forgejo Actions) runs on pushes and pull requests: `ruff`, `pytest`, the card build, and a check that the
committed bundle is up to date.

## 12. Migration and staged go-live

Before the legacy Store is rewritten, its original file bytes (the full HA envelope, names and unused
profiles included) are saved unchanged to the sibling `.storage/central_heating.<entry_id>.pre_schedules`.
HA's atomic write helper runs in an executor job with private permissions and fsync. Validation happens
first; backup failure aborts migration before Store save. A differing existing backup is never overwritten.
Unused profiles are warned by name and id. The new Store also enables `atomic_writes=True`.

Rollback: stop HA, install the previous integration version and restore each entry's `.pre_schedules`
backup over its original Store file before starting HA. Alternatively restore a complete pre-upgrade
HA backup. Downgrade alone cannot read the new Store; restoring discards post-upgrade changes.
Service lookups try exact schedule names before ids. The active-schedule select maps option names
to ids directly; websocket schedule-id commands also use ids directly. Before upgrading again after
rollback, move the old `.pre_schedules` file aside so the changed legacy Store can be backed up.


Minor version 4 upgrades older version-1 Stores automatically on the next integration load. Existing room IDs,
physical thermostats, settings, mode intent, shadow and overrides are preserved. One active Winter contains each
room's previous weekly targets, copied independently from its old profile. auto/summer become schedule/off;
services/API continue accepting the old values as aliases. Empty old installs get Winter with no rooms. Validation
finishes before HA saves the converted data. Read-only cross-instance ownership reads convert only in memory.

New installs start in shadow and Manual. A generic staged handover is recommended:
1. Configure physical rooms while TRVs retain their previous targets. Start boiler control in Manual after
   confirming shadow-off; only one boiler controller should send commands.
2. Create whole-house schedules and each room's week, then activate the desired schedule. Disable TRVs' internal
   schedules and any previous scheduler before selecting Schedule mode.
3. Shadow is a one-click pause of boiler output; Manual also pauses room writes. Restore previous controls
   deliberately when rolling back operating behaviour. Comparing with an earlier setup before handover is optional.

No house-specific IDs, names, topics, addresses or migration plans belong in this repository.

## 13. Build plan (pull requests)

Each pull request includes its tests and passing CI. Each is reviewed independently before the owner merges it.

1. **Scaffold and pure logic:** the layout, manifest, hacs.json, CI, `demand.py`, `smoothing.py` and `schedule.py`
   with full tests, including the golden test.
2. **Engine and boiler** (split for independent review):
   - **2a:** config/options flow, Store, boiler engine/adapter, shadow, mode select and boiler measurements/numbers;
   - **2b:** room climates/control, overrides, retries, services and diagnostics;
   - each part includes its own integration tests and independently passing CI.
3. **Websocket API and card, part 1** (split for independent review):
   - **3a:** the complete authenticated websocket API, admin writes, schedule management and subscriptions;
   - **3b:** bundling/loading, Overview, Rooms and Settings, a profile-list placeholder and offline demo.
4. **Card, part 2:** the Schedules tab and its week-grid editor.
5. **Polish:** translations, README (installation, set-up, migration), Repairs issues, and an end-to-end check
   against a real Home Assistant.

## 14. Rules for this repository

- **It's public** (mirrored to GitHub for HACS). Never commit entity IDs, names, addresses, topics other than the
  controller's documented defaults, screenshots with personal data, or credentials.
- **No releases or tags** from the build bot. HACS follows the default branch.
- **No network access** beyond Home Assistant's own MQTT connection, and no cloud services.
