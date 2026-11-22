"""The committed card is served locally and registered once for all entries."""

from unittest.mock import patch

import pytest
from homeassistant.components import frontend
from homeassistant.setup import async_setup_component

from custom_components.central_heating.const import DOMAIN
from custom_components.central_heating.frontend import CARD_URL, async_register_card

pytestmark = pytest.mark.integration


async def test_card_static_path_extra_js_and_repeated_registration(hass, hass_client):
    with patch.object(frontend, "add_extra_js_url", wraps=frontend.add_extra_js_url) as extra:
        assert await async_setup_component(hass, DOMAIN, {})
        await async_register_card(hass)
        await async_register_card(hass)
        extra.assert_called_once_with(hass, f"{CARD_URL}?v=0.1.0")
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert response.content_type in ("application/javascript", "text/javascript")
    script = await response.text()
    assert "central-heating-card" in script
    assert f"{CARD_URL}?v=0.1.0" in hass.data[frontend.DATA_EXTRA_MODULE_URL].urls


async def test_card_registration_failure_is_retryable(hass):
    assert await async_setup_component(hass, "http", {})
    with patch.object(
        type(hass.http), "async_register_static_paths", side_effect=RuntimeError("test")
    ):
        with pytest.raises(RuntimeError):
            await async_register_card(hass)
    assert not hass.data.get(f"{DOMAIN}_card_registered")
    await async_register_card(hass)
    assert hass.data[f"{DOMAIN}_card_registered"]
