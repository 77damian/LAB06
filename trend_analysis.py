import math
from datetime import datetime
from analysis import extended_summary

def _check_number(x) -> float:
    if not isinstance(x, (int, float)) or isinstance(x, bool) or not math.isfinite(x):
        raise ValueError(f"Invalid number: {x}")
    return float(x)


def moving_average( values:  list[float], samples: int) -> list[float]:
    if isinstance(samples,bool) or not isinstance(samples, int):
        raise ValueError(f"Invalid sample type: {samples}")

    if samples < 1:
        raise ValueError(f"Invalid sample count: {samples}")
    result = []
    sum_ = 0.0
    for i in range(len(values)):
        if i < samples:
            sum_ += _check_number(values[i])
            result.append(sum_ / (i + 1))
        else:
            sum_ += _check_number(values[i]) - _check_number(values[i - samples])
            result.append(sum_ / samples)
    return result


def linear_trend(points: list[dict]) -> dict:
    xs = []
    ys = []
    t0 = None

    for point in points:
        t = point["time"]
        if not isinstance(t, datetime) or t.tzinfo is None or t.tzinfo.utcoffset(t) is None:
            raise ValueError("Time must be a timezone-aware datetime")
        y = _check_number(point["value"])
        if t0 is None:
            t0 = t
        xs.append((t - t0).total_seconds() / 60.0)
        ys.append(y)

    if len(points) < 2:
        return {"slope_per_minute": None, "value_at_start": None, "fitted_values": [None] * len(points)}

    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)

    if den == 0:
        return {"slope_per_minute": None, "value_at_start": None, "fitted_values": [None] * len(points)}

    slope = num / den
    value_at_start = mean_y - slope * mean_x
    fitted_values = [value_at_start + slope * x for x in xs]
    return {"slope_per_minute": slope, "value_at_start": value_at_start, "fitted_values": fitted_values}


        


