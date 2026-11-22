# Central Heating for Home Assistant

A custom integration that runs a central-heating boiler from per-room radiator thermostats (TRVs), with weekly
heating profiles and its own dashboard card.

**Minimum Home Assistant:** 2026.10.0.

**Status:** development; not ready for live installation. See [`docs/DESIGN.md`](docs/DESIGN.md).

Blocking tests use the supported test-package/Home Assistant pair; move that pair forward when a 2026.11.x-compatible test-package release appears.


## Card (part 1)

The integration serves the committed card bundle locally and adds it to Home Assistant once, including with
multiple boiler entries. Add a **Central Heating** custom card in the dashboard editor and pick the boiler.
Manual YAML is also supported:

```yaml
type: custom:central-heating-card
config_entry_id: YOUR_CONFIG_ENTRY_ID
```

Overview shows computed boiler demand and shadow mode, room targets, overrides and synchronization problems.
Rooms edits physical thermostats and profiles; Settings edits tuning, retries and shadow. Schedule profiles are
listed now; the week-grid editor is a separate next PR. Logged-in users can read; only administrators can write.
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

Switch off the TRVs' own internal schedules before Central Heating drives room targets in auto mode.
Disable any previous room scheduler at the same time, so two schedulers do not fight each other.
For a staged handover, start boiler control in manual mode while TRVs keep their previous schedules;
then configure profiles, disable those schedules and switch to auto. Shadow mode is the safe install
default and pauses boiler commands with one click; manual mode pauses room schedule writes too.
Comparing with a previous setup is optional.
