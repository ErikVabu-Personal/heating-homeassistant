"""Whole-house scheduling controls on invented rooms and thermostats only."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import Context
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed_exact

from custom_components.central_heating.const import DOMAIN
from custom_components.central_heating.select import ActiveScheduleSelect
from tests.integration.test_websocket import client, command, entry

__all__ = ["entry", "client"]
pytestmark = pytest.mark.integration


def days(target=18, next_at="11:00", next_target=21):
    return {
        day: [{"start": "00:00", "target": target}, {"start": next_at, "target": next_target}]
        for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }


async def physical(hass):
    calls = []

    async def apply(call):
        calls.append(dict(call.data))
        old = hass.states.get(call.data["entity_id"])
        hass.states.async_set(
            call.data["entity_id"],
            call.data.get("hvac_mode", old.state),
            {**old.attributes, "temperature": call.data["temperature"]},
            context=Context(),
        )

    hass.services.async_register("climate", "set_temperature", apply)
    return calls


async def test_active_edits_apply_only_affected_rooms_and_inactive_edits_do_not_apply(
    hass, client, entry, freezer
):
    freezer.move_to("2026-01-05T10:00:00+00:00")
    await hass.config.async_set_time_zone("UTC")
    a = entry.runtime_data.store.data.rooms[0].id
    hass.states.async_set("climate.trv_b", "heat", {"temperature": 21, "current_temperature": 17})
    b = (
        await command(
            client, entry, "room/save", room={"name": "Room B", "trvs": ["climate.trv_b"]}
        )
    )["result"]["saved_id"]
    calls = await physical(hass)
    await command(client, entry, "mode/set", mode="schedule")
    await hass.async_block_till_done()
    calls.clear()
    with patch.object(
        entry.runtime_data.rooms, "async_apply", wraps=entry.runtime_data.rooms.async_apply
    ) as apply:
        saved = await command(
            client,
            entry,
            "schedule/save",
            schedule={"id": "winter", "name": "Winter", "rooms": {a: {"days": days(22)}}},
        )
        assert saved["success"]
        await hass.async_block_till_done()
        apply.assert_awaited_once_with(force=False, room_ids={a})
    assert calls and {call["entity_id"] for call in calls} == {"climate.trv_a"}
    calls.clear()
    other = (
        await command(
            client,
            entry,
            "schedule/save",
            schedule={"name": "Autumn", "rooms": {a: {"days": days(20)}, b: {"days": days(19)}}},
        )
    )["result"]["saved_id"]
    await hass.async_block_till_done()
    assert not calls
    assert (await command(client, entry, "schedule/activate", schedule_id=other))["success"]
    await hass.async_block_till_done()
    assert {call["entity_id"] for call in calls} == {"climate.trv_a", "climate.trv_b"}
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 20
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 19


async def test_only_active_schedule_starts_drive_room_timers(hass, client, entry, freezer):
    freezer.move_to("2026-01-05T10:00:00+00:00")
    await hass.config.async_set_time_zone("UTC")
    room = entry.runtime_data.store.data.rooms[0]
    calls = await physical(hass)
    await command(
        client,
        entry,
        "schedule/save",
        schedule={
            "id": "winter",
            "name": "Winter",
            "rooms": {room.id: {"days": days(18, "11:00", 21)}},
        },
    )
    await command(
        client,
        entry,
        "schedule/save",
        schedule={"name": "Inactive", "rooms": {room.id: {"days": days(18, "10:15", 25)}}},
    )
    await command(client, entry, "mode/set", mode="schedule")
    await hass.async_block_till_done()
    calls.clear()
    freezer.tick(timedelta(minutes=15))
    async_fire_time_changed_exact(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert not calls and hass.states.get("climate.trv_a").attributes["temperature"] == 18
    freezer.tick(timedelta(minutes=45))
    async_fire_time_changed_exact(hass, dt_util.utcnow())
    await hass.async_block_till_done()
    assert any(call["temperature"] == 21 for call in calls)


async def test_schedule_switch_active_edit_inactive_edit_and_rename_override_rules(
    hass, client, entry, freezer
):
    freezer.move_to("2026-01-05T10:00:00+00:00")
    await hass.config.async_set_time_zone("UTC")
    a = entry.runtime_data.store.data.rooms[0].id
    b = (
        await command(
            client, entry, "room/save", room={"name": "Room B", "trvs": ["climate.trv_b"]}
        )
    )["result"]["saved_id"]
    for room, kind in [(a, "next_block"), (b, "duration")]:
        assert (
            await command(
                client,
                entry,
                "override/set",
                room_id=room,
                temperature=23,
                kind=kind,
                **({"minutes": 120} if kind == "duration" else {}),
            )
        )["success"]
    initial = {o.room_id: o.until for o in entry.runtime_data.store.data.overrides}
    other = (
        await command(
            client,
            entry,
            "schedule/save",
            schedule={"name": "Autumn", "rooms": {a: {"days": days()}, b: {"days": days()}}},
        )
    )["result"]["saved_id"]
    assert {o.room_id: o.until for o in entry.runtime_data.store.data.overrides} == initial
    assert (await command(client, entry, "schedule/activate", schedule_id=other))["success"]
    changed = {o.room_id: o.until for o in entry.runtime_data.store.data.overrides}
    assert changed[a] == dt_util.utcnow() + timedelta(hours=1) and changed[b] == initial[b]
    assert (
        await command(client, entry, "schedule/save", schedule={"id": other, "name": "Renamed"})
    )["success"]
    assert {o.room_id: o.until for o in entry.runtime_data.store.data.overrides} == changed
    assert (
        await command(
            client,
            entry,
            "schedule/save",
            schedule={
                "id": other,
                "name": "Renamed",
                "rooms": {a: {"days": days(18, "12:00", 21)}},
            },
        )
    )["success"]
    current = {o.room_id: o.until for o in entry.runtime_data.store.data.overrides}
    assert current[a] == dt_util.utcnow() + timedelta(hours=2) and current[b] == initial[b]
    assert (
        await command(
            client,
            entry,
            "schedule/save",
            schedule={
                "id": "winter",
                "name": "Winter",
                "rooms": {a: {"days": days(18, "13:00", 21)}},
            },
        )
    )["success"]
    assert {o.room_id: o.until for o in entry.runtime_data.store.data.overrides} == current


async def test_every_new_schedule_and_room_command_sends_nothing_in_shadow_manual(
    hass, client, entry, mqtt_mock
):
    calls = await physical(hass)
    mqtt_mock.async_publish.reset_mock()
    room = entry.runtime_data.store.data.rooms[0].id
    assert (
        entry.runtime_data.store.data.mode.value == "manual"
        and entry.runtime_data.store.data.shadow
    )
    created = await command(client, entry, "schedule/save", schedule={"name": "Autumn"})
    assert created["success"]
    key = created["result"]["saved_id"]
    actions = [
        (
            "schedule/save",
            {"schedule": {"id": key, "name": "Autumn", "rooms": {room: {"days": days(23)}}}},
        ),
        ("schedule/activate", {"schedule_id": key}),
        ("schedule/save", {"schedule": {"id": key, "name": "Renamed"}}),
        (
            "room/save",
            {"room": {"name": "Room B", "trvs": ["climate.trv_b"], "copy_week_from_room": room}},
        ),
    ]
    for name, payload in actions:
        assert (await command(client, entry, name, **payload))["success"]
        await hass.async_block_till_done()
        assert not calls and not mqtt_mock.async_publish.call_args_list
    await hass.services.async_call(
        DOMAIN,
        "set_schedule",
        {"config_entry_id": entry.entry_id, "schedule": "winter"},
        blocking=True,
    )
    select = ActiveScheduleSelect(entry, "active_schedule")
    assert select.options == ["Winter", "Renamed"] and select.current_option == "Winter"
    await select.async_select_option("Renamed")
    assert select.current_option == "Renamed"
    await command(client, entry, "schedule/activate", schedule_id="winter")
    assert (await command(client, entry, "schedule/delete", schedule_id=key))["success"]
    assert select.options == ["Winter"]
    new_room = next(r for r in entry.runtime_data.store.data.rooms if r.id != room)
    assert (await command(client, entry, "room/delete", room_id=new_room.id))["success"]
    await hass.async_block_till_done()
    assert not calls and not mqtt_mock.async_publish.call_args_list


@pytest.mark.parametrize("alias,stored", [("auto", "schedule"), ("summer", "off")])
async def test_mode_aliases_services_and_websocket_store_canonical_values(
    hass, client, entry, alias, stored
):
    assert (await command(client, entry, "mode/set", mode=alias))["result"]["configuration"][
        "mode"
    ]["value"] == stored
    await hass.services.async_call(
        DOMAIN, "set_mode", {"config_entry_id": entry.entry_id, "mode": alias}, blocking=True
    )
    assert entry.runtime_data.store.data.mode.value == stored


async def test_atomic_overview_apply_and_schedule_validation(client, entry):
    before = entry.runtime_data.store.data
    assert not (await command(client, entry, "mode/set", mode="schedule", schedule_id="missing"))[
        "success"
    ]
    assert entry.runtime_data.store.data is before
    raw = {"id": "winter", "name": "Changed", "rooms": {before.rooms[0].id: {"days": days(20.25)}}}
    assert not (await command(client, entry, "schedule/save", schedule=raw))["success"]
    assert entry.runtime_data.store.data is before
    key = (await command(client, entry, "schedule/save", schedule={"name": "Autumn"}))["result"][
        "saved_id"
    ]
    result = await command(client, entry, "mode/set", mode="schedule", schedule_id=key)
    assert result["success"] and result["result"]["configuration"]["active_schedule_id"] == key


async def test_away_until_returns_to_schedule(hass, client, entry, freezer):
    freezer.move_to("2026-01-05T10:00:00+00:00")
    assert (
        await command(
            client,
            entry,
            "mode/set",
            mode="away",
            until=(dt_util.utcnow() + timedelta(minutes=5)).isoformat(),
        )
    )["success"]
    freezer.tick(timedelta(minutes=5))
    await entry.runtime_data.async_recalculate(apply_rooms=True)
    assert entry.runtime_data.store.data.mode.value == "schedule"


async def test_select_maps_exact_names_to_ids_and_conflicting_name_is_rejected(hass, client, entry):
    assert (
        await command(client, entry, "schedule/save", schedule={"id": "winter", "name": "Cold"})
    )["success"]
    before = entry.runtime_data.store.data
    conflict = await command(client, entry, "schedule/save", schedule={"name": "winter"})
    assert not conflict["success"]
    assert "another schedule's id" in conflict["error"]["message"]
    assert entry.runtime_data.store.data is before
    key = (await command(client, entry, "schedule/save", schedule={"name": "Autumn"}))["result"][
        "saved_id"
    ]
    select = ActiveScheduleSelect(entry, "active_schedule")
    with patch.object(entry.runtime_data, "async_set_schedule", new_callable=AsyncMock) as activate:
        await select.async_select_option("Autumn")
        activate.assert_awaited_once_with(key)
    await select.async_select_option("Autumn")
    assert entry.runtime_data.store.data.active_schedule_id == key
    assert select.current_option == "Autumn"


async def test_room_update_cannot_copy_weeks_and_is_atomic(client, entry):
    before = entry.runtime_data.store.data
    room = before.rooms[0]
    result = await command(
        client,
        entry,
        "room/save",
        room={
            "id": room.id,
            "name": "Changed",
            "trvs": list(room.trvs),
            "copy_week_from_room": room.id,
        },
    )
    assert not result["success"]
    assert "only supported when creating" in result["error"]["message"]
    assert entry.runtime_data.store.data is before


@pytest.mark.parametrize("mode", ["away", "off", "manual", "summer"])
async def test_schedule_id_outside_schedule_mode_is_rejected_atomically(client, entry, mode):
    before = entry.runtime_data.store.data
    result = await command(client, entry, "mode/set", mode=mode, schedule_id="winter")
    assert not result["success"]
    assert entry.runtime_data.store.data is before


async def test_room_schedule_attribute_follows_switch(hass, client, entry):
    room = entry.runtime_data.store.data.rooms[0]
    from homeassistant.helpers import entity_registry as er

    entity = er.async_get(hass).async_get_entity_id(
        "climate", DOMAIN, f"{entry.entry_id}_room_{room.id}"
    )
    assert hass.states.get(entity).attributes["schedule"] == "Winter"
    key = (await command(client, entry, "schedule/save", schedule={"name": "Autumn"}))["result"][
        "saved_id"
    ]
    assert (await command(client, entry, "schedule/activate", schedule_id=key))["success"]
    await hass.async_block_till_done()
    assert hass.states.get(entity).attributes["schedule"] == "Autumn"
    assert "profile" not in hass.states.get(entity).attributes
