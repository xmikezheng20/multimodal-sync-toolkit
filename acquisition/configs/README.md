# Acquisition Configs

These YAML files describe rig-side acquisition settings. They are separate from
the analysis configs used after recording.

- `example_v1_50hz.yaml`: one monochrome camera, 50 Hz sync, one output file.
- `example_v1_50hz_1h_segments.yaml`: same one-camera setup, split into one-hour video files.

The `video.ffmpeg_output_options` block is passed through as output-side ffmpeg
arguments. Use this block to adapt encoder settings to the FFmpeg version, GPU,
NVIDIA driver, and recording requirements on the acquisition computer.
