"""Serve the committed card once for all config entries; no external resources."""

from hashlib import sha256
from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

CARD_URL = "/central_heating/central-heating-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    if hass.data.get(f"{DOMAIN}_card_registered"):
        return
    directory = Path(__file__).parent
    bundle = directory / "frontend" / "central-heating-card.js"
    digest = await hass.async_add_executor_job(lambda: sha256(bundle.read_bytes()).hexdigest()[:16])
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL, str(directory / "frontend" / "central-heating-card.js"), False)]
    )
    frontend.add_extra_js_url(hass, f"{CARD_URL}?v={digest}")
    hass.data[f"{DOMAIN}_card_registered"] = True
