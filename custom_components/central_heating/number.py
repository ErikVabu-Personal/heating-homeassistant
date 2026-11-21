"""Stored boiler tuning settings."""

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.const import UnitOfTemperature
from homeassistant.helpers.entity import EntityCategory

from .entity import HeatingEntity

LIMITS = {
    "frost_temperature": (5, 18, 0.5),
    "hysteresis": (0.1, 1.0, 0.1),
    "away_temperature": (5, 30, 0.5),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SettingNumber(entry, key) for key in LIMITS])


class SettingNumber(HeatingEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_mode = NumberMode.BOX

    def __init__(self, entry, key):
        super().__init__(entry, key)
        self.key = key
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_step = LIMITS[
            key
        ]

    @property
    def native_value(self):
        return getattr(self.engine.store.data.settings, self.key)

    async def async_set_native_value(self, value: float) -> None:
        await self.engine.async_settings(**{self.key: value})
