# Acquisition Scripts

Acquisition helper scripts will live here.

`run_acquisition.py` launches the Bonsai acquisition workflow and starts ffmpeg processes that encode raw frames from Bonsai named pipes.

By default, ffmpeg uses `session.sync_rate_hz` from the acquisition config as the video frame rate. Set `video.frame_rate_hz` only when an explicit override is needed.
