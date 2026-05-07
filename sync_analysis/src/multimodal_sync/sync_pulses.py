"""Detect and index recorded sync pulse trains."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

import numpy as np

logger = logging.getLogger(__name__)

Chunk = tuple[int, np.ndarray]


@dataclass
class SyncPulseDetectionResult:
    """Pulse detection output for one recorded binary sync channel."""

    events: np.ndarray
    valid_pulses: np.ndarray
    rejected_pulses: np.ndarray
    sync_data: np.ndarray
    diagnostics: dict[str, int | float | bool | None]


def detect_digital_events(binary_signal: np.ndarray) -> np.ndarray:
    """Detect rising/falling event pairs in an in-memory binary signal.

    Edge indices follow the historical validator convention: the edge index is
    the sample immediately before the transition.
    """

    signal = np.asarray(binary_signal, dtype=bool)
    if signal.size < 2:
        return np.empty((0, 3), dtype=np.int64)

    rising_edges = np.where(~signal[:-1] & signal[1:])[0]
    falling_edges = np.where(signal[:-1] & ~signal[1:])[0]
    return pair_edges(rising_edges, falling_edges)


def pair_edges(rising_edges: np.ndarray, falling_edges: np.ndarray) -> np.ndarray:
    """Pair rising edges with the next following falling edge."""

    events: list[tuple[int, int, int]] = []
    fall_i = 0
    for rising in np.asarray(rising_edges, dtype=np.int64):
        while fall_i < len(falling_edges) and falling_edges[fall_i] <= rising:
            fall_i += 1
        if fall_i >= len(falling_edges):
            break
        falling = int(falling_edges[fall_i])
        events.append((int(rising), falling, falling - int(rising)))
        fall_i += 1
    if not events:
        return np.empty((0, 3), dtype=np.int64)
    return np.asarray(events, dtype=np.int64)


def detect_digital_events_from_chunks(chunks: Iterable[Chunk]) -> np.ndarray:
    """Detect digital events from `(global_start_sample, binary_chunk)` chunks."""

    events: list[tuple[int, int, int]] = []
    open_rising: int | None = None
    previous_value: bool | None = None
    previous_index: int | None = None

    def handle_transition(edge_index: int, new_value: bool) -> None:
        nonlocal open_rising
        if new_value:
            if open_rising is not None:
                logger.warning(
                    "Detected a rising edge before the previous pulse fell at sample %s",
                    edge_index,
                )
            open_rising = edge_index
        elif open_rising is not None:
            events.append((open_rising, edge_index, edge_index - open_rising))
            open_rising = None

    expected_start: int | None = None
    for start_sample, chunk in chunks:
        signal = np.asarray(chunk, dtype=bool)
        if signal.size == 0:
            continue
        start_sample = int(start_sample)

        if expected_start is not None and start_sample != expected_start:
            logger.warning(
                "Digital chunks are not contiguous: expected start %s, got %s",
                expected_start,
                start_sample,
            )

        if previous_value is not None and bool(signal[0]) != previous_value:
            if previous_index is None:
                raise RuntimeError("Internal state error: missing previous index")
            handle_transition(previous_index, bool(signal[0]))

        transition_indices = np.flatnonzero(signal[:-1] != signal[1:])
        for local_index in transition_indices:
            edge_index = start_sample + int(local_index)
            handle_transition(edge_index, bool(signal[local_index + 1]))

        previous_value = bool(signal[-1])
        previous_index = start_sample + signal.size - 1
        expected_start = start_sample + signal.size

    if not events:
        return np.empty((0, 3), dtype=np.int64)
    return np.asarray(events, dtype=np.int64)


def filter_pulses_by_width(
    events: np.ndarray,
    *,
    sample_rate_hz: float,
    sync_rate_hz: float,
    pulse_width_tolerance: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Keep pulse events whose high duration matches a 50% duty-cycle pulse."""

    events = np.asarray(events, dtype=np.int64)
    if events.size == 0:
        empty = np.empty((0, 3), dtype=np.int64)
        return empty, empty

    expected_width_samples = sample_rate_hz / (2 * sync_rate_hz)
    lower = expected_width_samples * (1 - pulse_width_tolerance)
    upper = expected_width_samples * (1 + pulse_width_tolerance)
    keep = (events[:, 2] >= lower) & (events[:, 2] <= upper)
    return events[keep], events[~keep]


def infer_pulse_indices(
    valid_pulses: np.ndarray,
    *,
    sample_rate_hz: float,
    sync_rate_hz: float,
    infer_missing_pulses: bool,
) -> tuple[np.ndarray, dict[str, int | float | bool | None]]:
    """Append inferred sync-pulse index and session time columns.

    When `infer_missing_pulses` is enabled, a gap between two valid observed
    pulses is rounded to an integer number of sync intervals. The next valid
    observed pulse is then assigned the corresponding inferred pulse index. No
    synthetic row is inserted for the missing pulse; the skipped index is only
    represented in the inferred-index column.
    """

    valid_pulses = np.asarray(valid_pulses, dtype=np.int64)
    if valid_pulses.size == 0:
        empty = np.empty((0, 5), dtype=float)
        return empty, {
            "inferred_pulse_count": 0,
            "missing_inferred_pulses": 0,
            "nonunit_intervals": 0,
            "interval_deviation_count": 0,
            "infer_missing_pulses": bool(infer_missing_pulses),
        }

    n_pulses = valid_pulses.shape[0]
    inferred_indices = np.zeros(n_pulses, dtype=np.int64)
    expected_interval_s = 1.0 / sync_rate_hz
    rising_times_nominal_s = valid_pulses[:, 0] / sample_rate_hz
    interval_deviation_count = 0
    nonunit_intervals = 0

    for index in range(1, n_pulses):
        dt = rising_times_nominal_s[index] - rising_times_nominal_s[index - 1]
        inferred_increment = int(round(dt / expected_interval_s))
        if inferred_increment < 1:
            inferred_increment = 1

        if infer_missing_pulses:
            increment = inferred_increment
        else:
            increment = 1

        if inferred_increment != 1:
            nonunit_intervals += 1
        if abs(dt - expected_interval_s) > 0.1 * expected_interval_s:
            interval_deviation_count += 1

        inferred_indices[index] = inferred_indices[index - 1] + increment

    inferred_times = inferred_indices / sync_rate_hz
    sync_data = np.column_stack((valid_pulses, inferred_indices, inferred_times))
    missing = int(inferred_indices[-1] + 1 - n_pulses)
    diagnostics = {
        "inferred_pulse_count": int(inferred_indices[-1]) + 1,
        "missing_inferred_pulses": missing,
        "nonunit_intervals": int(nonunit_intervals),
        "interval_deviation_count": int(interval_deviation_count),
        "infer_missing_pulses": bool(infer_missing_pulses),
    }
    return sync_data, diagnostics


def summarize_sync_detection(
    *,
    events: np.ndarray,
    valid_pulses: np.ndarray,
    rejected_pulses: np.ndarray,
    sync_data: np.ndarray,
    sample_rate_hz: float,
    sync_rate_hz: float,
    pulse_width_tolerance: float,
    infer_missing_pulses: bool,
    chunk_size_samples: int | None,
    inference_diagnostics: dict[str, int | float | bool | None],
) -> dict[str, int | float | bool | None]:
    """Build numeric diagnostics for one sync channel."""

    diagnostics: dict[str, int | float | bool | None] = {
        "sample_rate_hz": float(sample_rate_hz),
        "sync_rate_hz": float(sync_rate_hz),
        "pulse_width_tolerance": float(pulse_width_tolerance),
        "infer_missing_pulses": bool(infer_missing_pulses),
        "chunk_size_samples": chunk_size_samples,
        "candidate_pulses": int(events.shape[0]),
        "valid_pulses": int(valid_pulses.shape[0]),
        "rejected_pulses": int(rejected_pulses.shape[0]),
    }
    diagnostics.update(inference_diagnostics)

    if valid_pulses.size == 0:
        diagnostics.update(
            {
                "first_rising_sample": None,
                "last_rising_sample": None,
                "first_rising_time_nominal_s": None,
                "last_rising_time_nominal_s": None,
                "median_interval_samples": None,
                "min_interval_samples": None,
                "max_interval_samples": None,
                "median_interval_nominal_s": None,
                "min_interval_nominal_s": None,
                "max_interval_nominal_s": None,
                "median_pulse_width_samples": None,
                "median_pulse_width_nominal_s": None,
            }
        )
        return diagnostics

    rising = valid_pulses[:, 0]
    widths = valid_pulses[:, 2]
    diagnostics.update(
        {
            "first_rising_sample": int(rising[0]),
            "last_rising_sample": int(rising[-1]),
            "first_rising_time_nominal_s": float(rising[0] / sample_rate_hz),
            "last_rising_time_nominal_s": float(rising[-1] / sample_rate_hz),
            "median_pulse_width_samples": float(np.median(widths)),
            "median_pulse_width_nominal_s": float(np.median(widths) / sample_rate_hz),
        }
    )

    if rising.size > 1:
        intervals = np.diff(rising)
        diagnostics.update(
            {
                "median_interval_samples": float(np.median(intervals)),
                "min_interval_samples": int(np.min(intervals)),
                "max_interval_samples": int(np.max(intervals)),
                "median_interval_nominal_s": float(np.median(intervals) / sample_rate_hz),
                "min_interval_nominal_s": float(np.min(intervals) / sample_rate_hz),
                "max_interval_nominal_s": float(np.max(intervals) / sample_rate_hz),
            }
        )
    else:
        diagnostics.update(
            {
                "median_interval_samples": None,
                "min_interval_samples": None,
                "max_interval_samples": None,
                "median_interval_nominal_s": None,
                "min_interval_nominal_s": None,
                "max_interval_nominal_s": None,
            }
        )

    return diagnostics


def detect_sync_pulses_from_events(
    events: np.ndarray,
    *,
    sample_rate_hz: float,
    sync_rate_hz: float,
    pulse_width_tolerance: float,
    infer_missing_pulses: bool,
    chunk_size_samples: int | None = None,
) -> SyncPulseDetectionResult:
    """Filter and index sync pulses from pre-detected event pairs."""

    valid_pulses, rejected_pulses = filter_pulses_by_width(
        events,
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=pulse_width_tolerance,
    )
    sync_data, inference_diagnostics = infer_pulse_indices(
        valid_pulses,
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        infer_missing_pulses=infer_missing_pulses,
    )
    diagnostics = summarize_sync_detection(
        events=events,
        valid_pulses=valid_pulses,
        rejected_pulses=rejected_pulses,
        sync_data=sync_data,
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=pulse_width_tolerance,
        infer_missing_pulses=infer_missing_pulses,
        chunk_size_samples=chunk_size_samples,
        inference_diagnostics=inference_diagnostics,
    )
    return SyncPulseDetectionResult(
        events=events,
        valid_pulses=valid_pulses,
        rejected_pulses=rejected_pulses,
        sync_data=sync_data,
        diagnostics=diagnostics,
    )


def detect_sync_pulses(
    binary_signal: np.ndarray,
    *,
    sample_rate_hz: float,
    sync_rate_hz: float,
    pulse_width_tolerance: float,
    infer_missing_pulses: bool,
) -> SyncPulseDetectionResult:
    """Detect sync pulses from an in-memory binary signal."""

    events = detect_digital_events(binary_signal)
    return detect_sync_pulses_from_events(
        events,
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=pulse_width_tolerance,
        infer_missing_pulses=infer_missing_pulses,
        chunk_size_samples=None,
    )


def detect_sync_pulses_from_chunks(
    chunks: Iterable[Chunk],
    *,
    sample_rate_hz: float,
    sync_rate_hz: float,
    pulse_width_tolerance: float,
    infer_missing_pulses: bool,
    chunk_size_samples: int | None = None,
) -> SyncPulseDetectionResult:
    """Detect sync pulses from streamed binary chunks."""

    events = detect_digital_events_from_chunks(chunks)
    return detect_sync_pulses_from_events(
        events,
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=pulse_width_tolerance,
        infer_missing_pulses=infer_missing_pulses,
        chunk_size_samples=chunk_size_samples,
    )

