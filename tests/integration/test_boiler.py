"""Boiler lifecycle tests against the supported Home Assistant test pair."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.central_heating.boiler.diyless_mqtt import DiylessAdapter
from custom_components.central_heating.const import ADAPTER, DEFAULT_PREFIX, DOMAIN
from custom_components.central_heating.engine import HeatingEngine
from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Profile, Room
from custom_components.central_heating.storage import HeatingStore, Mode

pytestmark = pytest.mark.integration


async def build_engine(hass, *, shadow=False):
    store = HeatingStore(hass, "entry_a")
    profile = Profile("Profile A", tuple(Day(day, (Block("00:00", 21),)) for day in WEEKDAYS))
    room = Room("Room A", ("climate.trv_a",), profile.id)
    await store.async_update(
        lambda data: replace(data, profiles=(profile,), rooms=(room,), shadow=shadow)
    )
    hass.states.async_set("climate.trv_a", "heat", {"current_temperature": 18, "temperature": 21})
    ticks = {"now": 0.0}
    engine = HeatingEngine(
        hass, store, DiylessAdapter(hass, "entry_a", DEFAULT_PREFIX), monotonic=lambda: ticks["now"]
    )
    return engine, ticks


def messages(mqtt_mock):
    return [
        (call.args[0], call.args[1], call.args[2], call.args[3])
        for call in mqtt_mock.async_publish.call_args_list
    ]


async def test_exact_mqtt_start_change_keepalive_and_six_hour_source(hass, mqtt_mock):
    engine, ticks = await build_engine(hass)
    await engine.async_recalculate()
    assert messages(mqtt_mock) == [
        (f"{DEFAULT_PREFIX}/tempSource", "1", 0, False),
        (f"{DEFAULT_PREFIX}/temperature", "18.00", 0, False),
        (f"{DEFAULT_PREFIX}/targetTemperature", "21.0", 0, False),
        (f"{DEFAULT_PREFIX}/mode", "heat", 0, False),
    ]
    mqtt_mock.async_publish.reset_mock()
    ticks["now"] = 29
    await engine.async_recalculate()
    assert not messages(mqtt_mock)
    ticks["now"] = 30
    await engine.async_recalculate()
    assert len(messages(mqtt_mock)) == 3
    mqtt_mock.async_publish.reset_mock()
    await engine.async_set_mode("summer")
    assert messages(mqtt_mock)[-1] == (f"{DEFAULT_PREFIX}/mode", "off", 0, False)
    mqtt_mock.async_publish.reset_mock()
    ticks["now"] = 21600
    await engine.async_recalculate()
    assert messages(mqtt_mock)[0] == (f"{DEFAULT_PREFIX}/tempSource", "1", 0, False)


async def test_unknown_temperature_sends_only_setpoint_and_mode(hass, mqtt_mock):
    engine, _ = await build_engine(hass)
    hass.states.async_set("climate.trv_a", "unavailable")
    await engine.async_recalculate()
    assert messages(mqtt_mock) == [
        (f"{DEFAULT_PREFIX}/tempSource", "1", 0, False),
        (f"{DEFAULT_PREFIX}/targetTemperature", "16.0", 0, False),
        (f"{DEFAULT_PREFIX}/mode", "off", 0, False),
    ]


async def test_shadow_never_calls_adapter_including_unload(hass, mqtt_mock):
    engine, _ = await build_engine(hass, shadow=True)
    with (
        patch.object(engine.adapter, "async_start", new_callable=AsyncMock) as start,
        patch.object(engine.adapter, "async_apply", new_callable=AsyncMock) as apply,
        patch.object(engine.adapter, "async_stop", new_callable=AsyncMock) as stop,
    ):
        await engine.async_recalculate()
        assert engine.command.heat
        await engine.async_stop(unloading=True)
        start.assert_not_called()
        apply.assert_not_called()
        stop.assert_not_called()
    assert not messages(mqtt_mock)


async def test_unload_sends_off_once_but_shutdown_sends_nothing(hass, mqtt_mock):
    engine, _ = await build_engine(hass)
    await engine.async_start()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    mqtt_mock.async_publish.reset_mock()
    await engine.async_stop(unloading=True)
    await engine.async_stop(unloading=True)
    assert messages(mqtt_mock) == [(f"{DEFAULT_PREFIX}/mode", "off", 0, False)]
    other, _ = await build_engine(hass)
    await other.async_start()
    mqtt_mock.async_publish.reset_mock()
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    await other.async_stop(unloading=True)
    assert not messages(mqtt_mock)


async def test_away_until_returns_to_auto_and_disabled_room_is_ignored(hass, mqtt_mock):
    engine, _ = await build_engine(hass)
    await engine.store.async_update(
        lambda data: replace(
            data,
            rooms=(replace(data.rooms[0], enabled=False),),
            mode=Mode("away", datetime(2020, 1, 1, tzinfo=UTC)),
        )
    )
    await engine.async_recalculate()
    assert engine.store.data.mode.value == "auto"
    assert engine.demand.demand_count == 0


async def test_missing_mqtt_raises_repair_and_recovers(hass):
    engine, _ = await build_engine(hass)
    await engine.async_recalculate()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "mqtt_entry_a") is not None
    assert engine.last_sent is None


async def test_config_flow_missing_mqtt(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "mqtt_required"


async def test_config_flow_and_options(hass, mqtt_mock):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    with patch("custom_components.central_heating.async_setup_entry", return_value=True):
        created = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX}
        )
        await hass.async_block_till_done()
    assert created["type"] == "create_entry"
    entry = created["result"]
    options = await hass.config_entries.options.async_init(entry.entry_id)
    assert options["type"] == "form"
    with patch("homeassistant.config_entries.ConfigEntries.async_reload", return_value=True):
        changed = await hass.config_entries.options.async_configure(
            options["flow_id"], {"prefix": DEFAULT_PREFIX}
        )
    assert changed["data"] == {"prefix": DEFAULT_PREFIX}


async def test_entry_entities_start_manual_shadow_and_keep_settings(hass, mqtt_mock):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Boiler A",
        data={"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    engine = entry.runtime_data
    assert engine.store.data.shadow and engine.store.data.mode.value == "manual"
    states = hass.states.async_all()
    assert (
        len(
            [
                state
                for state in states
                if state.entity_id.startswith(
                    (
                        "sensor.boiler_a_",
                        "number.boiler_a_",
                        "select.boiler_a_",
                        "switch.boiler_a_",
                        "binary_sensor.boiler_a_",
                    )
                )
            ]
        )
        == 10
    )
    await engine.async_settings(frost_temperature=8)
    assert engine.store.data.settings.frost_temperature == 8
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not messages(mqtt_mock)
    reloaded = HeatingStore(hass, entry.entry_id)
    await reloaded.async_load()
    assert reloaded.data.settings.frost_temperature == 8


async def test_store_validation_and_failed_persistence_are_atomic(hass):
    store = HeatingStore(hass, "entry_a")
    original = store.data
    with pytest.raises(ValueError):
        await store.async_settings(hysteresis=0.15)
    assert store.data is original
    with patch.object(store._store, "async_save", side_effect=OSError("test failure")):
        with pytest.raises(OSError):
            await store.async_settings(frost_temperature=8)
    assert store.data is original


async def test_event_recalculation_startup_and_ten_second_timer(hass, freezer):
    from datetime import timedelta

    from homeassistant.core import CoreState
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    engine, ticks = await build_engine(hass, shadow=True)
    hass.state = CoreState.starting
    with patch.object(engine, "async_recalculate", wraps=engine.async_recalculate) as recalculate:
        await engine.async_start()
        assert recalculate.call_count == 0
        hass.state = CoreState.running
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
        await hass.async_block_till_done()
        assert recalculate.call_count == 1
        hass.states.async_set(
            "climate.trv_a", "heat", {"current_temperature": 18, "temperature": 20}
        )
        await hass.async_block_till_done()
        assert engine.command.setpoint == 20
        previous = recalculate.call_count
        ticks["now"] = 10
        freezer.tick(timedelta(seconds=10))
        async_fire_time_changed(hass, dt_util.utcnow())
        await hass.async_block_till_done()
        assert recalculate.call_count > previous
        await engine.async_stop(unloading=False)


async def test_mqtt_repair_clears_when_connection_is_available(hass, mqtt_mock):
    engine, _ = await build_engine(hass)
    with patch.object(hass.config_entries, "async_entries", return_value=[]):
        await engine.async_recalculate()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "mqtt_entry_a")
    await engine.async_recalculate()
    assert ir.async_get(hass).async_get_issue(DOMAIN, "mqtt_entry_a") is None
    assert engine.last_sent is not None


async def test_config_flow_rejects_wildcard_prefix(hass, mqtt_mock):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    from homeassistant.data_entry_flow import InvalidData

    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX + "/#"},
        )


async def test_concurrent_settings_writes_do_not_lose_updates(hass):
    import asyncio

    store = HeatingStore(hass, "entry_a")
    await asyncio.gather(
        store.async_settings(frost_temperature=8), store.async_settings(away_temperature=10)
    )
    assert store.data.settings.frost_temperature == 8
    assert store.data.settings.away_temperature == 10
