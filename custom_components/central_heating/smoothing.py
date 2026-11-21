"""Immutable outlier window followed by a time-based low-pass filter."""

from dataclasses import dataclass
from math import expm1, isfinite
from statistics import median

from .const import OUTLIER_RADIUS, SMOOTHING_TAU_SECONDS, SMOOTHING_WINDOW


@dataclass(frozen=True)
class SmoothingState:
    """Full-precision internal value and last accepted updates (seconds)."""

    accepted: tuple[float, ...] = ()
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
    if state.timestamp is not None and sample.timestamp < state.timestamp:
        raise ValueError("Smoothing timestamps must not move backwards")
    value = sample.raw
    if state.accepted:
        centre = median(state.accepted)
        if abs(value - centre) > OUTLIER_RADIUS:
            value = centre
    accepted = (*state.accepted, value)[-SMOOTHING_WINDOW:]
    if state.value is None:
        filtered = value
    else:
        if state.timestamp is None:
            raise ValueError("Initialized smoothing state needs a timestamp")
        elapsed = sample.timestamp - state.timestamp
        filtered = state.value + (value - state.value) * -expm1(-elapsed / SMOOTHING_TAU_SECONDS)
    updated = SmoothingState(accepted, filtered, sample.timestamp)
    return SmoothingResult(updated, round(filtered, 2))
