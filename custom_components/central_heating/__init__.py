"""Central Heating entry lifecycle; pure modules remain importable without HA."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS = ["select", "switch", "sensor", "binary_sensor", "number", "climate"]


def __getattr__(name: str):
    # HA asks for CONFIG_SCHEMA during setup; defer HA imports for the pure modules.
    if name == "CONFIG_SCHEMA":
        from homeassistant.helpers import config_validation as cv

        from .const import DOMAIN

        schema = cv.config_entry_only_config_schema(DOMAIN)
        globals()[name] = schema
        return schema
    raise AttributeError(name)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    from .frontend import async_register_card
    from .services import async_register_services
    from .websocket import async_register_websocket

    async_register_services(hass)
    async_register_websocket(hass)
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.exceptions import ConfigEntryError

    from .boiler.diyless_mqtt import DiylessAdapter
    from .config_flow import validate_prefix
    from .const import ADAPTER
    from .engine import HeatingEngine
    from .rooms import RoomController
    from .storage import HeatingStore

    try:
        if entry.data["adapter"] != ADAPTER:
            raise ValueError("Unsupported boiler adapter")
        prefix = validate_prefix(entry.options.get("prefix", entry.data["prefix"]))
        store = HeatingStore(hass, entry.entry_id)
        await store.async_load()
    except (ValueError, KeyError) as exc:
        raise ConfigEntryError(str(exc)) from exc
    entry.runtime_data = HeatingEngine(hass, store, DiylessAdapter(hass, entry.entry_id, prefix))
    entry.runtime_data.rooms = RoomController(entry.runtime_data, entry.entry_id)
    entry.async_on_unload(entry.runtime_data.close_subscriptions)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await entry.runtime_data.async_start()
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if entry.runtime_data.adapter.prefix != entry.options.get("prefix", entry.data["prefix"]):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop(unloading=True)
        return True
    return False


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    from homeassistant.helpers import issue_registry as ir

    from .const import DOMAIN
    from .storage import HeatingStore

    await HeatingStore(hass, entry.entry_id).async_remove()
    ir.async_delete_issue(hass, DOMAIN, f"mqtt_{entry.entry_id}")
    for domain, issue_id in tuple(ir.async_get(hass).issues):
        if domain == DOMAIN and issue_id.startswith(f"sync_{entry.entry_id}_"):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
