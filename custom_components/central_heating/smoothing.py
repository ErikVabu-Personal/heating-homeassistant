"""Immutable outlier window followed by a time-based low-pass filter."""

from dataclasses import dataclass
from math import expm1, isfinite
from statistics import median

from .const import OUTLIER_RADIUS, SMOOTHING_TAU_SECONDS, SMOOTHING_WINDOW


@dataclass(frozen=True)
class SmoothingState:
    """Full-precision internal value and last four raw values (rejected ones included)."""

    raw_values: tuple[float, ...] = ()
    value: float | None = None
    timestamp: float | None = None


@dataclass(frozen=True)
class SmoothingInput:
    raw: float | None
    timestamp: float


@dataclass(frozen=True)
class SmoothingResult:
    state: SmoothingState
    value: float | None


def smooth(sample: SmoothingInput, state: SmoothingState = SmoothingState()) -> SmoothingResult:
    """Keep unknown samples out of both history and elapsed-time accounting."""
    if sample.raw is None:
        return SmoothingResult(state, None)
    if not isfinite(sample.raw) or not isfinite(sample.timestamp):
        raise ValueError("Smoothing samples must be finite")
    value = sample.raw
    if len(state.raw_values) == SMOOTHING_WINDOW:
        centre = median(state.raw_values)
        if abs(value - centre) > OUTLIER_RADIUS:
            value = centre
    raw_values = (*state.raw_values, sample.raw)[-SMOOTHING_WINDOW:]
    if state.value is None:
        filtered = value
    else:
        if state.timestamp is None:
            raise ValueError("Initialized smoothing state needs a timestamp")
        elapsed = max(0.0, sample.timestamp - state.timestamp)
        filtered = state.value + (value - state.value) * -expm1(-elapsed / SMOOTHING_TAU_SECONDS)
    updated = SmoothingState(raw_values, filtered, sample.timestamp)
    return SmoothingResult(updated, round(filtered, 2))
