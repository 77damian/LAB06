# Changes relative to room_sensor_solved

We start with the `room_sensor_solved.zip` that I shared with you last time.
This is an extension of this version of the project.

All original Python modules except `run.py`, original checks, datasets, and the
original config/example.json are retained as were. The old run.py numerical
workflow is moved into `file_workflow.run_files`; the new entry point dispatches
the pipeline based on mode. Existing `run_finite.py` remains unchanged.

New source modules: `simulation.py`, `streaming.py`, `recording.py`,
`run_configuration.py`, `run_stream.py`, and the extracted `file_workflow.py`.
New config examples: files, quick simulation, ten five-second observations, and
continuous multi-channel simulation. 

The previous README, validation report, and generator planning note are retained.

## Compact handouts

`docs/01_START_HERE.md` and `GENERATOR_SOLUTIONS.md` are now companion materials. The README
points to them first.