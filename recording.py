"""Keep measurements, configuration, and plot-ready state as distinct data products.

A new session directory prevents one run replacing another. raw.jsonl contains
ALL acquired readings BEFORE selection/calibration. latest.json is replaceable
state, not an archive. Only one process should write a session.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import TextIO
from uuid import uuid4


def append_reading(stream: TextIO, reading: dict, fsync: bool = False) -> None:
    """TASK G6: write one complete JSON line, then flush Python's buffer.

Serialise before writing, so an invalid number does not write a partial object.
With fsync=True, also request filesystem synchronisation. Propagate write errors;
continuing silently would make a monitor appear healthy while losing its archive.
"""
    # TODO G6: your implementation begins here.
    # Serialise before writing (allow_nan=False), then add one newline.
    # Write and flush each record; call os.fsync only when requested.
    # The caller owns the file handle. Do not catch and hide I/O errors.
    raise NotImplementedError("G6: implement append_reading in recording.py.")


def write_snapshot(path: Path, document: dict) -> None:
    """Replace JSON state via a neighbouring temporary file, not a partial rewrite.

This supports a later reader of latest.json. It is not a database transaction or
power-failure guarantee. The session has one writer; the temp name is private.
"""
    text = json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def create_session(config: dict) -> Path:
    """Create a unique recording directory and a ready-to-run offline config."""
    parent = config["recording"]["directory"]
    parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    session = parent / (stamp + "_" + uuid4().hex[:8])
    session.mkdir()  # Never reuse a previous recording directory.
    # Relative paths below are interpreted beside this newly written config file.
    offline = {
        "mode": "files", "input": {"path": "raw.jsonl", "format": "jsonl"},
        "selection": config["selection"].copy(),
        "calibration": config["calibration"].copy(),
        "output": {"readings_path": "offline/calibrated.csv",
                   "summary_path": "offline/summary.json"},
        "logging": {"level": "INFO", "path": "offline/analysis.log"},
    }
    write_snapshot(session / "offline_config.json", offline)
    return session


def serialisable_config(config: dict) -> dict:
    """Copy settings for metadata; convert only the resolved Path objects to text."""
    result = {**config, "recording": config["recording"].copy(),
              "logging": config["logging"].copy()}
    result["recording"]["directory"] = str(config["recording"]["directory"])
    if config["logging"]["path"] is not None:
        result["logging"]["path"] = str(config["logging"]["path"])
    return result
