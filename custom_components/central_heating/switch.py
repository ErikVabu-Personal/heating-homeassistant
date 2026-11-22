"""Stored shadow mode; new entries start enabled."""

from homeassistant.components.switch import SwitchEntity

from .entity import HeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ShadowSwitch(entry, "shadow")])


class ShadowSwitch(HeatingEntity, SwitchEntity):
    @property
    def is_on(self):
        return self.engine.store.data.shadow

    async def async_turn_on(self, **kwargs) -> None:
        await self.engine.async_set_shadow(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.engine.async_set_shadow(False)
