"""Independent Python copy of the old package's raw-float template formulas."""


def raw_package(readings, hysteresis=0.3, frost_temperature=16.0):
    available = []
    demanding = []
    for current, target in readings:
        c = None if current in (None, "unknown", "unavailable") else float(current)
        t = None if target in (None, "unknown", "unavailable") else float(target)
        if c is not None:
            available.append(c)
            if t is not None and (t - c) > hysteresis:
                demanding.append((c, t))
    temperatures = [c for c, _ in demanding] if demanding else available
    return (
        len(demanding),
        round(sum(temperatures) / len(temperatures), 2) if temperatures else None,
        round(max(t for _, t in demanding), 1) if demanding else frost_temperature,
    )
