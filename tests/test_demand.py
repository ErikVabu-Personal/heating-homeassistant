"""Demand branches, missing states, rounding and independent package equivalence."""

from dataclasses import FrozenInstanceError, astuple
from random import Random

import pytest

from custom_components.central_heating.demand import DemandResult, TRVReading, calculate_demand
from tests.reference_demand import raw_package


@pytest.mark.parametrize(
    "readings,expected",
    [
        ([], (0, None, 16.0)),
        ([(20.7, 21.0)], (0, 20.7, 16.0)),
        ([(20.69, 21.0)], (1, 20.69, 21.0)),
        ([(20.0, 21.0), (18.0, 22.0), (25.0, 24.0)], (2, 19.0, 22.0)),
        ([(20.0, 20.0), (22.0, 21.0)], (0, 21.0, 16.0)),
        ([(20.123, 21.16), (19.998, 21.24)], (2, 20.06, 21.2)),
        ([(None, 21.0), ("unknown", 22.0), ("unavailable", None)], (0, None, 16.0)),
        ([(20.0, None), (22.0, "unknown"), (21.0, "unavailable")], (0, 21.0, 16.0)),
        ([("20.0", "21.0"), ("unavailable", "22.0")], (1, 20.0, 21.0)),
        ([(0.0, 1.0)], (1, 0.0, 1.0)),
    ],
)
def test_demand_branches(readings, expected):
    result = calculate_demand(TRVReading(*pair) for pair in readings)
    assert astuple(result) == expected


@pytest.mark.parametrize("missing", [None, "unknown", "unavailable"])
def test_missing_target_still_contributes_available_current(missing):
    assert calculate_demand([TRVReading(18, missing), TRVReading(22, 22)]) == DemandResult(
        0, 20, 16
    )


def test_settings_are_passed_without_global_state():
    assert calculate_demand(
        [TRVReading(20, 20.5)], hysteresis=0.6, frost_temperature=8.5
    ) == DemandResult(0, 20, 8.5)


@pytest.mark.parametrize(
    "value",
    [
        float("nan"),
        float("inf"),
        float("-inf"),
        True,
        False,
        "invalid",
        "n/a",
        "",
        "Unknown",
        "NaN",
        "inf",
        [],
        {},
        object(),
        10**1000,
    ],
)
@pytest.mark.parametrize("attribute", ["current", "target"])
def test_invalid_temperatures_are_missing(value, attribute):
    reading = TRVReading(
        **{attribute: value, "target" if attribute == "current" else "current": 20}
    )
    result = calculate_demand([reading, TRVReading(18, 21)])
    assert result == DemandResult(1, 18, 21)
    alone = calculate_demand([reading])
    assert alone.demand_count == 0
    assert alone.virtual_temp_raw == (20 if attribute == "target" else None)
    assert alone.virtual_setpoint == 16


def test_inputs_and_results_are_frozen():
    with pytest.raises(FrozenInstanceError):
        TRVReading(20, 21).current = 22
    with pytest.raises(FrozenInstanceError):
        calculate_demand([]).demand_count = 4


def test_golden_generated_fixtures_match_old_raw_float_package():
    rng = Random(0)
    matches = differences = 0
    for index in range(1000):
        hyst = rng.choice([0.1, 0.3, 0.5, 1.0])
        readings = []
        for _ in range(rng.randrange(7)):
            current = rng.choice([None, "unknown", "unavailable", rng.randrange(100, 300) / 10])
            target = rng.choice([None, "unknown", "unavailable", rng.randrange(100, 300) / 10])
            readings.append((current, target))
        if index % 50 == 0:
            hyst = 0.3
            readings.append((20.7, 21.0))
        result = astuple(
            calculate_demand([TRVReading(*pair) for pair in readings], hysteresis=hyst)
        )
        reference = raw_package(readings, hyst)
        if result == reference:
            matches += 1
            continue
        # Only the documented threshold rounding may alter which TRVs contribute.
        # Generated numeric values lie on a decimal grid: every changed predicate
        # must therefore be exactly on the hysteresis boundary in decimal terms.
        changed = []
        corrected = []
        for current, target in readings:
            if isinstance(current, (int, float)) and isinstance(target, (int, float)):
                raw = (target - current) > hyst
                rounded = round(target - current, 2) > round(hyst, 2)
                if raw != rounded:
                    assert round(target - current, 2) == round(hyst, 2)
                    assert raw is True and rounded is False
                    changed.append((current, target))
                if rounded:
                    corrected.append((current, target))
        assert changed
        available = [c for c, _ in readings if isinstance(c, (int, float))]
        temperatures = [c for c, _ in corrected] if corrected else available
        expected = (
            len(corrected),
            round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
            round(max(t for _, t in corrected), 1) if corrected else 16.0,
        )
        assert result == expected
        differences += 1
    assert matches > 900
    assert differences > 0


def test_golden_explicit_rounding_difference():
    readings = [(20.7, 21.0)]
    assert raw_package(readings) == (1, 20.7, 21.0)
    assert astuple(calculate_demand([TRVReading(*readings[0])])) == (0, 20.7, 16.0)


@pytest.mark.parametrize("delta,expected", [(0.3001, 0), (0.304, 0), (0.306, 1)])
def test_documented_hundredth_precision_threshold(delta, expected):
    assert calculate_demand([TRVReading(0, delta)]).demand_count == expected


@pytest.mark.parametrize("current,target", [(" 20.0 ", "21"), (20, "2.1e1"), ("20", 21.0)])
def test_finite_numeric_strings_remain_available(current, target):
    assert calculate_demand([TRVReading(current, target)]) == DemandResult(1, 20, 21)
