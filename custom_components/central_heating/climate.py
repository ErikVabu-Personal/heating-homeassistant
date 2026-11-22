"""One virtual climate entity per configured room."""

from statistics import mean

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .demand import TRVReading, available_temperature, calculate_demand
from .entity import HeatingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    known = set()

    @callback
    def discover():
        fresh = [room.id for room in entry.runtime_data.store.data.rooms if room.id not in known]
        known.update(fresh)
        if fresh:
            async_add_entities([RoomClimate(entry, room_id) for room_id in fresh])

    discover()
    entry.async_on_unload(entry.runtime_data.listen(discover))


class RoomClimate(HeatingEntity, ClimateEntity):
    _attr_hvac_modes = [HVACMode.HEAT]
    _attr_hvac_mode = HVACMode.HEAT
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _enable_turn_on_off_backwards_compatibility = False
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    if not hasattr(ClimateEntity, "native_temperature_unit"):
        _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_min_temp = 5
    _attr_max_temp = 30
    _attr_target_temperature_step = 0.5

    def __init__(self, entry, room_id):
        super().__init__(entry, f"room_{room_id}")
        self.room_id = room_id
        self._attr_translation_key = None

    @property
    def room(self):
        return next(
            (room for room in self.engine.store.data.rooms if room.id == self.room_id), None
        )

    @property
    def name(self):
        return self.room.name if self.room is not None else None

    @property
    def available(self):
        return self.room is not None and self.room.enabled

    def _readings(self):
        readings = []
        if self.room is not None:
            for trv in self.room.trvs:
                state = self.hass.states.get(trv)
                if state is not None and state.state not in ("unknown", "unavailable"):
                    readings.append(
                        TRVReading(
                            state.attributes.get("current_temperature"),
                            state.attributes.get("temperature") if state.state != "off" else None,
                        )
                    )
        return readings

    @property
    def native_current_temperature(self):
        values = [available_temperature(reading.current) for reading in self._readings()]
        values = [value for value in values if value is not None]
        return round(mean(values), 2) if values else None

    @property
    def native_target_temperature(self):
        if self.room is None:
            return None
        desired = self.engine.rooms.desired(self.room)
        if desired is not None:
            return desired
        values = [available_temperature(reading.target) for reading in self._readings()]
        values = [value for value in values if value is not None]
        return round(mean(values), 2) if values else None

    # 2026.11 renamed these properties; retain the 2026.10 API only on that release.
    if not hasattr(ClimateEntity, "native_current_temperature"):
        current_temperature = native_current_temperature
        target_temperature = native_target_temperature

    @property
    def hvac_action(self):
        demand = calculate_demand(
            self._readings(), hysteresis=self.engine.store.data.settings.hysteresis
        )
        return HVACAction.HEATING if demand.demand_count else HVACAction.IDLE

    @property
    def extra_state_attributes(self):
        if self.room is None:
            return {}
        plan = self.engine.rooms.schedule(self.room)
        override = next(
            (
                item
                for item in self.engine.store.data.overrides
                if item.room_id == self.room_id
                and item.until > dt_util.utcnow()
                and self.engine.store.data.mode.value in ("schedule", "away")
            ),
            None,
        )
        return {
            "schedule": next(
                item.name
                for item in self.engine.store.data.schedules
                if item.id == self.engine.store.data.active_schedule_id
            ),
            "scheduled_target": plan.current.block.target,
            "next_change": plan.next_change.at.isoformat() if plan.next_change else None,
            "next_target": plan.next_target,
            "override_until": override.until.isoformat() if override else None,
            "demanding": self.hvac_action == HVACAction.HEATING,
            "trvs": list(self.room.trvs),
            "sync_problem": any(trv in self.engine.rooms.problems for trv in self.room.trvs),
        }

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode != HVACMode.HEAT:
            raise ServiceValidationError("Room climates only support heat")

    async def async_set_temperature(self, **kwargs):
        async with self.engine._room_lock:
            await self.engine.rooms.async_set_override(
                self.room_id, kwargs["temperature"], source="card"
            )
        await self.engine.async_recalculate(apply_rooms=True)
