"""H1 checks: schema, WAL, read-only access, persistence, 24h config, Docker smoke."""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import db  # noqa: E402

ROW = ("2026-11-21T14:05:00+00:00", 1763733900000, "laboratory", "station-01",
       "temperature", "C", 21.5)
INSERT = ("INSERT INTO readings (time, ts_ms, room, sensor_id, metric, unit, value_raw) "
          "VALUES (?, ?, ?, ?, ?, ?, ?)")


class H1Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp, "sensors.db")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class SchemaTests(H1Base):
    def test_H1_schema_columns_and_index(self):
        conn = db.connect_writer(self.path)
        columns = [r[1] for r in conn.execute("PRAGMA table_info(readings)")]
        self.assertEqual(columns, ["id", "time", "ts_ms", "room", "sensor_id",
                                   "metric", "unit", "value_raw"])
        indexes = [r[1] for r in conn.execute("PRAGMA index_list(readings)")]
        self.assertIn("readings_series_time", indexes)
        conn.close()

    def test_H1_metric_check_rejects_bad_value(self):
        conn = db.connect_writer(self.path)
        bad = ROW[:4] + ("wind", "m/s", 3.0)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(INSERT, bad)
        conn.close()

    def test_H1_schema_creation_is_idempotent(self):
        db.connect_writer(self.path).close()
        conn = db.connect_writer(self.path)
        conn.execute(INSERT, ROW)
        conn.commit()
        conn.close()
        conn = db.connect_writer(self.path)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM readings").fetchone()[0], 1)
        conn.close()

    def test_H1_wal_and_busy_timeout(self):
        conn = db.connect_writer(self.path)
        self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(conn.execute("PRAGMA busy_timeout").fetchone()[0], 5000)
        conn.close()


class AccessTests(H1Base):
    def test_H1_readonly_cannot_write(self):
        db.connect_writer(self.path).close()
        conn = db.connect_readonly(self.path)
        with self.assertRaises(sqlite3.OperationalError):
            conn.execute(INSERT, ROW)
        conn.close()

    def test_H1_readonly_missing_file_fails(self):
        with self.assertRaises(sqlite3.OperationalError):
            db.connect_readonly(os.path.join(self.tmp, "nope.db"))

    def test_H1_wal_reader_while_writer_writes(self):
        writer = db.connect_writer(self.path)
        reader = db.connect_readonly(self.path)
        errors, counts = [], []

        def read_loop():
            try:
                for _ in range(200):
                    counts.append(reader.execute("SELECT COUNT(*) FROM readings").fetchone()[0])
            except sqlite3.OperationalError as error:  # e.g. "database is locked"
                errors.append(error)

        thread = threading.Thread(target=read_loop)
        thread.start()
        for i in range(500):
            writer.execute(INSERT, (ROW[0], ROW[1] + i) + ROW[2:])
            if i % 10 == 0:
                writer.commit()
        writer.commit()
        thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(counts, sorted(counts))  # the reader only ever sees growth
        self.assertEqual(reader.execute("SELECT COUNT(*) FROM readings").fetchone()[0], 500)
        writer.close()
        reader.close()

    def test_H1_data_persists_after_reopen(self):
        conn = db.connect_writer(self.path)
        conn.execute(INSERT, ROW)
        conn.commit()
        conn.close()  # like a container restart: same file, new process
        again = db.connect_readonly(self.path)
        self.assertEqual(again.execute("SELECT value_raw FROM readings").fetchone()[0], 21.5)
        again.close()


class ConfigTests(unittest.TestCase):
    def test_H1_24h_config_is_valid(self):
        from run_configuration import validate_simulation
        config = json.loads((ROOT / "config" / "simulation_24h.json").read_text())
        validate_simulation(config)
        sensors = config["simulation"]["sensors"]
        self.assertEqual([s["interval_seconds"] for s in sensors], [5.0, 10.0, 30.0, 10.0])
        self.assertIsNone(config["simulation"]["max_readings"])
        self.assertEqual(sum(86400 / s["interval_seconds"] for s in sensors), 37440)


class SmokeTests(unittest.TestCase):
    """Opt-in (H1_SMOKE=1): compose up, wait for the dashboard health endpoint, compose down."""

    @unittest.skipUnless(shutil.which("docker") and os.environ.get("H1_SMOKE") == "1"
                         and (ROOT / "dashboard.py").exists(),
                         "needs Docker, dashboard.py and H1_SMOKE=1")
    def test_H1_compose_smoke(self):
        import time
        import urllib.request
        port = os.environ.get("DASHBOARD_PORT", "8501")
        env = {**os.environ, "COMPOSE_PROJECT_NAME": "h1smoke"}
        try:
            subprocess.run(["docker", "compose", "up", "-d", "--build"],
                           cwd=ROOT, env=env, check=True)
            deadline = time.time() + 120
            while True:
                try:
                    urllib.request.urlopen(f"http://localhost:{port}/_stcore/health", timeout=3)
                    break
                except OSError:
                    if time.time() > deadline:
                        self.fail("dashboard health endpoint never became OK")
                    time.sleep(3)
        finally:
            subprocess.run(["docker", "compose", "down", "-v"], cwd=ROOT, env=env)


if __name__ == "__main__":
    unittest.main()
