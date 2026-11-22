"""Global heating mode."""

from homeassistant.components.select import SelectEntity

from .entity import HeatingEntity
from .storage import MODES


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ModeSelect(entry, "mode"), ActiveScheduleSelect(entry, "active_schedule")])


class ModeSelect(HeatingEntity, SelectEntity):
    _attr_options = list(MODES)

    @property
    def current_option(self):
        return self.engine.store.data.mode.value

    async def async_select_option(self, option: str) -> None:
        await self.engine.async_set_mode(option)


class ActiveScheduleSelect(HeatingEntity, SelectEntity):
    @property
    def options(self):
        return [item.name for item in self.engine.store.data.schedules]

    @property
    def current_option(self):
        return next(
            item.name
            for item in self.engine.store.data.schedules
            if item.id == self.engine.store.data.active_schedule_id
        )

    async def async_select_option(self, option: str) -> None:
        await self.engine.async_set_schedule(option)
