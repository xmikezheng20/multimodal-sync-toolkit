"""Configuration helpers for sync-analysis scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import SyncDetectionConfig


def load_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML config file."""

    with Path(path).open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    if not isinstance(data, dict):
        raise ValueError(f"Config file did not contain a mapping: {path}")
    return data


def config_root(config: dict[str, Any]) -> dict[str, Any]:
    """Return the inner config mapping, supporting the historical `config:` root."""

    root = config.get("config", config)
    if not isinstance(root, dict):
        raise ValueError("Config root must be a mapping")
    return root


def get_sync_rate_hz(root: dict[str, Any]) -> float:
    """Return the global session sync rate."""

    session = root.get("session", {})
    if isinstance(session, dict) and "sync_rate_hz" in session:
        return float(session["sync_rate_hz"])
    if "sync_rate" in root:
        return float(root["sync_rate"])
    raise KeyError("Missing global sync rate. Expected config.session.sync_rate_hz")


def _sync_detection_mapping(channel_config: dict[str, Any]) -> dict[str, Any]:
    sync_detection = channel_config.get("sync_detection", {})
    if sync_detection is None:
        return {}
    if not isinstance(sync_detection, dict):
        raise ValueError("sync_detection must be a mapping when provided")
    return sync_detection


def resolve_sync_detection_config(
    channel_config: dict[str, Any],
    *,
    default_pulse_width_tolerance: float = 0.01,
    default_infer_missing_pulses: bool = False,
    default_chunk_size_samples: int | None = None,
) -> SyncDetectionConfig:
    """Resolve channel-level sync detection settings."""

    sync_detection = _sync_detection_mapping(channel_config)
    chunk_size = (
        sync_detection["chunk_size_samples"]
        if "chunk_size_samples" in sync_detection
        else default_chunk_size_samples
    )
    if chunk_size is not None:
        chunk_size = int(chunk_size)
        if chunk_size <= 0:
            raise ValueError("chunk_size_samples must be positive or null")

    return SyncDetectionConfig(
        pulse_width_tolerance=float(
            sync_detection.get("pulse_width_tolerance", default_pulse_width_tolerance)
        ),
        infer_missing_pulses=bool(
            sync_detection.get("infer_missing_pulses", default_infer_missing_pulses)
        ),
        chunk_size_samples=chunk_size,
    )

