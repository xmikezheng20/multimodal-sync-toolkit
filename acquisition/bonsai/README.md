# Bonsai

Bonsai workflows for acquisition and monitoring will live here.

These workflows should remain acquisition-side assets. Analysis should not depend on Bonsai.

Current workflows:

- `workflows/simple_pulse_control.bonsai`: serial start/stop control for the Arduino pulse train.
- `workflows/triggered_video_monitor_v1.bonsai`: Arduino pulse control plus one triggered FLIR camera monitor.
- `workflows/triggered_video_writer_v1.bonsai`: Arduino pulse control plus one triggered FLIR camera written to a named pipe for ffmpeg encoding.
- `workflows/triggered_video_writer_v2.bonsai`: Arduino pulse control plus two triggered FLIR cameras written to separate named pipes for ffmpeg encoding.

The `_vN` suffix means the workflow is wired for `N` video streams. A rig with three cameras should use a corresponding `_v3` workflow and config.
