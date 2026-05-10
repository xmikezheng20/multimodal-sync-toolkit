# Acquisition Configs

These YAML files describe rig-side acquisition settings. They are separate from
the analysis configs used after recording.

- `example_v1_50hz.yaml`: one monochrome camera, 50 Hz sync, one output file, using newer FFmpeg/NVENC-style options.
- `example_v1_50hz_1h_segments.yaml`: same one-camera setup, split into one-hour video files.
- `example_v1_50hz_legacy_ffmpeg422.yaml`: one-camera example using the older FFmpeg 4.2.2/defaults-channel stack.
- `example_v1_50hz_legacy_ffmpeg422_1h_segments.yaml`: legacy FFmpeg 4.2.2 example with one-hour video segments.

The `video.ffmpeg_output_options` block is passed through as output-side ffmpeg
arguments. Use this block to adapt encoder settings to the FFmpeg version, GPU,
NVIDIA driver, and recording requirements on the acquisition computer.
