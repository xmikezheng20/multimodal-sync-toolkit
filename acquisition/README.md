# Acquisition

Rig-side assets for synchronized multimodal acquisition.

This layer will contain Arduino firmware, Bonsai workflows, acquisition scripts, and acquisition-specific configuration examples. It is intended for the acquisition computer and may depend on Windows-only recording software, camera drivers, Bonsai, ffmpeg, and Arduino tooling.

Acquisition configuration should describe how the rig records data. It is separate from the analysis configuration used later to validate a recorded session.

Create the acquisition environment with:

```bash
conda env create -f envs/acquisition.yaml
conda activate ~/.conda/envs/multimodal-sync-acquisition
```
