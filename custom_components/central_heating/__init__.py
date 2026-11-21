"""Central Heating entry lifecycle."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .boiler.diyless_mqtt import DiylessAdapter
from .config_flow import validate_prefix
from .const import ADAPTER
from .engine import HeatingEngine
from .storage import HeatingStore

PLATFORMS = [
    Platform.SELECT,
    Platform.SWITCH,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.NUMBER,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data["adapter"] != ADAPTER:
        raise ValueError("Unsupported boiler adapter")
    prefix = validate_prefix(entry.options.get("prefix", entry.data["prefix"]))
    store = HeatingStore(hass, entry.entry_id)
    await store.async_load()
    entry.runtime_data = HeatingEngine(hass, store, DiylessAdapter(hass, entry.entry_id, prefix))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await entry.runtime_data.async_start()
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop(unloading=True)
        return True
    return False
