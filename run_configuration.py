"""Add a mode switch while preserving the previous configuration service.

The old schema (no mode field) still means files. The original configuration.py
is unchanged. New checks below concern only streaming settings, not a framework.
Paths are ALWAYS resolved beside the configuration file that contains them.
"""
from copy import deepcopy
import json
from math import isfinite
from pathlib import Path

from configuration import validate_config, resolve_paths
from records import UNITS


def exact_keys(value, keys: set, label: str) -> None:
    """Fail early on misspelled, missing, or unexpected configuration entries."""
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{label} must be an object with exactly these keys: {sorted(keys)}")


def number(value, label: str, minimum=None, strict=False) -> None:
    """Require finite numbers; bool is deliberately not accepted as an integer."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number.")
    try:
        valid = isfinite(value)
    except OverflowError:
        valid = False
    if not valid or (minimum is not None and
                     (value <= minimum if strict else value < minimum)):
        raise ValueError(f"{label} is outside its permitted finite range.")


def nonempty_text(value, label: str) -> None:
    """Require text; identities may not have accidental leading/trailing spaces."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty text.")


def validate_simulation(config: dict) -> None:
    """WORKED INFRASTRUCTURE: validate before any logs/recordings are created."""
    exact_keys(config, {"mode", "simulation", "recording", "stream", "selection",
                        "calibration", "logging"}, "config")
    if config["mode"] != "simulation":
        raise ValueError("mode must be simulation here.")
    exact_keys(config["simulation"], {"sensors", "max_readings"}, "simulation")
    exact_keys(config["recording"], {"directory", "fsync"}, "recording")
    exact_keys(config["stream"], {"window_size"}, "stream")
    exact_keys(config["selection"], {"room", "sensor_id", "metric"}, "selection")
    exact_keys(config["calibration"], {"enabled", "scale", "offset"}, "calibration")
    exact_keys(config["logging"], {"level", "path"}, "logging")

    # Reuse the old schema checks for selection, calibration and logging. The
    # placeholder finite paths are only validation input; they are never opened.
    validate_config({
        "input": {"path": "unused.csv", "format": "csv"},
        "selection": config["selection"], "calibration": config["calibration"],
        "output": {"readings_path": "unused-output.csv", "summary_path": "unused.json"},
        "logging": config["logging"],
    })
    for value, label, nullable in (
        (config["simulation"]["max_readings"], "simulation.max_readings", True),
        (config["stream"]["window_size"], "stream.window_size", False),
    ):
        if nullable and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{label} must be a positive integer" + (" or null." if nullable else "."))
    nonempty_text(config["recording"]["directory"], "recording.directory")
    if not isinstance(config["recording"]["fsync"], bool):
        raise ValueError("recording.fsync must be true or false.")

    sensors = config["simulation"]["sensors"]
    if not isinstance(sensors, list) or not sensors:
        raise ValueError("simulation.sensors must be a non-empty array.")
    identities = set()
    for index, sensor in enumerate(sensors):
        label = f"simulation.sensors[{index}]"
        exact_keys(sensor, {"room", "sensor_id", "metric", "interval_seconds",
                            "mean", "noise_std", "seed"}, label)
        for key in ("room", "sensor_id", "metric"):
            nonempty_text(sensor[key], f"{label}.{key}")
            if sensor[key] != sensor[key].strip():
                raise ValueError(f"{label}.{key} must not have surrounding whitespace.")
        if sensor["metric"] not in UNITS:
            raise ValueError(f"{label}.metric must be temperature, pressure, or humidity.")
        number(sensor["interval_seconds"], f"{label}.interval_seconds", 0, strict=True)
        number(sensor["mean"], f"{label}.mean")
        number(sensor["noise_std"], f"{label}.noise_std", 0)
        if sensor["metric"] == "humidity" and not 0 <= sensor["mean"] <= 100:
            raise ValueError(f"{label}.mean must be between 0 and 100 for humidity.")
        if sensor["metric"] == "pressure" and sensor["mean"] <= 0:
            raise ValueError(f"{label}.mean must be positive for pressure.")
        if isinstance(sensor["seed"], bool) or not isinstance(sensor["seed"], int):
            raise ValueError(f"{label}.seed must be an integer.")
        identity = tuple(sensor[k] for k in ("room", "sensor_id", "metric"))
        if identity in identities:
            raise ValueError(f"Duplicate sensor series: {identity}")
        identities.add(identity)
    selected = tuple(config["selection"][k] for k in ("room", "sensor_id", "metric"))
    if selected not in identities:
        raise ValueError("selection must match a configured simulated series.")


def load_run_config(path: Path) -> dict:
    """Read once, choose the schema, resolve paths, and protect the config file."""
    path = Path(path).resolve()
    try:
        with path.open(encoding="utf-8") as stream:
            raw = json.load(stream)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: JSON line {error.lineno}: {error.msg}") from error
    if not isinstance(raw, dict):
        raise ValueError("Configuration must be a JSON object.")
    mode = raw.get("mode", "files")
    if mode == "files":
        legacy = {key: value for key, value in raw.items() if key != "mode"}
        validate_config(legacy)
        result = resolve_paths(legacy, path.parent)
        targets = [result["output"]["readings_path"], result["output"]["summary_path"],
                   result["logging"]["path"]]
    elif mode == "simulation":
        validate_simulation(raw)
        result = deepcopy(raw)
        result["recording"]["directory"] = (path.parent / raw["recording"]["directory"]).resolve()
        if raw["logging"]["path"] is not None:
            result["logging"]["path"] = (path.parent / raw["logging"]["path"]).resolve()
        targets = [result["recording"]["directory"], result["logging"]["path"]]
        if targets[0] == targets[1]:
            raise ValueError("Path collision: recording directory and log file.")
    else:
        raise ValueError("mode must be files or simulation.")
    if path in targets:
        raise ValueError("An output/log path must not overwrite the configuration file.")
    result["mode"] = mode
    return result
