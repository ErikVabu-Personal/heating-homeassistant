"""Room control on a local HA fixture with invented radiator thermostats."""

from dataclasses import replace
from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import Context, CoreState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.central_heating.const import DOMAIN
from custom_components.central_heating.engine import HeatingEngine
from custom_components.central_heating.rooms import RoomController
from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Room, Week
from custom_components.central_heating.storage import HeatingStore, Mode
from tests.schedules import seed

pytestmark = pytest.mark.integration


async def build_rooms(hass, freezer, *, respond=True, mode="schedule", sync=True, blocks=None):
    freezer.move_to("2026-01-05T05:59:50+00:00")
    await hass.config.async_set_time_zone("UTC")
    profile = Week(
        "Week A",
        tuple(Day(day, blocks or (Block("00:00", 18), Block("06:00", 21))) for day in WEEKDAYS),
    )
    room = Room("Room A", ("climate.trv_a", "climate.trv_b"))
    store = HeatingStore(hass, "entry_a")
    await store.async_update(
        lambda data: replace(
            data,
            schedules=(seed(profile, (room,)),),
            rooms=(room,),
            mode=Mode(mode),
            settings=replace(data.settings, retry_seconds=10, sync_rooms_on_knob_change=sync),
        )
    )
    calls = []

    async def apply(call):
        calls.append(call)
        if respond:
            old = hass.states.get(call.data["entity_id"])
            hass.states.async_set(
                call.data["entity_id"],
                call.data.get("hvac_mode", old.state),
                {**old.attributes, "temperature": call.data["temperature"]},
                context=Context(),
            )

    hass.services.async_register("climate", "set_temperature", apply)
    for trv, modes in [("climate.trv_a", ["heat", "off"]), ("climate.trv_b", ["off"])]:
        hass.states.async_set(
            trv,
            "heat" if trv == "climate.trv_a" else "off",
            {"current_temperature": 17, "temperature": 18, "hvac_modes": modes},
        )
    engine = HeatingEngine(hass, store, AsyncMock())
    engine.rooms = RoomController(engine, "entry_a")
    await engine.async_start()
    await hass.async_block_till_done()
    return engine, room, calls


async def advance(hass, freezer, seconds):
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_block_boundary_writes_only_differences_and_needed_hvac_mode(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    assert calls == []
    report(hass, "climate.trv_a", 18, mode="off")
    await hass.async_block_till_done()
    await advance(hass, freezer, 10)
    assert len(calls) == 2
    assert calls[0].data == {"entity_id": "climate.trv_a", "temperature": 21, "hvac_mode": "heat"}
    assert calls[1].data == {"entity_id": "climate.trv_b", "temperature": 21}
    assert calls[0].context == engine.rooms.last_commanded["climate.trv_a"][2]
    await engine.async_recalculate()
    assert len(calls) == 2
    engine.adapter.assert_not_called()
    await engine.async_stop(unloading=False)


async def test_three_retries_then_problem_repair_and_success_clears(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    assert len(calls) == 2
    for _ in range(4):
        await advance(hass, freezer, 10)
    assert len(calls) == 8  # initial send and exactly three retries per TRV
    assert engine.rooms.problems == set(room.trvs)
    assert ir.async_get(hass).async_get_issue(DOMAIN, "sync_entry_a_climate.trv_a")
    await advance(hass, freezer, 10)
    assert len(calls) == 8
    for trv in room.trvs:
        old = hass.states.get(trv)
        hass.states.async_set(trv, "heat", {**old.attributes, "temperature": 21}, context=Context())
    await hass.async_block_till_done()
    assert not engine.rooms.problems
    assert ir.async_get(hass).async_get_issue(DOMAIN, "sync_entry_a_climate.trv_a") is None
    assert not engine.store.data.overrides
    await engine.async_stop(unloading=False)


@pytest.mark.parametrize("sync", [True, False])
async def test_knob_change_sets_override_and_optional_room_sync(hass, freezer, sync):
    engine, room, calls = await build_rooms(hass, freezer, sync=sync)
    await advance(hass, freezer, 10)
    calls.clear()
    old = hass.states.get("climate.trv_a")
    hass.states.async_set(
        "climate.trv_a", "heat", {**old.attributes, "temperature": 22.5}, context=Context()
    )
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 22.5
    assert engine.store.data.overrides[0].source == "trv"
    assert len(calls) == (1 if sync else 0)
    assert hass.states.get("climate.trv_b").attributes["temperature"] == (22.5 if sync else 21)
    await engine.async_stop(unloading=False)


async def test_late_commanded_value_without_our_context_is_not_override(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    previous_context = engine.rooms.last_commanded["climate.trv_a"][2]
    freezer.tick(timedelta(seconds=5))
    report_context = Context()
    assert report_context.id != previous_context.id
    old = hass.states.get("climate.trv_a")
    hass.states.async_set(
        "climate.trv_a", "heat", {**old.attributes, "temperature": 21}, context=report_context
    )
    await hass.async_block_till_done()
    assert not engine.store.data.overrides
    assert "climate.trv_a" not in engine.rooms.pending
    await engine.async_stop(unloading=False)


async def test_duration_override_expires_and_profile_target_resumes(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    await engine.rooms.async_set_override(room.id, 22, 1)
    await engine.async_recalculate(apply_rooms=True)
    await hass.async_block_till_done()
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 22
    await advance(hass, freezer, 60)
    assert not engine.store.data.overrides
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 21
    await engine.async_stop(unloading=False)


async def test_until_next_change_skips_midnight(hass, freezer):
    engine, room, calls = await build_rooms(
        hass, freezer, blocks=(Block("00:00", 18), Block("07:00", 21), Block("18:00", 18))
    )
    freezer.move_to("2026-01-05T23:00:00+00:00")
    await engine.rooms.async_set_override(room.id, 22)
    assert engine.store.data.overrides[0].until.isoformat() == "2026-01-06T07:00:00+00:00"
    await engine.async_stop(unloading=False)


async def test_back_online_reapplies_without_creating_knob_override(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    hass.states.async_set("climate.trv_a", "unavailable")
    await hass.async_block_till_done()
    calls.clear()
    hass.states.async_set(
        "climate.trv_a",
        "off",
        {"temperature": 10, "current_temperature": 17, "hvac_modes": ["heat"]},
    )
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data["temperature"] == 21
    assert not engine.store.data.overrides
    await engine.async_stop(unloading=False)


async def test_manual_writes_nothing_and_does_not_track_knob(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, mode="manual")
    await advance(hass, freezer, 10)
    old = hass.states.get("climate.trv_a")
    hass.states.async_set("climate.trv_a", "heat", {**old.attributes, "temperature": 23})
    await hass.async_block_till_done()
    assert not calls and not engine.store.data.overrides
    await engine.async_stop(unloading=False)


async def test_away_expiry_summer_and_profile_change_clear_override(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await engine.async_set_mode("away", dt_util.utcnow() + timedelta(seconds=20))
    await hass.async_block_till_done()
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 15
    await advance(hass, freezer, 20)
    assert engine.store.data.mode.value == "schedule"
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 21
    await engine.async_set_mode("off")
    await hass.async_block_till_done()
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 16
    assert engine.command.heat is False
    await engine.async_set_mode("schedule")
    await engine.rooms.async_set_override(room.id, 22)
    other = Week("Autumn", tuple(Day(day, (Block("00:00", 19),)) for day in WEEKDAYS))
    await engine.store.async_update(
        lambda data: replace(data, schedules=(*data.schedules, seed(other, (room,), id="autumn")))
    )
    await engine.async_set_schedule("autumn")
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 22
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 22
    await engine.async_stop(unloading=False)


async def test_stopping_cancels_pending_retries_and_schedule(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    assert engine.rooms.pending
    await engine.async_stop(unloading=True)
    assert not engine.rooms.pending
    assert engine.rooms._timer is None
    previous = len(calls)
    await advance(hass, freezer, 120)
    assert len(calls) == previous


async def test_invalid_override_does_not_replace_existing_one(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await engine.rooms.async_set_override(room.id, 22, 30)
    original = engine.store.data
    with pytest.raises(ServiceValidationError):
        await engine.rooms.async_set_override(room.id, 30.1)
    assert engine.store.data is original
    await engine.async_stop(unloading=False)


def report(hass, trv, target, *, mode="heat"):
    state = hass.states.get(trv)
    hass.states.async_set(trv, mode, {**state.attributes, "temperature": target}, context=Context())


async def test_knob_back_to_schedule_clears_override(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    report(hass, "climate.trv_a", 23)
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 23
    report(hass, "climate.trv_a", 21)
    await hass.async_block_till_done()
    assert not engine.store.data.overrides
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 21
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 21
    await engine.async_stop(unloading=False)


async def test_late_older_echo_after_card_override_keeps_new_target(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)  # 21 still unconfirmed
    await engine.rooms.async_set_override(room.id, 23, 60, source="card")
    await engine.async_recalculate(apply_rooms=True)
    pending = engine.rooms.pending["climate.trv_a"]
    assert [command.target for command in pending.commands] == [21, 23]
    report(hass, "climate.trv_a", 21)
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 23
    assert [command.target for command in pending.commands] == [23]
    previous = len(calls)
    await advance(hass, freezer, 10)
    assert len(calls) > previous and calls[-1].data["temperature"] == 23
    report(hass, "climate.trv_a", 23)
    await hass.async_block_till_done()
    assert "climate.trv_a" not in engine.rooms.pending
    await engine.async_stop(unloading=False)


async def test_foreign_then_stale_then_real_after_new_card_override(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    report(hass, "climate.trv_a", 21)  # Foreign device confirmation
    await hass.async_block_till_done()
    await engine.rooms.async_set_override(room.id, 23, 60, source="card")
    await engine.async_recalculate(apply_rooms=True)
    previous = len(calls)
    state = hass.states.get("climate.trv_a")
    hass.states.async_set(
        "climate.trv_a", "heat", {**state.attributes, "current_temperature": 17.1}
    )
    await hass.async_block_till_done()  # stale 21 while 23 is pending
    assert len(calls) == previous
    assert engine.store.data.overrides[0].target == 23
    report(hass, "climate.trv_a", 23)  # real confirmation
    await hass.async_block_till_done()
    assert "climate.trv_a" not in engine.rooms.pending
    report(hass, "climate.trv_a", 22.5)  # subsequent real knob change
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 22.5
    await engine.async_stop(unloading=False)


async def test_no_room_reapply_on_ticks_temperature_events_or_off(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    calls.clear()
    report(hass, "climate.trv_a", 21, mode="off")
    await hass.async_block_till_done()
    assert not calls
    await advance(hass, freezer, 30)
    state = hass.states.get("climate.trv_a")
    hass.states.async_set("climate.trv_a", "off", {**state.attributes, "current_temperature": 10})
    await hass.async_block_till_done()
    assert not calls
    assert engine.demand.demand_count == 0  # both physical TRVs are off
    # A mode change is the next trigger and restores heat where supported.
    await engine.async_set_mode("away")
    await hass.async_block_till_done()
    assert calls[0].data["hvac_mode"] == "heat"
    await engine.async_stop(unloading=False)


async def test_block_timer_does_not_need_the_boiler_tick(hass, freezer):
    from unittest.mock import patch

    from homeassistant.core import callback

    @callback
    def no_tick(*args, **kwargs):
        return lambda: None

    with patch("custom_components.central_heating.engine.async_track_time_interval", no_tick):
        engine, room, calls = await build_rooms(hass, freezer)
        await advance(hass, freezer, 10)
    assert len(calls) == 2 and calls[0].data["temperature"] == 21
    await engine.async_stop(unloading=False)


async def test_slow_trv_handler_does_not_block_boiler_keepalives(hass, freezer):
    import asyncio

    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    release, entered = asyncio.Event(), asyncio.Event()

    async def hang(call):
        entered.set()
        await release.wait()

    hass.services.async_register("climate", "set_temperature", hang)
    ticks = {"now": 0}
    engine.monotonic = lambda: ticks["now"]
    engine.adapter.last_success = True
    await engine.async_set_shadow(False)
    try:
        await engine.rooms.async_set_override(room.id, 23)
        await asyncio.wait_for(engine.async_recalculate(apply_rooms=True), timeout=1)
        await asyncio.wait_for(entered.wait(), timeout=1)
        engine.adapter.async_apply.reset_mock()
        for tick in (30, 60):
            ticks["now"] = tick
            await asyncio.wait_for(engine.async_recalculate(), timeout=1)
        assert engine.adapter.async_apply.call_count == 2
    finally:
        release.set()
        await hass.async_block_till_done()
        await engine.async_stop(unloading=False)


async def test_room_exception_cannot_skip_boiler_send(hass, freezer):
    from unittest.mock import patch

    engine, room, calls = await build_rooms(hass, freezer)
    engine.adapter.last_success = True
    await engine.async_set_shadow(False)
    engine._last_command = None
    engine.adapter.async_apply.reset_mock()
    with patch.object(engine.rooms, "async_apply", side_effect=RuntimeError("room failure")):
        await engine.async_recalculate(apply_rooms=True)
    engine.adapter.async_apply.assert_awaited_once()
    await engine.async_stop(unloading=False)


@pytest.mark.parametrize("mode", ["off", "manual"])
async def test_knobs_ignored_in_non_override_modes(hass, freezer, mode):
    engine, room, calls = await build_rooms(hass, freezer, mode=mode)
    calls.clear()
    report(hass, "climate.trv_a", 24)
    await hass.async_block_till_done()
    assert not engine.store.data.overrides and not calls
    await advance(hass, freezer, 5)
    assert not calls
    if mode == "off":
        await engine.async_data_changed()
        await hass.async_block_till_done()
        assert calls[0].data["temperature"] == 16
    await engine.async_stop(unloading=False)


async def test_apply_now_rewrites_pending_and_problem_rooms(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    engine.rooms.pending["climate.trv_a"].retries = 2
    engine.rooms.problems.add("climate.trv_b")
    before = len(calls)
    await engine.async_recalculate(apply_rooms=True, force=True)
    await hass.async_block_till_done()
    assert len(calls) == before + 2
    assert all(item.retries == 0 for item in engine.rooms.pending.values())
    assert not engine.rooms.problems
    await engine.async_stop(unloading=False)


async def test_startup_apply_and_no_starting_trv_writes(hass, freezer):
    from homeassistant.const import EVENT_HOMEASSISTANT_STARTED

    hass.state = CoreState.starting
    engine, room, calls = await build_rooms(hass, freezer, blocks=(Block("00:00", 21),))
    await engine.rooms.async_apply()
    await engine._tick(dt_util.utcnow())
    report(hass, "climate.trv_a", 20)
    await hass.async_block_till_done()
    assert not calls and not engine.store.data.overrides
    hass.state = CoreState.running
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert len(calls) == 2
    assert calls[0].data["temperature"] == 21
    await engine.async_stop(unloading=False)


@pytest.mark.parametrize("foreign,changed_desired", [(True, False), (False, True)])
async def test_retry_checks_foreign_change_and_unchanged_desired(
    hass, freezer, foreign, changed_desired
):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    pending = engine.rooms.pending["climate.trv_a"]
    engine._state_unsubscribe()
    engine._state_unsubscribe = None
    if foreign:
        report(hass, "climate.trv_a", 24)
    if changed_desired:
        await engine.rooms.async_set_override(room.id, 23)
    before = len(calls)
    await engine.rooms._retry("climate.trv_a", pending)
    await hass.async_block_till_done()
    assert len(calls) == before
    assert "climate.trv_a" not in engine.rooms.pending
    await engine.async_stop(unloading=False)


async def test_knob_duration_rounding_and_clamping(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    await engine.async_settings(override_default="duration", override_minutes=37)
    for raw, expected in [(23.2, 23), (40, 30), (1, 5)]:
        report(hass, "climate.trv_a", raw)
        await hass.async_block_till_done()
        override = engine.store.data.overrides[0]
        assert override.target == expected
        assert override.until == dt_util.utcnow() + timedelta(minutes=37)
    await engine.async_stop(unloading=False)


async def test_desired_ignores_expired_override_without_cleanup(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await engine.rooms.async_set_override(room.id, 23, 1)
    assert engine.rooms.desired(room) == 23
    freezer.tick(timedelta(minutes=2))
    assert engine.store.data.overrides  # no timer or cleanup was run
    assert engine.rooms.desired(room) == 21
    await engine.async_stop(unloading=False)


async def test_stale_precommand_value_is_retried_then_window_expires(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    report(
        hass, "climate.trv_a", 18
    )  # switch off -> heat but old temperature while command pending
    await hass.async_block_till_done()
    assert not engine.store.data.overrides
    before = len(calls)
    await advance(hass, freezer, 10)
    assert len(calls) > before
    await advance(hass, freezer, 40)
    pending = engine.rooms.pending.get("climate.trv_a")
    if pending is not None:
        engine.rooms._prune(pending)
        assert not pending.commands
    await engine.async_stop(unloading=False)


async def test_no_redundant_hvac_mode_when_already_heat(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    await engine.rooms.async_set_override(room.id, 23)
    await engine.async_recalculate(apply_rooms=True)
    await hass.async_block_till_done()
    assert (
        "hvac_mode"
        not in next(call for call in calls if call.data["entity_id"] == "climate.trv_a").data
    )
    await engine.async_stop(unloading=False)


@pytest.mark.parametrize("source", ["knob", "card"])
async def test_sleepy_trv_back_to_schedule_queues_corrective_command(hass, freezer, source):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    sleepy = SleepyTRV(hass, "climate.trv_b")
    if source == "knob":
        report(hass, "climate.trv_a", 23)
        await hass.async_block_till_done()
    else:
        await engine.rooms.async_set_override(room.id, 23, source="card")
        await engine.async_recalculate(apply_rooms=True)
        await hass.async_block_till_done()
    assert [call.data["temperature"] for call in sleepy.queue] == [23]
    assert sleepy.physical_target == 21
    if source == "knob":
        report(hass, "climate.trv_a", 21)
        await hass.async_block_till_done()
    else:
        await engine.rooms.async_clear_override(room.id)
        await engine.async_recalculate(apply_rooms=True)
        await hass.async_block_till_done()
    assert not engine.store.data.overrides
    assert [call.data["temperature"] for call in sleepy.queue] == [23, 21]
    pending = engine.rooms.pending["climate.trv_b"]
    assert [command.target for command in pending.commands] == [23, 21]
    await sleepy.wake(count=1)
    assert sleepy.physical_target == 23
    assert engine.rooms.pending["climate.trv_b"] is pending
    assert [command.target for command in pending.commands] == [21]
    assert pending.cancel is not None
    assert not engine.store.data.overrides
    await sleepy.wake()
    assert sleepy.physical_target == 21
    assert "climate.trv_b" not in engine.rooms.pending
    assert not engine.rooms.problems and not engine.store.data.overrides
    await engine.async_stop(unloading=False)


@pytest.mark.parametrize("lost", [False, True])
async def test_sleepy_optimistic_stale_real_or_lost_command(hass, freezer, lost):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    sleepy = SleepyTRV(hass, "climate.trv_b", optimistic=True)
    await advance(hass, freezer, 10)  # Schedule requests 21; physical device is still 18.
    pending = engine.rooms.pending["climate.trv_b"]
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 21
    assert sleepy.physical_target == 18
    assert len(pending.commands) == 1
    await engine.async_data_changed()  # A normal trigger cannot confirm the optimistic value.
    await hass.async_block_till_done()
    assert engine.rooms.pending["climate.trv_b"] is pending
    assert len(sleepy.sent) == 1
    if lost:
        await sleepy.wake(lose_commands=True)
    await sleepy.stale()  # 21 -> 18 foreign report must reach the stale guard.
    assert engine.rooms.pending["climate.trv_b"] is pending
    assert pending.observed == 18
    assert not engine.store.data.overrides
    if lost:
        await advance(hass, freezer, 10)
        assert pending.retries == 1
        assert len(sleepy.queue) == 1
        assert sleepy.queue[0].data["temperature"] == 21
        assert not engine.store.data.overrides
    await sleepy.wake()
    assert sleepy.physical_target == 21
    if lost:
        # The optimistic value is already in HA: real devices do not force identical updates.
        # No state-change event is emitted on wake, so confirmation comes from retry readback.
        assert engine.rooms.pending["climate.trv_b"] is pending
        await advance(hass, freezer, 10)
    assert "climate.trv_b" not in engine.rooms.pending
    assert not engine.store.data.overrides and not engine.rooms.problems
    await engine.async_stop(unloading=False)


async def test_provisional_report_can_be_confirmed_by_retry_readback(hass, freezer):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    sleepy = SleepyTRV(hass, "climate.trv_b", optimistic=True)
    await advance(hass, freezer, 10)
    assert "climate.trv_b" in engine.rooms.pending
    count = len(sleepy.sent)
    await advance(hass, freezer, 10)  # The retry check sees the target in HA, as specified.
    assert "climate.trv_b" not in engine.rooms.pending
    assert len(sleepy.sent) == count
    await engine.async_stop(unloading=False)


async def test_foreign_confirmation_drops_all_older_commands(hass, freezer):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    sleepy = SleepyTRV(hass, "climate.trv_a", optimistic=True)
    for target in (22, 23, 24):
        await engine.rooms.async_set_override(room.id, target, source="card")
        await engine.async_recalculate(apply_rooms=True)
        await hass.async_block_till_done()
    pending = engine.rooms.pending["climate.trv_a"]
    assert [command.target for command in pending.commands] == [22, 23, 24]
    sleepy.report(
        22, context=sleepy.sent[0].context
    )  # An older optimistic echo is provisional too.
    await hass.async_block_till_done()
    assert [command.target for command in pending.commands] == [22, 23, 24]
    assert engine.store.data.overrides[0].target == 24
    sleepy.report(23)  # Foreign device report confirms 23, including older 22.
    await hass.async_block_till_done()
    assert [command.target for command in pending.commands] == [24]
    assert pending.observed == 23
    assert engine.rooms.pending["climate.trv_a"] is pending
    await engine.async_stop(unloading=False)


async def test_off_attribute_update_keeps_pending_heat_command(hass, freezer):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    report(hass, "climate.trv_a", 21, mode="off")
    await hass.async_block_till_done()
    assert "climate.trv_a" not in engine.rooms.pending
    sleepy = SleepyTRV(hass, "climate.trv_a")
    await engine.async_data_changed()  # Next trigger must restore heat, with equal target.
    await hass.async_block_till_done()
    assert len(sleepy.queue) == 1
    assert sleepy.queue[0].data == {
        "entity_id": "climate.trv_a",
        "temperature": 21,
        "hvac_mode": "heat",
    }
    pending = engine.rooms.pending["climate.trv_a"]
    state = hass.states.get("climate.trv_a")
    hass.states.async_set("climate.trv_a", "off", {**state.attributes, "current_temperature": 16})
    await hass.async_block_till_done()
    assert engine.rooms.pending["climate.trv_a"] is pending
    assert pending.cancel is not None
    await advance(hass, freezer, 10)
    assert engine.rooms.pending["climate.trv_a"] is pending
    assert pending.retries == 1  # Equal temperature while still off is not heat confirmation.
    await sleepy.wake()
    assert hass.states.get("climate.trv_a").state == "heat"
    assert "climate.trv_a" not in engine.rooms.pending
    # A new transition into off is still a pause even while a different target is pending.
    await engine.rooms.async_set_override(room.id, 23)
    await engine.async_recalculate(apply_rooms=True)
    await hass.async_block_till_done()
    assert "climate.trv_a" in engine.rooms.pending
    report(hass, "climate.trv_a", 21, mode="off")
    await hass.async_block_till_done()
    assert "climate.trv_a" not in engine.rooms.pending
    await engine.async_stop(unloading=False)


async def test_boundary_reschedules_after_room_apply_exception(hass, freezer):
    from unittest.mock import patch

    engine, room, calls = await build_rooms(
        hass, freezer, blocks=(Block("00:00", 18), Block("06:00", 21), Block("07:00", 19))
    )
    with patch.object(engine.rooms, "_write", side_effect=RuntimeError("test failure")):
        await advance(hass, freezer, 10)
    assert engine.rooms._timer is not None
    assert not calls
    await advance(hass, freezer, 3600)
    assert len(calls) == 2
    assert all(call.data["temperature"] == 19 for call in calls)
    await engine.async_stop(unloading=False)


async def test_null_hvac_modes_does_not_break_apply_or_reschedule(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer)
    state = hass.states.get("climate.trv_a")
    hass.states.async_set("climate.trv_a", "off", {**state.attributes, "hvac_modes": None})
    await hass.async_block_till_done()
    await advance(hass, freezer, 10)
    assert len(calls) == 2
    assert "hvac_mode" not in calls[0].data
    assert engine.rooms._timer is not None
    await engine.async_stop(unloading=False)


async def test_apply_now_sync_off_includes_knob_override_for_all_trvs(hass, freezer):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer, sync=False)
    await advance(hass, freezer, 10)
    sleepy = SleepyTRV(hass, "climate.trv_b")
    report(hass, "climate.trv_a", 23)
    await hass.async_block_till_done()
    assert engine.store.data.overrides[0].target == 23
    assert not sleepy.queue
    await engine.async_recalculate(apply_rooms=True, force=True)
    await hass.async_block_till_done()
    assert [call.data["temperature"] for call in sleepy.queue] == [23]
    await sleepy.wake()
    assert sleepy.physical_target == 23
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 23
    await engine.async_stop(unloading=False)


async def test_normal_trigger_preserves_pending_and_exhausted_retry_budgets(hass, freezer):
    engine, room, calls = await build_rooms(hass, freezer, respond=False)
    await advance(hass, freezer, 10)
    pending = engine.rooms.pending["climate.trv_a"]
    pending.retries = 2
    before = len(calls)
    await engine.async_data_changed()  # Same desired target: wait for existing retry.
    await hass.async_block_till_done()
    assert len(calls) == before
    assert engine.rooms.pending["climate.trv_a"] is pending and pending.retries == 2
    for _ in range(4):
        await advance(hass, freezer, 10)  # Both TRVs exhaust their retry budgets.
    assert engine.rooms.problems == set(room.trvs)
    before = len(calls)
    await engine.async_data_changed()  # Normal triggers must not silently restart retries.
    await hass.async_block_till_done()
    assert len(calls) == before and not engine.rooms.pending
    assert engine.rooms.problems == set(room.trvs)
    await engine.rooms.async_set_override(
        room.id, 23
    )  # A changed desired target gets a new budget.
    await engine.async_recalculate(apply_rooms=True)
    await hass.async_block_till_done()
    assert len(calls) == before + 2
    assert not engine.rooms.problems
    assert all(pending.retries == 0 for pending in engine.rooms.pending.values())
    await engine.async_stop(unloading=False)


async def test_knob_equal_to_schedule_without_override_does_not_save_store(hass, freezer):
    from unittest.mock import patch

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    # Represent an independent device state just before returning its knob to schedule.
    engine._state_unsubscribe()
    engine._state_unsubscribe = None
    report(hass, "climate.trv_a", 23)
    await hass.async_block_till_done()
    engine._watch_trvs()
    assert not engine.store.data.overrides
    with patch.object(engine.store, "async_update", wraps=engine.store.async_update) as save:
        report(hass, "climate.trv_a", 21)
        await hass.async_block_till_done()
        save.assert_not_awaited()
    assert not engine.store.data.overrides
    await engine.async_stop(unloading=False)


async def test_attribute_only_report_cannot_confirm_optimistic_target(hass, freezer):
    """R03: a room-temperature update must not release the stale setpoint guard."""
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    sleepy = SleepyTRV(hass, "climate.trv_b", optimistic=True)
    await advance(hass, freezer, 10)
    pending = engine.rooms.pending["climate.trv_b"]
    assert sleepy.physical_target == 18
    assert hass.states.get("climate.trv_b").attributes["temperature"] == 21
    await sleepy.wake(lose_commands=True)
    state = hass.states.get("climate.trv_b")
    hass.states.async_set(
        "climate.trv_b",
        state.state,
        {**state.attributes, "current_temperature": 17.5},
        context=Context(),
    )
    await hass.async_block_till_done()
    assert engine.rooms.pending["climate.trv_b"] is pending
    assert pending.commands[0].before == 18
    await sleepy.stale()
    assert engine.rooms.pending["climate.trv_b"] is pending
    assert not engine.store.data.overrides
    assert hass.states.get("climate.trv_a").attributes["temperature"] == 21
    await advance(hass, freezer, 10)
    assert pending.retries == 1
    assert len(sleepy.queue) == 1
    await sleepy.wake()
    assert sleepy.physical_target == 21
    assert engine.rooms.pending["climate.trv_b"] is pending
    await advance(hass, freezer, 10)
    assert "climate.trv_b" not in engine.rooms.pending
    assert not engine.store.data.overrides
    await engine.async_stop(unloading=False)


async def test_stale_off_after_optimistic_heat_restore_does_not_pause(hass, freezer):
    """R09: losing a queued heat restore still leads to a retry after stale off."""
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    report(hass, "climate.trv_a", 21, mode="off")
    await hass.async_block_till_done()
    sleepy = SleepyTRV(hass, "climate.trv_a", optimistic=True)
    await engine.async_data_changed()
    await hass.async_block_till_done()
    pending = engine.rooms.pending["climate.trv_a"]
    assert hass.states.get("climate.trv_a").state == "heat"
    assert sleepy.physical_mode == "off"
    assert pending.commands[0].before_mode == "off"
    await sleepy.wake(lose_commands=True)
    await sleepy.stale()
    assert hass.states.get("climate.trv_a").state == "off"
    assert engine.rooms.pending["climate.trv_a"] is pending
    assert pending.cancel is not None
    assert not engine.store.data.overrides
    await advance(hass, freezer, 10)
    assert pending.retries == 1
    assert sleepy.queue[0].data["hvac_mode"] == "heat"
    await sleepy.wake()
    assert sleepy.physical_mode == "heat"
    # Real and optimistic state are identical; HA emits no state change to confirm it.
    assert engine.rooms.pending["climate.trv_a"] is pending
    await advance(hass, freezer, 10)
    assert "climate.trv_a" not in engine.rooms.pending
    assert not engine.rooms.problems
    await engine.async_stop(unloading=False)


async def test_partial_confirmation_updates_observed_for_next_retry(hass, freezer):
    """P14: retry must accept an older confirmed command as its new baseline."""
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    sleepy = SleepyTRV(hass, "climate.trv_a")
    for target in (22, 23):
        await engine.rooms.async_set_override(room.id, target, source="card")
        await engine.async_recalculate(apply_rooms=True)
        await hass.async_block_till_done()
    pending = engine.rooms.pending["climate.trv_a"]
    assert pending.observed == 21
    assert [command.target for command in pending.commands] == [22, 23]
    await sleepy.wake(count=1)
    assert pending.observed == 22
    assert [command.target for command in pending.commands] == [23]
    before = len(sleepy.sent)
    await advance(hass, freezer, 10)
    assert engine.rooms.pending["climate.trv_a"] is pending
    assert pending.retries == 1
    assert len(sleepy.sent) == before + 1
    assert sleepy.sent[-1].data["temperature"] == 23
    assert engine.store.data.overrides[0].target == 23
    await engine.async_stop(unloading=False)


async def test_s09_new_setpoint_while_off_cannot_confirm_pending_heat(hass, freezer):
    from tests.integration.sleepy_trv import SleepyTRV

    engine, room, calls = await build_rooms(hass, freezer)
    await advance(hass, freezer, 10)
    report(hass, "climate.trv_a", 18, mode="off")
    await hass.async_block_till_done()
    sleepy = SleepyTRV(hass, "climate.trv_a")
    await engine.async_data_changed()
    await hass.async_block_till_done()
    pending = engine.rooms.pending["climate.trv_a"]
    assert pending.commands[-1].target == 21
    # Temperature changed to the requested target, but the physical device is still off.
    report(hass, "climate.trv_a", 21, mode="off")
    await hass.async_block_till_done()
    assert engine.rooms.pending["climate.trv_a"] is pending
    assert pending.cancel is not None
    await advance(hass, freezer, 10)
    assert pending.retries == 1
    assert engine.rooms.pending["climate.trv_a"] is pending
    await sleepy.wake()
    assert "climate.trv_a" not in engine.rooms.pending
    assert hass.states.get("climate.trv_a").state == "heat"
    await engine.async_stop(unloading=False)
