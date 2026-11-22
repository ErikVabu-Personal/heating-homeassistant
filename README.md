# Central Heating for Home Assistant

A custom integration that runs a central-heating boiler from per-room radiator thermostats (TRVs), with whole-house weekly
schedules and its own dashboard card.

**Minimum Home Assistant:** 2026.10.0.

**Status:** active development. See [`docs/DESIGN.md`](docs/DESIGN.md).

Blocking tests use the supported test-package/Home Assistant pair; move that pair forward when a 2026.11.x-compatible test-package release appears.


## Installation

1. Open Home Assistant's community store (HACS; recent versions call it **Marketplace** under **Settings**).
2. In **Custom repositories**, add `https://github.com/ErikVabu-Personal/heating-homeassistant` with type **Integration**.
3. Download **Central Heating** and restart Home Assistant when prompted.
4. Choose **Add integration → Central Heating** and complete setup.
5. Add a dashboard card with type `custom:central-heating-card` and select the heating instance.
   The integration loads the card automatically; no separate resource URL is needed.

## Modes

| Name | Value (services/API) | Behaviour |
|---|---|---|
| Schedule | `schedule` | Rooms follow their room weeks in the active whole-house schedule. |
| Away | `away` | All rooms at the configured away temperature, optionally until an end time. |
| Off | `off` | Boiler heating off; radiators kept at the frost temperature. Hot water unaffected. |
| Manual | `manual` | Central Heating doesn't touch the radiators; the boiler still follows their demand. |

Active overrides still take precedence in Schedule and Away. Store/select values are `schedule`, `away`, `off`, `manual`.
Services and the API also accept `auto` and `summer` as aliases for `schedule` and `off`.

## Card

The integration serves the committed card bundle locally and adds it to Home Assistant once, including with
multiple boiler entries. Add a **Central Heating** custom card in the dashboard editor and pick the boiler.
Manual YAML is also supported:

```yaml
type: custom:central-heating-card
config_entry_id: YOUR_CONFIG_ENTRY_ID
```

Overview shows computed boiler demand and shadow mode, room targets, overrides and synchronization problems.
Rooms edits physical thermostats and initial week seeding; Settings edits tuning, retries and shadow. Schedules edits
whole-house schedules with one active plan. Select a room to edit its week using a desktop grid or phone-friendly
day list. Create by copying a plan or blank 18° weeks; copy days or room weeks; Save/Discard explicitly.
Active/last schedule deletion is protected. Logged-in users can read; only administrators can write.
Shadow pauses boiler output, while manual mode pauses room writes.

### Review without Home Assistant

Open `frontend/demo/index.html` directly in a browser. Its committed `demo.js` contains the card, invented
Room A/Room B data and an in-memory websocket mock. Nothing is sent to Home Assistant or an external service.
The preview controls switch between 1080 px and 390 px layouts and light/dark HA theme variables. Demo changes
are temporary; Reset restores the fixtures.

```sh
cd frontend
npm ci
npm run typecheck
npm run lint
npm test
npm run build
```

Dependencies are pinned by `package-lock.json`. CI uses the existing checksum-verified Node 22, validates both
Python versions, runs frontend checks, rebuilds both committed bundles and rejects bundle drift. The production
card uses HA theme variables, local SVG icons and no external fonts, scripts or style requests.


### Reloads and boiler handover

The card shows a reconnecting notice and pauses controls during an entry reload or connection interruption.
It retries after 1, 2, 4, 8, 16 and at most 30 seconds, and reconnects promptly when the connection is ready.
Subscriptions end with an explicit unload event; identical snapshots are not pushed.

Shadow control is separate from Settings. Enabling shadow immediately pauses boiler commands. Disabling shadow
requires confirmation inside the card that Central Heating will start sending commands to the boiler controller.
Saving temperature/retry settings never changes shadow. Display times follow HA's locale and time-format preference;
away date-picker payloads remain local wall-clock time in HA's configured server zone. The bundle URL includes its
content hash so a changed build cannot keep the old cache key. Missing assigned TRVs remain visible in the room editor.

### Thermostat schedules and staged handover

Switch off the TRVs' own internal schedules before Central Heating drives room targets in Schedule mode.
Disable any previous room scheduler at the same time, so two schedulers do not fight each other.
For a staged handover, start boiler control in manual mode while TRVs keep their previous schedules;
then configure room weeks, activate a schedule, disable those old schedules and switch to Schedule. Shadow mode is the safe install
default and pauses boiler commands with one click; manual mode pauses room schedule writes too.
Comparing with a previous setup is optional.

### Upgrading

Store minor version 4 turns the previous profiles into one active **Winter** schedule. Every room keeps a copy
of its previous week, its thermostat assignments, settings and overrides (including expiry kind). Existing Manual
and shadow settings stay as they are. The new **Active schedule** select and `central_heating.set_schedule`
service choose a plan by name or id.

The mode select now offers `schedule`/`away`/`off`/`manual`. Update automations using
`select.select_option`: `auto` and `summer` no longer work as select options. The services and API
still accept those aliases. Room climate attributes now expose `schedule` instead of `profile`.
Service lookups try exact schedule names before ids; selectors and schedule-id commands use ids directly.

Before replacing a legacy Store, migration atomically saves its original bytes (including unused profiles
and profile names) to `.storage/central_heating.<entry_id>.pre_schedules`. Unused profiles are listed by
name and id in a warning. If this backup cannot be written, migration stops and leaves the original alone.
The migrated Store uses atomic, fsynced writes too. Keep the backup until the upgrade is accepted.

To roll back, stop Home Assistant, install the previous integration version, and restore the matching
`.pre_schedules` file over `.storage/central_heating.<entry_id>` before starting Home Assistant.
Restore every affected entry's file; changes made after migration will be lost on rollback. Alternatively,
restore a complete pre-upgrade Home Assistant backup. Installing an older version alone cannot read the
new schedule Store.

Before upgrading again after a rollback, move each old `.pre_schedules` file aside to a safe location
so the next migration can back up the current legacy Store. Keep that earlier backup as well.

### Schedule bars and day overview

On phones the selected room has seven day bars. Tap a day to open its existing time/temperature list
below; short blocks retain their true width and reveal full values in that list. Desktop dragging stays
available. The Schedules **Rooms / Overview** toggle compares all rooms for one day of the selected plan;
tapping a row returns to its room editor. The overview is read-only and follows the current draft.
Its now marker appears only on the active plan and today's day in Home Assistant's time zone, refreshing
every minute. Preview nine invented rooms with `frontend/demo/index.html?rooms=9&tab=Schedules`.
