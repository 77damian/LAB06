"""Orchestrate one acquisition session; keep the data flow visible.

This is the effectful outer layer: time, logging and files belong here. Small
transformations stay in streaming.py. No web server or plot loop is started.
"""
from datetime import datetime, timezone
from itertools import islice
import logging
from pathlib import Path
import time

from recording import append_reading, create_session, serialisable_config, write_snapshot
from simulation import simulate_sensors
from streaming import build_snapshot, rolling_windows, select_calibrated

LOGGER = logging.getLogger(__name__)


def run_simulation(config: dict) -> Path:
    """Run until a count limit or Ctrl+C; archive raw data before processing it."""
    session = create_session(config)
    raw_path = session / "raw.jsonl"
    LOGGER.info("Recording session: %s", session)
    print(f"Session: {session}", flush=True)
    print("First reading arrives after its configured interval. Stop with Ctrl+C.", flush=True)
    print(f'Offline analysis: python run.py "{session / "offline_config.json"}"', flush=True)

    count = 0  # Counts ALL raw records, not just the selected plot series.
    selected_count = 0
    started = time.monotonic()
    status = "running"
    metadata = {"started_at": datetime.now(timezone.utc).isoformat(),
                "config": serialisable_config(config), "status": status,
                "records_saved": 0, "selected_records": 0}
    snapshot = build_snapshot([], config["selection"], config["calibration"],
                              config["stream"]["window_size"])
    write_snapshot(session / "session.json", metadata)
    write_snapshot(session / "latest.json", {**snapshot, "status": status,
                                            "records_saved": 0, "selected_records": 0})
    source = simulate_sensors(config["simulation"]["sensors"])
    limit = config["simulation"]["max_readings"]
    incoming = source if limit is None else islice(source, limit)
    try:
        # Exclusive creation protects an existing archive; this handle stays open.
        with raw_path.open("x", encoding="utf-8", newline="\n") as output:
            def record_incoming():
                """A deliberate side-effecting generator: record, then pass through."""
                nonlocal count
                for raw in incoming:
                    append_reading(output, raw, config["recording"]["fsync"])
                    count += 1
                    # DEBUG is optional; raw.jsonl is the data, not this text log.
                    LOGGER.debug("Recorded %s / %s / %s", raw["room"],
                                 raw["sensor_id"], raw["metric"])
                    yield raw

            # The raw archive is UPSTREAM of selection: other sensors are not lost.
            selected = select_calibrated(record_incoming(), config["selection"],
                                         config["calibration"])
            windows = rolling_windows(selected, config["stream"]["window_size"])
            for window in windows:
                selected_count += 1
                snapshot = build_snapshot(window, config["selection"], config["calibration"],
                                          config["stream"]["window_size"])
                write_snapshot(session / "latest.json", {
                    **snapshot, "status": status, "records_saved": count,
                    "selected_records": selected_count,
                })
                last = window[-1]
                print(f'{last["time"]} | {last["metric"]}={last["value"]:.3f} '
                      f'{last["unit"]} | window n={len(window)} '
                      f'mean={snapshot["summary"]["mean"]:.3f}', flush=True)
        status = "completed"  # The finite prefix was exhausted normally.
    except KeyboardInterrupt:
        status = "interrupted"
        LOGGER.info("Ctrl+C received; closing the current recording.")
    except Exception as error:
        status = "failed"
        metadata["error"] = f"{type(error).__name__}: {error}"
        raise  # A storage/processing error must produce a non-zero exit status.
    finally:
        source.close()
        metadata.update(status=status, records_saved=count, selected_records=selected_count,
                        finished_at=datetime.now(timezone.utc).isoformat(),
                        elapsed_seconds=time.monotonic() - started)
        # Preserve an original failure even if a full disk prevents final metadata.
        try:
            write_snapshot(session / "session.json", metadata)
            write_snapshot(session / "latest.json", {
                **snapshot, "status": status, "records_saved": count,
                "selected_records": selected_count,
            })
        except OSError:
            if status != "failed":
                raise
            LOGGER.exception("Could not write final metadata; raw data may still be readable.")
    print(f"Saved {count} raw readings; {selected_count} selected. Status: {status}.", flush=True)
    LOGGER.info("Session %s: %d raw readings saved", status, count)
    return session
