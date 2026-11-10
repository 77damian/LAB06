"""Create infinite simulated measurements; the consumer decides when to stop.

G1 generates numbers without waiting. G2 waits without generating data. The
supplied scheduler combines them for several independent measurement channels.
All clocks can be replaced in tests, but normal runs use actual elapsed time.
"""
from datetime import datetime, timezone
from math import isfinite
import random
import time
from typing import Callable, Iterator

from records import UNITS, parse_record


def sensor_values(sensor: dict) -> Iterator[float]:
    """TASK G1: yield seeded noisy values forever, retaining no history.

Use a private Random instance, not random.seed(). Temperature is in C, humidity
in percent, pressure in hPa. The clipping is a teaching model, not sensor physics.
"""
    # TODO G1: your implementation begins here.
    # Create your own random.Random using sensor["seed"].
    # In an infinite loop, sample, check finiteness, apply the metric limits,
    # and yield one float. Do not sleep or accumulate a list here.
    raise NotImplementedError("G1: implement sensor_values in simulation.py.")
    yield 0.0  # Unreachable marker: preserve generator behaviour until implemented.


def wait_until(deadline: float, clock: Callable = time.monotonic,
               sleep: Callable = time.sleep) -> None:
    """TASK G2: wait until an absolute monotonic deadline, without busy-waiting.

Recheck after sleeping. An OS can wake us late; a test sleeper can wake us early.
Neither case should cause us to deliberately emit before the deadline.
"""
    # TODO G2: your implementation begins here.
    # Subtract clock() from deadline to find the remaining delay.
    # While it is positive, call sleep(remaining), then check the clock again.
    # Never busy-wait or request a negative sleep.
    raise NotImplementedError("G2: implement wait_until in simulation.py.")


def utc_now() -> datetime:
    """Use wall-clock UTC for stored timestamps, not for scheduling delays."""
    return datetime.now(timezone.utc)


def simulate_sensors(sensors: list[dict], *, clock: Callable = time.monotonic,
                     sleep: Callable = time.sleep,
                     now: Callable = utc_now) -> Iterator[dict]:
    """WORKED SCHEDULER: yield one due reading at a time, indefinitely.

Each configured item is one (room, sensor_id, metric) channel. Configuration is
validated before this function is used. Ties follow configuration order. The
first reading is due AFTER its first interval, not immediately at startup.
"""
    if not sensors:
        raise ValueError("Configure at least one sensor channel.")
    # A single consumer advances this generator. There are no background threads.
    streams = [sensor_values(sensor) for sensor in sensors]
    start = clock()  # Generator execution begins on its first next(), not creation.
    deadlines = [start + sensor["interval_seconds"] for sensor in sensors]
    try:
        while True:
            # Choose the next due channel; do not sleep once for every sensor.
            index = min(range(len(sensors)), key=lambda i: deadlines[i])
            sensor = sensors[index]
            due = deadlines[index]
            wait_until(due, clock, sleep)
            emitted = clock()
            reading = parse_record({
                "time": now().isoformat(), "room": sensor["room"],
                "sensor_id": sensor["sensor_id"], "metric": sensor["metric"],
                "value": next(streams[index]), "unit": UNITS[sensor["metric"]],
            })
            # Normally preserve the phase (5, 10, 15...). If processing falls far
            # behind, emit ONE reading and rebase, rather than invent a backlog.
            following = due + sensor["interval_seconds"]
            if following <= emitted:
                following = emitted + sensor["interval_seconds"]
            deadlines[index] = following
            yield reading
    finally:
        # Explicitly close child generators when a limit or Ctrl+C stops the run.
        for stream in streams:
            stream.close()
