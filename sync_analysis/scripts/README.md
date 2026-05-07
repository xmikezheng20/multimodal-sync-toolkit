# Analysis Scripts

Command-line entry points for validation and demo-video rendering.

These scripts should call reusable code from `src/multimodal_sync/`.

Validate one recorded session:

```bash
python scripts/validate_session.py \
  -s /path/to/session \
  -c configs/example_session_01_50hz.yaml \
  --log-file /path/to/session/logs/validate_session.log
```

Render a short demo video clip:

```bash
python scripts/make_demo_video.py \
  --session /path/to/session \
  --session-config configs/example_session_01_50hz.yaml \
  --demo-video-config configs/demo_video/example_video_audio_waveform.yaml \
  --clip-start-session-s 0 \
  --clip-end-session-s 3 \
  --output /path/to/demo.mp4
```

The demo-video clip bounds are session times in seconds. Component layout, frame rate, audio-track settings, and encoder options are configured in the demo-video YAML file.
