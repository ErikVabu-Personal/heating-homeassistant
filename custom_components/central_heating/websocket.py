"""Authenticated reads, admin-only atomic writes and throttled status subscriptions."""

import asyncio
import logging
from dataclasses import asdict

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .climate import RoomClimate
from .const import DOMAIN
from .demand import available_temperature
from .schedule import WEEKDAYS
from .schedule_config import affected_rooms, edit
from .storage import MODE_INPUTS, HeatingStore, to_json

_LOGGER = logging.getLogger(__name__)

_NAME = vol.All(str, vol.Length(min=1, max=200))
_ID = vol.All(str, vol.Length(min=1, max=100))
_NUMBER = vol.Any(int, float)
_BLOCK = vol.Schema({vol.Required("start"): str, vol.Required("target"): _NUMBER})
_WEEK = vol.Schema(
    {vol.Required("days"): vol.Schema({vol.Required(day): [_BLOCK] for day in WEEKDAYS})}
)
_SCHEDULE = vol.Schema(
    {
        vol.Optional("id"): _ID,
        vol.Required("name"): _NAME,
        vol.Optional("rooms"): {_ID: _WEEK},
    }
)
_ROOM = vol.Schema(
    {
        vol.Optional("id"): _ID,
        vol.Required("name"): _NAME,
        vol.Required("trvs"): [cv.entity_id],
        vol.Optional("copy_week_from_room"): _ID,
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
    "schedule/save": {vol.Required("config_entry_id"): _ID, vol.Required("schedule"): _SCHEDULE},
    "schedule/delete": {vol.Required("config_entry_id"): _ID, vol.Required("schedule_id"): _ID},
    "schedule/activate": {vol.Required("config_entry_id"): _ID, vol.Required("schedule_id"): _ID},
    "settings/save": {
        vol.Required("config_entry_id"): _ID,
        vol.Optional("settings"): _SETTINGS,
        vol.Optional("shadow"): bool,
    },
    "mode/set": {
        vol.Required("config_entry_id"): _ID,
        vol.Required("mode"): vol.In(MODE_INPUTS),
        vol.Optional("until"): vol.Any(None, cv.datetime),
        vol.Optional("schedule_id"): _ID,
    },
    "override/set": {
        vol.Required("config_entry_id"): _ID,
        vol.Required("room_id"): _ID,
        vol.Required("temperature"): _NUMBER,
        vol.Optional("minutes"): vol.All(int, vol.Range(min=1, max=10080)),
        vol.Optional("kind"): vol.In(["next_block", "duration"]),
    },
    "override/clear": {vol.Required("config_entry_id"): _ID, vol.Required("room_id"): _ID},
}


def _entry(hass, entry_id):
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        raise ValueError("Heating instance is not loaded")
    return entry


@callback
def room_entity_ids(hass):
    """Virtual room climates are never physical thermostats, including other instances."""
    return sorted(
        item.entity_id
        for item in er.async_get(hass).entities.values()
        if item.platform == DOMAIN and item.entity_id.startswith("climate.")
    )


async def async_used_trv_ids(hass, entry_id, *, strict=False):
    """Read ownership without migrating other stores; only room saves fail closed."""
    used = set()
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry_id:
            continue
        try:
            runtime = getattr(other, "runtime_data", None)
            data = (
                runtime.store.data
                if runtime is not None
                else await HeatingStore.async_read_only(hass, other.entry_id)
            )
            used.update(trv for room in data.rooms for trv in room.trvs)
        except OSError, ValueError, TypeError, KeyError, AttributeError:
            if strict:
                raise ValueError(
                    "Cannot verify thermostat ownership: another heating instance's storage is unreadable"
                ) from None
            _LOGGER.warning(
                "Skipping unreadable thermostat ownership for heating entry %s", other.entry_id
            )
    return sorted(used)


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
            "entity_id": er.async_get(engine.hass).async_get_entity_id(
                "climate", DOMAIN, f"{entry.entry_id}_room_{room.id}"
            ),
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
        "room_entity_ids": room_entity_ids(engine.hass),
        "used_trv_ids": getattr(engine, "other_entry_trvs", []),
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
        await engine.async_set_mode(msg["mode"], until, msg.get("schedule_id"))
        return None
    if command in ("override/set", "override/clear"):
        async with engine._room_lock:
            if command == "override/set":
                await engine.rooms.async_set_override(
                    msg["room_id"],
                    msg["temperature"],
                    msg.get("minutes"),
                    source="card",
                    kind=msg.get("kind"),
                )
            else:
                await engine.rooms.async_clear_override(msg["room_id"])
        await engine.async_recalculate(apply_rooms=True)
        return None

    saved_id = None

    before = engine.store.data

    def update(data):
        nonlocal saved_id
        candidate, saved_id = edit(data, command, msg)
        return candidate

    async with engine.hass.data[f"{DOMAIN}_trv_lock"]:
        async with engine._lock:
            async with engine._room_lock:
                if command == "room/save":
                    trvs = set(msg["room"]["trvs"])
                    if trvs.intersection(room_entity_ids(engine.hass)):
                        raise ValueError("Virtual room climates cannot be used as thermostats")
                    if trvs.intersection(
                        await async_used_trv_ids(engine.hass, entry.entry_id, strict=True)
                    ):
                        raise ValueError("A thermostat already belongs to another heating instance")
                before = engine.store.data
                shadow_before = engine.store.data.shadow
                await engine.store.async_update(update)
                if shadow_before != engine.store.data.shadow:
                    engine._last_command = None
                    engine._last_send_tick = engine._last_source_tick = None
    if command == "room/delete":
        registry = er.async_get(engine.hass)
        entity_id = registry.async_get_entity_id(
            "climate", DOMAIN, f"{entry.entry_id}_room_{msg['room_id']}"
        )
        if entity_id is not None:
            registry.async_remove(entity_id)
    engine.other_entry_trvs = await async_used_trv_ids(engine.hass, entry.entry_id)
    changed = affected_rooms(before, engine.store.data)
    await engine.async_data_changed(room_ids=changed if command.startswith("schedule/") else None)
    return saved_id


@callback
def _subscribe(hass, connection, msg, entry):
    engine = entry.runtime_data
    timer = None
    last_sent = dt_util.utcnow().timestamp()
    closed = False
    last_snapshot = status(entry)

    @callback
    def send(now):
        nonlocal timer, last_sent, last_snapshot
        timer = None
        if closed:
            return
        snapshot = status(entry)
        if snapshot == last_snapshot:
            return
        last_sent = dt_util.utcnow().timestamp()
        last_snapshot = snapshot
        connection.send_event(msg["id"], snapshot)

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
        engine._subscription_cleanups.discard(entry_unloaded)
        unsubscribe_engine()
        if timer is not None:
            timer()
            timer = None

    connection.subscriptions[msg["id"]] = unsubscribe

    @callback
    def entry_unloaded():
        try:
            if not closed:
                connection.send_event(msg["id"], {"unloaded": True})
        finally:
            unsubscribe()
            # Keep the inert unsubscribe record until the HA client acknowledges it.
            # No engine, timer or unload hook remains attached to this record.
            connection.subscriptions[msg["id"]] = lambda: None

    engine._subscription_cleanups.add(entry_unloaded)
    connection.send_result(msg["id"])
    connection.send_event(msg["id"], last_snapshot)


@callback
def async_register_websocket(hass):
    """Register every command once, including with several config entries."""
    marker = f"{DOMAIN}_websocket_registered"
    if hass.data.get(marker):
        return
    hass.data[marker] = True
    hass.data[f"{DOMAIN}_trv_lock"] = asyncio.Lock()

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
                        ],
                        "room_entity_ids": room_entity_ids(hass),
                    },
                )
                return
            try:
                entry = _entry(hass, msg["config_entry_id"])
            except ValueError as exc:
                connection.send_error(msg["id"], "not_found", str(exc))
                return
            try:
                entry.runtime_data.other_entry_trvs = await async_used_trv_ids(hass, entry.entry_id)
            except ValueError as exc:
                connection.send_error(msg["id"], "invalid_data", str(exc))
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
