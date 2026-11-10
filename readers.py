"""Read finite sensor files without doing calibration or statistical analysis.

CSV is the original worked example. R1 and R2 now supply equivalent JSON and
JSON Lines readers. Every format uses parse_record as the same input boundary.
"""
import csv
import json
from pathlib import Path

from records import FIELDS, parse_record


def read_csv(path: Path) -> list[dict]:
    """Read a header-based CSV file, stopping at the first invalid row."""
    records = []
    # newline="" lets csv handle line endings; utf-8-sig also accepts a CSV BOM.
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or not set(FIELDS) <= set(reader.fieldnames):
            raise ValueError(f"{path}: CSV header must contain {', '.join(FIELDS)}")
        for row in reader:
            try:
                if None in row:  # DictReader uses None for unexpected extra fields.
                    raise ValueError("Too many columns in this CSV row.")
                records.append(parse_record(row))
            except ValueError as error:
                # Keep the location so that you can find and repair the input.
                raise ValueError(f"{path}: CSV line {reader.line_num}: {error}") from error
    return records


def read_json(path: Path) -> list[dict]:
    """SOLUTION R1: read a JSON array and return standard records in file order."""
    # Decode the complete finite document once. Missing files still raise OSError.
    with Path(path).open(encoding="utf-8") as stream:
        try:
            rows = json.load(stream)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"{path}: JSON line {error.lineno}, column {error.colno}: {error.msg}"
            ) from error

    # An object containing a 'readings' field is not our agreed file format.
    if not isinstance(rows, list):
        raise ValueError(f"{path}: JSON input must be an array of reading objects.")

    records = []
    for number, row in enumerate(rows, start=1):
        try:
            records.append(parse_record(row))
        except ValueError as error:
            # An item number is not a physical line number in a multi-line array.
            raise ValueError(f"{path}: JSON item {number}: {error}") from error
    return records


def read_jsonl(path: Path) -> list[dict]:
    """SOLUTION R2: decode one object per non-blank line; return a finite list."""
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, start=1):
            if not line.strip():
                continue  # A blank line is not a measurement and is safe to skip.
            try:
                records.append(parse_record(json.loads(line)))
            except ValueError as error:
                # JSONDecodeError is also a ValueError, so both failures get context.
                raise ValueError(f"{path}: JSON Lines line {number}: {error}") from error
    # Reading one line at a time is NOT bounded-memory processing if we keep all rows.
    return records


def read_data(path: Path, file_format: str) -> list[dict]:
    """Choose a reader explicitly; do not guess the format from a file suffix."""
    # A visible conditional is enough; there is no registry or plugin framework.
    if file_format == "csv":
        return read_csv(path)
    if file_format == "json":
        return read_json(path)
    if file_format == "jsonl":
        return read_jsonl(path)
    raise ValueError(f"Unsupported input format: {file_format!r}")
