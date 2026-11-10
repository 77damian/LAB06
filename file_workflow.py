"""The previous finite workflow, moved out of run.py without changing its calculation.

A file still contains a finite dataset. Do not pass an infinite generator to the
list-building functions below. The new run.py chooses this or the streaming path.
"""
import logging
from analysis import explore_data, summarise_by_series
from processing import process_readings
from readers import read_data
from records import UNITS
from storage import save_csv, save_json

LOGGER = logging.getLogger(__name__)


def run_files(config: dict) -> None:
    """Read, explore, select, calibrate and save exactly as in the previous stage."""
    LOGGER.info("Reading %s input: %s", config["input"]["format"], config["input"]["path"])
    raw_readings = read_data(config["input"]["path"], config["input"]["format"])
    exploration = explore_data(raw_readings)
    raw_summaries = summarise_by_series(raw_readings)
    LOGGER.info("Read %d raw records in %d distinct series", len(raw_readings),
                len(exploration["series"]))

    # Pure processing receives values/settings, not filenames or loggers.
    result = process_readings(raw_readings, config["selection"], config["calibration"])
    LOGGER.info("Selected %d records for %s", len(result["readings"]), config["selection"])
    if result["calibration_applied"]:
        LOGGER.info("Calibration enabled: scale=%s, offset=%s",
                    config["calibration"]["scale"], config["calibration"]["offset"])
    else:
        LOGGER.info("Calibration disabled; selected values remain raw.")
    if not result["readings"]:
        LOGGER.warning("Selection is empty; saving no readings and undefined statistics.")

    # Keep raw exploration separate from the selected, possibly calibrated summary.
    # Paths become strings only where they are deliberately included as JSON metadata.
    report = {
        "source": {"path": str(config["input"]["path"]), "format": config["input"]["format"]},
        "series": {**config["selection"], "unit": UNITS[config["selection"]["metric"]]},
        "calibration_applied": result["calibration_applied"],
        "calibration": config["calibration"].copy(),
        "summary": result["summary"],
        "raw_exploration": exploration,
        "raw_series_summaries": raw_summaries,
    }
    save_csv(config["output"]["readings_path"], result["readings"])
    save_json(config["output"]["summary_path"], report)
    LOGGER.info("Saved processed readings: %s", config["output"]["readings_path"])
    LOGGER.info("Saved summary and raw exploration: %s", config["output"]["summary_path"])
    label = "Calibrated" if result["calibration_applied"] else "Uncalibrated"
    print(f"{label} summary:", result["summary"])

