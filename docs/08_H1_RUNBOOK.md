# 08 — H1 runbook: database, Docker, 24h run

Owner: Arseni Fayeu (H1). Contract: section 3, 6 and 7 of `07_DASHBOARD_VIZUALIZATION.md`.

## Files

| File | Job |
|---|---|
| `schema.sql` | the `readings` table and index (section 3) |
| `db.py` | `connect_writer(path)`, `connect_readonly(path)` (WAL, busy timeout 5000 ms) |
| `config/simulation_24h.json` | 4 channels, 37 440 rows per day, `max_readings: null` |
| `Dockerfile.collector`, `Dockerfile.dashboard`, `docker-compose.yml` | the two containers and the `dbdata` volume |
| `.env.example`, `.dockerignore`, `requirements-dashboard.txt` | settings and image inputs |
| `checks/test_h1_infra.py` | tests |

## Start (three commands)

```bash
cp .env.example .env
docker compose up --build
# open http://localhost:8501
```

The collector needs `sqlite_sink.py` (H2) and the dashboard needs `dashboard.py` (H5) in the image; until both are merged the matching container does not start.

Stop with `docker compose stop` (data stays). `docker compose down -v` deletes the data.

## Tests

```bash
python -m unittest discover -s checks -p "test_h1_infra.py" -v
H1_SMOKE=1 python -m unittest discover -s checks -p "test_h1_infra.py" -v   # also compose up/down (needs dashboard.py)
```

## The real 24 h run (H1 does it personally)

Start only after H2, H3 and H5 are merged and `docker compose up` works. Keep the computer awake.

1. Note the start: time, `docker compose ps`, row count:
   `docker compose exec collector python -c "import sqlite3;print(sqlite3.connect('/data/sensors.db').execute('select count(*) from readings').fetchone())"`
2. During the run: `docker compose logs -f collector`; write down any restart (`docker compose ps`).
3. At the end: the same row count (expected about 37 440), the last lines of the log, and the backup:
   `docker compose cp collector:/data/sensors.db ./sensors_backup.db`

## Known notes

- `config/simulation_24h.json` uses the old Gaussian generator. After H3 is merged, add `model: "realistic"` to the sensors.
- The dashboard healthcheck uses Python instead of `curl` (the slim image has no curl).
