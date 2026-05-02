# Sync Analysis

Installable Python package and scripts for session validation and session-time mapping.

Install the full development environment from this folder:

```bash
cd sync_analysis
conda env create --prefix $HOME/.conda/envs/multimodal-sync-analysis -f envs/analysis.yaml
conda activate $HOME/.conda/envs/multimodal-sync-analysis
```

Or install into an existing Python environment:

```bash
cd sync_analysis
pip install -e ".[all]"
```

This layer should remain independent from the acquisition computer setup. It validates recorded data after acquisition and builds timing tables that map modality-specific samples or frames onto the shared session clock.
