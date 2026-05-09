# Acquisition

Rig-side assets for synchronized multimodal acquisition.

This layer will contain Arduino firmware, Bonsai workflows, acquisition scripts, and acquisition-specific configuration examples. It is intended for the acquisition computer and may depend on Windows-only recording software, camera drivers, Bonsai, ffmpeg, and Arduino tooling.

Acquisition configuration should describe how the rig records data. It is separate from the analysis configuration used later to validate a recorded session.

Create the acquisition environment with:

```bash
conda env create --prefix $HOME/.conda/envs/multimodal-sync-acquisition -f acquisition/envs/acquisition.yaml
conda activate $HOME/.conda/envs/multimodal-sync-acquisition
```

The acquisition environment is pinned to a tested Windows/NVIDIA video encoding stack. In particular, the ffmpeg build, NVIDIA driver, and `h264_nvenc` encoder options need to work together. The current environment file uses Python 3.12 with ffmpeg 4.2.2 from the default conda channel, tested on Windows 11 with an NVIDIA RTX 3060 and NVIDIA driver 581.57. If video acquisition or encoding fails, consider testing a different NVIDIA driver, ffmpeg version, or encoder setting.

Video encoder options are configured in the acquisition YAML under `video.ffmpeg_output_options`. This block is passed through to ffmpeg as output-side options, so different rigs can use the encoder settings appropriate for their FFmpeg version, GPU, driver, and recording requirements without changing the Python wrapper.
