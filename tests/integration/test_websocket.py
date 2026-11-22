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
    assert result["result"]["entries"] == [{"entry_id": entry.entry_id, "title": "Boiler A"}]
    assert len(result["result"]["room_entity_ids"]) == 1
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
    engine.temperature = 18.5
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


async def test_status_exposes_real_virtual_entities_across_instances(hass, client, entry):
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    own_room = entry.runtime_data.store.data.rooms[0]
    own_entity = registry.async_get_entity_id(
        "climate", DOMAIN, f"{entry.entry_id}_room_{own_room.id}"
    )
    assert own_entity is not None
    other = MockConfigEntry(
        domain=DOMAIN, data={"adapter": ADAPTER, "prefix": "boiler_b/properties"}
    )
    other.add_to_hass(hass)
    other_entity = registry.async_get_or_create(
        "climate",
        DOMAIN,
        f"{other.entry_id}_room_other",
        suggested_object_id="renamed_room",
        config_entry=other,
    )
    # Real entity IDs can be user-renamed and do not contain random room IDs.
    assert other_entity.entity_id == "climate.renamed_room"
    result = await command(client, entry, "get")
    assert result["result"]["rooms"][own_room.id]["entity_id"] == own_entity
    assert set(result["result"]["room_entity_ids"]) == {own_entity, other_entity.entity_id}
    await client.send_json_auto_id({"type": f"{DOMAIN}/get"})
    discovery = await client.receive_json()
    assert other_entity.entity_id in discovery["result"]["room_entity_ids"]


async def test_explicit_next_change_ignores_duration_default(client, entry, freezer):
    from datetime import UTC, datetime, timedelta

    engine = entry.runtime_data
    room_id = engine.store.data.rooms[0].id
    freezer.move_to("2026-01-05T08:00:00+00:00")
    await engine.store.async_settings(override_default="duration", override_minutes=37)
    result = await command(
        client, entry, "override/set", room_id=room_id, temperature=23, kind="next_block"
    )
    assert result["success"]
    assert engine.store.data.overrides[0].until == datetime(
        2026, 1, 12, 8, tzinfo=UTC
    )  # Constant week cap.
    result = await command(
        client, entry, "override/set", room_id=room_id, temperature=23, kind="duration", minutes=60
    )
    assert result["success"]
    assert engine.store.data.overrides[0].until == datetime(2026, 1, 5, 8, tzinfo=UTC) + timedelta(
        minutes=60
    )
    result = await command(
        client, entry, "override/set", room_id=room_id, temperature=23, kind="duration"
    )
    assert result["success"]
    assert engine.store.data.overrides[0].until == datetime(2026, 1, 5, 8, tzinfo=UTC) + timedelta(
        minutes=37
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "next_block", "minutes": 60},
        {"kind": "invalid"},
    ],
)
async def test_invalid_explicit_override_kind_is_atomic(client, entry, payload):
    before = entry.runtime_data.store.data
    result = await command(
        client, entry, "override/set", room_id=before.rooms[0].id, temperature=23, **payload
    )
    assert not result["success"]
    assert entry.runtime_data.store.data is before


async def test_fifty_subscribe_cycles_keep_cleanup_sets_and_unload_hooks_flat(client, entry):
    engine = entry.runtime_data
    baseline_hooks = len(entry._on_unload or [])
    baseline_listeners = len(engine._listeners)
    assert not engine._subscription_cleanups
    for _ in range(50):
        result = await command(client, entry, "subscribe")
        assert result["success"]
        await client.receive_json()
        assert len(engine._subscription_cleanups) == 1
        assert len(engine._listeners) == baseline_listeners + 1
        assert len(entry._on_unload or []) == baseline_hooks
        await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
        assert (await client.receive_json())["success"]
        assert not engine._subscription_cleanups
        assert len(engine._listeners) == baseline_listeners
        assert len(entry._on_unload or []) == baseline_hooks


@pytest.mark.parametrize("reload", [False, True])
async def test_actual_unload_or_reload_sends_final_unloaded_event(hass, client, entry, reload):
    engine = entry.runtime_data
    result = await command(client, entry, "subscribe")
    initial = await client.receive_json()
    assert initial["event"]["config_entry_id"] == entry.entry_id
    engine.temperature = 18.5
    engine._notify()  # Leave a pending notification: shutdown must cancel it.
    if reload:
        assert await hass.config_entries.async_reload(entry.entry_id)
    else:
        assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await client.send_json_auto_id({"type": f"{DOMAIN}/get", "config_entry_id": entry.entry_id})
    final = await client.receive_json()
    assert final["type"] == "event" and final["id"] == result["id"]
    assert final["event"] == {"unloaded": True}
    response = await client.receive_json()
    assert response["type"] == "result"
    assert response["success"] is reload
    assert not engine._subscription_cleanups
    # HA websocket client removes its old message before resubscribing (including after reconnect).
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
    assert (await client.receive_json())["success"]
    if reload:
        new = await command(client, entry, "subscribe")
        assert new["success"]
        assert (await client.receive_json())["event"]["config_entry_id"] == entry.entry_id
        await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": new["id"]})
        assert (await client.receive_json())["success"]
    if reload:
        assert entry.runtime_data is not engine
        assert not entry.runtime_data._subscription_cleanups


async def test_unchanged_snapshots_do_not_emit_events(hass, client, entry, freezer):
    engine = entry.runtime_data
    result = await command(client, entry, "subscribe")
    await client.receive_json()
    for _ in range(5):
        engine._notify()
    freezer.tick(2)
    async_fire_time_changed_exact(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    # If an unchanged event was queued, it would arrive before this get's result.
    response = await command(client, entry, "get")
    assert response["type"] == "result" and response["success"]
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
    assert (await client.receive_json())["success"]


async def test_room_delete_removes_climate_registry_state_and_override(hass, client, entry):
    from homeassistant.helpers import entity_registry as er

    engine = entry.runtime_data
    room = engine.store.data.rooms[0]
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("climate", DOMAIN, f"{entry.entry_id}_room_{room.id}")
    assert entity_id and hass.states.get(entity_id) is not None
    result = await command(client, entry, "override/set", room_id=room.id, temperature=23)
    assert result["success"] and engine.store.data.overrides
    result = await command(client, entry, "room/delete", room_id=room.id)
    assert result["success"]
    await hass.async_block_till_done()
    assert not engine.store.data.rooms and not engine.store.data.overrides
    assert registry.async_get(entity_id) is None
    assert hass.states.get(entity_id) is None
    assert room.id not in result["result"]["rooms"]


async def test_room_save_rejects_renamed_virtual_thermostat_atomically(hass, client, entry):
    from homeassistant.helpers import entity_registry as er

    engine = entry.runtime_data
    room = engine.store.data.rooms[0]
    registry = er.async_get(hass)
    own_entity = registry.async_get_entity_id("climate", DOMAIN, f"{entry.entry_id}_room_{room.id}")
    registry.async_update_entity(own_entity, new_entity_id="climate.renamed_virtual")
    await hass.async_block_till_done()
    before = engine.store.data
    result = await command(
        client,
        entry,
        "room/save",
        room={"name": "Room B", "trvs": ["climate.renamed_virtual"], "profile_id": room.profile_id},
    )
    assert not result["success"] and result["error"]["code"] == "invalid_data"
    assert engine.store.data is before


@pytest.mark.parametrize("loaded", [False, True])
async def test_room_save_rejects_trv_owned_by_other_instance(hass, client, entry, loaded, tmp_path):
    other = MockConfigEntry(
        domain=DOMAIN, title="Boiler B", data={"adapter": ADAPTER, "prefix": "boiler_b/properties"}
    )
    other.add_to_hass(hass)
    profile = Profile("Profile B", tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS))
    room = Room("Room B", ("climate.shared_trv",), profile.id)
    store = HeatingStore(hass, other.entry_id)
    await store.async_update(lambda data: replace(data, profiles=(profile,), rooms=(room,)))
    if not loaded:
        import json
        from pathlib import Path

        hass.config.config_dir = str(tmp_path)
        path = Path(hass.config.path(".storage", f"{DOMAIN}.{other.entry_id}"))
        await hass.async_add_executor_job(lambda: path.parent.mkdir(parents=True, exist_ok=True))
        await hass.async_add_executor_job(
            path.write_text,
            json.dumps({"version": 1, "minor_version": 2, "data": to_json(store.data)}),
        )
    if loaded:
        assert await hass.config_entries.async_setup(other.entry_id)
        await hass.async_block_till_done()
    engine = entry.runtime_data
    before = engine.store.data
    result = await command(
        client,
        entry,
        "room/save",
        room={
            "name": "Room C",
            "trvs": ["climate.shared_trv"],
            "profile_id": before.profiles[0].id,
        },
    )
    assert not result["success"] and result["error"]["code"] == "invalid_data"
    assert engine.store.data is before
    status = await command(client, entry, "get")
    assert "climate.shared_trv" in status["result"]["used_trv_ids"]
    if loaded:
        await hass.config_entries.async_unload(other.entry_id)


async def test_profile_save_reapplies_rooms_to_physical_trv(hass, client, entry):
    from homeassistant.core import Context

    calls = []

    async def apply(call):
        calls.append(dict(call.data))
        state = hass.states.get(call.data["entity_id"])
        hass.states.async_set(
            call.data["entity_id"],
            call.data.get("hvac_mode", state.state),
            {**state.attributes, "temperature": call.data["temperature"]},
            context=Context(),
        )

    hass.services.async_register("climate", "set_temperature", apply)
    assert (await command(client, entry, "mode/set", mode="auto"))["success"]
    await hass.async_block_till_done()
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 18
    calls.clear()
    profile = entry.runtime_data.store.data.profiles[0]
    changed = {
        "id": profile.id,
        "name": profile.name,
        "days": {day: [{"start": "00:00", "target": 22}] for day in WEEKDAYS},
    }
    result = await command(client, entry, "profile/save", profile=changed)
    assert result["success"]
    await hass.async_block_till_done()
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 22
    assert any(call["temperature"] == 22 for call in calls)


async def test_partial_settings_preserve_all_unsupplied_values(client, entry):
    engine = entry.runtime_data
    await engine.store.async_settings(
        hysteresis=0.5,
        away_temperature=14.5,
        override_default="duration",
        override_minutes=71,
        retry_seconds=83,
        sync_rooms_on_knob_change=False,
    )
    before = to_json(engine.store.data)["settings"]
    result = await command(client, entry, "settings/save", settings={"frost_temperature": 8})
    assert result["success"]
    assert to_json(engine.store.data)["settings"] == {**before, "frost_temperature": 8}
    assert engine.store.data.shadow


@pytest.mark.parametrize("kind", ["room", "profile"])
async def test_saving_unknown_existing_id_is_not_create(client, entry, kind):
    before = entry.runtime_data.store.data
    payload = (
        {
            "id": "unknown_existing",
            "name": "Room B",
            "trvs": ["climate.trv_b"],
            "profile_id": before.profiles[0].id,
        }
        if kind == "room"
        else {**profile_payload(), "id": "unknown_existing"}
    )
    result = await command(client, entry, f"{kind}/save", **{kind: payload})
    assert not result["success"] and result["error"]["code"] == "invalid_data"
    assert entry.runtime_data.store.data is before


async def test_websocket_shadow_enable_resets_every_send_cache(client, entry):
    engine = entry.runtime_data
    engine._last_command = engine.command
    engine._last_send_tick = 123
    engine._last_source_tick = 456
    # Start with real output enabled so toggling to shadow is an actual change.
    await engine.store.async_update(lambda data: replace(data, shadow=False))
    result = await command(client, entry, "settings/save", shadow=True)
    assert result["success"] and engine.store.data.shadow
    assert engine._last_command is None
    assert engine._last_send_tick is None
    assert engine._last_source_tick is None


async def test_schedule_shared_frontend_fixtures_are_accepted_or_rejected_atomically(client, entry):
    import json
    from pathlib import Path

    cases = json.loads((Path(__file__).parents[1] / "fixtures/schedule_contract.json").read_text())
    for case in cases:
        before = entry.runtime_data.store.data
        result = await command(client, entry, "profile/save", profile=case["profile"])
        assert result["success"] is case["valid"], case["name"]
        if not case["valid"]:
            assert entry.runtime_data.store.data is before


@pytest.mark.parametrize("problem", [ValueError("bad data"), OSError("cannot read")])
async def test_other_unreadable_store_does_not_break_status_subscribe_or_mode(
    hass, client, entry, problem
):
    other = MockConfigEntry(
        domain=DOMAIN, title="Boiler B", data={"adapter": ADAPTER, "prefix": "boiler_b/properties"}
    )
    other.add_to_hass(hass)
    with patch.object(HeatingStore, "async_read_only", side_effect=problem):
        result = await command(client, entry, "get")
        assert result["success"]
        result = await command(client, entry, "subscribe")
        assert result["success"]
        assert (await client.receive_json())["type"] == "event"
        await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": result["id"]})
        assert (await client.receive_json())["success"]
        assert (await command(client, entry, "mode/set", mode="auto"))["success"]
        before = entry.runtime_data.store.data
        result = await command(
            client,
            entry,
            "room/save",
            room={"name": "Room B", "trvs": ["climate.trv_b"], "profile_id": before.profiles[0].id},
        )
        assert not result["success"]
        assert "storage is unreadable" in result["error"]["message"]
        assert entry.runtime_data.store.data is before


async def test_other_entry_ownership_never_migrates_or_saves_store(hass, client, entry, tmp_path):
    import json
    from pathlib import Path

    other = MockConfigEntry(
        domain=DOMAIN, title="Boiler B", data={"adapter": ADAPTER, "prefix": "boiler_b/properties"}
    )
    other.add_to_hass(hass)
    hass.config.config_dir = str(tmp_path)
    raw = to_json(entry.runtime_data.store.data)
    path = Path(hass.config.path(".storage", f"{DOMAIN}.{other.entry_id}"))
    envelope = json.dumps(
        {"version": 1, "minor_version": 1, "key": f"{DOMAIN}.{other.entry_id}", "data": raw}
    )
    await hass.async_add_executor_job(lambda: path.parent.mkdir(parents=True, exist_ok=True))
    await hass.async_add_executor_job(path.write_text, envelope)
    before = await hass.async_add_executor_job(path.stat)
    with patch.object(
        HeatingStore, "async_load", side_effect=AssertionError("ownership must not migrate")
    ):
        result = await command(client, entry, "get")
        assert result["success"]
        assert "climate.trv_a" in result["result"]["used_trv_ids"]
        await hass.async_block_till_done()
    assert await hass.async_add_executor_job(path.read_text) == envelope
    assert (await hass.async_add_executor_job(path.stat)).st_mtime_ns == before.st_mtime_ns


async def test_read_only_store_rejects_newer_minor_version_l05(hass, client, entry, tmp_path):
    import json
    from pathlib import Path

    other = MockConfigEntry(
        domain=DOMAIN, title="Boiler B", data={"adapter": ADAPTER, "prefix": "boiler_b/properties"}
    )
    other.add_to_hass(hass)
    hass.config.config_dir = str(tmp_path)
    path = Path(hass.config.path(".storage", f"{DOMAIN}.{other.entry_id}"))
    await hass.async_add_executor_job(lambda: path.parent.mkdir(parents=True, exist_ok=True))
    envelope = json.dumps(
        {"version": 1, "minor_version": 4, "data": to_json(entry.runtime_data.store.data)}
    )
    await hass.async_add_executor_job(path.write_text, envelope)
    with pytest.raises(ValueError, match="Unsupported heating Store version"):
        await HeatingStore.async_read_only(hass, other.entry_id)
    assert (await command(client, entry, "get"))["success"]
    before = entry.runtime_data.store.data
    result = await command(
        client,
        entry,
        "room/save",
        room={"name": "Room B", "trvs": ["climate.trv_b"], "profile_id": before.profiles[0].id},
    )
    assert not result["success"]
    assert "storage is unreadable" in result["error"]["message"]
    assert entry.runtime_data.store.data is before
    assert await hass.async_add_executor_job(path.read_text) == envelope


@pytest.mark.parametrize("kind", ["next_block", "duration"])
@pytest.mark.parametrize("mode", ["auto", "manual"])
async def test_profile_edit_recomputes_only_next_change_override_after_reload(
    hass, client, entry, freezer, kind, mode
):
    from datetime import timedelta

    freezer.move_to("2026-01-05T10:00:00+00:00")
    await hass.config.async_set_time_zone("UTC")
    assert (await command(client, entry, "mode/set", mode=mode))["success"]
    room = entry.runtime_data.store.data.rooms[0]
    result = await command(
        client,
        entry,
        "override/set",
        room_id=room.id,
        temperature=23,
        kind=kind,
        **({"minutes": 120} if kind == "duration" else {}),
    )
    assert result["success"]
    before = entry.runtime_data.store.data.overrides[0]
    assert before.kind == kind
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.store.data.overrides[0].kind == kind
    calls = []

    async def apply(call):
        calls.append(dict(call.data))

    hass.services.async_register("climate", "set_temperature", apply)
    payload = {
        "id": room.profile_id,
        "name": "Edited profile",
        "days": {
            day: [
                {"start": "00:00", "target": 18},
                {"start": "11:00", "target": 21},
                {"start": "22:00", "target": 18},
            ]
            for day in WEEKDAYS
        },
    }
    result = await command(client, entry, "profile/save", profile=payload)
    assert result["success"]
    after = entry.runtime_data.store.data.overrides[0]
    assert after.target == 23 and after.kind == kind
    assert after.until == (
        dt_util.utcnow() + timedelta(hours=1) if kind == "next_block" else before.until
    )
    if mode == "manual":
        assert not calls
    # A later apply must not move the already recomputed expiry again.
    freezer.tick(timedelta(minutes=5))
    await entry.runtime_data.async_data_changed()
    assert entry.runtime_data.store.data.overrides[0].until == after.until


@pytest.mark.parametrize("mode", ["auto", "away", "summer", "manual"])
async def test_websocket_mode_values_stay_internal(client, entry, mode):
    result = await command(client, entry, "mode/set", mode=mode)
    assert result["success"]
    assert result["result"]["configuration"]["mode"]["value"] == mode


@pytest.mark.parametrize("label", ["Schedule", "Away", "Heating off", "Manual", "unknown"])
async def test_websocket_mode_rejects_display_labels(client, entry, label):
    before = entry.runtime_data.store.data
    result = await command(client, entry, "mode/set", mode=label)
    assert not result["success"]
    assert entry.runtime_data.store.data is before


async def test_o06_constant_week_cap_does_not_slide_on_later_reapply(client, entry, freezer):
    from datetime import timedelta

    freezer.move_to("2026-01-05T10:00:00+00:00")
    room = entry.runtime_data.store.data.rooms[0]
    assert (
        await command(
            client, entry, "override/set", room_id=room.id, temperature=23, kind="next_block"
        )
    )["success"]
    freezer.tick(timedelta(hours=1))
    payload = profile_payload()
    payload["id"] = room.profile_id
    for blocks in payload["days"].values():
        blocks[0]["target"] = 19
    assert (await command(client, entry, "profile/save", profile=payload))["success"]
    expected = dt_util.utcnow() + timedelta(days=7)
    assert entry.runtime_data.store.data.overrides[0].until == expected
    for _ in range(3):
        freezer.tick(timedelta(minutes=5))
        await entry.runtime_data.async_data_changed()
        assert entry.runtime_data.store.data.overrides[0].until == expected


async def test_profile_rename_keeps_next_change_override_expiry(client, entry, freezer):
    from datetime import timedelta

    freezer.move_to("2026-01-05T10:00:00+00:00")
    room = entry.runtime_data.store.data.rooms[0]
    assert (
        await command(
            client, entry, "override/set", room_id=room.id, temperature=23, kind="next_block"
        )
    )["success"]
    original = entry.runtime_data.store.data.overrides[0].until
    freezer.tick(timedelta(minutes=30))
    payload = profile_payload("Renamed profile")
    payload["id"] = room.profile_id
    assert (await command(client, entry, "profile/save", profile=payload))["success"]
    assert entry.runtime_data.store.data.overrides[0].until == original
    assert entry.runtime_data.store.data.profiles[0].name == "Renamed profile"
