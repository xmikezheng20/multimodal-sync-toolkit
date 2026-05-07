# Notebooks

Example notebooks for sync inspection, session-time mapping, and demo-video layout.

The notebooks assume an example session folder is available locally. Set the environment variable `MULTIMODAL_SYNC_EXAMPLE_SESSION` to that session path before running them, or edit the `SESSION_BASEPATH` / `session_basepath` cell in the notebook.

- `inspect_audio_lsb_sync.ipynb`: load an Avisoft WAV file from a session folder, extract the embedded LSB sync track, and plot the full recording plus a zoomed sync onset.
- `inspect_intan_digital_sync.ipynb`: load an Intan `digitalin.dat` file from a session folder, extract one digital input channel, and plot the full recording plus a zoomed sync onset.
- `map_buzzer_led_to_session_timebase.ipynb`: detect example audio/video events in file-local coordinates, convert them to source indices, and map them to session time.
- `design_demo_video_frame.ipynb`: preview one configured demo-video frame and tune component layout before rendering an MP4.
