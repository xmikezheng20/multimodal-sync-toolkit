"""Simple event detection and timebase-mapping helpers."""

from __future__ import annotations

from typing import Protocol

import numpy as np
import pandas as pd


class SourceToSessionTimebase(Protocol):
    """Protocol for objects that map source indices to session time."""

    def source_to_session_time(self, source_index: float | np.ndarray) -> float | np.ndarray:
        ...


def find_intervals_from_mask(
    x: np.ndarray,
    mask: np.ndarray,
    *,
    gap_threshold: float,
    min_duration: float = 0.0,
    max_duration: float | None = None,
) -> np.ndarray:
    """Find intervals where a boolean mask is true along a sorted numeric axis.

    The gap and duration thresholds use the same units as `x`.
    """

    x = np.asarray(x)
    mask = np.asarray(mask, dtype=bool)
    if x.ndim != 1 or mask.ndim != 1:
        raise ValueError("x and mask must be 1D")
    if x.size != mask.size:
        raise ValueError("x and mask must have equal length")
    if x.size == 0 or not np.any(mask):
        return np.empty((0, 2), dtype=float)

    active_x = np.sort(x[mask])
    gaps = np.flatnonzero(np.diff(active_x) > gap_threshold)
    interval_starts = np.insert(gaps + 1, 0, 0)
    interval_ends = np.append(gaps, active_x.size - 1)
    intervals = np.column_stack((active_x[interval_starts], active_x[interval_ends]))

    durations = intervals[:, 1] - intervals[:, 0]
    keep = durations >= min_duration
    if max_duration is not None:
        keep &= durations <= max_duration
    return intervals[keep]


def detect_threshold_intervals(
    x: np.ndarray,
    signal: np.ndarray,
    *,
    threshold: float,
    direction: str = "above",
    gap_threshold: float,
    min_duration: float = 0.0,
    max_duration: float | None = None,
) -> np.ndarray:
    """Detect intervals where a 1D signal crosses a threshold.

    The gap and duration thresholds use the same units as `x`.
    """

    signal = np.asarray(signal)
    if signal.ndim != 1:
        raise ValueError("signal must be 1D")
    if direction == "above":
        mask = signal > threshold
    elif direction == "below":
        mask = signal < threshold
    else:
        raise ValueError("direction must be 'above' or 'below'")
    return find_intervals_from_mask(
        x,
        mask,
        gap_threshold=gap_threshold,
        min_duration=min_duration,
        max_duration=max_duration,
    )


def intervals_to_dataframe(
    intervals: np.ndarray,
    *,
    start_col: str = "start",
    end_col: str = "end",
    duration_col: str = "duration",
) -> pd.DataFrame:
    """Convert an interval array to a DataFrame with duration."""

    intervals = np.asarray(intervals)
    if intervals.size == 0:
        return pd.DataFrame(columns=[start_col, end_col, duration_col])
    if intervals.ndim != 2 or intervals.shape[1] != 2:
        raise ValueError("intervals must have shape (n, 2)")

    df = pd.DataFrame(intervals, columns=[start_col, end_col])
    df[duration_col] = df[end_col] - df[start_col]
    return df


def file_local_time_events_to_source_indices(
    events: pd.DataFrame,
    *,
    file_source_start_index: int,
    source_rate_hz: float,
    file_local_start_col: str = "start",
    file_local_end_col: str = "end",
    source_start_col: str = "source_start_index",
    source_end_col: str = "source_end_index",
) -> pd.DataFrame:
    """Add global source indices to events detected in file-local time.

    This is the usual bridge between file-by-file analysis output and the
    channel-wide source coordinate system described by a validation file-info
    table.
    """

    missing = {file_local_start_col, file_local_end_col} - set(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {sorted(missing)}")
    mapped = events.copy()
    mapped[source_start_col] = (
        int(file_source_start_index)
        + mapped[file_local_start_col].to_numpy() * float(source_rate_hz)
    ).round().astype("int64")
    mapped[source_end_col] = (
        int(file_source_start_index)
        + mapped[file_local_end_col].to_numpy() * float(source_rate_hz)
    ).round().astype("int64")
    mapped["source_duration_indices"] = mapped[source_end_col] - mapped[source_start_col]
    return mapped


def file_local_index_events_to_source_indices(
    events: pd.DataFrame,
    *,
    file_source_start_index: int,
    file_local_start_col: str = "start",
    file_local_end_col: str = "end",
    source_start_col: str = "source_start_index",
    source_end_col: str = "source_end_index",
) -> pd.DataFrame:
    """Add global source indices to events detected in file-local indices."""

    missing = {file_local_start_col, file_local_end_col} - set(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {sorted(missing)}")
    mapped = events.copy()
    mapped[source_start_col] = (
        int(file_source_start_index) + mapped[file_local_start_col].to_numpy()
    ).round().astype("int64")
    mapped[source_end_col] = (
        int(file_source_start_index) + mapped[file_local_end_col].to_numpy()
    ).round().astype("int64")
    mapped["source_duration_indices"] = mapped[source_end_col] - mapped[source_start_col]
    return mapped


def map_event_source_indices_to_session_time(
    events: pd.DataFrame,
    timebase: SourceToSessionTimebase,
    *,
    start_col: str = "source_start_index",
    end_col: str = "source_end_index",
    output_start_col: str = "session_start_s",
    output_end_col: str = "session_end_s",
) -> pd.DataFrame:
    """Map source-index event bounds to shared session time."""

    missing = {start_col, end_col} - set(events.columns)
    if missing:
        raise ValueError(f"events missing required columns: {sorted(missing)}")

    mapped = events.copy()
    if mapped.empty:
        mapped[output_start_col] = pd.Series(dtype=float)
        mapped[output_end_col] = pd.Series(dtype=float)
        mapped["session_duration_s"] = pd.Series(dtype=float)
        return mapped

    mapped[output_start_col] = timebase.source_to_session_time(mapped[start_col].to_numpy())
    mapped[output_end_col] = timebase.source_to_session_time(mapped[end_col].to_numpy())
    mapped["session_duration_s"] = mapped[output_end_col] - mapped[output_start_col]
    return mapped
