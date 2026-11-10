# Room sensors — from finite files to paced generators

**For this meeting:** use [Start Here](docs/01_START_HERE.md) and [Solutions](GENERATOR_SOLUTIONS.md) together. The longer guides are optional.

**Edition: BACKBONE.** The earlier finite tasks are already solved.
Six new G1–G6 function bodies are left for you to implement. File mode works now;
simulation becomes runnable after G1, G2, G4, G5 and G6 are complete.
This folder extends the latest `room_sensor_solved` solution; it does not replace
it with a web application. You still run ordinary Python files from a folder.

You will now process measurements that arrive over time rather than as a complete
list. You can choose a file or simulated sensors in JSON. The simulator records
every acquired measurement for offline analysis, while a small rolling window
prepares the selected series for a later visualisation step.


## Start with what you already know

Extract this folder beside your previous work. In a terminal inside this folder:

```bash
python --version
python run.py
```

The default still uses the previous `config/example.json` and processes a finite
file. `python run_finite.py` also still works. You can now make the mode explicit:

```bash
python run.py config/files.json
```

## Try the new stage

```bash
# Ten readings, 0.2 seconds apart: a small, genuinely paced demonstration.
python run.py config/simulation_quick.json

# Ten readings, 5 seconds apart: the first at about 5 s, the tenth at about 50 s.
python run.py config/simulation_10_readings.json

# Several measurement channels; keep collecting until you press Ctrl+C.
python run.py config/simulation_continuous.json
```

The scheduler does not emit at time zero. A five-second interval therefore means
roughly fifty seconds to collect ten measurements from one sensor. This is
ordinary OS-paced execution, not a hard-real-time guarantee; processing and
scheduling may make a run longer. The quick config actually changes the interval;
it does not invent timestamps or bypass sleeping.

## What you configure

`mode` is `files` or `simulation`. Each simulated channel has `room`, `sensor_id`,
`metric`, `interval_seconds`, `mean`, `noise_std`, and `seed`. Supported metric/unit
pairs are `temperature`/`C`, `pressure`/`hPa`, and `humidity`/`%`, exactly as in the
previous record contract. A station can have several channels with different
intervals. `max_readings: null` runs without a count limit; a positive integer
limits the TOTAL raw records across all channels, before selection.

`selection` still identifies one series. Its `calibration` applies only to that
series. All raw readings, including unselected humidity/pressure/other rooms, are
archived before any calibration. `stream.window_size` bounds the number of
selected observations retained for the live summary.

## What a run creates

Each simulation prints a unique directory under `output/sessions/`:

```text
<unique-session>/
    raw.jsonl             All recorded RAW measurements, one object per line
    session.json          Configuration, timing, counts, and final run status
    latest.json           Selected, calibrated rolling window and its statistics
    offline_config.json   Ready-to-run config for analysing this archive later
```

After stopping, copy the offline-analysis command printed by your run:

```text
python run.py "<actual-session-directory>/offline_config.json"
```

This creates `offline/calibrated.csv` and `offline/summary.json` inside that session.
It does not replace the raw recording. The offline summary uses the entire finite
recording; the live summary uses only the most recent window. They need not match.

## Two handouts for this session

Use these side by side; you do not need to read every guide first.

- [Start here](docs/01_START_HERE.md): your six tasks, settings, commands, and expected results.
- [Solutions — G1–G6](GENERATOR_SOLUTIONS.md): short explanations and checks for each task.

The remaining guides in `docs/` are **optional reference** for extra detail on
pacing, configuration, recording, visualisation, and edge cases. Earlier
assignment guides and `SOLUTIONS.md` concern the preceding finite-data stage.
`PREVIOUS_GENERATOR_PLAN.md` is historical, not this iteration's task list.

## Your main working files

Only three modules contain new student tasks: `simulation.py` (G1, G2),
`streaming.py` (G3, G4, G5), and `recording.py` (G6). The scheduler and orchestration
are worked infrastructure so that you can concentrate on small functions first.

`run.py` chooses the mode. `file_workflow.py` contains the earlier finite workflow.
`run_configuration.py` validates the new settings while reusing the original
configuration service. `run_stream.py` connects acquisition, recording, processing,
and finite snapshots. It is intentionally an ordinary visible loop, not a service
framework.

## Check your work

```bash
# Earlier checks plus the new generator checks:
python -m unittest discover -s checks -p "*.py" -v

# Only this iteration:
python -m unittest discover -s checks -p "test_generator_extension.py" -v
```

In the student edition, unimplemented G tasks are reported as **skipped**, not
passed. Other failures remain failures. The reference edition must have no skipped
tasks. Most timing checks use an explicitly injected fake clock; application runs
always use real clocks and real waits.

## Boundaries to keep visible

A generator advances only when consumed; it is not an independently running
hardware sensor. Slow downstream work can delay acquisition. This stage skips
missed time slots instead of generating fake catch-up measurements. Memory is
bounded during streaming, but the raw file and operational log can grow without
limit. Ordinary flushing is not a guarantee against power failure. Details and
verified limitations are in the guides and `VALIDATION.md`.
