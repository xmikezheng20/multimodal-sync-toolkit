# Acquisition

Rig-side assets for synchronized multimodal acquisition.

This layer contains Arduino firmware, Bonsai workflows, acquisition scripts, and acquisition-specific configuration examples. It is intended for the acquisition computer and may depend on Windows-only recording software, camera drivers, Bonsai, ffmpeg, and Arduino tooling.

Acquisition configuration should describe how the rig records data. It is separate from the analysis configuration used later to validate a recorded session.

Create the acquisition environment with:

```bash
conda env create --prefix $HOME/.conda/envs/multimodal-sync-acquisition -f acquisition/envs/acquisition.yaml
conda activate $HOME/.conda/envs/multimodal-sync-acquisition
```

The default acquisition environment installs Python 3.12 and FFmpeg from conda-forge. A legacy FFmpeg 4.2.2 environment is also provided in `acquisition/envs/acquisition_legacy_ffmpeg422.yaml`. The FFmpeg build, NVIDIA driver, GPU hardware, and `h264_nvenc` encoder options need to work together, so each acquisition computer should be tested with a short representative recording before long sessions.

Two tested examples are included as starting points:

- GeForce RTX 3060, NVIDIA driver 581.57, conda-forge FFmpeg 8.1.1, and the modern config.
- Quadro RTX 4000, NVIDIA driver 516.94, default-channel FFmpeg 4.2.2, and the legacy config.

Video encoder options are configured in the acquisition YAML under `video.ffmpeg_output_options`. This block is passed through to ffmpeg as output-side options, so different rigs can use the encoder settings appropriate for their FFmpeg version, GPU, driver, and recording requirements without changing the Python wrapper.

The acquisition wrapper launches Bonsai with active conda paths removed from Bonsai's `PATH`. This keeps Bonsai.Spinnaker using the Windows Spinnaker SDK DLLs while ffmpeg continues to run from the active conda environment.
