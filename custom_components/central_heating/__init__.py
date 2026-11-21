"""Central Heating entry lifecycle; pure modules remain importable without HA."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

PLATFORMS = ["select", "switch", "sensor", "binary_sensor", "number"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    from homeassistant.exceptions import ConfigEntryError

    from .boiler.diyless_mqtt import DiylessAdapter
    from .config_flow import validate_prefix
    from .const import ADAPTER
    from .engine import HeatingEngine
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
