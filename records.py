"""WORKED EXAMPLE: turn a row from any reader into the same small dictionary.

You do not need to change this file for your first tasks. Read DATA_CONTRACT.md
before writing a new reader. Keep file opening and logging out of this function.
"""
from datetime import datetime, timezone
from math import isfinite

# These are the only input units in this first iteration. No conversion is hidden.
UNITS = {"temperature": "C", "humidity": "%", "pressure": "hPa"}
FIELDS = ("time", "room", "sensor_id", "metric", "value", "unit")


def parse_record(row: dict) -> dict:
    """Validate one raw row; return a new record with a numeric value and UTC time."""
    if not isinstance(row, dict):
        raise ValueError("Each reading must be a dictionary/object.")
    missing = set(FIELDS) - row.keys()
    if missing:
        raise ValueError(f"Missing reading fields: {sorted(missing)}")

    # CSV supplies strings. JSON may supply numbers. Both become a finite float.
    raw_value = row["value"]
    if isinstance(raw_value, bool) or not isinstance(raw_value, (str, int, float)):
        raise ValueError("value must be a number, not a boolean or null.")
    try:
        value = float(raw_value)
    except (ValueError, OverflowError) as error:
        raise ValueError("value must be numeric.") from error
    if not isfinite(value):
        raise ValueError("value must be finite; NaN and infinity are not readings.")

    # Require meaningful text instead of silently converting missing IDs to strings.
    text = {}
    for name in ("time", "room", "sensor_id", "metric", "unit"):
        if not isinstance(row[name], str) or not row[name].strip():
            raise ValueError(f"{name} must be non-empty text.")
        text[name] = row[name].strip()
    metric = text["metric"]
    if metric not in UNITS or text["unit"] != UNITS[metric]:
        raise ValueError(f"Unsupported metric/unit pair: {metric!r}, {text['unit']!r}")

    # An explicit timezone prevents a local computer setting from changing the data.
    instant = datetime.fromisoformat(text["time"])
    if instant.utcoffset() is None:
        raise ValueError("time must include a timezone, for example +00:00.")
    text["time"] = instant.astimezone(timezone.utc).isoformat()
    return {**text, "value": value}
