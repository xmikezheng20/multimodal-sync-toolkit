"""Shared result models for session validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SyncDetectionConfig:
    """Configuration for detecting one recorded sync pulse train."""

    pulse_width_tolerance: float = 0.01
    infer_missing_pulses: bool = False
    chunk_size_samples: int | None = None


@dataclass
class PulseChannelResult:
    """Validation result for a modality channel that records sync pulses."""

    modality: str
    channel_id: str
    sample_rate_hz: float
    sync_data: np.ndarray
    file_info: pd.DataFrame
    diagnostics: dict[str, Any]
    output_subdir: tuple[str, ...]
    sync_data_filename: str
    file_info_filename: str

    @property
    def validation_count(self) -> int:
        if self.sync_data.size == 0:
            return 0
        return int(self.sync_data[-1, 3]) + 1

    @property
    def count_label(self) -> str:
        return f"{self.modality}:{self.channel_id}"


@dataclass
class FrameChannelResult:
    """Validation result for a video-like channel counted by frames."""

    modality: str
    channel_id: str
    frame_rate_hz: float | None
    frame_count: int
    file_info: pd.DataFrame
    diagnostics: dict[str, Any]
    output_subdir: tuple[str, ...]
    file_info_filename: str

    @property
    def validation_count(self) -> int:
        return int(self.frame_count)

    @property
    def count_label(self) -> str:
        return f"{self.modality}:{self.channel_id}"


@dataclass
class ValidationResult:
    """Top-level validation result for one session."""

    session_basepath: str
    sync_rate_hz: float
    pulse_channels: list[PulseChannelResult] = field(default_factory=list)
    frame_channels: list[FrameChannelResult] = field(default_factory=list)
    counts: pd.DataFrame | None = None
    pulse_diagnostics: pd.DataFrame | None = None
    success: bool = False

