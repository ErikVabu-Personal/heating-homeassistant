"""Virtual boiler measurements."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTemperature

from .entity import HeatingEntity

KEYS = ("demand_count", "virtual_temperature", "virtual_temperature_raw", "virtual_setpoint")


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([HeatingSensor(entry, key) for key in KEYS])


class HeatingSensor(HeatingEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry, key):
        super().__init__(entry, key)
        self.key = key
        if key != "demand_count":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        return {
            "demand_count": self.engine.demand.demand_count,
            "virtual_temperature": self.engine.temperature,
            "virtual_temperature_raw": self.engine.demand.virtual_temp_raw,
            "virtual_setpoint": self.engine.demand.virtual_setpoint,
        }[self.key]
