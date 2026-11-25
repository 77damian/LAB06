# 07 — Dashboard and 24h data collection

A short guide for the whole team: **what we build, how the pieces fit together, and who does what (tasks H1–H5).**

---

## 1. Vision

We already have a Python program that simulates room sensors (temperature, humidity, pressure). In this sprint we turn it into a small **monitoring system**:

1. A **collector** produces realistic sensor readings and stores them in a **SQLite database**.
2. A **Streamlit dashboard** reads the database and shows the data in the browser.
3. Everything runs in **Docker**, so `docker compose up` works on any computer.
4. We let it run for **24 hours** and use the result for the final report.

**Sprint goal:** a working dashboard, fed by our own generator, with a full 24h dataset behind it.

**Not in scope:** a web API, user login, real hardware sensors, alerts, cloud deployment.

### Principles

- **The dashboard never creates data.** It only reads. Refreshing or closing the browser must not change what is collected (same rule as in lab07).
- **Raw values are stored; calibration is applied when reading.** We can change the calibration without losing data.
- **A series is always `(room, sensor_id, metric)`.** Never mix temperature and humidity, never group by room alone.
- **Honest data.** "No data" and "unknown" are shown as empty (`None`), never as `0`.
- **One writer.** Only the collector writes to the database. Everything else reads.
- **Each person tests their own code.** A task is done only when its tests pass.

---

## 2. Architecture

```
 ┌────────────┐   INSERT    ┌───────────────────┐   SELECT   ┌───────────────┐
 │ collector  │ ──────────► │ SQLite file       │ ◄───────── │   Streamlit   │ ◄── browser :8501
 │ (generator │             │ sensors.db (WAL)  │            │  (dashboard)  │
 │  + sinks)  │             │ in Docker volume  │            └───────────────┘
 └─────┬──────┘             └───────────────────┘
       │ also appends
       ▼
  raw.jsonl backup (mounted folder ./output)
```

| Container | Technology | Port | Job |
|---|---|---|---|
| `collector` | Python (our existing code) | — | Generates readings, writes to SQLite + JSONL backup |
| `dashboard` | Streamlit | 8501 | Charts and numbers for humans |

There is **no separate database server.** Both containers mount the same Docker volume (`dbdata`) that holds `sensors.db`.

### Why SQLite is fine here

- About 115 000 rows per day (about 25 MB). Tiny for SQLite.
- One writer, a few readers. SQLite in **WAL mode** allows reading while the collector writes.
- Nothing to install or configure, and the file is easy to copy as evidence of the 24h run.

### Rules to make it work

- Open every connection with `PRAGMA journal_mode=WAL;` and `PRAGMA busy_timeout=5000;`.
- The dashboard opens the database **read-only** (`file:...?mode=ro`, `uri=True`).
- Use a **Docker named volume**, not a Windows bind mount, for the `.db` file (SQLite locking is unreliable on bind-mounted Windows folders).
- Do not put the `.db` file on a network drive.
- All database access goes through `store.py` (section 5). If SQLite is ever too small, only that module and the writer change.

---

## 3. Data model

One table. Timestamps are always UTC.

```sql
CREATE TABLE IF NOT EXISTS readings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    time       TEXT    NOT NULL,   -- ISO 8601 UTC, e.g. 2026-11-21T14:05:00.123456+00:00
    ts_ms      INTEGER NOT NULL,   -- same moment as epoch milliseconds (fast range queries, bucketing)
    room       TEXT    NOT NULL,
    sensor_id  TEXT    NOT NULL,
    metric     TEXT    NOT NULL CHECK (metric IN ('temperature','humidity','pressure')),
    unit       TEXT    NOT NULL,   -- C, %, hPa
    value_raw  REAL    NOT NULL    -- before calibration
);

CREATE INDEX IF NOT EXISTS readings_series_time ON readings (room, sensor_id, metric, ts_ms);
```

Bucketing example (5-minute buckets) in SQL:

```sql
SELECT (ts_ms / 300000) * 300000 AS bucket_ms,
       AVG(value_raw), MIN(value_raw), MAX(value_raw), COUNT(*)
FROM readings
WHERE room=? AND sensor_id=? AND metric=? AND ts_ms BETWEEN ? AND ?
GROUP BY bucket_ms ORDER BY bucket_ms;
```

SQLite has no median function, so the median is computed in Python.

---

## 4. Realistic data generator ("fake weather")

The current generator draws independent random numbers around a fixed mean, so the plot is only noise. We want curves that look like a real day. The model is small and deterministic for a given seed.

### Temperature

```
T(t) = base
     + amplitude * sin( 2π * (hour(t) - 9) / 24 )     # daily cycle: coldest ~03:00, warmest ~15:00
     + weather(t)                                      # slow random drift
     + noise                                           # sensor jitter
```

- `base` ≈ 21 °C (room), `amplitude` ≈ 2 °C (a room is more stable than outdoors).
- `weather(t)` is a **mean-reverting random walk** (Ornstein–Uhlenbeck): it wanders slowly but is pulled back to 0, so the temperature never drifts away.
  `weather = weather + θ·(0 − weather)·dt + σ·√dt·N(0,1)`, with a long time constant (hours).
- `noise` = small Gaussian (σ ≈ 0.05–0.1 °C) so the curve is not perfectly smooth.

### Humidity

Warmer air with the same moisture means lower relative humidity, so humidity moves **opposite** to temperature:

```
H(t) = base_h − k * (T(t) − base) + weather_h(t) + noise      # k ≈ 2 %/°C, clipped to [0, 100]
```

In the formula, `T(t) − base` means **only the daily cycle of temperature** (`amplitude * sin(...)`), not the random drift or noise of the temperature channel. Every channel stays an independent generator, so interleaving channels never changes any sequence.

### Pressure

Slow changes plus a tiny twice-a-day wave:

```
P(t) = base_p + 0.5 * sin( 2π * hour(t) / 12 ) + weather_p(t) + noise     # base_p ≈ 1013 hPa
```

### Rules

- **Deterministic:** same `seed` → same sequence (given the same time steps). Each sensor has its own private `random.Random`.
- **Values stay physical:** humidity in [0, 100], pressure ≥ 0, no `NaN`/`inf`.
- **No sleeping inside the generator.** Timing stays in the scheduler (`wait_until`).
- **Time is injectable** (`now=` parameter) so tests can feed a fake clock and check the daily shape.
- **Demo mode:** optional `time_scale` (e.g. 144 means 24 simulated hours in 10 real minutes), so the team can see a "full day" without waiting. The stored timestamp stays the real UTC time; only the model phase is accelerated. The real 24h run uses `time_scale = 1`.

### Configuration (sensor entry)

```json
{
  "room": "laboratory", "sensor_id": "station-01", "metric": "temperature",
  "interval_seconds": 5.0, "mean": 21.0, "noise_std": 0.08, "seed": 42,
  "model": "realistic",
  "daily_amplitude": 2.0, "peak_hour_utc": 15, "time_scale": 1
}
```

`model` is optional; without it the old Gaussian generator is used, so all current tests keep working. `run_configuration.validate_simulation` checks exact keys, so the new optional keys must be added there.

---

## 5. The "API": contracts between the tasks

There is no HTTP API. The tasks talk to each other through **Python modules**. This section is the contract. If you need to change a signature, tell the owner of the other side first.

| Contract | Provider → consumer |
|---|---|
| 5.2 `store.py` | **H4 → H5** (reads from the database) |
| 5.3 `trend_analysis.py` (+ existing `analysis.py`) | **H4 → H5** (and used inside `store.py`) |
| 5.4 `dashboard_helpers.py` | **H5** (pure functions, tested on their own) |
| 5.5 `seed_demo_db.py` | **H4 → H5** (fake data so H5 can start immediately) |
| 5.5b `mock_store.py` | **H5** (fallback if `store.py` is not ready) |
| 5.6 `db.py`, `SqliteSink` | H1 / H2 (writer side) |

### 5.1 Conventions (everyone)

- **Series identity** is always a dict: `{"room": "laboratory", "sensor_id": "station-01", "metric": "temperature"}`.
- **Times** are timezone-aware `datetime` objects in UTC. Never naive datetimes, never strings (only `store.py` converts to and from the database).
- **Ranges** are half-open: `start` is included, `end` is excluded.
- **Undefined numbers** are `None`, never `0` and never `NaN`.
- **Calibration** is `scale` and `offset`; the displayed value is `value_raw * scale + offset`. `scale` must be greater than 0.
- **Errors** raised by `store.py` (H5 catches `StoreError` only):

```python
class StoreError(Exception): ...
class SeriesNotFound(StoreError): ...      # the series has no rows in the database
class InvalidQuery(StoreError): ...        # start >= end, unknown bucket, scale <= 0, too many points
class DatabaseUnavailable(StoreError): ... # file missing, locked for too long, corrupt
```

- **Types** used below:

```python
Series  = dict   # {"room": str, "sensor_id": str, "metric": str}
Point   = dict   # raw:      {"time": datetime, "value": float}
                 # bucketed: {"time": datetime, "value": float, "min": float, "max": float, "count": int}
```

### 5.2 `store.py` — H4 provides, H5 uses

All functions take an open read-only connection (`conn`) as the first argument and contain **all the SQL** of the project.

```python
BUCKETS = {"raw": None, "10s": 10, "1m": 60, "5m": 300, "15m": 900, "1h": 3600}   # name -> seconds

list_series(conn) -> list[dict]
get_latest(conn, series, scale=1.0, offset=0.0) -> Point | None
get_readings(conn, series, start, end, bucket="raw", scale=1.0, offset=0.0, limit=5000) -> list[Point]
get_summary(conn, series, start, end, scale=1.0, offset=0.0) -> dict
get_quality(conn, series, start, end, expected_interval_seconds) -> dict
get_health(conn, now=None) -> dict
```

#### `list_series(conn)`

Every series that has at least one row, sorted by `(room, sensor_id, metric)`. Empty database → `[]`.

```python
[{"room": "laboratory", "sensor_id": "station-01", "metric": "temperature", "unit": "C",
  "count": 17280, "first_time": datetime(...), "last_time": datetime(...)}]
```

#### `get_latest(conn, series, scale, offset)`

The most recent point of the series (calibrated), or `None` if the series has no rows. Used for the "Latest value" card. It does not depend on the selected time range.

```python
{"time": datetime(2026, 11, 21, 14, 5, tzinfo=utc), "value": 21.43}
```

#### `get_readings(conn, series, start, end, bucket, scale, offset, limit)`

Points in `[start, end)`, **ascending by time**.

- `bucket="raw"` → one point per reading, only `time` and `value`.
- Any other bucket → one point per non-empty bucket. `time` is the **start** of the bucket, `value` is the average, plus `min`, `max`, `count`. Empty buckets are **omitted**, not filled with zeros (so gaps stay visible).
- Calibration is applied to `value`, `min` and `max`.
- If the result would have more than `limit` points → `InvalidQuery` (H5 must choose a bigger bucket, see `choose_bucket`).
- Unknown series → `SeriesNotFound`. Known series, nothing in the range → `[]`.

```python
get_readings(conn, S, start, end, bucket="5m")
# [{"time": datetime(2026,11,21,14,0,tzinfo=utc), "value": 21.43, "min": 21.30, "max": 21.58, "count": 60}, ...]
```

#### `get_summary(conn, series, start, end, scale, offset)`

Statistics of all readings in `[start, end)` (always from raw readings, not from buckets).

```python
{"count": 17280, "mean": 21.2, "minimum": 18.9, "maximum": 23.4,
 "median": 21.1, "sample_sd": 1.3, "slope_per_minute": 0.0021}
```

- Empty range → `count: 0` and all other values `None`. One reading → `sample_sd` and `slope_per_minute` are `None`.
- `slope_per_minute` is the least-squares trend on **real timestamps** (from `analysis.linear_trend`). It describes this range only; it is not a forecast.
- Unknown series → `SeriesNotFound`.

#### `get_quality(conn, series, start, end, expected_interval_seconds)`

Did we collect what we should have?

```python
{"expected_count": 17280, "actual_count": 17251, "coverage": 0.9983,
 "gaps": [{"from": datetime(...), "to": datetime(...), "missing_approx": 6}],
 "duplicates": 0}
```

- `expected_count = floor((end - start) / interval)`; `coverage = actual / expected` (`None` if expected is 0, can be above 1).
- A **gap** is a pause between two consecutive readings longer than `3 * interval`. `missing_approx = round(pause / interval) - 1`.
- `duplicates` = number of readings with exactly the same `ts_ms` as the previous one.
- `interval <= 0` → `InvalidQuery`.

#### `get_health(conn, now=None)`

```python
{"database": "ok", "total_readings": 48213,
 "last_reading_time": datetime(...), "last_reading_age_seconds": 3.2}
```

Empty database → `total_readings: 0`, `last_reading_time: None`, `last_reading_age_seconds: None`. `now` is injectable for tests (default: current UTC time). If the file cannot be read → `DatabaseUnavailable`.

### 5.3 `trend_analysis.py` — H4 provides (pure functions)

No database, no Streamlit, no clock. Input is validated: non-finite numbers (`NaN`, `inf`, booleans) raise `ValueError`.

**Important:** the project already has an `analysis.py` (used by `processing.py`, `streaming.py`, `run_finite.py` and several tests). **Do not edit or replace it.** The new functions go into a **new file `trend_analysis.py`** (same name as in lab07). `extended_summary` already exists in `analysis.py`: import it, do not rewrite it.

```python
moving_average(values: list[float], samples: int) -> list[float]
# Trailing mean, one output per input, partial windows at the start.
# [10, 20, 30, 40], samples=3  ->  [10, 15, 20, 30]      samples < 1 -> ValueError

linear_trend(points: list[dict]) -> dict
# points: [{"time": datetime, "value": float}, ...]  (ascending)
# -> {"slope_per_minute": float|None, "value_at_start": float|None, "fitted_values": list[float|None]}
# Least squares on elapsed minutes. Fewer than 2 distinct times -> None slope and a list of None.

# --- already exists in analysis.py, reuse it: ---
# from analysis import extended_summary
# extended_summary(values: list[float]) -> {"count", "mean", "minimum", "maximum", "median", "sample_sd"}
# Empty -> count 0 and None for the rest. One value -> sample_sd is None.
```

The ideas for the two new functions come from `lab07/trend_analysis.py`.

### 5.4 `dashboard_helpers.py` — H5 provides (pure functions)

Everything that can be written without Streamlit goes here, so it can be unit-tested. Streamlit code only calls these.

```python
RANGE_CHOICES = {"Last 1 hour": 1, "Last 6 hours": 6, "Last 24 hours": 24}   # name -> hours (plus "Custom")

range_for_choice(choice: str, now: datetime) -> tuple[datetime, datetime]
# (now - hours, now). Unknown choice -> ValueError.

choose_bucket(start: datetime, end: datetime, max_points: int = 1000) -> str
# Range <= 15 minutes -> "raw".
# Otherwise the smallest bucket from ["10s","1m","5m","15m","1h"] that gives <= max_points buckets;
# if none fits -> "1h".
# 1 h -> "10s" (360)   6 h -> "1m" (360)   24 h -> "5m" (288)

format_number(value: float | None, digits: int = 2, unit: str = "") -> str
# None -> "—";  21.4321, 2, "C" -> "21.43 C"

build_chart_columns(points: list[Point], moving_average_samples: int | None, show_trend: bool) -> dict
# Equal-length columns for st.line_chart:
#   "Time (UTC)", "Measurement"                       always
#   "Moving average"                                  if moving_average_samples is not None (uses analysis.moving_average)
#   "Linear trend"                                    if show_trend (uses analysis.linear_trend)
# Empty points -> all columns are empty lists.

points_to_csv(series: Series, unit: str, points: list[Point]) -> str
# Header: time,room,sensor_id,metric,unit,value   (ISO 8601 times, one row per point)

freshness(health: dict, now: datetime, stale_after_seconds: float = 30.0) -> tuple[str, str]
# -> (level, message); level is one of "success", "info", "warning", "error"
#   no rows yet        -> ("info",    "Waiting for the first reading.")
#   age <= stale_after -> ("success", "Recent reading: 3.2 s old.")
#   age >  stale_after -> ("warning", "Stale data: no reading for 95 s. Is the collector running?")
#   age < -2 s         -> ("warning", "Timestamp is in the future. Check the clocks.")
```

#### How the Streamlit page must use `store.py`

- **Backend switch:** `dashboard.py` picks the module with `STORE_BACKEND` (`sqlite` = `store.py`, the default; `mock` = `mock_store.py`, see 5.5b). Both have the same functions.
- **Connection:** open once with `@st.cache_resource` → `db.connect_readonly(os.environ["DB_PATH"])` (not needed for the mock backend).
- **Queries:** wrap each `store.*` call in `@st.cache_data(ttl=REFRESH_SECONDS)`. Pass only hashable arguments (a series as a tuple `(room, sensor_id, metric)`, datetimes, numbers). Round `end` down to the refresh interval, otherwise every rerun gets a new cache key.
- **Errors:** catch `StoreError` around every call. On failure keep the last good view in `st.session_state` and show a warning; for `SeriesNotFound` show "no data for this series".
- **Never** import the generator or the collector, and never write to the database.
- **Environment variables:** `DB_PATH` (default `/data/sensors.db`), `REFRESH_SECONDS` (default `5`), `STALE_AFTER_SECONDS` (default `30`).

#### Page layout (what H5 builds)

1. Sidebar: series selector (from `list_series`), range choice, calibration `scale`/`offset`, moving-average samples, show-trend checkbox, refresh interval, pause button.
2. Health banner (from `get_health` + `freshness`).
3. Cards: latest value (`get_latest`), mean, min/max, count, slope per minute (`get_summary`).
4. Line chart (`get_readings` + `choose_bucket` + `build_chart_columns`), time on the x-axis, unit in the y-axis label.
5. Expander "Data quality" (`get_quality`) and a "Download CSV" button (`points_to_csv`).

### 5.5 `seed_demo_db.py` — H4 provides, so H5 can start immediately

```python
seed_demo_db(path, hours=24, interval_seconds=5.0, end=None, seed=1) -> None
# Creates (or replaces) a SQLite file with the real schema and a deterministic fake day of data for
# 2 series: laboratory/station-01/temperature and laboratory/station-01/humidity.
# Includes one deliberate gap of about 10 minutes, so the quality view has something to show.
```

Location: `seed_demo_db.py` in the project folder (also runnable as `python seed_demo_db.py demo.db`). H5 runs the dashboard against this file with `DB_PATH=demo.db` until the collector works.

### 5.5b `mock_store.py` — H5 provides (plan B if SQLite is not ready)

If `store.py` or `seed_demo_db.py` is late, or the team decides to drop SQLite, the dashboard must still be buildable and demonstrable. `mock_store.py` has **exactly the same function names, arguments, return shapes and errors as section 5.2**, but it needs no database file:

- Data is generated in memory, deterministically, from a fixed seed: a daily sine for temperature, an opposite curve for humidity, small noise, one gap of 10 minutes. It reuses `trend_analysis` and `analysis` for the maths.
- `list_series` returns two series; any other series → `SeriesNotFound`.
- `get_health` reports a last reading a few seconds ago, so the banner shows "live".
- Switch: `STORE_BACKEND=mock streamlit run dashboard.py`.

To stop the mock from drifting away from the real `store.py`, H4's test file contains one **contract test** that runs the same checks (shape of every return value, error types) against both modules.

If SQLite is dropped completely, only `store.py` and the writer (`sqlite_sink.py`, `db.py`) are replaced (for example by files: the existing `raw.jsonl` + `latest.json` flow from lab07). The dashboard and its helpers do not change, because they only talk to the section 5.2 functions.

### 5.6 Writer side — H1 and H2 (`db.py`, `sqlite_sink.py`)

```python
# db.py (H1)
connect_writer(path)   -> sqlite3.Connection   # creates the schema if missing; WAL; busy_timeout=5000
connect_readonly(path) -> sqlite3.Connection   # opened with mode=ro; WAL; busy_timeout=5000

# collector sink (H2)
class SqliteSink:
    def __init__(self, path, batch_size=50, flush_seconds=2.0): ...
    def write(self, reading: dict) -> None     # buffers; flushes by size or time
    def flush(self) -> None                    # executemany + commit
    def close(self) -> None                    # flush, then close
```

A `reading` is the existing record dict (`time`, `room`, `sensor_id`, `metric`, `value`, `unit`). The sink stores `value` as `value_raw`, parses `time` with `datetime.fromisoformat`, stores it normalised to UTC (`isoformat()`), and derives `ts_ms = int(dt.timestamp() * 1000)`.

---

## 6. Running with Docker

```bash
cp .env.example .env
docker compose up --build         # start everything
docker compose logs -f collector  # watch the collector
docker compose stop               # stop (data stays)
docker compose down -v            # stop AND delete all data
```

| What | Where |
|---|---|
| Dashboard | http://localhost:8501 (host port can be changed with `DASHBOARD_PORT` in `.env`, e.g. 8502 if 8501 is busy) |
| Database file | Docker volume `dbdata`, path `/data/sensors.db` inside the containers |
| Raw backup | `./output/` on the host |

Sketch of `docker-compose.yml`:

```yaml
services:
  collector:
    build: {context: ., dockerfile: Dockerfile.collector}
    command: python run.py config/simulation_24h.json
    env_file: .env                      # DB_PATH=/data/sensors.db
    volumes: [dbdata:/data, ./output:/app/output]
    restart: unless-stopped
    stop_grace_period: 15s              # time to flush on SIGTERM
  dashboard:
    build: {context: ., dockerfile: Dockerfile.dashboard}
    env_file: .env
    volumes: [dbdata:/data]             # NOT :ro, see the note below
    ports: ["${DASHBOARD_PORT:-8501}:8501"]
    depends_on: [collector]
    healthcheck: {test: ["CMD", "curl", "-f", "http://localhost:8501/_stcore/health"], interval: 10s}
    restart: unless-stopped
volumes: {dbdata: {}}
```

Note: the dashboard container mounts the volume **without** `:ro`. A SQLite database in WAL mode needs the readers to be able to touch the `-shm` file, so a read-only mount makes the dashboard fail to open it. Read-only access is enforced inside the code instead (`connect_readonly`, `mode=ro`).

To get the database file out for the report: `docker compose cp collector:/data/sensors.db ./sensors_backup.db`.

For the 24h run: use a computer that will not go to sleep, keep Docker running, and save logs and row counts at the end.

---

## 7. Project layout and integration agreements

**We do not move or rename any existing file.** The project stays flat, exactly as it is now. New files are added next to the old ones. Branches only conflict where two people edit the same file, so section 7.2 says who may touch which file.

### 7.1 Layout (existing files stay where they are)

```
EXISTING (unchanged location)           NEW FILES                                  OWNER
simulation.py, streaming.py,            db.py, schema.sql                          H1
recording.py, records.py,               Dockerfile.collector, Dockerfile.dashboard,
run.py, run_stream.py,                  docker-compose.yml, .env.example,
run_configuration.py, analysis.py,      .dockerignore, requirements-dashboard.txt,
configuration.py, ...                   config/simulation_24h.json                 H1
config/  checks/  docs/  data/          sqlite_sink.py                             H2
                                        realistic_model.py,
                                        config/simulation_realistic.json           H3
                                        store.py, trend_analysis.py,
                                        seed_demo_db.py                            H4
                                        dashboard.py, dashboard_helpers.py,
                                        mock_store.py                              H5
                                        checks/test_h1_infra.py ... test_h5_dashboard.py   each owner
```

Note: `store.py` (database reads) is different from the old `storage.py` (CSV/JSON writers). `trend_analysis.py` is new; the old `analysis.py` is **not** replaced.

### 7.2 Who touches which existing file

| Existing file | Who may edit | What exactly |
|---|---|---|
| `simulation.py` | **H2 first, then H3** | H2 merges `feature/G2` (`wait_until`) **first**, before anyone else edits the file, and does not touch it again. After that merge, H3 edits `sensor_values` and the call in `simulate_sensors` (section 7.3). Nobody else. |
| `run_configuration.py` | **H3 only** | Allow the optional sensor keys of the realistic model in `validate_simulation` (section 7.3). |
| `run_stream.py` | **H2 only** | Write each raw reading to the SQLite sink as well (section 7.4). |
| `run.py` | **H2 only** | Turn SIGTERM into a clean stop (section 7.4). |
| `recording.py`, `records.py`, `streaming.py`, `configuration.py`, `analysis.py`, `processing.py`, `storage.py`, `readers.py`, ... | **nobody** | Used as they are. If you think one must change, ask in the group first. |
| `config/` | H1 adds `simulation_24h.json`, H3 adds `simulation_realistic.json` | Existing config files are not edited. |
| `checks/` | each owner adds their own `test_hN_*.py` | Existing check files are not edited. |
| `docs/07_DASHBOARD_VIZUALIZATION.md` | anyone, **only for agreed changes** | Sections 3, 5 and 7 are the contract. |

New files are edited only by the owner in the table 7.1.

### 7.3 Generator interface (H3 ↔ H2)

The realistic model needs the time of day, but today `sensor_values(sensor)` has no time. Agreed change in `simulation.py`:

```python
def sensor_values(sensor: dict, now: Callable[[], datetime] = utc_now) -> Iterator[float]: ...
# - sensor without "model" (or model != "realistic"): old Gaussian behaviour, `now` is ignored.
# - sensor with "model": "realistic": values come from realistic_model.py.

# simulate_sensors(...) passes its own `now` into every sensor_values(sensor, now).
```

```python
# realistic_model.py (H3)
class RealisticModel:
    def __init__(self, sensor: dict): ...          # reads mean, noise_std, seed, daily_amplitude, ...
    def value(self, when: datetime) -> float: ...  # next value for the model time `when`
```

- **Model time:** `model_time = first_call_time + (when - first_call_time) * time_scale`. With `time_scale = 1` this is real time.
- **Sensor keys:** the 7 existing keys stay required. Optional keys, allowed **only** with `"model": "realistic"`: `model`, `daily_amplitude` (default 2.0), `peak_hour_utc` (default 15), `time_scale` (default 1). Unknown keys are still rejected.
- All existing tests (G1–G6 and the old ones) must keep passing without changes.

### 7.4 Collector wiring (H2)

To avoid changing the configuration schema, **the database is enabled by the environment variable `DB_PATH`**:

- `DB_PATH` set → `run_simulation` also writes every raw reading to `SqliteSink(DB_PATH)` (right after `append_reading`, before selection). `raw.jsonl` is still written.
- `DB_PATH` not set → behaviour is exactly as today (so old checks and offline runs are unaffected).
- Sink closed in the existing `finally` block, so the buffer is flushed on Ctrl+C and on SIGTERM.
- `run.py` installs a `SIGTERM` handler that raises `KeyboardInterrupt`, so `docker stop` takes the same clean path as Ctrl+C.
- If the database stays unavailable after retries (about 30 s of back-off), the sink raises, the run ends with status `failed` and a non-zero exit, and Docker restarts the container. No silent loss.

### 7.5 Ports and the 24h run

- **One published port:** the dashboard on `8501` (change the host side with `DASHBOARD_PORT` in `.env`). There is no other port: the database is a file and there is no API.
- **The 24h run is owned by H1 (Arseni).** H1 creates `config/simulation_24h.json`: 4 channels (laboratory temperature 5 s, humidity 10 s, pressure 30 s, office temperature 10 s, about 37 000 rows per day), `max_readings: null`, and the realistic model once H3 is merged. The real run starts only after the full stack works end to end.

### 7.6 Tests: same way as the existing checks

We write tests exactly like the existing ones in `checks/`:

- `unittest` only (no extra test framework), files named `checks/test_h1_infra.py`, `test_h2_collector.py`, `test_h3_generator.py`, `test_h4_store.py`, `test_h5_dashboard.py`.
- Each test method contains the task label, for example `test_H4_get_readings_bucket_edges`, so `-k H4` works.
- **Tests exist before the implementation.** At the very start every owner commits the function stubs (raising `NotImplementedError("H4: implement get_summary")`) together with their tests. A test that hits `NotImplementedError` is **skipped, not passed**, using the same small `exercise` decorator that `checks/test_generator_extension.py` already has (copy it into your file). Goal at the end: zero skips.
- Run only your tasks, or everything:

```bash
python -m unittest discover -s checks -p "test_h*.py" -v      # all H tasks
python -m unittest discover -s checks -p "test_h4_store.py" -v  # one task
python -m unittest discover -s checks -p "*.py"                 # everything, old checks too
```

- Tests use temporary or in-memory SQLite files and fake clocks. No test may need Docker, a running collector or the network, except the single smoke test of H1 (it is skipped if Docker is not available).

### 7.7 What is not verified yet

All contracts in this document are agreed on paper. They are verified for the first time the first time the full stack runs end to end (`docker compose up`). If something does not fit, the consumer proposes the change, we update this document **first**, then the code.

Git: one branch per task (`feature/H1` … `feature/H5`), pull request to `main`, reviewed by one other person.

---

## 8. Tasks H1–H5

**Team:** Albert Ka, Arseni Fayeu, Damian Jamski, Robert Jarosz, Tobiasz Kapera.

Pick one of the free tasks. Write your name next to it.

| Task | Area | Owner |
|---|---|---|
| **H1** | Docker + Database | Arseni Fayeu |
| **H2** | Collector | Albert Ka |
| **H3** | Realistic generator + 24h report | Robert Jarosz |
| **H4** | Data access + analysis | Tobiasz Kapera |
| **H5** | Streamlit dashboard | Damian Jamski |

### H1 — Docker + Database

**Delivers**
- `schema.sql` with the table and index from section 3.
- `db.py` (`connect_writer`, `connect_readonly`) with WAL and busy timeout, schema creation on first start.
- `Dockerfile.collector`, `Dockerfile.dashboard`, `docker-compose.yml`, `.env.example`, `.dockerignore`, `requirements-dashboard.txt` (Streamlit), named volume `dbdata`, restart policy, healthcheck, `DASHBOARD_PORT`.
- `config/simulation_24h.json` (section 7.5).
- **First:** `db.py` and `schema.sql`, so H2 and H4 can use them.
- Runbook (section 6) kept up to date. One-command start from a fresh clone.
- Starts, watches and documents the **24h run (H1 runs it personally)** (row counts at start and end, logs, container restarts, backup of `sensors.db`).

**Tests**
- Schema test: columns exist, the `metric` CHECK rejects a bad value, the index exists.
- WAL test: one connection writes in a loop while another reads; no "database is locked" error.
- Read-only test: the dashboard connection cannot write.
- Persistence: data is still there after `docker compose restart`.
- Smoke test: `compose up`, wait until the dashboard health endpoint is OK, `compose down` (skipped when Docker is not available).

**Done when:** a teammate on another computer runs the stack with three commands and sees data.

### H2 — Collector

**Delivers**
- Merge `feature/G2` (`wait_until`) so the simulator can run on `main`.
- `sqlite_sink.py` with `SqliteSink` (batched inserts, section 5.6). The JSONL side stays the existing `append_reading`.
- Wiring in `run_stream.py` and the SIGTERM handler in `run.py` (section 7.4). **No other existing file.**
- Retry when the database is busy or locked; no crash and no silent loss (keep the buffer, retry, log).
- Clean shutdown on SIGTERM: flush the buffer, close files.
- Run all configured channels; read `DB_PATH` from the environment.
- Heartbeat log line every minute (readings written so far).

**Tests**
- Batching by size and by time with an in-memory SQLite database.
- Simulated "database is locked" then recovery: all readings arrive, in order.
- SIGTERM flushes the buffer.
- Existing G1–G6 tests still pass.

**Done when:** the collector runs 10 minutes in Docker, row counts per channel match the intervals, and nothing is lost on `docker compose stop`.

### H3 — Realistic generator + 24h report

**Delivers**
- `realistic_model.py` and `model: "realistic"` for temperature, humidity and pressure (section 4), plugged into `sensor_values` with the signature from section 7.3. The old behaviour is unchanged when `model` is absent.
- Config validation for the new optional keys in `run_configuration.py` (the only person allowed to edit it).
- `config/simulation_realistic.json` as an example.
- `time_scale` demo mode.
- After the 24h run: the data-quality analysis (using `get_quality` from H4), plots, and the written report.

**Tests**
- Same seed → same sequence; different seeds differ; `model` absent → identical to the old generator.
- With a fake clock over 24 h: the temperature minimum is near 03:00 and the maximum near 15:00; the amplitude is within tolerance.
- Humidity correlates negatively with temperature and stays within [0, 100].
- Pressure stays in a plausible band; no `NaN`/`inf` over 1 million steps.
- Interleaving two sensors does not change either sequence.

**Done when:** a 24-hour plot from the generator clearly shows a daily cycle with believable small wiggles.

### H4 — Data access + analysis

**Delivers**
- `store.py` with every function and error class from section 5.2 (`list_series`, `get_latest`, `get_readings`, `get_summary`, `get_quality`, `get_health`), including bucketed queries and gap detection.
- `trend_analysis.py` as in section 5.3: `moving_average`, `linear_trend`. `extended_summary` is reused from the existing `analysis.py` (do not edit that file).
- Calibration applied on read (`scale`, `offset`).
- Parameter validation that raises `InvalidQuery` (unknown bucket, `start >= end`, `scale <= 0`, too many points).
- **`seed_demo_db.py` (section 5.5) in the first days**, so H5 can work before the collector exists.

**Tests**
- Pure functions: moving-average warm-up, trend with irregular timestamps, fewer than 2 points → `None`, empty and single-point summary, non-finite input rejected.
- `store` against an in-memory SQLite database: empty table, one point, half-open range edges, bucket edges (empty buckets omitted), unknown series (`SeriesNotFound`), calibration math, `limit` exceeded, gap detection on data with known gaps, `get_health` on an empty database.
- `seed_demo_db` is deterministic: the same arguments give identical rows.
- Contract test: the shape of every `store.py` return value and error is also checked against `mock_store.py` (section 5.5b).

**Done when:** every example in section 5.2 and 5.3 is covered by a passing test, and H5 can build the whole dashboard using only these two modules.

### H5 — Streamlit dashboard

**Delivers**
- `dashboard_helpers.py` with the pure functions from section 5.4 (`range_for_choice`, `choose_bucket`, `format_number`, `build_chart_columns`, `points_to_csv`, `freshness`).
- `dashboard.py`: Streamlit app that reads only through `store.py` (read-only connection), following the caching and error rules in section 5.4.
- `mock_store.py` (section 5.5b), switchable with `STORE_BACKEND=mock`.
- Series selector and time range: last 1 h, 6 h, 24 h, custom.
- Automatic bucket size so a chart never draws more than about 1000 points.
- Chart with time on the x-axis and the unit in the label; optional moving average and trend line.
- Stat cards: latest value, mean, min/max, count, trend slope.
- Status banner from `get_health()` (live, stale, no data). On a read error keep the last good view and say so.
- Refresh interval and pause button (`st.fragment(run_every=...)`); CSV download button.
- Stretch: overview of all series on one page; coverage and gaps view from `get_quality`.

**Tests**
- Pure helper functions, using the examples from section 5.4: `choose_bucket` (1 h → `10s`, 6 h → `1m`, 24 h → `5m`, 10 min → `raw`), `format_number` (`None` → "—"), `build_chart_columns` (equal lengths, empty input), `points_to_csv`, `freshness` (all four cases).
- Mocked `store` for empty data, `SeriesNotFound`, `DatabaseUnavailable` and success cases (the last good view is kept on error).
- Streamlit `AppTest` smoke test if time allows.

**Done when:** the dashboard works against `demo.db` from `seed_demo_db`, and with the full stack running it shows live data, survives a collector restart, and can display the whole 24h history.

---

## 9. Definition of done

- Merged to `main` through a reviewed pull request.
- Your own tests exist and pass locally and in the container.
- Your folder has a short README (how to run, which environment variables).
- Anything you changed in sections 3 or 5 was agreed with the team first.
