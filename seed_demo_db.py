import math
import os
import random
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

SCHEMA = """
CREATE TABLE readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    time       TEXT    NOT NULL,
    ts_ms      INTEGER NOT NULL,
    room       TEXT    NOT NULL,
    sensor_id  TEXT    NOT NULL,
    metric     TEXT    NOT NULL CHECK (metric IN ('temperature','humidity','pressure')),
    unit       TEXT    NOT NULL,
    value_raw  REAL    NOT NULL
);
CREATE INDEX readings_series_time ON readings (room, sensor_id, metric, ts_ms);
"""


def seed_demo_db(path, hours=24, interval_seconds=5.0, end=None, seed=1) -> None:
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(f"{path}{suffix}"):
            os.remove(f"{path}{suffix}")

    end = end or datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    gap_start = start + timedelta(hours=hours / 2)
    gap_end = gap_start + timedelta(minutes=10)

    rng = random.Random(seed)
    rows = []
    t = start
    step = timedelta(seconds=interval_seconds)

    while t < end:
        if not (gap_start <= t < gap_end):
            wave = 2.0 * math.sin(2 * math.pi * (t.hour + t.minute / 60 - 9) / 24)
            temp = 21.0 + wave + rng.gauss(0, 0.08)
            hum = max(0.0, min(100.0, 50.0 - 2 * wave + rng.gauss(0, 0.25)))
            iso, ts_ms = t.isoformat(), int(t.timestamp() * 1000)

            rows.append((iso, ts_ms, "laboratory", "station-01", "temperature", "C", temp))
            rows.append((iso, ts_ms, "laboratory", "station-01", "humidity", "%", hum))
        t += step

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO readings (time, ts_ms, room, sensor_id, metric, unit, value_raw) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )


if __name__ == "__main__":
    seed_demo_db(sys.argv[1] if len(sys.argv) > 1 else "demo.db")