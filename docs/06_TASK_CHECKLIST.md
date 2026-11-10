# 6. Your implementation checklist

Use these checks as completion criteria, not as a substitute for understanding
what your functions consume, retain, and return. Existing finite-data tasks are
already solved. Only the new G tasks are placeholders in the student edition.

## G1 — `sensor_values(sensor)`

You should create one private random-number generator when iteration starts,
using the configured seed. Repeatedly produce Gaussian noisy values with the
configured mean and standard deviation. Reject nonfinite generated values. Bound
humidity to [0, 100] and pressure below by zero. Yield one number and retain no
history. Do not sleep here.

Check that zero noise gives a constant; equal seeds give equal value sequences;
interleaving two different sensors does not alter either sequence; and constructing
the generator without consuming it does no sampling. Use `islice` for finite tests.

## G2 — `wait_until(deadline, clock, sleep)`

Calculate the remaining delay against the injected monotonic clock. Sleep while
the remaining delay is positive, then recheck. Do not call sleep with a negative
argument, spin without sleeping, or interpret an absolute deadline as a duration.

Check an already passed deadline, an exact wait, and a test sleeper that wakes
early. Then read `simulate_sensors`: the first reading must arrive after its first
interval; independent channels must not wait sequentially on each other's periods.
The scheduler itself is supplied so this task can stay small.

## G3 — `iter_jsonl(path)`

Open a finished file lazily, inside the generator. Skip blank lines. Decode and
validate one row with `parse_record`, then yield it. Preserve line order and
include the filename and line number in errors. Use a `with` block so exhausting
or explicitly closing the generator releases the file.

Check an empty file, a valid file, and a malformed third line after a valid first
line. You should be able to receive the first record before discovering the later
error. Do not return the old list-building reader as a substitute for this task.

## G4 — `select_calibrated(readings, selection, calibration)`

Inspect each input once. Filter by the complete series identity before applying
calibration. Return fresh dictionaries whether calibration is enabled or disabled.
Do not log, read configuration files, print, or materialise the whole input.

Check that a humidity record is ignored when temperature is selected; raw input
is unchanged; and requesting one selected item does not read beyond that item.
A filter may still consume several rejected records to find a match. That is not
unnecessary read-ahead; it is the defined selection behaviour.

## G5 — `rolling_windows(readings, size)`

Validate a positive integer size, rejecting booleans as sizes. Use a bounded deque.
Store copies, and yield independent finite snapshots. Produce warm-up windows
rather than waiting until the buffer is full. Reject an attempt to mix series or
units in the same window.

Check that 3,000 generated records never produce a window larger than its capacity.
Mutate a previous returned snapshot and verify later snapshots are unaffected.
Use the supplied `build_snapshot` and earlier `extended_summary` rather than
reimplementing statistical formulae in the generator.

## G6 — `append_reading(stream, reading, fsync=False)`

Serialise first with nonfinite values disallowed. Write one JSON object followed
by one newline; flush after each row. When requested, call `os.fsync` after the
flush. Do not open/close the stream here, filter records, or swallow errors.

Check visibility through a second file handle before the writer is closed. Two
calls must give two complete lines. Invalid serialisation must not append broken
text. A closed stream or simulated disk failure must stop visibly.

## Run focused checks while you work

From the project folder:

```bash
python -m unittest discover -s checks -p "test_generator_extension.py" -k G1 -v
python -m unittest discover -s checks -p "test_generator_extension.py" -v
python -m unittest discover -s checks -p "*.py" -v
```

The focused G1 command is an example; change the search string as needed.
Unfinished tasks are skipped by catching only `NotImplementedError`. Incorrect
outputs, unexpected errors, and failed assertions are not turned into skips.
Some integration checks are skipped until the task functions they depend on can
run. Once all tasks are implemented, there should be no task-related skips.

Most timing tests inject a fake clock so they do not make you wait fifty seconds
on every run. A short integration check really sleeps. You should also run the
provided five-second configuration yourself and compare its actual elapsed time
with the intended schedule.

## Integration completion criteria

Run file mode and confirm the earlier calibrated mean is unchanged. Run the quick
simulation, then the ten-reading five-second example. Confirm ten raw JSONL lines
and only five points in the final rolling snapshot. Run offline analysis using the
generated config; confirm its selected count is ten and that raw data is unchanged.

Run multiple channels with a small total limit. Check that the archive contains
unselected channels while the live snapshot contains one series. Run continuously
and stop with Ctrl+C; inspect final status and saved counts. Intentionally set an
invalid interval or misspell a metric and verify that configuration fails before
recording starts.

Finally, describe where side effects occur and which functions you can test using
ordinary finite lists. Explain why bounded RAM does not imply bounded disk use.
Do not add plots or a browser as part of passing this iteration: that is the next
consumer of the interface you have just prepared.
