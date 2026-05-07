"""Containers for continuous data in source and session timebases."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SourceSignal:
    """Continuous data in one channel's source index space."""

    values: np.ndarray
    source_indices: np.ndarray
    source_rate_hz: float
    modality: str
    channel_id: str
    source_index_name: str = "sample"

    def __post_init__(self) -> None:
        values = np.asarray(self.values)
        source_indices = np.asarray(self.source_indices)
        if source_indices.ndim != 1:
            raise ValueError("source_indices must be 1D")
        if values.shape[0] != source_indices.size:
            raise ValueError("values first dimension must match source index length")
        if float(self.source_rate_hz) <= 0:
            raise ValueError("source_rate_hz must be positive")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "source_indices", source_indices)

    @property
    def n_points(self) -> int:
        """Number of source samples, frames, or signal points."""

        return int(self.source_indices.size)

    @property
    def source_times_nominal_s(self) -> np.ndarray:
        """Source-channel time in seconds based on the nominal source rate."""

        return np.asarray(self.source_indices, dtype=float) / float(self.source_rate_hz)

    @property
    def first_source_index(self) -> int | float | None:
        if self.n_points == 0:
            return None
        return self.source_indices[0].item()

    @property
    def last_source_index(self) -> int | float | None:
        if self.n_points == 0:
            return None
        return self.source_indices[-1].item()


@dataclass(frozen=True)
class SessionSignal:
    """Continuous data mapped onto the shared session timebase."""

    values: np.ndarray
    source_indices: np.ndarray
    session_times_s: np.ndarray
    source_rate_hz: float
    modality: str
    channel_id: str
    source_index_name: str = "sample"

    def __post_init__(self) -> None:
        values = np.asarray(self.values)
        source_indices = np.asarray(self.source_indices)
        session_times_s = np.asarray(self.session_times_s)
        if source_indices.ndim != 1 or session_times_s.ndim != 1:
            raise ValueError("source_indices and session_times_s must be 1D")
        if source_indices.size != session_times_s.size:
            raise ValueError("source_indices and session_times_s must have equal length")
        if values.shape[0] != source_indices.size:
            raise ValueError("values first dimension must match source index length")
        if float(self.source_rate_hz) <= 0:
            raise ValueError("source_rate_hz must be positive")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "source_indices", source_indices)
        object.__setattr__(self, "session_times_s", session_times_s)

    @property
    def n_points(self) -> int:
        """Number of session-mapped samples, frames, or signal points."""

        return int(self.source_indices.size)

    @property
    def duration_s(self) -> float:
        """Approximate duration spanned by the signal."""

        if self.n_points <= 1:
            return 0.0
        return float(self.session_times_s[-1] - self.session_times_s[0])

    @property
    def first_source_index(self) -> int | float | None:
        if self.n_points == 0:
            return None
        return self.source_indices[0].item()

    @property
    def last_source_index(self) -> int | float | None:
        if self.n_points == 0:
            return None
        return self.source_indices[-1].item()


def map_source_signal_to_session_time(source_signal, timebase) -> SessionSignal:
    """Map a source-space signal onto session time."""

    session_times_s = timebase.source_to_session_time(source_signal.source_indices)
    return SessionSignal(
        values=source_signal.values,
        source_indices=source_signal.source_indices,
        session_times_s=np.asarray(session_times_s),
        source_rate_hz=source_signal.source_rate_hz,
        modality=source_signal.modality,
        channel_id=source_signal.channel_id,
        source_index_name=source_signal.source_index_name,
    )
