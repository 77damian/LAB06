# 3. Configure your acquisition and run it

You should be able to change a sensor's measurement interval or mean without
editing its implementation. The JSON configuration describes the experiment;
the Python code enforces how those settings are interpreted.

## File mode remains the familiar baseline

`config/files.json` is the earlier finite configuration with one new entry:

```json
"mode": "files"
```

The `input.path` and `input.format` select CSV, JSON, or JSON Lines. Selection,
calibration, outputs, and logging behave as before. The original
`config/example.json`, without a mode field, is accepted as file mode so your
existing exercises and scripts do not break.

File mode reads the whole finite dataset. It does not replay original timestamps
with delays. For large recordings, use the lazy reader from G3 with the bounded
processing functions instead of assuming file mode has bounded memory.

## A complete single-sensor simulation configuration

The following is the supplied `config/simulation_10_readings.json`:

```json
{
  "mode": "simulation",
  "simulation": {
    "max_readings": 10,
    "sensors": [
      {
        "room": "laboratory",
        "sensor_id": "station-01",
        "metric": "temperature",
        "interval_seconds": 5.0,
        "mean": 21.0,
        "noise_std": 0.25,
        "seed": 42
      }
    ]
  },
  "recording": {
    "directory": "../output/sessions",
    "fsync": false
  },
  "stream": {"window_size": 5},
  "selection": {
    "room": "laboratory",
    "sensor_id": "station-01",
    "metric": "temperature"
  },
  "calibration": {"enabled": true, "scale": 1.02, "offset": -0.4},
  "logging": {"level": "INFO", "path": "../output/simulation.log"}
}
```

This configuration actually waits for observations. It does not precompute ten
values and assign them artificial future timestamps. The application limit is
outside the infinite generator, so the same source can be used with or without a
finite demonstration limit.

## Read each setting as an experimental choice

`room`, `sensor_id`, and `metric` identify a series. Two entries may use the same
station ID for different metrics, but duplicate full series identities are an
error. The names are exact, case-sensitive values; use `temperature`, not `temp`.
The unit is selected from the existing contract rather than independently
configured, preventing accidental temperature/pressure unit mismatches.

`interval_seconds` is the nominal period, a positive finite number. A five-second
period corresponds to 0.2 readings per second. We configure the period rather
than accepting both period and frequency, so there is no disagreement to resolve
between two settings. Subsecond periods are allowed; do not expect precise
high-frequency timing from this teaching application.

`mean` and `noise_std` describe the raw simulated quantity in its own units.
`noise_std` must be nonnegative. It describes variability, not a calibration
uncertainty estimate. `seed` must be an integer. Repeating a seed reproduces a
channel's value sequence; real timestamps are intentionally not reproducible.
Give different channels different seeds unless identical noise sequences are
part of your experiment.

`max_readings` is a positive integer or `null`. The integer counts all raw
observations across all configured channels, before selection. It does not mean
N observations per station, N selected points, or N simultaneous batches. Zero
is rejected to avoid an ambiguous special meaning. Use JSON `null` for no count
limit; Python's `None` is not JSON syntax.

`window_size` is the maximum number of selected records used in a live snapshot.
A capacity of five does not delete old records from the raw archive. The
`selection` must match one of your simulated channels; otherwise configuration
validation stops the run before acquisition.

`calibration` retains the previous scale/offset model. Its coefficients belong to
the selected series only. The raw archive is written before this transformation,
so offline analysis can apply a revised calibration later without trying to undo
an earlier correction.

`recording.directory` is a parent directory for new unique session folders.
`fsync: false` still flushes every record from Python's buffer. Setting it to true
also requests filesystem synchronisation for every raw record, which can make
acquisition slower. It is not a complete transaction or power-failure guarantee.

`logging.level` controls operational messages. `logging.path: null` disables the
operational file log, not the measurement recording. The raw data file and log
file have different purposes.

## Configure several independent channels

The continuous example supplies these channels:

| Room / station | Metric | Period |
|---|---|---:|
| laboratory / station-01 | temperature | 5 s |
| laboratory / station-01 | humidity | 7 s |
| laboratory / station-01 | pressure | 10 s |
| office / station-02 | temperature | 12 s |

They share one scheduler but not a single sampling period. The terminal and live
snapshot initially select laboratory temperature. All four channels go to the
raw archive, including events that do not produce a new terminal line. Change the
selection to another configured channel to monitor it instead.

To add a channel, copy one sensor object and edit its identity, metric, numerical
model, interval, and seed. Do not edit the scheduler. Keep your new configuration
in a separate JSON file so you retain the working examples.

## Understand how paths are resolved

The default config filename is anchored beside `run.py`, using the script's
location. An explicit config filename on the command line is resolved from your
terminal's current directory. Paths INSIDE the config are resolved from the
config file's directory, not the terminal and not an arbitrary project root.

For example, `../output/sessions` in `config/simulation_quick.json` points to the
project's `output/sessions`. In a generated session's `offline_config.json`, the
input `raw.jsonl` points beside that config. `Path` objects implement `/` as path
joining; this is not division of strings.

You can start the program from elsewhere by using an absolute config path:

```text
python /path/to/project/run.py /path/to/project/config/simulation_quick.json
```

The paths in the configuration still resolve in the same place. Configuration
validation also prevents the configured log or output destinations from targeting
the configuration file itself. Do not run two acquisition processes against the
same operational log as a concurrency experiment in this iteration.

## Try three controlled experiments

First, set `noise_std` to zero and disable calibration. Explain why every raw
value equals the configured mean. Then enable scale 2 and offset 1 and verify
that the live value changes but the raw archive does not.

Second, compare the quick and five-second configurations. They differ in the real
period, not in the interpretation of timestamps. Measure total elapsed time from
startup, not just the difference between first and last observation times.

Third, set `max_readings` to a small number in the multi-channel configuration.
Count records of each metric in `raw.jsonl`. Their sum, not each individual count,
should equal the configured limit. A run can end before the selected slow channel
has produced anything; its snapshot then correctly has no points and undefined
statistics rather than a fabricated zero.
