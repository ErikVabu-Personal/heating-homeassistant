"""Serve the committed card once for all config entries; no external resources."""

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARD_URL = "/central_heating/central-heating-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    directory = Path(__file__).parent
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(directory / "frontend" / "central-heating-card.js"), False)]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    hass.data[f"{DOMAIN}_card_registered"] = True
