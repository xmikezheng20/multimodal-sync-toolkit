# multimodal-sync-toolkit

A modular toolkit for synchronized multimodal data acquisition and session-time alignment in systems neuroscience.

## Protocol

This repository accompanies the protocol:

Xiaoyue Mike Zheng, Martin Davis, Arkarup Banerjee. A modular toolkit for synchronized multimodal data acquisition in systems neuroscience. protocols.io. Final public link pending.

Refer to the protocol for the synchronization approach, hardware setup, acquisition workflow, and detailed implementation steps.

## Repository Organization

This repository is organized as one protocol companion with two separable layers:

- `acquisition/`: rig-side assets for generating and recording a shared sync pulse train.
- `sync_analysis/`: an installable Python package and scripts for validating sessions and mapping recorded data onto the shared session timebase.

The two layers intentionally have separate environments and configuration files. Acquisition and analysis often run on different computers, and each layer should be usable without depending on the other.

## Documentation

The central timing model is described in `docs/session_time_model.md`.
