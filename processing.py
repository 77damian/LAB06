"""The functional core: select, optionally calibrate, and summarise finite records.

No configuration file is opened here. No globals are read and no input is mutated.
File access, logging and saving belong to the application entry point.
"""
from collections.abc import Iterable

from analysis import extended_summary, select_series
from calibration import calibrate_reading


def process_readings(readings: Iterable[dict], selection: dict,
                     calibration: dict) -> dict:
    """SOLUTION X3: consume one source once and return a new finite result."""
    # Filter first: these coefficients belong to this one physical series only.
    selected = select_series(readings, **selection)
    if calibration["enabled"]:
        processed = [calibrate_reading(record, calibration["scale"], calibration["offset"])
                     for record in selected]
    else:
        # Still return new dictionaries, so a caller cannot edit raw data via output.
        processed = [record.copy() for record in selected]

    values = [record["value"] for record in processed]
    return {"readings": processed, "summary": extended_summary(values),
            "calibration_applied": calibration["enabled"]}
