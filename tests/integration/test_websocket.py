"""Websocket commands through an authenticated local Home Assistant server."""

import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest
from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed_exact,
)

from custom_components.central_heating.const import ADAPTER, DEFAULT_PREFIX, DOMAIN
from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Profile, Room
from custom_components.central_heating.storage import HeatingStore, to_json
from custom_components.central_heating.websocket import SCHEMAS, async_register_websocket

pytestmark = pytest.mark.integration


@pytest.fixture
async def entry(hass, mqtt_mock):
    entry = MockConfigEntry(
        domain=DOMAIN, title="Boiler A", data={"adapter": ADAPTER, "prefix": DEFAULT_PREFIX}
    )
    entry.add_to_hass(hass)
    profile = Profile("Profile A", tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS))
    room = Room("Room A", ("climate.trv_a",), profile.id)
    hass.states.async_set("climate.trv_a", "heat", {"current_temperature": 17, "temperature": 21})
    store = HeatingStore(hass, entry.entry_id)
    await store.async_update(lambda data: replace(data, profiles=(profile,), rooms=(room,)))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    yield entry
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.fixture
async def client(hass, entry, hass_ws_client):
    return await hass_ws_client(hass)


async def command(client, entry, name, **data):
    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/{name}", "config_entry_id": entry.entry_id, **data}
    )
    return await client.receive_json()


def profile_payload(name="Profile B"):
    return {"name": name, "days": {day: [{"start": "00:00", "target": 18}] for day in WEEKDAYS}}


async def test_get_discovery_and_live_status(client, entry):
    await client.send_json_auto_id({"type": f"{DOMAIN}/get"})
    result = await client.receive_json()
    assert result["result"] == {"entries": [{"entry_id": entry.entry_id, "title": "Boiler A"}]}
    result = await command(client, entry, "get")
    assert result["success"]
    status = result["result"]
    assert status["configuration"] == to_json(entry.runtime_data.store.data)
    room = entry.runtime_data.store.data.rooms[0]
    assert status["rooms"][room.id]["current"] == 17
    assert status["rooms"][room.id]["target"] == 21
    assert status["rooms"][room.id]["desired"] is None
    assert status["rooms"][room.id]["trvs"] == {"climate.trv_a": 21}
    assert status["global"]["shadow"]
    assert status["global"]["mode"]["value"] == "manual"
    assert status["rooms"][room.id]["next_change"] is None


async def test_profile_room_crud_and_references(client, entry):
    result = await command(client, entry, "profile/save", profile=profile_payload())
    assert result["success"]
    profile_id = result["result"]["saved_id"]
    result = await command(
        client, entry, "profile/save", profile={**profile_payload("Profile C"), "id": profile_id}
    )
    assert result["result"]["configuration"]["profiles"][profile_id]["name"] == "Profile C"
    result = await command(
        client,
        entry,
        "room/save",
        room={"name": "Room B", "trvs": ["climate.trv_b"], "profile_id": profile_id},
    )
    room_id = result["result"]["saved_id"]
    result = await command(
        client,
        entry,
        "room/save",
        room={
            "id": room_id,
            "name": "Room C",
            "trvs": ["climate.trv_b"],
            "profile_id": profile_id,
            "area_id": "area_b",
            "enabled": False,
        },
    )
    assert result["result"]["configuration"]["rooms"][room_id]["name"] == "Room C"
    result = await command(client, entry, "profile/delete", profile_id=profile_id)
    assert not result["success"] and result["error"]["code"] == "invalid_data"
    result = await command(client, entry, "room/delete", room_id=room_id)
    assert room_id not in result["result"]["configuration"]["rooms"]
    result = await command(client, entry, "profile/delete", profile_id=profile_id)
    assert profile_id not in result["result"]["configuration"]["profiles"]


async def test_settings_shadow_mode_override_and_clear(client, entry):
    engine = entry.runtime_data
    room_id = engine.store.data.rooms[0].id
    result = await command(
        client,
        entry,
        "settings/save",
        settings={"frost_temperature": 8, "override_minutes": 45},
        shadow=False,
    )
    assert result["success"]
    assert engine.store.data.settings.frost_temperature == 8 and not engine.store.data.shadow
    result = await command(client, entry, "mode/set", mode="away", until="2027-01-01T12:00:00")
    assert result["success"] and engine.store.data.mode.until.tzinfo is not None
    result = await command(
        client, entry, "override/set", room_id=room_id, temperature=23, minutes=30
    )
    assert result["success"] and engine.store.data.overrides[0].target == 23
    result = await command(client, entry, "override/clear", room_id=room_id)
    assert result["success"] and not engine.store.data.overrides
    assert (await command(client, entry, "mode/set", mode="manual"))["success"]


@pytest.mark.parametrize(
    "name,payload",
    [
        ("get", {"config_entry_id": "missing"}),
        ("subscribe", {"config_entry_id": "missing"}),
        (
            "room/save",
            {"room": {"name": "Room B", "trvs": ["climate.trv_a"], "profile_id": "missing"}},
        ),
        ("room/delete", {"room_id": "missing"}),
        (
            "profile/save",
            {
                "profile": {
                    "name": "Profile B",
                    "days": {day: [{"start": "00:05", "target": 18}] for day in WEEKDAYS},
                }
            },
        ),
        ("profile/delete", {"profile_id": "missing"}),
        (
            "settings/save",
            {"settings": {"frost_temperature": 8, "hysteresis": 0.15}, "shadow": False},
        ),
        ("mode/set", {"mode": "auto", "until": "2027-01-01T12:00:00+00:00"}),
        ("override/set", {"room_id": "missing", "temperature": 23}),
        ("override/clear", {"room_id": "missing"}),
    ],
)
async def test_invalid_semantics_are_atomic(client, entry, name, payload):
    before = entry.runtime_data.store.data
    result = await command(client, entry, name, **payload)
    assert not result["success"]
    assert result["error"]["code"] in ("invalid_data", "not_found")
    assert entry.runtime_data.store.data is before


@pytest.mark.parametrize(
    "name,payload",
    [
        ("get", {"unexpected": True}),
        ("subscribe", {"unexpected": True}),
        ("room/save", {"room": {"name": "Room B"}}),
        ("room/delete", {"room_id": 1}),
        ("profile/save", {"profile": {"name": "Profile B", "days": {}}}),
        ("profile/delete", {"profile_id": 1}),
        ("settings/save", {"settings": {"unexpected": True}}),
        ("mode/set", {"mode": "invalid"}),
        ("override/set", {"room_id": "room_a", "temperature": 23, "minutes": 10081}),
        ("override/clear", {"room_id": 1}),
    ],
)
async def test_invalid_schemas_are_atomic(client, entry, name, payload):
    before = entry.runtime_data.store.data
    result = await command(client, entry, name, **payload)
    assert not result["success"] and result["error"]["code"] == "invalid_format"
    assert entry.runtime_data.store.data is before


@pytest.mark.parametrize("name", [name for name in SCHEMAS if name not in ("get", "subscribe")])
async def test_non_admin_cannot_write(hass, client, entry, hass_admin_user, name):
    # Permissions are checked per call, not cached when the socket is opened.
    hass_admin_user.is_owner = False
    await hass.auth.async_update_user(hass_admin_user, group_ids=[GROUP_ID_USER])
    room = entry.runtime_data.store.data.rooms[0]
    payloads = {
        "room/save": {
            "room": {"name": "Room B", "trvs": ["climate.trv_b"], "profile_id": room.profile_id}
        },
        "room/delete": {"room_id": room.id},
        "profile/save": {"profile": profile_payload()},
        "profile/delete": {"profile_id": room.profile_id},
        "settings/save": {"shadow": False},
        "mode/set": {"mode": "auto"},
        "override/set": {"room_id": room.id, "temperature": 23},
        "override/clear": {"room_id": room.id},
    }
    before = entry.runtime_data.store.data
    result = await command(client, entry, name, **payloads[name])
    assert not result["success"] and result["error"]["code"] == "unauthorized"
    assert entry.runtime_data.store.data is before


async def test_non_admin_reads_and_subscribes(hass, client, entry, hass_admin_user):
    hass_admin_user.is_owner = False
    await hass.auth.async_update_user(hass_admin_user, group_ids=[GROUP_ID_USER])
    assert (await command(client, entry, "get"))["success"]
    result = await command(client, entry, "subscribe")
    assert result["success"]
    event = await client.receive_json()
    assert event["event"]["config_entry_id"] == entry.entry_id
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
    assert (await client.receive_json())["success"]


async def test_subscribe_coalesces_once_per_second_and_unsubscribes(hass, client, entry, freezer):
    engine = entry.runtime_data
    before = len(engine._listeners)
    result = await command(client, entry, "subscribe")
    subscription_id = result["id"]
    await client.receive_json()  # Initial snapshot.
    assert len(engine._listeners) == before + 1
    for _ in range(5):
        engine._notify()
    freezer.tick(0.9)
    async_fire_time_changed_exact(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    # Send a regular get; any premature event would arrive before its result.
    result = await command(client, entry, "get")
    assert result["type"] == "result"
    freezer.tick(0.1)
    async_fire_time_changed_exact(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    await hass.async_block_till_done()
    await client.send_json_auto_id({"type": f"{DOMAIN}/get", "config_entry_id": entry.entry_id})
    event = await client.receive_json()
    assert event["type"] == "event" and event["id"] == subscription_id
    assert (await client.receive_json())["type"] == "result"
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": subscription_id})
    assert (await client.receive_json())["success"]
    assert len(engine._listeners) == before
    engine._notify()
    freezer.tick(2)
    await asyncio.sleep(0)
    result = await command(client, entry, "get")
    assert result["type"] == "result"  # No queued event after unsubscribe.


async def test_socket_close_and_entry_unload_remove_pending_subscription(hass, client, entry):
    engine = entry.runtime_data
    await command(client, entry, "subscribe")
    await client.receive_json()
    before = len(engine._listeners)
    engine._notify()
    await client.close()
    await hass.async_block_till_done()
    assert len(engine._listeners) == before - 1
    # Unloading also calls the idempotent cleanup; fixture unload may safely call again.
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_websocket_registers_once(hass, entry):
    with patch("homeassistant.components.websocket_api.async_register_command") as register:
        async_register_websocket(hass)
        register.assert_not_called()
