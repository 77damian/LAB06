-- H1: the one table of the project. Timestamps are always UTC.
CREATE TABLE IF NOT EXISTS readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    time       TEXT    NOT NULL,   -- ISO 8601 UTC, e.g. 2026-11-21T14:05:00.123456+00:00
    ts_ms      INTEGER NOT NULL,   -- same moment as epoch milliseconds (range queries, bucketing)
    room       TEXT    NOT NULL,
    sensor_id  TEXT    NOT NULL,
    metric     TEXT    NOT NULL CHECK (metric IN ('temperature','humidity','pressure')),
    unit       TEXT    NOT NULL,   -- C, %, hPa
    value_raw  REAL    NOT NULL    -- before calibration
);

CREATE INDEX IF NOT EXISTS readings_series_time ON readings (room, sensor_id, metric, ts_ms);
