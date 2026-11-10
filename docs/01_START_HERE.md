# Start here — sensors that produce data over time

**Handout 1 of 2 · Your working guide**

Keep **Solutions — G1–G6** beside this sheet. Work on one function, compare the
explanation, then run its checks. Both handouts are for this session; the longer
guides are optional reference.

## 1. What you are building

Extend your existing program with sensors that yield measurements over time:

```text
simulate → save every raw reading → select one series → calibrate
         → keep a small rolling window → calculate its statistics
```

The archive keeps **all channels, before calibration**. The window prepares data
for a future plot; you are not building the plot yet.

Open a terminal inside the project folder and confirm the previous workflow works:

```bash
python run.py
```

No installation or packaging changes are needed.

## 2. Your six functions

Earlier assignments are solved. Implement only the labelled G1–G6 placeholders.
The scheduler, configuration handling, and application assembly are supplied.

| Task | Where you work | What your function does |
|---|---|---|
| G1 | `simulation.py`: `sensor_values` | Yield seeded, noisy values indefinitely; do not sleep here. |
| G2 | `simulation.py`: `wait_until` | Sleep until the next deadline; do not spin in a waiting loop. |
| G3 | `streaming.py`: `iter_jsonl` | Read a finished recording one validated record at a time. |
| G4 | `streaming.py`: `select_calibrated` | Select one room/sensor/metric and yield corrected copies. |
| G5 | `streaming.py`: `rolling_windows` | Yield independent snapshots, retaining at most the configured window size. |
| G6 | `recording.py`: `append_reading` | Write one JSON line and flush it immediately. |

Use short finite inputs to test transformations. Never call `list()` on an
infinite source. For G1, request a few values with `next()` or `itertools.islice()`.

## 3. Choose the behaviour in JSON

Edit a supplied configuration rather than starting from an empty file.

| Setting | Meaning |
|---|---|
| `mode` | `"files"` or `"simulation"`. |
| `simulation.sensors` | Channels with room, sensor ID, metric, interval, mean, noise, and seed. |
| `simulation.max_readings` | Total raw records across **all** channels; `null` means no count limit. |
| `selection` / `calibration` | The series to monitor and its correction. |
| `stream.window_size` | Maximum selected readings retained for the live summary. |

Use `temperature` (C), `pressure` (hPa), or `humidity` (%).
The **first reading follows the first interval**: one channel with a 5-second
interval takes approximately 50 seconds to produce 10 readings. Processing can
add delays; these are not hard-real-time guarantees.

## 4. Check and run

```bash
python -m unittest discover -s checks -p "test_generator_extension.py" -v
```

Add `-k G1` to focus on G1; change the task label as needed. A **skip means
unfinished**, not passed. Aim for no skips once all six tasks are complete.

Simulation needs G1, G2, G4, G5, and G6. Start with the quick example:

```bash
python run.py config/simulation_quick.json
python run.py config/simulation_10_readings.json
python run.py config/simulation_continuous.json
```

The examples use 0.2-second sampling, 5-second sampling, and continuous multiple
channels respectively. Stop the continuous run with **Ctrl+C**. G3 adds lazy replay
of a finished recording; it does not wait between records.

## 5. Inspect your result

In the printed session folder, inspect `raw.jsonl` (all raw records), `latest.json`
(the selected window and matching statistics), and `session.json` (settings and
run status). Run the **offline-analysis command printed by your program**; it uses
that session's `offline_config.json`.

For the quick example, expect **10 archived readings, 5 points in the final live
window, and 10 selected readings in the offline analysis**. Their means can differ
because the live and offline summaries use different samples.
