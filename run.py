"""Choose files or simulated sensors from JSON; no installation is required.

Run `python run.py` for the unchanged finite example, or use the new JSON files
under config/. Importing this module starts neither acquisition nor file writing.
"""
import argparse
import logging
from pathlib import Path
import signal

from file_workflow import run_files
from logging_service import configure_logging
from run_configuration import load_run_config
from run_stream import run_simulation

ROOT = Path(__file__).resolve().parent
LOGGER = logging.getLogger(__name__)

def _sigterm_to_keyboard_interrupt(signum, frame):
    raise KeyboardInterrupt

def main(config_path: Path = ROOT / "config" / "example.json") -> None:
    """Validate first, configure logging once, then choose one visible workflow."""
    config = load_run_config(config_path)
    configure_logging(config["logging"]["level"], config["logging"]["path"])
    LOGGER.info("Loaded configuration: %s", Path(config_path).resolve())
    if config["mode"] == "files":
        run_files(config)
    else:
        previous_handler = signal.signal(signal.SIGTERM, _sigterm_to_keyboard_interrupt)
        try:
            run_simulation(config)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read a file or record paced sensor generators.")
    parser.add_argument("config", nargs="?", type=Path,
                        default=ROOT / "config" / "example.json",
                        help="JSON configuration (relative CLI paths start in your terminal directory)")
    args = parser.parse_args()
    try:
        main(args.config)
    except (OSError, ValueError, NotImplementedError) as error:
        LOGGER.error("Run stopped: %s", error)
        raise SystemExit(1) from error
