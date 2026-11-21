"""Computed boiler call, including shadow calculations."""

from dataclasses import asdict

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import HeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([BoilerCall(entry, "boiler_call")])


class BoilerCall(HeatingEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.engine.command.heat

    @property
    def extra_state_attributes(self):
        return {
            "last_command": asdict(self.engine.command),
            "last_sent": self.engine.last_sent.isoformat() if self.engine.last_sent else None,
            "shadow": self.engine.store.data.shadow,
        }
