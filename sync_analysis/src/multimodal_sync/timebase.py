"""Map modality-specific indices onto the shared session timebase."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


def interp_linear_extrapolation(
    x: float | np.ndarray,
    xp: np.ndarray,
    fp: np.ndarray,
) -> float | np.ndarray:
    """Interpolate with linear extrapolation outside the reference support."""

    xp = np.asarray(xp, dtype=float)
    fp = np.asarray(fp, dtype=float)
    x_arr = np.atleast_1d(np.asarray(x, dtype=float))

    if xp.ndim != 1 or fp.ndim != 1 or xp.size != fp.size:
        raise ValueError("xp and fp must be 1D arrays of equal length")
    if xp.size == 0:
        raise ValueError("xp and fp must be non-empty")

    y = np.interp(x_arr, xp, fp)
    if xp.size >= 2:
        left_dx = xp[1] - xp[0]
        right_dx = xp[-1] - xp[-2]
        if left_dx == 0 or right_dx == 0:
            raise ValueError("Interpolation reference indices must be strictly increasing")

        left_slope = (fp[1] - fp[0]) / left_dx
        right_slope = (fp[-1] - fp[-2]) / right_dx

        left_mask = x_arr < xp[0]
        right_mask = x_arr > xp[-1]
        if np.any(left_mask):
            y[left_mask] = fp[0] + (x_arr[left_mask] - xp[0]) * left_slope
        if np.any(right_mask):
            y[right_mask] = fp[-1] + (x_arr[right_mask] - xp[-1]) * right_slope

    if np.isscalar(x):
        return float(np.asarray(y).reshape(-1)[0])
    return y


@dataclass(frozen=True)
class SyncTimebase:
    """Timebase for a stream that records the sync pulse train."""

    source_indices: np.ndarray
    session_times_s: np.ndarray
    source_rate_hz: float | None = None
    source_index_name: str = "sample"

    @classmethod
    def from_sync_data(
        cls,
        sync_data: np.ndarray,
        *,
        source_rate_hz: float | None = None,
        source_index_name: str = "sample",
    ) -> "SyncTimebase":
        """Build a timebase from a validation sync table."""

        sync_data = np.asarray(sync_data)
        if sync_data.ndim != 2 or sync_data.shape[1] < 5:
            raise ValueError("sync_data must have shape (n_pulses, >=5)")
        if sync_data.shape[0] == 0:
            raise ValueError("sync_data must contain at least one pulse")
        return cls(
            source_indices=np.asarray(sync_data[:, 0], dtype=float),
            session_times_s=np.asarray(sync_data[:, 4], dtype=float),
            source_rate_hz=source_rate_hz,
            source_index_name=source_index_name,
        )

    @classmethod
    def from_file(
        cls,
        path: str | Path,
        *,
        source_rate_hz: float | None = None,
        source_index_name: str = "sample",
    ) -> "SyncTimebase":
        """Load a validation sync table from disk and build a timebase."""

        return cls.from_sync_data(
            np.load(path),
            source_rate_hz=source_rate_hz,
            source_index_name=source_index_name,
        )

    def __post_init__(self) -> None:
        if self.source_indices.ndim != 1 or self.session_times_s.ndim != 1:
            raise ValueError("source_indices and session_times_s must be 1D")
        if self.source_indices.size != self.session_times_s.size:
            raise ValueError("source_indices and session_times_s must have equal length")
        if self.source_indices.size == 0:
            raise ValueError("timebase references must be non-empty")
        if np.any(np.diff(self.source_indices) <= 0):
            raise ValueError("source_indices must be strictly increasing")
        if np.any(np.diff(self.session_times_s) <= 0):
            raise ValueError("session_times_s must be strictly increasing")

    @property
    def first_session_time_s(self) -> float:
        return float(self.session_times_s[0])

    @property
    def last_session_time_s(self) -> float:
        return float(self.session_times_s[-1])

    def source_to_session_time(self, source_index: float | np.ndarray) -> float | np.ndarray:
        """Map source sample/frame indices to session time in seconds."""

        return interp_linear_extrapolation(
            source_index,
            self.source_indices,
            self.session_times_s,
        )

    def session_time_to_source(
        self,
        session_time: float | np.ndarray,
        *,
        round_index: bool = True,
    ) -> int | np.ndarray:
        """Map session time in seconds to source sample/frame indices."""

        source_index = interp_linear_extrapolation(
            session_time,
            self.session_times_s,
            self.source_indices,
        )
        if round_index:
            source_index = np.rint(source_index).astype(int)
            if np.isscalar(session_time):
                return int(np.asarray(source_index).reshape(-1)[0])
        return source_index

    def source_indices_for_window(self, start_time: float, end_time: float) -> tuple[int, int]:
        """Return rounded source-index bounds for a session-time window."""

        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time")
        start = self.session_time_to_source(start_time, round_index=True)
        end = self.session_time_to_source(end_time, round_index=True)
        return int(start), int(end)

    def to_dict(self) -> dict[str, Any]:
        """Return compact metadata for summaries and debugging."""

        return {
            "source_index_name": self.source_index_name,
            "source_rate_hz": self.source_rate_hz,
            "n_reference_points": int(self.source_indices.size),
            "first_source_index": float(self.source_indices[0]),
            "last_source_index": float(self.source_indices[-1]),
            "first_session_time_s": self.first_session_time_s,
            "last_session_time_s": self.last_session_time_s,
        }


@dataclass(frozen=True)
class FrameTimebase:
    """Timebase for hardware-triggered video where one frame equals one sync pulse."""

    sync_rate_hz: float

    def frame_to_session_time(self, frame_index: float | np.ndarray) -> float | np.ndarray:
        """Map global frame indices to session time in seconds."""

        out = np.asarray(frame_index, dtype=float) / float(self.sync_rate_hz)
        if np.isscalar(frame_index):
            return float(np.asarray(out).reshape(-1)[0])
        return out

    def session_time_to_frame(
        self,
        session_time: float | np.ndarray,
        *,
        round_index: bool = True,
    ) -> int | np.ndarray:
        """Map session time in seconds to global frame indices."""

        frame_index = np.asarray(session_time, dtype=float) * float(self.sync_rate_hz)
        if round_index:
            frame_index = np.rint(frame_index).astype(int)
            if np.isscalar(session_time):
                return int(np.asarray(frame_index).reshape(-1)[0])
        elif np.isscalar(session_time):
            return float(np.asarray(frame_index).reshape(-1)[0])
        return frame_index

    def source_to_session_time(self, source_index: float | np.ndarray) -> float | np.ndarray:
        """Alias used by generic event-mapping helpers."""

        return self.frame_to_session_time(source_index)

    def session_time_to_source(
        self,
        session_time: float | np.ndarray,
        *,
        round_index: bool = True,
    ) -> int | np.ndarray:
        """Alias used by generic segment-loading helpers."""

        return self.session_time_to_frame(session_time, round_index=round_index)

    def source_indices_for_window(self, start_time: float, end_time: float) -> tuple[int, int]:
        """Return rounded global-frame bounds for a session-time window."""

        if end_time <= start_time:
            raise ValueError("end_time must be greater than start_time")
        return (
            int(self.session_time_to_frame(start_time, round_index=True)),
            int(self.session_time_to_frame(end_time, round_index=True)),
        )
