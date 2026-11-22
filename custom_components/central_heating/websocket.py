"""Authenticated reads, admin-only atomic writes and throttled status subscriptions."""

from dataclasses import asdict
from uuid import uuid4

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .climate import RoomClimate
from .const import DOMAIN
from .demand import available_temperature
from .schedule import WEEKDAYS
from .storage import MODES, from_json, to_json

_NAME = vol.All(str, vol.Length(min=1, max=200))
_ID = vol.All(str, vol.Length(min=1, max=100))
_NUMBER = vol.Any(int, float)
_BLOCK = vol.Schema({vol.Required("start"): str, vol.Required("target"): _NUMBER})
_PROFILE = vol.Schema(
    {
        vol.Optional("id"): _ID,
        vol.Required("name"): _NAME,
        vol.Required("days"): vol.Schema({vol.Required(day): [_BLOCK] for day in WEEKDAYS}),
    }
)
_ROOM = vol.Schema(
    {
        vol.Optional("id"): _ID,
        vol.Required("name"): _NAME,
        vol.Required("trvs"): [cv.entity_id],
        vol.Required("profile_id"): _ID,
        vol.Optional("area_id", default=None): vol.Any(None, str),
        vol.Optional("enabled", default=True): bool,
    }
)
_SETTINGS = vol.Schema(
    {
        vol.Optional("frost_temperature"): _NUMBER,
        vol.Optional("hysteresis"): _NUMBER,
        vol.Optional("away_temperature"): _NUMBER,
        vol.Optional("override_default"): vol.In(["next_block", "duration"]),
        vol.Optional("override_minutes"): int,
        vol.Optional("sync_rooms_on_knob_change"): bool,
        vol.Optional("retry_seconds"): _NUMBER,
    }
)
SCHEMAS = {
    "get": {vol.Optional("config_entry_id"): _ID},
    "subscribe": {vol.Required("config_entry_id"): _ID},
    "room/save": {vol.Required("config_entry_id"): _ID, vol.Required("room"): _ROOM},
    "room/delete": {vol.Required("config_entry_id"): _ID, vol.Required("room_id"): _ID},
    "profile/save": {vol.Required("config_entry_id"): _ID, vol.Required("profile"): _PROFILE},
    "profile/delete": {vol.Required("config_entry_id"): _ID, vol.Required("profile_id"): _ID},
    "settings/save": {
        vol.Required("config_entry_id"): _ID,
        vol.Optional("settings"): _SETTINGS,
        vol.Optional("shadow"): bool,
    },
    "mode/set": {
        vol.Required("config_entry_id"): _ID,
        vol.Required("mode"): vol.In(MODES),
        vol.Optional("until"): vol.Any(None, cv.datetime),
    },
    "override/set": {
        vol.Required("config_entry_id"): _ID,
        vol.Required("room_id"): _ID,
        vol.Required("temperature"): _NUMBER,
        vol.Optional("minutes"): vol.All(int, vol.Range(min=1, max=10080)),
    },
    "override/clear": {vol.Required("config_entry_id"): _ID, vol.Required("room_id"): _ID},
}


def _entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ValueError("Heating instance is not loaded")
    return entry


@callback
def status(entry):
    """Build a detached, JSON-safe snapshot without changing any heating state."""
    engine = entry.runtime_data
    rooms = {}
    for room in engine.store.data.rooms:
        entity = RoomClimate(entry, room.id)
        entity.hass = engine.hass
        attributes = entity.extra_state_attributes
        rooms[room.id] = {
            "name": room.name,
            "current": entity.native_current_temperature,
            "desired": engine.rooms.desired(room),
            "target": entity.native_target_temperature,
            "trvs": {
                trv: available_temperature(state.attributes.get("temperature"))
                if (state := engine.hass.states.get(trv)) is not None
                and state.state not in ("unknown", "unavailable")
                else None
                for trv in room.trvs
            },
            **{
                key: attributes[key]
                for key in (
                    "demanding",
                    "sync_problem",
                    "override_until",
                    "next_change",
                    "next_target",
                )
            },
        }
    config = to_json(engine.store.data)
    return {
        "config_entry_id": entry.entry_id,
        "configuration": config,
        "global": {
            "demand_count": engine.demand.demand_count,
            "virtual_temp": engine.temperature,
            "virtual_temp_raw": engine.demand.virtual_temp_raw,
            "virtual_setpoint": engine.demand.virtual_setpoint,
            "command": asdict(engine.command),
            "last_sent": engine.last_sent.isoformat() if engine.last_sent else None,
            "shadow": engine.store.data.shadow,
            "mode": config["mode"],
        },
        "rooms": rooms,
    }


async def _write(entry, command, msg):
    engine = entry.runtime_data
    if command == "mode/set":
        until = msg.get("until")
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=dt_util.get_default_time_zone())
        await engine.async_set_mode(msg["mode"], until)
        return None
    if command in ("override/set", "override/clear"):
        async with engine._room_lock:
            if command == "override/set":
                await engine.rooms.async_set_override(
                    msg["room_id"], msg["temperature"], msg.get("minutes"), source="card"
                )
            else:
                await engine.rooms.async_clear_override(msg["room_id"])
        await engine.async_recalculate(apply_rooms=True)
        return None

    saved_id = None

    # All fields (including settings+shadow) are decoded and validated together before one save.
    def update(data):
        nonlocal saved_id
        raw = to_json(data)
        if command in ("room/save", "profile/save"):
            kind = "room" if command == "room/save" else "profile"
            value = dict(msg[kind])
            saved_id = value.pop("id", None)
            if saved_id is not None and saved_id not in raw[f"{kind}s"]:
                raise ValueError(f"Unknown {kind}")
            saved_id = saved_id or uuid4().hex
            raw[f"{kind}s"][saved_id] = value
        elif command == "room/delete":
            if msg["room_id"] not in raw["rooms"]:
                raise ValueError("Unknown room")
            del raw["rooms"][msg["room_id"]]
            raw["overrides"].pop(msg["room_id"], None)
        elif command == "profile/delete":
            if msg["profile_id"] not in raw["profiles"]:
                raise ValueError("Unknown profile")
            del raw["profiles"][msg["profile_id"]]
        elif command == "settings/save":
            if "settings" not in msg and "shadow" not in msg:
                raise ValueError("Provide settings or shadow")
            raw["settings"].update(msg.get("settings", {}))
            if "shadow" in msg:
                raw["shadow"] = msg["shadow"]
        return from_json(raw)

    async with engine._lock:
        async with engine._room_lock:
            shadow_before = engine.store.data.shadow
            await engine.store.async_update(update)
            if shadow_before != engine.store.data.shadow:
                engine._last_command = None
                engine._last_send_tick = engine._last_source_tick = None
    await engine.async_data_changed()
    return saved_id


@callback
def _subscribe(hass, connection, msg, entry):
    engine = entry.runtime_data
    timer = None
    last_sent = dt_util.utcnow().timestamp()
    closed = False

    @callback
    def send(now):
        nonlocal timer, last_sent
        timer = None
        if closed:
            return
        last_sent = dt_util.utcnow().timestamp()
        connection.send_event(msg["id"], status(entry))

    @callback
    def changed():
        nonlocal timer
        if not closed and timer is None:
            timer = async_call_later(
                hass, max(0, 1 - (dt_util.utcnow().timestamp() - last_sent)), send
            )

    unsubscribe_engine = engine.listen(changed)

    @callback
    def unsubscribe():
        nonlocal closed, timer
        if closed:
            return
        closed = True
        unsubscribe_engine()
        if timer is not None:
            timer()
            timer = None

    connection.subscriptions[msg["id"]] = unsubscribe

    @callback
    def entry_unloaded():
        unsubscribe()
        connection.subscriptions.pop(msg["id"], None)

    entry.async_on_unload(entry_unloaded)
    connection.send_result(msg["id"])
    connection.send_event(msg["id"], status(entry))


@callback
def async_register_websocket(hass):
    """Register every command once, including with several config entries."""
    marker = f"{DOMAIN}_websocket_registered"
    if hass.data.get(marker):
        return
    hass.data[marker] = True

    def register(command, fields):
        @websocket_api.async_response
        async def handle(hass, connection, msg):
            if connection.user is None:
                connection.send_error(msg["id"], "unauthorized", "Login required")
                return
            if command not in ("get", "subscribe") and not connection.user.is_admin:
                connection.send_error(msg["id"], "unauthorized", "Admin user required")
                return
            if command == "get" and "config_entry_id" not in msg:
                connection.send_result(
                    msg["id"],
                    {
                        "entries": [
                            {"entry_id": entry.entry_id, "title": entry.title}
                            for entry in hass.config_entries.async_entries(DOMAIN)
                            if entry.state is ConfigEntryState.LOADED
                        ]
                    },
                )
                return
            try:
                entry = _entry(hass, msg["config_entry_id"])
            except ValueError as exc:
                connection.send_error(msg["id"], "not_found", str(exc))
                return
            if command == "subscribe":
                _subscribe(hass, connection, msg, entry)
                return
            try:
                saved_id = await _write(entry, command, msg) if command != "get" else None
            except (ValueError, KeyError, TypeError, ServiceValidationError, vol.Invalid) as exc:
                connection.send_error(msg["id"], "invalid_data", str(exc))
                return
            result = status(entry)
            if saved_id is not None:
                result["saved_id"] = saved_id
            connection.send_result(msg["id"], result)

        websocket_api.async_register_command(
            hass,
            f"{DOMAIN}/{command}",
            handle,
            websocket_api.BASE_COMMAND_MESSAGE_SCHEMA.extend(
                {"type": f"{DOMAIN}/{command}", **fields}
            ),
        )

    for command, fields in SCHEMAS.items():
        register(command, fields)
