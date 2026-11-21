# Central Heating: design (v1)

**Status:** proposed, for review before building starts.

## 1. Goal

One Home Assistant integration that does three things:
- controls a central-heating boiler from the demand of per-room radiator thermostats (TRVs);
- runs weekly heating profiles for the rooms;
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
| **TRV** | A `climate` entity of a radiator thermostat that reports `current_temperature` and a target (`temperature`). |
| **Room** | A named group of one or more TRVs that always share a target. Each room follows one profile. |
| **Profile** | A weekly program: for each weekday, a list of blocks, where each block has a start time and a target temperature. |
| **Block** | It starts at its start time and runs until the next block. Each day starts with a block at 00:00. |
| **Override** | A temporary target for a room that wins over its profile. It's set from the card, a service or a TRV's own knob. |
| **Mode** | A global state: `auto`, `away`, `summer` or `manual` (§6.2). |
| **Demand** | A room (TRV) whose target is more than the hysteresis above its current temperature. |
| **Boiler adapter** | The piece that sends the computed boiler command to a specific controller (§5.3). v1 has one: the DIYLESS thermostat over MQTT. |
| **Shadow mode** | The integration computes everything but sends nothing to the boiler. |

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
| Boiler mode | `heat` if demand > 0, else `off` | the same, plus `off` in `summer` mode |
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
  - rooms, profiles, mode and tuning settings live in a `Store` and are edited through the card (websocket API)
    or services.

## 5. Boiler control

### 5.1 Demand, virtual temperature and setpoint
For each TRV in any enabled room, with `c` = `current_temperature` and `t` = target (`temperature`). A value counts
as available unless it's `None`, `unknown` or `unavailable`.

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

1. **Outlier rejection:** keep a window of the last 4 accepted raw values. If a new value differs from the window's
   median by more than 1.5 °C, use the median instead.
2. **Low-pass:** `y ← y + (x − y) · (1 − e^(−Δt/τ))`, with τ = 300 s and Δt the seconds since the last update. The
   first value initialises `y`. Rounded to 2 decimals.
3. **Unknown raw value:** smoothing state is kept, and nothing is sent (§5.4).

### 5.3 Boiler adapter
```python
@dataclass(frozen=True)
class BoilerCommand:
    heat: bool                  # demand_count > 0 and mode != "summer"
    room_temperature: float | None   # virtual_temp; None when unknown
    setpoint: float             # virtual_setpoint

class BoilerAdapter(Protocol):
    async def async_start(self) -> None: ...
    async def async_apply(self, cmd: BoilerCommand, *, keepalive: bool) -> None: ...
    async def async_stop(self, *, unloading: bool) -> None: ...
```
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
- **Before sending:** check that the MQTT integration is loaded. If it isn't, log it and raise a Repairs issue,
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

## 6. Rooms, profiles, modes and overrides

### 6.1 Data model (Store, version 1)
```jsonc
{
  "settings": {
    "frost_temperature": 16.0,
    "hysteresis": 0.3,
    "away_temperature": 15.0,
    "override_default": "next_block",      // or "duration"
    "override_minutes": 120,
    "sync_rooms_on_knob_change": true,
    "retry_seconds": 300
  },
  "mode": {"value": "manual", "until": null},          // a new entry starts in manual
  "profiles": {
    "<profile_id>": {
      "name": "Living",
      "days": {
        "mon": [{"start": "00:00", "target": 18.0}, {"start": "06:30", "target": 21.0}, ...],
        "tue": [...], "wed": [...], "thu": [...], "fri": [...], "sat": [...], "sun": [...]
      }
    }
  },
  "rooms": {
    "<room_id>": {"name": "Kitchen", "trvs": ["climate.x", "climate.y"], "profile_id": "<profile_id>",
                  "area_id": null, "enabled": true}
  },
  "overrides": {"<room_id>": {"target": 22.0, "until": "2026-01-01T18:00:00+01:00", "source": "card"}}
}
```

**Validation, on every write:**
- **Blocks:** each day has at least one block, the first starting at `00:00`. Start times are `HH:MM` on a 5-minute
  grid, strictly increasing. Targets are 5.0–30.0 in steps of 0.5.
- **TRVs:** each TRV belongs to at most one room. A room has at least one TRV.
- **Deleting:** a profile can't be deleted while rooms use it.
- **IDs:** profile and room IDs are random. Names are for display only.

Times are local wall-clock times (`dt_util`). A daylight-saving change applies blocks by local time: a block at a
time that doesn't exist that day starts at the next valid minute.

### 6.2 Modes
| Mode | Room target written to TRVs | Boiler |
|---|---|---|
| `auto` | the override if one is active, otherwise the profile block | follows demand |
| `away` | the override if one is active, otherwise `away_temperature` | follows demand |
| `summer` | `frost_temperature` | always `off` |
| `manual` | nothing is written; the TRVs keep whatever they have | follows demand |

- `away` can have an `until` time; when it passes, the mode returns to `auto`.
- The mode is a `select` entity, and is also set through the card or a service.

### 6.3 Applying targets to TRVs
- **Desired target for a room:** given by the mode table in §6.2. In `manual` mode there's none.
- **Re-evaluate all rooms:**
  - at every block start of any profile in use (`async_track_point_in_time` on the next start, then reschedule);
  - when the mode changes;
  - when an override is set, cleared or expires;
  - when rooms, profiles or settings are saved;
  - once after Home Assistant has started.
- **Writing:** for each TRV whose target differs from the desired one, call `climate.set_temperature` with
  `temperature`. Add `hvac_mode: heat` only if the TRV is in another mode and lists `heat` among its modes. Write
  only on a difference, because radio TRVs have limited bandwidth.
- **Record our writes:** keep `last_commanded[trv] = (target, time, context)`, and use our own `Context` for writes.
- **Retry:** 300 s after a write (a setting, `retry_seconds`, because battery TRVs can be slow to report), if the TRV
  still shows a different target and nothing else changed it, write again. Retry at most 3 times. After that, set `sync_problem` on the room's attributes, log a warning, and raise a
  Repairs issue that clears itself on the next successful sync.
- **TRV back online:** when a TRV goes from `unavailable` or `unknown` to available, re-apply its room's desired
  target.

### 6.4 Overrides
- **From the card or a service:** a target, plus either `next_block` (until the room's next block start) or a
  number of minutes.
- **From a TRV knob:** a TRV target change to a value that differs from `last_commanded` becomes an override, using
  `settings.override_default`. If `sync_rooms_on_knob_change` is on, the other TRVs in that room get the same
  target.
  - **Decide by value, not context.** Battery and radio TRVs often report a commanded change minutes later, after
    Home Assistant's context window has expired, so the state change no longer carries our context. A report equal
    to `last_commanded` is ours, whatever its context.
- **Expiry:** an override expires at its `until`, or when it's cleared, or when the room's profile changes. The
  room then goes back to the desired target.
- **Manual mode:** knob changes are not tracked as overrides, because nothing is scheduled.

## 7. Entities

All unique IDs are `<entry_id>_<key>`. Entity names are translated; there are no hard-coded entity IDs.

| Platform | Entity | Notes |
|---|---|---|
| `climate` | one per room | `current_temperature` = the mean of the room's available TRVs; `target_temperature` = the desired target (or the TRVs' target in `manual`). `hvac_modes: [heat]`. `hvac_action: heating` while the room is demanding. `set_temperature` sets an override with the default length. Attributes: `profile`, `scheduled_target`, `next_change`, `next_target`, `override_until`, `demanding`, `trvs`, `sync_problem`. |
| `select` | mode | `auto`, `away`, `summer`, `manual` |
| `switch` | shadow mode | §5.4 |
| `sensor` | demand count, virtual temperature, virtual temperature (raw), virtual setpoint | °C where it applies, with `state_class: measurement` |
| `binary_sensor` | boiler call | on when the computed command has `heat = true`. Attributes: the last command, the last time it was sent, `shadow`. |
| `number` | frost temperature, hysteresis, away temperature | write to `settings` |

**Diagnostics:** settings, rooms, profiles, mode, overrides, the last command and the timing of sends. No
credentials are involved.

## 8. Services and websocket API

**Services** (`central_heating.*`, with the target given by `config_entry_id`):

| Service | Fields |
|---|---|
| `set_mode` | `mode`, optional `until` (`away` only) |
| `set_override` | `room` (a room's climate entity), `temperature`, optional `minutes` (otherwise the default) |
| `clear_override` | `room` |
| `apply_now` | none. It re-evaluates and writes all rooms. |

**Websocket commands.** Writes need an admin user; reads need any logged-in user.

| Command | Purpose |
|---|---|
| `central_heating/get` | all of the Store, plus live status: per room the current, desired and TRV targets, demanding, `sync_problem`; globally the demand count, virtual values, last command, shadow, mode |
| `central_heating/subscribe` | pushes the same status object whenever it changes, at most once per second |
| `central_heating/room/save`, `.../room/delete` | create, update or delete a room |
| `central_heating/profile/save`, `.../profile/delete` | create or update a profile; delete one that no room uses |
| `central_heating/settings/save` | partial update of `settings` |
| `central_heating/mode/set`, `.../override/set`, `.../override/clear` | the same as the services |

Every command validates with voluptuous, returns structured errors, and never partly applies a change.

## 9. Card

- **Built with** Lit and TypeScript, bundled with rollup into a single file,
  `custom_components/central_heating/frontend/central-heating-card.js`. The built file is committed, because HACS
  installs files as they are. CI checks that it matches the source.
- **Loaded by the integration itself,** so no manual dashboard resource is needed:
  `hass.http.async_register_static_paths([StaticPathConfig(...)])` and
  `frontend.add_extra_js_url(hass, f"{url}?v={version}")`.
- **Card type:** `custom:central-heating-card`. It's registered in `window.customCards` with a small visual editor
  that picks the config entry, if there's more than one.
- **Styling:** Home Assistant theme variables only. It works at phone width and makes no external requests.

**Tabs:**
1. **Overview:**
   - the mode selector (with an "until" date and time for away);
   - the boiler status: calling for heat or not, the demand count, the virtual temperature and setpoint, and a
     shadow-mode badge;
   - a list of rooms with current and target temperature, a flame icon when demanding, and an override badge
     ("22° until 18:00").
   - Tapping a room opens a quick override with − and + buttons and a choice of "until next block", 1 h, 2 h, 3 h or
     a custom time, plus "back to schedule".
2. **Schedules:**
   - a list of profiles, and for each profile a week grid with 7 rows of 24 hours, the blocks coloured by
     temperature;
   - tap a block to change its temperature, drag a boundary to move it, tap empty space to split, and remove a
     block (it merges with the one before);
   - "copy day to …" with weekday checkboxes, and "copy profile";
   - shows which rooms use the profile.
3. **Rooms:** add or edit a room: its name, its TRVs (an entity picker limited to `climate` entities that no other
   room uses), its profile, an optional area, and whether it's enabled.
4. **Settings:** frost temperature, hysteresis, away temperature, the default override length, room sync on knob
   changes, and shadow mode.

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
It aborts with a clear message if MQTT isn't set up. The options flow edits the prefix.

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
  - daylight-saving changes in both directions;
  - every validation rule.
- **Golden test:** feed the same TRV fixtures to a Python copy of the package's templates and to `demand.py`. The
  results must be identical, apart from the documented rounding fix.

**Integration** (`pytest-homeassistant-custom-component`, pinned to a current Home Assistant release):
- the config flow, including when MQTT is missing;
- the entities created from a Store fixture;
- **MQTT** with `mqtt_mock`: the exact topics and payloads; a send on change; the 30 s keep-alive; `tempSource` at
  start; **nothing sent in shadow mode**; `summer` forces `off`; `mode = off` on unload;
- schedule writes at a block start (with a frozen clock), with no write when the target is already correct;
- retry and `sync_problem`; a knob change becomes an override; override expiry; a TRV coming back online;
- websocket: an admin can write, a non-admin can't, and a bad input changes nothing;
- the services.

**CI** (Forgejo Actions) runs on pushes and pull requests: `ruff`, `pytest`, the card build, and a check that the
committed bundle is up to date.

## 12. Migration

The house-specific plan (entity IDs, rooms, profiles) is not kept in this public repo.

1. **Install** through HACS and add the integration. It starts in **shadow mode** and **manual** mode, so nothing
   changes.
2. **Set up** rooms and profiles in the card that reproduce the current schedules.
3. **Compare** for a few days:
   - demand count and setpoint must be identical, apart from the rounding fix;
   - the virtual temperature must be within ±0.1 °C;
   - the boiler call must match.
4. **Cut over:**
   - turn off the old automations and schedules;
   - set the mode to `auto`, check the TRV writes, then turn shadow mode off.
   - **Going back** means turning shadow mode on and turning the old automations and schedules on again.
5. **Clean up:** remove the old package, Scheduler and its card, and the leftover entities.

## 13. Build plan (pull requests)

Each pull request includes its tests and passing CI. Each is reviewed independently before the owner merges it.

1. **Scaffold and pure logic:** the layout, manifest, hacs.json, CI, `demand.py`, `smoothing.py` and `schedule.py`
   with full tests, including the golden test.
2. **Engine and boiler:**
   - the config flow, Store, engine, the DIYLESS adapter, shadow mode and the mode select;
   - the sensors, binary sensor, numbers and room climates;
   - the services and diagnostics;
   - the integration tests.
3. **Websocket API and card, part 1:** the API, the bundling and loading, and the Overview, Rooms and Settings
   tabs.
4. **Card, part 2:** the Schedules tab and its week-grid editor.
5. **Polish:** translations, README (installation, set-up, migration), Repairs issues, and an end-to-end check
   against a real Home Assistant.

## 14. Rules for this repository

- **It's public** (mirrored to GitHub for HACS). Never commit entity IDs, names, addresses, topics other than the
  controller's documented defaults, screenshots with personal data, or credentials.
- **No releases or tags** from the build bot. HACS follows the default branch.
- **No network access** beyond Home Assistant's own MQTT connection, and no cloud services.
