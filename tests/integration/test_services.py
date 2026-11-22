"""Public service and room-climate behavior through real HA platforms."""

from dataclasses import replace

import pytest
import voluptuous as vol
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.central_heating.const import ADAPTER, DEFAULT_PREFIX, DOMAIN
from custom_components.central_heating.diagnostics import async_get_config_entry_diagnostics
from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Room, Week
from custom_components.central_heating.storage import HeatingStore, seed_room
from tests.schedules import seed

pytestmark = pytest.mark.integration


async def setup_entry(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Boiler A",
        data={"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX},
    )
    entry.add_to_hass(hass)
    profile = Week(
        "Week A", tuple(Day(day, (Block("00:00", 18), Block("07:00", 21))) for day in WEEKDAYS)
    )
    room = Room("Room A", ("climate.trv_a",))
    hass.states.async_set(
        "climate.trv_a",
        "heat",
        {"current_temperature": 20, "temperature": 21, "hvac_modes": ["heat"]},
    )
    store = HeatingStore(hass, entry.entry_id)
    await store.async_update(
        lambda data: replace(data, schedules=(seed(profile, (room,)),), rooms=(room,))
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    entity_id = er.async_get(hass).async_get_entity_id(
        "climate", DOMAIN, f"{entry.entry_id}_room_{room.id}"
    )
    return entry, room, entity_id


async def test_services_room_climate_and_diagnostics(hass, mqtt_mock):
    entry, room, climate = await setup_entry(hass)
    engine = entry.runtime_data
    state = hass.states.get(climate)
    assert state.attributes["current_temperature"] == 20
    assert state.attributes["temperature"] == 21  # manual reads the TRV target
    assert state.attributes["hvac_modes"] == ["heat"]
    assert "next_change" in state.attributes and "next_target" in state.attributes
    await hass.services.async_call(
        "climate", "set_temperature", {"entity_id": climate, "temperature": 22}, blocking=True
    )
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].source == "card"
    assert engine.store.data.overrides[0].target == 22
    await hass.services.async_call(
        DOMAIN,
        "clear_override",
        {"config_entry_id": entry.entry_id, "room": climate},
        blocking=True,
    )
    assert not engine.store.data.overrides
    await hass.services.async_call(
        DOMAIN,
        "set_override",
        {"config_entry_id": entry.entry_id, "room": climate, "temperature": 23, "minutes": 60},
        blocking=True,
    )
    assert engine.store.data.overrides[0].target == 23
    await hass.services.async_call(
        DOMAIN, "set_mode", {"config_entry_id": entry.entry_id, "mode": "off"}, blocking=True
    )
    assert engine.command.heat is False
    await hass.services.async_call(
        DOMAIN, "apply_now", {"config_entry_id": entry.entry_id}, blocking=True
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["configuration"]["settings"]["hysteresis"] == 0.3
    assert diagnostics["configuration"]["rooms"][room.id]["trvs"] == ["climate.trv_a"]
    assert diagnostics["command"]["heat"] is False
    assert diagnostics["shadow"] is True
    assert "prefix" not in diagnostics and "credentials" not in diagnostics
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    "service,changes",
    [
        ("set_mode", {"mode": "schedule", "until": "2027-01-01T00:00:00+00:00"}),
        ("set_override", {"temperature": 31}),
        ("set_override", {"temperature": 20.1}),
        ("clear_override", {"room": "climate.unrelated"}),
        ("apply_now", {"config_entry_id": "missing_entry"}),
    ],
)
async def test_invalid_service_write_changes_nothing(hass, mqtt_mock, service, changes):
    entry, room, climate = await setup_entry(hass)
    engine = entry.runtime_data
    previous = engine.store.data
    values = {"config_entry_id": entry.entry_id}
    if service in ("set_override", "clear_override"):
        values["room"] = climate
    values.update(changes)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, service, values, blocking=True)
    assert engine.store.data is previous
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_new_room_entity_is_discovered_after_store_update(hass, mqtt_mock):
    entry, room, climate = await setup_entry(hass)
    engine = entry.runtime_data
    other = Room("Room B", ("climate.trv_b",))
    await engine.store.async_update(lambda data: seed_room(data, other))
    await engine.async_data_changed()
    await hass.async_block_till_done()
    other_entity = er.async_get(hass).async_get_entity_id(
        "climate", DOMAIN, f"{entry.entry_id}_room_{other.id}"
    )
    assert hass.states.get(other_entity) is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_room_entity_reports_sync_problem_and_next_target(hass, mqtt_mock):
    entry, room, climate = await setup_entry(hass)
    engine = entry.runtime_data
    engine.rooms.problems.add("climate.trv_a")
    engine._notify()
    await hass.async_block_till_done()
    state = hass.states.get(climate)
    assert state.attributes["sync_problem"] is True
    assert state.attributes["next_target"] in (18, 21)
    assert state.attributes["trvs"] == ["climate.trv_a"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_room_climate_actions_names_override_visibility_and_constant_week(hass, mqtt_mock):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    from custom_components.central_heating.climate import RoomClimate

    entry, room, climate = await setup_entry(hass)
    engine = entry.runtime_data
    entity = RoomClimate(entry, room.id)
    entity.hass = hass
    assert entity.name == room.name and entity.translation_key is None
    assert entity.hvac_action == "heating"
    await entity.async_set_hvac_mode("heat")
    assert not engine.store.data.overrides
    with pytest.raises(ServiceValidationError):
        await entity.async_set_temperature(temperature=22.1)
    await entity.async_set_temperature(temperature=22)
    assert entity.extra_state_attributes["override_until"] is None  # manual
    await engine.async_set_mode("schedule")
    assert entity.extra_state_attributes["override_until"] is not None
    await engine.async_set_mode("off")
    assert entity.extra_state_attributes["override_until"] is None
    await engine.async_set_mode("away")
    assert entity.extra_state_attributes["override_until"] is not None
    expired = replace(engine.store.data.overrides[0], until=dt_util.utcnow() - timedelta(seconds=1))
    await engine.store.async_update(lambda data: replace(data, overrides=(expired,)))
    assert entity.extra_state_attributes["override_until"] is None
    constant = Week("Constant", tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS))
    await engine.store.async_update(
        lambda data: replace(data, schedules=(seed(constant, (room,)),))
    )
    assert entity.extra_state_attributes["next_change"] is None
    assert entity.extra_state_attributes["next_target"] is None
    old = hass.states.get("climate.trv_a")
    hass.states.async_set("climate.trv_a", "off", old.attributes)
    await hass.async_block_till_done()
    assert entity.hvac_action == "idle"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_local_until_and_minutes_bounds(hass, mqtt_mock, freezer):
    from datetime import UTC, datetime, timedelta

    from homeassistant.util import dt as dt_util

    freezer.move_to("2026-01-05T08:00:00+00:00")
    await hass.config.async_set_time_zone("Europe/Berlin")
    entry, room, climate = await setup_entry(hass)
    await hass.services.async_call(
        DOMAIN,
        "set_mode",
        {"config_entry_id": entry.entry_id, "mode": "away", "until": "2026-01-05T12:00:00"},
        blocking=True,
    )
    assert entry.runtime_data.store.data.mode.until.astimezone(UTC) == datetime(
        2026, 1, 5, 11, tzinfo=UTC
    )
    for minutes in (1, 10080):
        await hass.services.async_call(
            DOMAIN,
            "set_override",
            {
                "config_entry_id": entry.entry_id,
                "room": climate,
                "temperature": 23,
                "minutes": minutes,
            },
            blocking=True,
        )
        assert entry.runtime_data.store.data.overrides[0].until == dt_util.utcnow() + timedelta(
            minutes=minutes
        )
    for minutes in (0, 10081):
        with pytest.raises((ServiceValidationError, vol.Invalid)):
            await hass.services.async_call(
                DOMAIN,
                "set_override",
                {
                    "config_entry_id": entry.entry_id,
                    "room": climate,
                    "temperature": 23,
                    "minutes": minutes,
                },
                blocking=True,
            )
    await hass.config_entries.async_unload(entry.entry_id)


async def test_service_registration_once_and_apply_now_dispatch(hass, mqtt_mock):
    from unittest.mock import patch

    from custom_components.central_heating import async_setup

    entry, room, climate = await setup_entry(hass)
    with patch.object(type(hass.services), "async_register") as register:
        assert await async_setup(hass, {})
        register.assert_not_called()
    with patch.object(entry.runtime_data, "async_recalculate") as recalculate:
        await hass.services.async_call(
            DOMAIN, "apply_now", {"config_entry_id": entry.entry_id}, blocking=True
        )
        recalculate.assert_awaited_once_with(apply_rooms=True, force=True)
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("mode", ["schedule", "away", "off", "manual"])
async def test_mode_service_and_select_keep_internal_values(hass, mqtt_mock, mode):
    from custom_components.central_heating.select import ModeSelect

    entry, room, climate = await setup_entry(hass)
    entity = ModeSelect(entry, "mode")
    assert entity.translation_key == "mode"
    assert entity.options == ["schedule", "away", "off", "manual"]
    await hass.services.async_call(
        DOMAIN, "set_mode", {"config_entry_id": entry.entry_id, "mode": mode}, blocking=True
    )
    assert entry.runtime_data.store.data.mode.value == mode
    assert entity.current_option == mode
    await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("label", ["Schedule", "Away", "Heating off", "Manual", "unknown"])
async def test_mode_service_rejects_display_labels(hass, mqtt_mock, label):
    entry, room, climate = await setup_entry(hass)
    before = entry.runtime_data.store.data
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "set_mode", {"config_entry_id": entry.entry_id, "mode": label}, blocking=True
        )
    assert entry.runtime_data.store.data is before
    await hass.config_entries.async_unload(entry.entry_id)
