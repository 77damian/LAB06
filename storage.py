"""Write finite snapshots without selecting, calibrating or analysing data.

All writers replace their target. Only operational logging uses append mode.
The entry point/configuration must ensure that output never targets an input file.
"""
import csv
import json
from pathlib import Path
from typing import Union

from records import FIELDS


def save_json(path: Path, data: Union[dict, list]) -> None:
    """Write a readable JSON snapshot, creating the parent directory if needed."""
    # Serialise first: a bad value must not truncate a previously valid snapshot.
    text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")


def save_csv(path: Path, readings: list[dict]) -> None:
    """SOLUTION W1: replace a CSV snapshot; write a header even for no readings."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # newline="" prevents the text layer from adding extra newline conversions.
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(readings)


def save_jsonl(path: Path, readings: list[dict]) -> None:
    """SOLUTION W2: replace a snapshot containing one complete JSON object per line."""
    # This assignment is finite. Preparing the text first detects invalid JSON
    # values before opening an existing output in replacement mode.
    text = "".join(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n"
                   for record in readings)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")  # Empty input writes an empty file.
