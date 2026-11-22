"""The committed card is served locally and registered once for all entries."""

from hashlib import sha256
from pathlib import Path
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
        bundle = (
            Path(__file__).parents[2]
            / "custom_components"
            / "central_heating"
            / "frontend"
            / "central-heating-card.js"
        )
        digest = sha256(bundle.read_bytes()).hexdigest()[:16]
        extra.assert_called_once_with(hass, f"{CARD_URL}?v={digest}")
    client = await hass_client()
    response = await client.get(CARD_URL)
    assert response.status == 200
    assert response.content_type in ("application/javascript", "text/javascript")
    script = await response.text()
    assert "central-heating-card" in script
    assert f"{CARD_URL}?v={digest}" in hass.data[frontend.DATA_EXTRA_MODULE_URL].urls


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


async def test_bundle_cache_key_changes_with_content(hass):
    assert await async_setup_component(hass, "http", {})
    with (
        patch("pathlib.Path.read_bytes", return_value=b"bundle one"),
        patch.object(frontend, "add_extra_js_url") as extra,
    ):
        await async_register_card(hass)
        first = extra.call_args.args[1]
    hass.data.pop(f"{DOMAIN}_card_registered")
    with (
        patch("pathlib.Path.read_bytes", return_value=b"bundle two"),
        patch.object(type(hass.http), "async_register_static_paths"),
        patch.object(frontend, "add_extra_js_url") as extra,
    ):
        await async_register_card(hass)
        second = extra.call_args.args[1]
    assert first != second
    assert first.endswith(sha256(b"bundle one").hexdigest()[:16])
    assert second.endswith(sha256(b"bundle two").hexdigest()[:16])
