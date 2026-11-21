"""Outlier window semantics, full-precision state and elapsed-time filtering."""

from dataclasses import FrozenInstanceError
from math import exp

import pytest

from custom_components.central_heating.smoothing import SmoothingInput, SmoothingState, smooth


def test_first_sample_initializes_and_rounds_only_output():
    result = smooth(SmoothingInput(20.12345, 10))
    assert result.value == 20.12
    assert result.state.value == 20.12345
    assert result.state.raw_values == (20.12345,)
    assert result.state.timestamp == 10


def test_outlier_replacement_keeps_raw_history():
    state = SmoothingState((20, 20.5, 21, 21.5), 20, 0)
    result = smooth(SmoothingInput(30, 300), state)
    assert result.state.raw_values == (20.5, 21, 21.5, 30)
    assert result.value == round(20 + 0.75 * (1 - exp(-1)), 2)
    assert state.raw_values == (20, 20.5, 21, 21.5)


@pytest.mark.parametrize(
    "raw,accepted", [(21.5, 21.5), (18.5, 18.5), (21.50001, 20), (18.49999, 20)]
)
def test_outlier_radius_is_strict(raw, accepted):
    result = smooth(SmoothingInput(raw, 10), SmoothingState((20, 20, 20, 20), 20, 0))
    assert result.state.raw_values[-1] == raw
    assert result.value == round(20 + (accepted - 20) * (1 - exp(-10 / 300)), 2)


def test_history_is_bounded_to_last_four_raw_values():
    state = SmoothingState()
    for timestamp, raw in enumerate([20, 20.2, 20.4, 20.6, 20.8, 21.0]):
        state = smooth(SmoothingInput(raw, timestamp), state).state
    assert state.raw_values == (20.4, 20.6, 20.8, 21.0)


@pytest.mark.parametrize("step", [1, 10, 30, 60, 100, 300])
def test_time_based_convergence_is_independent_of_update_interval(step):
    state = smooth(SmoothingInput(20, 0)).state
    for timestamp in range(step, 301, step):
        state = smooth(SmoothingInput(21, timestamp), state).state
    assert state.value == pytest.approx(20 + (1 - exp(-1)), abs=1e-12)
    assert smooth(SmoothingInput(21, 300), state).value == 20.63


def test_irregular_intervals_compose_without_rounding_the_internal_state():
    state = smooth(SmoothingInput(20, 0)).state
    for timestamp in [0.1, 3.7, 34.2, 127.3, 300]:
        state = smooth(SmoothingInput(21, timestamp), state).state
    assert state.value == pytest.approx(21 - exp(-1), abs=1e-12)


def test_unknown_keeps_state_and_elapsed_time():
    state = smooth(SmoothingInput(20, 0)).state
    missing = smooth(SmoothingInput(None, 250), state)
    assert missing.value is None and missing.state is state
    assert smooth(SmoothingInput(21, 300), missing.state).value == 20.63
    initial = SmoothingState()
    assert smooth(SmoothingInput(None, 100), initial).state is initial


def test_duplicate_timestamp_has_zero_low_pass_step():
    state = smooth(SmoothingInput(20, 100)).state
    result = smooth(SmoothingInput(21, 100), state)
    assert result.value == 20
    assert result.state.raw_values == (20, 21)


def test_backward_timestamp_keeps_value_and_updates_timestamp():
    state = smooth(SmoothingInput(20, 10)).state
    result = smooth(SmoothingInput(21, 9), state)
    assert result.state.value == 20
    assert result.state.timestamp == 9
    assert result.state.raw_values == (20, 21)
    resumed = smooth(SmoothingInput(21, 19), result.state)
    assert resumed.state.value == pytest.approx(20 + (1 - exp(-10 / 300)))


@pytest.mark.parametrize(
    "raw,timestamp", [(float("nan"), 1), (float("inf"), 1), (20, float("nan")), (20, float("inf"))]
)
def test_nonfinite_input_rejected(raw, timestamp):
    with pytest.raises(ValueError, match="finite"):
        smooth(SmoothingInput(raw, timestamp))


def test_state_input_result_are_frozen():
    for value, attribute in [
        (SmoothingState(), "value"),
        (SmoothingInput(20, 0), "raw"),
        (smooth(SmoothingInput(20, 0)), "value"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, 1)


@pytest.mark.parametrize("length", [1, 2, 3])
def test_outlier_filter_waits_for_a_full_window(length):
    state = SmoothingState((17,) * length, 17, 0)
    result = smooth(SmoothingInput(20, 10), state)
    assert result.state.value == pytest.approx(17 + 3 * (1 - exp(-10 / 300)))
    assert result.state.raw_values[-1] == 20


def test_sustained_step_recovers_within_a_few_samples():
    state = SmoothingState()
    for timestamp in range(0, 100, 10):
        state = smooth(SmoothingInput(17, timestamp), state).state
    outputs = []
    for timestamp in range(100, 3700, 10):
        result = smooth(SmoothingInput(20, timestamp), state)
        state = result.state
        outputs.append(result.value)
    assert outputs[:2] == [17, 17]
    assert outputs[2] > 17
    assert state.raw_values == (20, 20, 20, 20)
    assert outputs[-1] == 20


def test_single_spike_is_rejected_but_remains_in_raw_window():
    state = SmoothingState((17, 17, 17, 17), 17, 0)
    spike = smooth(SmoothingInput(30, 10), state)
    assert spike.value == 17
    assert spike.state.raw_values == (17, 17, 17, 30)
    result = smooth(SmoothingInput(17, 20), spike.state)
    assert result.value == 17


def test_outlier_uses_median_not_mean():
    state = SmoothingState((17, 17, 18, 25), 17, 0)
    result = smooth(SmoothingInput(30, 300), state)
    assert result.value == round(17 + 0.5 * (1 - exp(-1)), 2)
    assert result.state.raw_values == (17, 18, 25, 30)
