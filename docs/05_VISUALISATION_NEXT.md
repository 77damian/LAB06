# 5. Leave a clear boundary for the final visualisation step

Your current output is numerical data, terminal messages, and JSON. That is
intentional. You are preparing a source that a future plot can consume without
changing the generator, calibration, or statistics.

## What a plot needs

A basic time-series plot needs timestamps, numerical values, a series identity,
and a unit. If you display a mean beside the plot, the mean should describe the
same points that are visible. `build_snapshot` already produces these together.

The structure of `latest.json` is:

```text
series                 room, sensor_id, metric, unit
points                 [{time: ..., value: ...}, ...]
summary                count, mean, minimum, maximum, median, sample_sd
window_capacity        maximum number of selected points retained
calibration_applied    whether the selected values were corrected
calibration            the coefficients and enabled flag
status                 running / completed / interrupted / failed
records_saved          raw count at this snapshot update
selected_records       selected count at this snapshot update
```

There are no image bytes or plotting-library objects in this document. A notebook,
a desktop plot, or a later HTTP API can interpret the same numerical structure.
The application currently writes it to a file; it does not serve that file over
HTTP or implement a dashboard.

## Read the meaning before plotting

Plot `time` on the horizontal axis, not just point number. Arrival intervals can
be irregular when the computer is busy. Retain the timezone or convert it
explicitly for display. Do not assume every gap equals the configured period.

Use the supplied metric and unit in labels. One live snapshot represents exactly
one `(room, sensor_id, metric)` series. Do not plot humidity and temperature as
though they were values of the same quantity. Supporting several simultaneous
views is a separate next-step requirement, not a reason to mix their statistics.

An empty `points` array is a legitimate state before the first selected reading.
An unavailable statistic is JSON `null`, not zero. With one point, sample standard
deviation is unavailable. Your future visualisation should show these conditions
honestly instead of drawing invented observations or error bars.

The selected series may update less frequently than other channels. `records_saved`
in a running snapshot is not a continuously refreshed system-wide counter. The
latest point's timestamp tells you when the displayed data was acquired. Final
metadata is refreshed again on clean shutdown.

## Do not make plotting drive measurement frequency

The current generator is pull-based: it advances when the acquisition pipeline
requests another value. If you place a slow plot update inside that same loop,
plotting can delay the next acquisition. That limitation is explicit in this
single-process teaching stage.

When you later build an independently refreshed interface, keep one acquisition
owner and let the view read recorded/snapshotted data. Opening a second view must
not create a second simulated sensor stream or consume alternate measurements
from the first. Refreshing the chart should not itself request a new measurement.

For the next small iteration, first plot a finished recording. Then read the
replaceable bounded snapshot at a chosen display rate. Only after those ideas are
clear should you consider a dedicated acquisition thread/process or an HTTP API.
No such concurrency or web service is hidden in this folder.

## Why the snapshot is replaced through a temporary file

A future reader should not normally see half a JSON document while the writer is
rewriting it. The supplied helper writes a neighbouring temporary file and then
replaces the target. This is a single-writer, local-file design; it is not a
transaction protocol or a universal guarantee for every remote filesystem.
A future client should still handle missing files, parse/read failures, and stale
data rather than assume every read will succeed.

The raw archive is different: it must keep every acquired record. Do not replace
`raw.jsonl` with a rolling snapshot to make a plot easier to draw.

## A small completion exercise now

Open your last `latest.json`. Count the points and compare that count with
`summary.count`. Calculate their mean independently and compare it with the
stored mean. Identify the series and unit without consulting the configuration.
Then compare with the offline summary and explain why its count may be larger.

You are ready for the visualisation iteration when you can specify everything
the plot needs using this data contract alone, without asking the plotting code
to perform acquisition or duplicate the calibration rules.
