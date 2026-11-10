# 2. Work through generators step by step

Read this guide with `simulation.py` and `streaming.py` open beside it. Try the
short examples in a Python session started in the project folder, or place them
in a temporary scratch script beside `run.py`.

## Step 1 — Observe what `yield` changes

```python
def three_values():
    yield 20.0
    yield 21.0
    yield 22.0

values = three_values()
print(next(values))
print(next(values))
print(list(values))
```

You see `20.0`, then `21.0`, then `[22.0]`. Creating the generator does not execute
its body to completion. Each request resumes it until the next `yield`; its local
state survives the pause. The final `list` requests only the remaining value.
Calling `list(values)` again gives an empty list because this generator is now
exhausted. A new call to `three_values()` creates a fresh generator.

A generator is not a second thread. While it is paused at `yield`, it does not
continue measuring somewhere else. The caller controls progress by requesting
the next item. Keep this in mind when you later add slow plotting or file access.

## Step 2 — Make the value source infinite: G1

Your `sensor_values(sensor)` function should retain a private random-number
generator, then yield one numerical value per request indefinitely. You do not
store earlier values inside it. The consumer, not this function, decides how many
to request.

The settings include a mean, a noise standard deviation, and a seed. With zero
noise the output should equal the mean. With the same seed and settings, a newly
created generator should reproduce the same value sequence. Use a private
`random.Random` object rather than resetting the global random state. Two sensor
streams should not change each other's sequences simply because their calls are
interleaved.

Use Gaussian noise for this teaching example. Bound humidity to 0–100 percent
and pressure below by zero; temperature is not clipped. These simple limits are
not a physical model of your sensor, and clipping changes a distribution near
its bounds. Values must remain finite. Do not add file writing, logging, or
calibration to this function.

After implementing G1, try:

```python
import json
from itertools import islice
from pathlib import Path
from simulation import sensor_values

config = json.loads(Path("config/simulation_quick.json").read_text())
specification = config["simulation"]["sensors"][0]
values = sensor_values(specification)
print(list(islice(values, 4)))
values.close()
```

This step is intentionally fast: the value generator does not sleep. You are
separating the numerical model from the timing mechanism.

**Never call `list(sensor_values(...))`.** The generator has no natural final
value, so that expression cannot finish normally and keeps accumulating output.

## Step 3 — Introduce real waiting: G2

A time interval and a timestamp answer different questions. `interval_seconds`
says how long to wait between scheduled measurements. The stored UTC timestamp
says when an actual reading was produced. The scheduler uses a monotonic clock
for elapsed time; the records use timezone-aware wall-clock UTC.

`wait_until(deadline, clock, sleep)` receives an absolute deadline on that elapsed
clock. Compute the remaining delay, sleep while it is positive, and check the
clock again. Do not repeatedly check the time without sleeping: that would waste
CPU while waiting. Do not call `sleep(deadline)`: the deadline is not a duration.

For example, if the current elapsed-clock value is 100 and the deadline is 105,
you need a delay of five seconds. If the deadline has already passed, return
without requesting a negative sleep.

The `clock` and `sleep` arguments allow the tests to substitute a small fake clock.
That is test infrastructure, not an accelerated application mode. The defaults
are the real `time.monotonic` and `time.sleep` functions.

## Step 4 — Read the supplied scheduler

`simulate_sensors` combines the value generators with waiting. Its first deadline
for each channel is the starting clock value plus that channel's interval. For
one channel with a five-second interval, the intended arrival sequence is:

```text
start       first       second                      tenth
0 s          5 s         10 s          ...            50 s
```

There are ten waits, not nine. However, the difference between the first and last
stored timestamps is approximately 45 seconds. That is not a contradiction: the
first five-second wait occurs before the first timestamp is stored.

Ordinary operating-system scheduling can wake a program late. The code does not
claim exact deterministic real-time guarantees. It also cannot acquire data
while its consumer is busy indefinitely. If it falls substantially behind, it
produces one current observation for the due channel and moves its next deadline
forward. It does not invent several past observations with fabricated times.

With multiple channels, the scheduler selects the earliest deadline. Consider a
temperature channel every two seconds and humidity every five seconds:

```text
2 s  temperature
4 s  temperature
5 s  humidity
6 s  temperature
8 s  temperature
10 s temperature, then humidity
```

Sleeping for two seconds and then five seconds in a simple loop over sensors
would not reproduce this schedule. The supplied scheduler keeps one deadline per
channel. Equal deadlines are processed in configuration order. The number of
channels is fixed by your configuration, so scheduler state does not grow during
an acquisition.

## Step 5 — Read a finished recording lazily: G3

The earlier `read_jsonl` reads lines one by one but appends every record to a list.
That still retains the whole file. Your new `iter_jsonl(path)` should open the file
inside its generator body and yield each parsed record immediately.

Skip blank lines. Use the existing `parse_record` function so the data contract
stays identical. A bad JSON object or measurement should produce a useful error
with the filename and physical line number; do not silently skip damaged data.

The file belongs to the generator's `with` block. Exhausting it closes the file.
When you stop early, explicitly close it, for example with `contextlib.closing`:

```python
from contextlib import closing
from itertools import islice
from pathlib import Path
from streaming import iter_jsonl

# Replace this with the raw.jsonl path printed by your completed run.
path = Path("output/sessions/YOUR_SESSION/raw.jsonl")
with closing(iter_jsonl(path)) as source:
    for reading in islice(source, 3):
        print(reading)
```

This reader is for a finished finite recording. It stops at end-of-file; it does
not wait for another process to append more lines. Do not treat it as a live
file-tail service in this iteration.

## Step 6 — Process one record at a time: G4

Your `select_calibrated` is the lazy counterpart of the earlier finite pipeline.
For each incoming record, compare the exact `(room, sensor_id, metric)` with the
selection. Ignore nonmatching records. For a matching record, yield a new
calibrated dictionary, or a new unmodified copy when calibration is disabled.

Use `calibrate_reading` rather than rewriting its formula. Do not call the older
`select_series` inside this generator: that function returns a complete list and
would try to exhaust the source before returning.

The calibration operation is pure: it receives a record and coefficients, and
returns a new record without changing its input. The iterator as a whole is
consumed once. "Functional" does not mean that the source has no state, and it
does not require replacing every readable `for` loop with `map` and lambdas.

## Step 7 — Summarise a finite window of an infinite source: G5

An exact median of all measurements so far would require retaining more data or a
different data structure. In this iteration, ask a simpler question: what are the
statistics of the last N selected readings?

Keep a `deque` with a maximum length. Append each selected record, then yield a
separate snapshot of the current contents. During warm-up, yield windows of one,
two, three, ... records. Once capacity is reached, new records displace the oldest.

A window of five observations is not necessarily a window of five seconds.
Irregular delays remain visible in the stored timestamps. Ensure one window never
mixes different rooms, sensors, metrics, or units. The supplied pipeline selects
first; a guard inside your window function also protects direct callers.

Return copies so a later consumer cannot mutate a previous snapshot and corrupt
the next one. Copying a bounded window is acceptable here. The supplied snapshot
builder calculates the statistics and points from that same window; therefore a
future plot and its displayed mean describe exactly the same observations.

## Read further

The Python Functional Programming HOWTO explains generator execution and lazy
iteration: https://docs.python.org/3.13/howto/functional.html . The timing APIs are
specified in https://docs.python.org/3.13/library/time.html . `islice` is documented
in https://docs.python.org/3.13/library/itertools.html , and bounded deques in
https://docs.python.org/3.13/library/collections.html#collections.deque .
