"""Global heating mode."""

from homeassistant.components.select import SelectEntity

from .entity import HeatingEntity
from .storage import MODES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ModeSelect(entry, "mode")])


class ModeSelect(HeatingEntity, SelectEntity):
    _attr_options = list(MODES)

    @property
    def current_option(self):
        return self.engine.store.data.mode.value

    async def async_select_option(self, option: str) -> None:
        await self.engine.async_set_mode(option)
