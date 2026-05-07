# Sync Analysis

Installable Python package and scripts for session validation and session-time mapping.

This layer is meant to run after acquisition on a completed session folder. It validates the recorded sync reference, writes timing tables under `sync/`, and provides helpers for mapping modality-specific data into the shared session timebase.

## Installation

Install the full development environment from this folder:

```bash
cd sync_analysis
conda env create --prefix $HOME/.conda/envs/multimodal-sync-analysis -f envs/analysis.yaml
conda activate $HOME/.conda/envs/multimodal-sync-analysis
pip install -e ".[all]"
```

The conda environment installs Python and the `ffmpeg` executable. Python package dependencies are installed by `pip` from `pyproject.toml`.

To install into an existing Python environment:

```bash
cd sync_analysis
pip install -e ".[all]"
```

This layer should remain independent from the acquisition computer setup. It validates recorded data after acquisition and builds timing tables that map modality-specific samples or frames onto the shared session clock.

## Coordinate Systems

The analysis code keeps three coordinate systems separate:

- `file_local`: indices or times inside one source file, such as seconds within one WAV file or frame numbers within one MP4 segment.
- `source`: channel-wide sample or frame indices after all files for one channel are concatenated in recording order.
- `session`: the shared sync-defined clock, where the first valid sync pulse is `t = 0` and pulse `i` occurs at `i / sync_rate_hz`.

Most modality-specific analysis should happen in file-local or source coordinates without thinking about synchronization. For example, detect audio events in each WAV file, detect video events in each video segment, or run pose tracking per video file. After those results are expressed as source indices, use the sync timebase helpers to map them once onto session time.

## Session Validation

Run validation from `sync_analysis/`:

```bash
python scripts/validate_session.py \
  -s /path/to/session \
  -c configs/example_session_01_50hz.yaml \
  --log-file /path/to/session/logs/validate_session.log
```

Validation writes a `sync/` folder into the session. The key outputs are:

- `sync/validation_counts.csv`: frame and pulse counts used for cross-modality consistency checks.
- `sync/pulse_diagnostics.csv`: per-channel pulse detection diagnostics.
- `sync/<modality>/<channel_id>/*_file_info.csv`: file order and source-index ranges for segmented source data.
- `sync/<modality>/<channel_id>/*_sync_data.npy`: pulse lookup tables for sampled modalities that record the sync train.

For pulse channels, each `*_sync_data.npy` row is:

```text
rising_sample, falling_sample, pulse_duration_samples, pulse_index, session_time_s
```

If `sync_detection.infer_missing_pulses` is enabled for a channel, the validator can assign a later observed pulse a skipped pulse index when a local recording defect drops a pulse. It does not insert synthetic pulse rows. This is useful for audio LSB sync defects, but is disabled by default for Intan digital inputs.

## Mapping and Demo Videos

The notebook `notebooks/map_buzzer_led_to_session_timebase.ipynb` demonstrates the intended workflow: detect events per file, convert file-local results into source indices using the validation file-info tables, then map source indices to session time with `SyncTimebase` or `FrameTimebase`.

Demo videos use the same session-time mapping layer. `scripts/make_demo_video.py` takes a session, a session config, a demo-video layout config, and a session-time clip window. The renderer samples the requested session-time window at the configured output frame rate, updates each visual component at those session times, writes a temporary video, writes a temporary audio track when configured, and muxes them into the final MP4.
