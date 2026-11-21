"""DIYLESS commands through Home Assistant's MQTT connection only."""

import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir

from ..const import DOMAIN
from .base import BoilerCommand

_LOGGER = logging.getLogger(__name__)


class DiylessAdapter:
    def __init__(self, hass: HomeAssistant, entry_id: str, prefix: str) -> None:
        self.hass, self.entry_id, self.prefix = hass, entry_id, prefix
        self.last_success = False

    async def _publish(self, values: dict[str, str]) -> None:
        self.last_success = False
        if not any(
            entry.state is ConfigEntryState.LOADED
            for entry in self.hass.config_entries.async_entries("mqtt")
        ):
            self._unavailable()
            return
        try:
            for suffix, payload in values.items():
                await mqtt.async_publish(
                    self.hass, f"{self.prefix}/{suffix}", payload, qos=0, retain=False
                )
        except HomeAssistantError:
            self._unavailable()
            return
        self.last_success = True
        ir.async_delete_issue(self.hass, DOMAIN, f"mqtt_{self.entry_id}")

    def _unavailable(self) -> None:
        _LOGGER.warning("Central Heating cannot send: MQTT is unavailable")
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            f"mqtt_{self.entry_id}",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="mqtt_unavailable",
        )

    async def async_start(self) -> None:
        await self._publish({"tempSource": "1"})

    async def async_apply(self, cmd: BoilerCommand, *, keepalive: bool) -> None:
        values = {}
        if cmd.room_temperature is not None:
            values["temperature"] = f"{cmd.room_temperature:.2f}"
        values["targetTemperature"] = f"{cmd.setpoint:.1f}"
        values["mode"] = "heat" if cmd.heat else "off"
        await self._publish(values)

    async def async_stop(self, *, unloading: bool) -> None:
        if unloading:
            await self._publish({"mode": "off"})
