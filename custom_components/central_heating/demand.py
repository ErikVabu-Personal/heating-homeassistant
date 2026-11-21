"""Pure demand and virtual boiler values for enabled rooms' TRVs."""

from collections.abc import Iterable
from dataclasses import dataclass
from math import isfinite

from .const import DEFAULT_FROST_TEMPERATURE, DEFAULT_HYSTERESIS

type Temperature = float | int | str | None


@dataclass(frozen=True)
class TRVReading:
    """Current and target values; callers omit TRVs from disabled rooms."""

    current: Temperature
    target: Temperature


@dataclass(frozen=True)
class DemandResult:
    demand_count: int
    virtual_temp_raw: float | None
    virtual_setpoint: float


def available_temperature(value: Temperature) -> float | None:
    """Convert state values without letting unavailable or nonfinite values propagate."""
    if value is None or value in ("unknown", "unavailable"):
        return None
    if isinstance(value, bool):
        raise ValueError("Temperature must be a finite number")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Temperature must be a finite number") from None
    if not isfinite(number):
        raise ValueError("Temperature must be a finite number")
    return number


def calculate_demand(
    readings: Iterable[TRVReading],
    *,
    hysteresis: float = DEFAULT_HYSTERESIS,
    frost_temperature: float = DEFAULT_FROST_TEMPERATURE,
) -> DemandResult:
    """Apply §5.1, retaining the documented rounded demand threshold."""
    if not isfinite(hysteresis) or not isfinite(frost_temperature):
        raise ValueError("Demand settings must be finite")
    available: list[float] = []
    demanding: list[tuple[float, float]] = []
    for reading in readings:
        current = available_temperature(reading.current)
        target = available_temperature(reading.target)
        if current is not None:
            available.append(current)
            if target is not None and round(target - current, 2) > round(hysteresis, 2):
                demanding.append((current, target))
    values = [current for current, _ in demanding] if demanding else available
    return DemandResult(
        demand_count=len(demanding),
        virtual_temp_raw=round(sum(values) / len(values), 2) if values else None,
        virtual_setpoint=(
            round(max(target for _, target in demanding), 1) if demanding else frost_temperature
        ),
    )
