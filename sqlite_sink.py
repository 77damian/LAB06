"""Buffered SQLite sink for simulated sensor readings."""

import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable

from db import connect_writer


class SqliteSink:
    def __init__(self, path: str, batch_size: int = 50, flush_seconds: float = 2.0) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if flush_seconds < 0:
            raise ValueError("flush_seconds must not be negative")

        self._conn = connect_writer(path)
        self._batch_size = batch_size
        self._flush_seconds = flush_seconds
        self._buffer: list[tuple] = []
        self._last_flush = time.monotonic()
        self._closed = False
        self._written = 0
        self._retry_sleep: Callable[[float], None] = time.sleep
        self._monotonic: Callable[[], float] = time.monotonic

    def write(self, reading: dict) -> None:
        if self._closed:
            raise RuntimeError("SqliteSink is closed")

        parsed = datetime.fromisoformat(reading["time"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)

        time_text = parsed.isoformat()
        ts_ms = int(parsed.timestamp() * 1000)

        self._buffer.append((
            time_text,
            ts_ms,
            reading["room"],
            reading["sensor_id"],
            reading["metric"],
            reading["unit"],
            float(reading["value"]),
        ))

        elapsed = self._monotonic() - self._last_flush
        if len(self._buffer) >= self._batch_size or elapsed >= self._flush_seconds:
            self.flush()

    def flush(self) -> None:
        if self._closed or not self._buffer:
            return

        deadline = self._monotonic() + 30.0
        delay = 0.05

        while True:
            try:
                self._conn.executemany(
                    """
                    INSERT INTO readings
                        (time, ts_ms, room, sensor_id, metric, unit, value_raw)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._buffer,
                )
                self._conn.commit()
                break
            except sqlite3.OperationalError as error:
                if "locked" not in str(error).lower() and "busy" not in str(error).lower():
                    self._conn.rollback()
                    raise

                self._conn.rollback()
                if self._monotonic() >= deadline:
                    raise RuntimeError(
                        "SQLite remained locked/busy for 30 seconds; "
                        f"{len(self._buffer)} readings remain buffered"
                    ) from error

                self._retry_sleep(delay)
                delay = min(delay * 2.0, 1.0)

        self._written += len(self._buffer)
        self._buffer.clear()
        self._last_flush = self._monotonic()

    @property
    def written_count(self) -> int:
        return self._written

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.flush()
        finally:
            self._conn.close()
            self._closed = True