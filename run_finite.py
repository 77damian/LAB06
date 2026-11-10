"""SOLUTION I1: the first assignment, with all choices visible in Python.

Run: python run_finite.py
Start here before moving to the configuration-based run.py. No config file is read.
"""
import logging
import sys
from pathlib import Path

from analysis import explore_data, extended_summary, select_series, summarise_by_series
from calibration import calibrate_reading
from logging_service import configure_logging
from readers import read_data
from records import UNITS
from storage import save_csv, save_json, save_jsonl

# Path objects interpret / as joining path components, not numerical division.
ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)
INPUT_PATH = ROOT / "data" / "readings.csv"
INPUT_FORMAT = "csv"
SELECTION = {"room": "laboratory", "sensor_id": "station-01", "metric": "temperature"}
SCALE = 1.02
OFFSET = -0.4
OUTPUT_DIR = ROOT / "output" / "finite"


def main() -> None:
    """Read -> explore -> select -> calibrate -> summarise -> save."""
    # Configuration-file validation is the next stage. For this visible-settings
    # example, at least guard against accidentally using the input as a destination.
    targets = [OUTPUT_DIR / name for name in
               ("run.log", "calibrated.csv", "calibrated.jsonl", "summary.json")]
    if INPUT_PATH.resolve() in [path.resolve() for path in targets]:
        raise ValueError("An output/log path must not overwrite the input file.")
    configure_logging("INFO", OUTPUT_DIR / "run.log")
    LOGGER.info("Reading %s input: %s", INPUT_FORMAT, INPUT_PATH)
    raw_readings = read_data(INPUT_PATH, INPUT_FORMAT)

    # These two products describe ALL raw series; neither applies calibration.
    exploration = explore_data(raw_readings)
    raw_summaries = summarise_by_series(raw_readings)
    LOGGER.info("Read %d raw records in %d series", len(raw_readings), len(exploration["series"]))

    selected_readings = select_series(raw_readings, **SELECTION)
    LOGGER.info("Selected %d records for %s", len(selected_readings), SELECTION)
    calibrated_readings = [calibrate_reading(record, SCALE, OFFSET)
                           for record in selected_readings]
    LOGGER.info("Calibration enabled: scale=%s, offset=%s", SCALE, OFFSET)
    if not calibrated_readings:
        LOGGER.warning("Selection is empty; no readings were calibrated.")
    values = [record["value"] for record in calibrated_readings]
    summary = extended_summary(values)

    # One selected result, two serialisations: both writers are completed examples.
    save_csv(OUTPUT_DIR / "calibrated.csv", calibrated_readings)
    save_jsonl(OUTPUT_DIR / "calibrated.jsonl", calibrated_readings)
    save_json(OUTPUT_DIR / "summary.json", {
        "source": {"path": str(INPUT_PATH), "format": INPUT_FORMAT},
        "series": {**SELECTION, "unit": UNITS[SELECTION["metric"]]},
        "calibration_applied": True,
        "calibration": {"enabled": True, "scale": SCALE, "offset": OFFSET},
        "summary": summary,
        "raw_exploration": exploration,
        "raw_series_summaries": raw_summaries,
    })
    for path in targets[1:]:
        LOGGER.info("Saved %s", path)
    print("Calibrated summary:", summary)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit("Run python run_finite.py without arguments; edit its visible settings.")
    try:
        main()
    except (OSError, ValueError) as error:
        LOGGER.error("Run stopped: %s", error)
        raise SystemExit(1) from error
