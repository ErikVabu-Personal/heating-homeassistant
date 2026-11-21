"""Validated entry-scoped services; websocket editing follows in a later PR."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .storage import MODES

SCHEMAS = {
    "set_mode": vol.Schema(
        {
            vol.Required("config_entry_id"): str,
            vol.Required("mode"): vol.In(MODES),
            vol.Optional("until"): cv.datetime,
        }
    ),
    "set_override": vol.Schema(
        {
            vol.Required("config_entry_id"): str,
            vol.Required("room"): cv.entity_id,
            vol.Required("temperature"): vol.Coerce(float),
            vol.Optional("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1)),
        }
    ),
    "clear_override": vol.Schema(
        {vol.Required("config_entry_id"): str, vol.Required("room"): cv.entity_id}
    ),
    "apply_now": vol.Schema({vol.Required("config_entry_id"): str}),
}


def async_register_services(hass):
    async def handle(call):
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
            raise ServiceValidationError("Heating entry is not loaded")
        engine = entry.runtime_data
        try:
            if call.service == "set_mode":
                await engine.async_set_mode(call.data["mode"], call.data.get("until"))
                return
            if call.service in ("set_override", "clear_override"):
                entity = er.async_get(hass).async_get(call.data["room"])
                if entity is None or entity.config_entry_id != entry.entry_id:
                    raise ValueError("Room does not belong to this entry")
                room = next(
                    (
                        room
                        for room in engine.store.data.rooms
                        if entity.unique_id == f"{entry.entry_id}_room_{room.id}"
                    ),
                    None,
                )
                if room is None:
                    raise ValueError("Unknown room climate")
                async with engine._lock:
                    if call.service == "set_override":
                        await engine.rooms.async_set_override(
                            room.id, call.data["temperature"], call.data.get("minutes")
                        )
                    else:
                        await engine.rooms.async_clear_override(room.id)
            await engine.async_recalculate()
        except (ValueError, KeyError) as exc:
            raise ServiceValidationError(str(exc)) from exc

    for name, schema in SCHEMAS.items():
        if not hass.services.has_service(DOMAIN, name):
            hass.services.async_register(DOMAIN, name, handle, schema=schema)
