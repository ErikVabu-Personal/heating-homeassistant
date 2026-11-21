"""Real HA fixtures with mocked MQTT; no live broker or instance."""

import pytest


@pytest.fixture(autouse=True)
def custom_components_enabled(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def frontend_setup():
    # The card is not part of these PRs; retain dependency loading without a UI bundle.
    from unittest.mock import AsyncMock, patch

    with patch("homeassistant.components.frontend.async_setup", new=AsyncMock(return_value=True)):
        yield


@pytest.fixture
async def mqtt_mock(mqtt_mock, mqtt_client_mock):
    # Disconnect the wrapped client before its patch context is torn down.
    yield mqtt_mock
    await mqtt_mock.async_disconnect()
    from unittest.mock import Mock

    mqtt_client_mock.on_socket_close(mqtt_client_mock, None, Mock(fileno=Mock(return_value=-1)))
