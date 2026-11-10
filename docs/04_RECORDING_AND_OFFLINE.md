# 4. Record now; analyse again later

An on-screen value is not a dataset. Your run must preserve the measurements
independently of what you choose to display or how many points fit in a rolling
window. This guide explains the recording contract and your G6 task.

## Inspect one session

Run the quick simulation after completing the required tasks. The terminal prints
the actual session directory and an offline-analysis command. The directory name
contains a UTC timestamp and a random suffix. It is created afresh; a later run
must not silently replace the previous raw data.

`raw.jsonl` contains every acquired raw observation, one JSON object per line.
Its fields match the earlier `DATA_CONTRACT.md`. There is no JSON array surrounding
the file and no comma between successive records. That makes each completed line
independently readable, without waiting for an indefinitely long array to close.

`session.json` records the settings used, startup time, status, counts, and final
elapsed time. It starts with status `running`; ordinary completion or Ctrl+C writes
final metadata. After an abrupt process kill, its status/counts may still be the
startup values. In that case the completed raw lines are the evidence of what was
recorded, not an assumed successful shutdown.

`latest.json` contains only the selected rolling window and its matching
statistics. It is replaced, not appended to. Treat it as a convenient view of
recent state, never as the measurement archive. Its running counts are those at
the latest selected update, so unselected arrivals can make those counts lag until
the next selected update or shutdown.

`offline_config.json` is a finite-file configuration written for this particular
raw archive. You can copy it, change the selected series or calibration, and rerun
analysis without repeating the acquisition.

## Implement G6: one record, one line, then flush

Your `append_reading` receives an already-open text stream and one standard
record. It does not choose a path or reopen the file for every measurement.

First serialise the record, disallowing NaN and infinity. Then write the resulting
JSON text followed by a newline. Finally flush the stream. Serialising before
writing means a serialisation error does not partially replace an earlier record
with an invalid representation. Do not catch a write error and continue as though
recording succeeded.

The caller opens a new raw file once and holds it inside a `with` block. The file
is created exclusively, so an unexpected existing filename causes an error
instead of overwriting a recording. Each write adds a new line at the current end.
This differs from the earlier `save_jsonl`, which deliberately replaces an entire
finite snapshot. That earlier function is unchanged.

An optional `fsync` setting asks for `os.fsync` after `flush`. Ordinary `flush`
passes Python-buffered content to the operating system; it is not a promise that
power can be removed without data loss. Filesystem synchronisation has additional
cost, and durability still depends on the filesystem/storage system. At the slow
teaching intervals you can compare the two settings, but do not claim that either
implements a crash-proof acquisition database.

Python documents the `flush` then `fsync` sequence here:
https://docs.python.org/3.13/library/os.html#os.fsync .

## Keep the archive upstream of selection

Find `record_incoming` in `run_stream.py`. It performs a deliberate side effect:
it writes a raw record, increments the saved-record count, and then yields that
same raw record to the next stage. It does not calibrate or filter it.

Selection follows recording. Calibration follows selection. This order gives you
all the raw data while preserving the previous rule that one series' calibration
must not be applied to another. G4 copies a record before changing its value,
preventing a later correction from modifying the raw dictionary unexpectedly.

Do not create two separate consumers of the same generator, one for saving and
one for analysis. They would compete for successive observations rather than
receive identical copies of an independent dataset. Here there is one explicit
path through the source: record, then process, then publish the bounded snapshot.

## Reanalyse your completed recording

Stop the simulation normally, or wait for its count limit. Copy the exact command
printed by the program. It has this form:

```text
python run.py "output/sessions/YOUR_SESSION/offline_config.json"
```

The filename above is a pattern, not a literal session name. Use the real path
from your own run. File mode creates the following additional files:

```text
YOUR_SESSION/offline/calibrated.csv
YOUR_SESSION/offline/summary.json
YOUR_SESSION/offline/analysis.log
```

The summary includes exploration of all raw series and a selected calibrated
summary, just as in the earlier solved project. Raw values are calibrated once
at analysis time. Do not point this input at an already calibrated output while
leaving calibration enabled unless a second correction is explicitly intended.

For ten selected readings and a window size of five, `latest.json` describes five
points, while the offline summary describes ten. Different means are expected:
they are answers to different questions. Check the counts before deciding that a
numerical discrepancy is a bug.

## Replay lazily with your G3 reader

The ordinary finite file workflow still builds complete lists. For a large
finished archive, connect your generator reader to the bounded pipeline instead:

```python
from contextlib import closing
from pathlib import Path
from run_configuration import load_run_config
from streaming import iter_jsonl, select_calibrated, rolling_windows, build_snapshot

# Replace YOUR_SESSION with the actual directory printed by your simulation.
settings = Path("output/sessions/YOUR_SESSION/offline_config.json")
config = load_run_config(settings)
last = None
with closing(iter_jsonl(config["input"]["path"])) as raw:
    selected = select_calibrated(raw, config["selection"], config["calibration"])
    for window in rolling_windows(selected, 5):
        last = build_snapshot(window, config["selection"], config["calibration"], 5)
print(last)
```

This reads every line once but retains only the recent selected window. It does
not wait according to the stored timestamps. An empty file or an absent selection
leaves `last` as `None`; handle that explicitly rather than assuming a reading
exists.

## Stopping and failures

Use Ctrl+C in the terminal for the intended shutdown path. Waiting is interruptible.
The raw file is closed, the source generator is closed, and final session/snapshot
metadata is written with status `interrupted`. A positive count limit ends with
status `completed`. Storage or processing errors end with `failed` where final
metadata can still be written, and propagate as a visible failure.

A second interruption during cleanup, a process kill, a full disk, or power loss
is outside this clean-shutdown guarantee. The final JSONL line might be incomplete
after a crash. The reader reports it rather than silently accepting a damaged
record. Preserve the original recording before attempting manual recovery; work
on a copy containing only complete, validated lines.

Streaming memory is bounded by the configured channels and window. Disk usage is
not: both raw measurements and the operational log can grow. Use finite trial
runs first, monitor available space, and keep long-duration retention/rotation as
a later engineering requirement.
