"""Set up operational messages once at application startup, never during import.

The console tells you what is happening now; the optional file keeps earlier runs.
Numerical functions remain quiet. A log is not a measurement-data product.
"""
import logging
from pathlib import Path
from typing import Optional

LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def configure_logging(level: str = "INFO", log_path: Optional[Path] = None) -> None:
    """SOLUTION L1: configure a console and an optional UTF-8 append-only file log."""
    if not isinstance(level, str) or level not in LEVELS:
        raise ValueError(f"Unsupported logging level: {level!r}")

    handlers = [logging.StreamHandler()]
    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # 'a' appends. Opening in 'w' would erase messages from earlier runs.
        handlers.append(logging.FileHandler(path, mode="a", encoding="utf-8"))

    # Replacing the entry point's old handlers prevents duplicate messages.
    # This global reset suits our standalone script, not a general-purpose library.
    logging.basicConfig(level=level, handlers=handlers, force=True,
                        format="%(levelname)s | %(name)s | %(message)s")
