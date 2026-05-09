# Acquisition Scripts

Acquisition helper scripts will live here.

`run_acquisition.py` launches the Bonsai acquisition workflow and starts ffmpeg processes that encode raw frames from Bonsai named pipes.

By default, ffmpeg uses `session.sync_rate_hz` from the acquisition config as the video frame rate. Set `video.frame_rate_hz` only when the video frame rate should differ from the sync rate.

Output-side ffmpeg arguments are configured with `video.ffmpeg_output_options`. A mapping is usually easiest:

```yaml
video:
  ffmpeg_output_options:
    c:v: h264_nvenc
    profile:v: high
    preset: p5
    rc: vbr
    cq: 23
    b:v: "0"
```

The wrapper also accepts an ordered list of options for cases where repeated flags or exact ordering are needed. These options are inserted after the raw-video input and before the output path.
