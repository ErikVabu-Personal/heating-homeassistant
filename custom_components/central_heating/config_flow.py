"""Configure one boiler; MQTT remains an optional integration dependency."""

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState, ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .const import ADAPTER, DEFAULT_PREFIX, DOMAIN


def validate_prefix(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value.endswith("/")
        or any(character in value for character in ("+", "#", "\x00"))
    ):
        raise vol.Invalid("Invalid MQTT topic prefix")
    return value


class CentralHeatingConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        if not any(
            entry.state is ConfigEntryState.LOADED
            for entry in self.hass.config_entries.async_entries("mqtt")
        ):
            return self.async_abort(reason="mqtt_required")
        schema = vol.Schema(
            {
                vol.Required("name", default="Central Heating"): vol.All(str, vol.Length(min=1)),
                vol.Required("adapter", default=ADAPTER): vol.In([ADAPTER]),
                vol.Required("prefix", default=DEFAULT_PREFIX): str,
            }
        )
        errors = {}
        if user_input is not None:
            try:
                clean = schema(user_input)
                clean["prefix"] = validate_prefix(clean["prefix"])
            except vol.Invalid:
                errors["prefix"] = "invalid_config"
            else:
                self._async_abort_entries_match({"prefix": clean["prefix"]})
                if any(
                    entry.options.get("prefix", entry.data.get("prefix")) == clean["prefix"]
                    for entry in self._async_current_entries()
                ):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(title=clean["name"], data=clean)
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return CentralHeatingOptionsFlow()


class CentralHeatingOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        schema = vol.Schema(
            {
                vol.Required(
                    "prefix",
                    default=self.config_entry.options.get(
                        "prefix", self.config_entry.data["prefix"]
                    ),
                ): str
            }
        )
        errors = {}
        if user_input is not None:
            try:
                clean = schema(user_input)
                clean["prefix"] = validate_prefix(clean["prefix"])
            except vol.Invalid:
                errors["prefix"] = "invalid_config"
            else:
                if any(
                    entry.entry_id != self.config_entry.entry_id
                    and entry.options.get("prefix", entry.data.get("prefix")) == clean["prefix"]
                    for entry in self.hass.config_entries.async_entries(DOMAIN)
                ):
                    errors["prefix"] = "already_configured"
                else:
                    return self.async_create_entry(title="", data=clean)
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
