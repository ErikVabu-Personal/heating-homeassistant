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
from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Room, Week
from custom_components.central_heating.storage import HeatingStore, Mode
from tests.schedules import seed

pytestmark = pytest.mark.integration


async def build_engine(hass, *, shadow=False):
    store = HeatingStore(hass, "entry_a")
    profile = Week("Week A", tuple(Day(day, (Block("00:00", 21),)) for day in WEEKDAYS))
    room = Room("Room A", ("climate.trv_a",))
    await store.async_update(
        lambda data: replace(
            data, schedules=(seed(profile, (room,)),), rooms=(room,), shadow=shadow
        )
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
    await engine.async_set_mode("off")
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
    assert engine.store.data.mode.value == "schedule"
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
        == 11
    )
    await engine.async_settings(frost_temperature=8)
    assert engine.store.data.settings.frost_temperature == 8
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not messages(mqtt_mock)
    reloaded = HeatingStore(hass, entry.entry_id)
    await reloaded.async_load()
    assert reloaded.data.settings.frost_temperature == 8


async def test_store_validation_atomic_and_disk_failure_logged(hass, caplog):
    from homeassistant.util.file import WriteError

    store = HeatingStore(hass, "entry_a")
    original = store.data
    with pytest.raises(ValueError):
        await store.async_settings(hysteresis=0.15)
    assert store.data is original
    # Fail below Store.async_save: this is where HA catches a real disk failure.
    with patch.object(store._store, "_async_write_data", side_effect=WriteError("disk full")):
        await store.async_settings(frost_temperature=8)
    assert store.data.settings.frost_temperature == 8
    assert "Error writing config" in caplog.text


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
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX + "/#"},
    )
    assert result["errors"] == {"prefix": "invalid_config"}


async def test_concurrent_settings_writes_do_not_lose_updates(hass):
    import asyncio

    store = HeatingStore(hass, "entry_a")
    entered, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def paused_save(payload):
        calls.append(payload)
        if len(calls) == 1:
            entered.set()
            await release.wait()

    with patch.object(store._store, "async_save", side_effect=paused_save):
        first = asyncio.create_task(store.async_settings(frost_temperature=8))
        await entered.wait()
        second = asyncio.create_task(store.async_settings(away_temperature=10))
        await asyncio.sleep(0)
        assert len(calls) == 1
        release.set()
        await asyncio.gather(first, second)
    assert store.data.settings.frost_temperature == 8
    assert store.data.settings.away_temperature == 10


async def test_http_config_and_options_forms_serialize(hass, mqtt_mock, hass_client):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "config", {})
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    client = await hass_client()
    response = await client.post("/api/config/config_entries/flow", json={"handler": DOMAIN})
    assert response.status == 200
    form = await response.json()
    assert any(field["name"] == "prefix" for field in form["data_schema"])
    response = await client.post(
        f"/api/config/config_entries/flow/{form['flow_id']}",
        json={"name": "Boiler A", "adapter": ADAPTER, "prefix": "invalid/#"},
    )
    assert response.status == 200
    assert (await response.json())["errors"] == {"prefix": "invalid_config"}
    with patch("custom_components.central_heating.async_setup_entry", return_value=True):
        response = await client.post(
            f"/api/config/config_entries/flow/{form['flow_id']}",
            json={"name": "Boiler A", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX},
        )
        assert response.status == 200
        created = await response.json()
        await hass.async_block_till_done()
    response = await client.post(
        "/api/config/config_entries/options/flow", json={"handler": created["result"]["entry_id"]}
    )
    assert response.status == 200
    options = await response.json()
    assert options["data_schema"][0]["name"] == "prefix"
    response = await client.post(
        f"/api/config/config_entries/options/flow/{options['flow_id']}",
        json={"prefix": "invalid/#"},
    )
    assert response.status == 200
    assert (await response.json())["errors"] == {"prefix": "invalid_config"}


async def test_starting_tick_and_trv_event_never_call_adapter(hass, mqtt_mock):
    from homeassistant.core import CoreState

    engine, _ = await build_engine(hass)
    hass.state = CoreState.starting
    with (
        patch.object(engine.adapter, "async_start") as start,
        patch.object(engine.adapter, "async_apply") as apply,
    ):
        await engine.async_start()
        await engine._tick(datetime.now(UTC))
        hass.states.async_set(
            "climate.trv_a", "heat", {"temperature": 25, "current_temperature": 18}
        )
        await hass.async_block_till_done()
        start.assert_not_called()
        apply.assert_not_called()
    await engine.async_stop(unloading=False)


async def test_duplicate_prefix_aborts(hass, mqtt_mock):
    entry = MockConfigEntry(domain=DOMAIN, data={"adapter": ADAPTER, "prefix": DEFAULT_PREFIX})
    entry.add_to_hass(hass)
    form = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        form["flow_id"], {"name": "Boiler B", "adapter": ADAPTER, "prefix": DEFAULT_PREFIX}
    )
    assert result["type"] == "abort" and result["reason"] == "already_configured"


async def test_entry_actions_ids_options_and_real_unload(hass, mqtt_mock):
    from homeassistant.exceptions import ServiceValidationError
    from homeassistant.helpers import entity_registry as er

    entry = MockConfigEntry(
        domain=DOMAIN, title="Boiler A", data={"adapter": ADAPTER, "prefix": DEFAULT_PREFIX}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = er.async_get(hass)

    def entity_id(platform, key):
        found = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
        assert found is not None
        return found

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": entity_id("number", "away_temperature"), "value": 15.5},
        blocking=True,
    )
    assert entry.runtime_data.store.data.settings.away_temperature == 15.5
    with pytest.raises(ServiceValidationError):
        from custom_components.central_heating.number import SettingNumber

        await SettingNumber(entry, "away_temperature").async_set_native_value(15.25)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity_id("select", "mode"), "option": "off"},
        blocking=True,
    )
    assert entry.runtime_data.store.data.mode.value == "off"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": entity_id("switch", "shadow")}, blocking=True
    )
    assert not entry.runtime_data.store.data.shadow
    assert entry.runtime_data._last_send_tick is not None
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": entity_id("switch", "shadow")}, blocking=True
    )
    assert entry.runtime_data._last_send_tick is None
    assert entry.runtime_data._last_source_tick is None
    assert entry.runtime_data._last_command is None
    assert "last_sent" not in hass.states.get(entity_id("binary_sensor", "boiler_call")).attributes
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        options = await hass.config_entries.options.async_init(entry.entry_id)
        await hass.config_entries.options.async_configure(
            options["flow_id"], {"prefix": DEFAULT_PREFIX}
        )
        await hass.async_block_till_done()
        reload.assert_not_called()
    options = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        options["flow_id"], {"prefix": "boiler_b/properties"}
    )
    await hass.async_block_till_done()
    assert entry.runtime_data.adapter.prefix == "boiler_b/properties"
    await entry.runtime_data.async_set_shadow(False)
    engine = entry.runtime_data
    mqtt_mock.async_publish.reset_mock()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert engine._stopped
    assert engine._state_unsubscribe is None and not engine._unsubscribers
    assert messages(mqtt_mock) == [("boiler_b/properties/mode", "off", 0, False)]


async def test_store_minor_migration_and_entry_removal(hass, hass_storage):
    from custom_components.central_heating import async_remove_entry

    entry = MockConfigEntry(domain=DOMAIN, data={})
    hass_storage[f"{DOMAIN}.{entry.entry_id}"] = {
        "version": 1,
        "minor_version": 1,
        "key": f"{DOMAIN}.{entry.entry_id}",
        "data": {"settings": {"frost_temperature": 8}},
    }
    store = HeatingStore(hass, entry.entry_id)
    await store.async_load()
    assert store.data.shadow and store.data.settings.frost_temperature == 8
    assert hass_storage[f"{DOMAIN}.{entry.entry_id}"]["minor_version"] == 4
    DiylessAdapter(hass, entry.entry_id, DEFAULT_PREFIX)._unavailable()
    await async_remove_entry(hass, entry)
    assert f"{DOMAIN}.{entry.entry_id}" not in hass_storage
    assert ir.async_get(hass).async_get_issue(DOMAIN, f"mqtt_{entry.entry_id}") is None


async def test_invalid_entry_data_is_config_entry_error(hass):
    from homeassistant.exceptions import ConfigEntryError

    from custom_components.central_heating import async_setup_entry

    entry = MockConfigEntry(domain=DOMAIN, data={"adapter": "invalid", "prefix": DEFAULT_PREFIX})
    with pytest.raises(ConfigEntryError):
        await async_setup_entry(hass, entry)
    entry = MockConfigEntry(domain=DOMAIN, data={"adapter": ADAPTER, "prefix": DEFAULT_PREFIX})
    with patch.object(HeatingStore, "async_load", side_effect=ValueError("bad stored data")):
        with pytest.raises(ConfigEntryError):
            await async_setup_entry(hass, entry)


async def test_mqtt_unavailable_logged_once_per_transition(hass, caplog):
    adapter = DiylessAdapter(hass, "entry_a", DEFAULT_PREFIX)
    for _ in range(4):
        await adapter.async_start()
    assert caplog.text.count("Central Heating cannot send") == 1
    with (
        patch("homeassistant.components.mqtt.async_publish"),
        patch.object(hass.config_entries, "async_entries") as entries,
    ):
        from unittest.mock import Mock

        from homeassistant.config_entries import ConfigEntryState

        entries.return_value = [Mock(state=ConfigEntryState.LOADED)]
        await adapter.async_start()
    await adapter.async_start()
    assert caplog.text.count("Central Heating cannot send") == 2


@pytest.mark.parametrize("use_options", [False, True])
async def test_options_flow_rejects_other_boilers_effective_prefix(hass, mqtt_mock, use_options):
    other = MockConfigEntry(
        domain=DOMAIN,
        data={"adapter": ADAPTER, "prefix": "boiler_b/properties"},
        options={"prefix": "boiler_c/properties"} if use_options else {},
    )
    edited = MockConfigEntry(domain=DOMAIN, data={"adapter": ADAPTER, "prefix": DEFAULT_PREFIX})
    for entry in (other, edited):
        entry.add_to_hass(hass)
    original = dict(edited.options)
    form = await hass.config_entries.options.async_init(edited.entry_id)
    prefix = other.options.get("prefix", other.data["prefix"])
    result = await hass.config_entries.options.async_configure(form["flow_id"], {"prefix": prefix})
    assert result["type"] == "form"
    assert result["errors"] == {"prefix": "already_configured"}
    assert dict(edited.options) == original
    result = await hass.config_entries.options.async_configure(
        form["flow_id"], {"prefix": DEFAULT_PREFIX}
    )
    assert result["type"] == "create_entry"
    assert result["data"] == {"prefix": DEFAULT_PREFIX}  # Self is not a duplicate.


async def test_remove_entry_clears_only_its_own_sync_repairs(hass):
    from custom_components.central_heating import async_remove_entry

    entry = MockConfigEntry(domain=DOMAIN, data={})
    own = [f"sync_{entry.entry_id}_climate.trv_a", f"sync_{entry.entry_id}_climate.trv_b"]
    other = ["sync_other_entry_climate.trv_a", f"sync_{entry.entry_id}suffix_climate.trv_a"]
    for issue_id in own + other:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="sync_problem",
        )
    ir.async_create_issue(
        hass,
        "other_domain",
        own[0],
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="test",
    )
    await async_remove_entry(hass, entry)
    registry = ir.async_get(hass)
    assert all(registry.async_get_issue(DOMAIN, issue_id) is None for issue_id in own)
    assert all(registry.async_get_issue(DOMAIN, issue_id) is not None for issue_id in other)
    assert registry.async_get_issue("other_domain", own[0]) is not None


async def test_config_entry_only_schema_is_exposed_without_eager_ha_imports(hass, caplog):
    from custom_components.central_heating import CONFIG_SCHEMA

    assert callable(CONFIG_SCHEMA)
    assert CONFIG_SCHEMA({}) == {}
    assert CONFIG_SCHEMA({DOMAIN: {}, "other": {}}) == {DOMAIN: {}, "other": {}}
    assert "does not support YAML setup" in caplog.text
