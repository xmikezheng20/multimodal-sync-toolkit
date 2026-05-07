"""Video frame-count validation helpers."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ..continuous import SourceSignal
from ..files import require_files
from ..media_info import _require_cv2, compute_video_file_info
from ..models import FrameChannelResult
from ..segments import local_bounds_for_row, resolve_data_file, select_overlapping_files

logger = logging.getLogger(__name__)


def validate_video_channel(
    *,
    session_basepath: Path,
    video_config: dict,
    channel_config: dict,
) -> FrameChannelResult:
    """Validate one configured video channel by counting frames."""

    channel_id = str(channel_config["channel_id"])
    base_dir = str(video_config.get("video_base_dir", "raw_video"))
    channel_dir = session_basepath / base_dir / channel_id
    video_paths = require_files(channel_dir, (".mp4", ".avi", ".mov"))
    file_info = compute_video_file_info(video_paths)

    expected_fps = video_config.get("video_file_sr")
    if expected_fps is not None:
        expected_fps = float(expected_fps)
        observed_fps = sorted(set(round(float(v), 6) for v in file_info["fps"]))
        mismatches = [fps for fps in observed_fps if abs(fps - expected_fps) > 0.01]
        if mismatches:
            raise ValueError(
                f"Video FPS mismatch for {channel_id}: expected {expected_fps}, "
                f"found {observed_fps}"
            )

    frame_count = int(file_info["num_frames"].sum())
    diagnostics = {
        "files": len(video_paths),
        "frame_count": frame_count,
        "expected_fps": expected_fps,
        "observed_fps_values": ";".join(str(v) for v in sorted(set(file_info["fps"]))),
    }
    logger.info(
        "Video channel %s: %s file(s), total_frames=%s, fps=%s",
        channel_id,
        len(video_paths),
        frame_count,
        diagnostics["observed_fps_values"],
    )

    return FrameChannelResult(
        modality="video",
        channel_id=channel_id,
        frame_rate_hz=expected_fps,
        frame_count=frame_count,
        file_info=file_info,
        diagnostics=diagnostics,
        output_subdir=("video", channel_id),
        file_info_filename="video_file_info.csv",
    )


def read_video_frame(
    *,
    file_info: pd.DataFrame,
    video_basepath: str | Path,
    frame_index: int,
) -> np.ndarray:
    """Read one global frame from a segmented video channel."""

    selected = select_overlapping_files(
        file_info,
        global_start=int(frame_index),
        global_end=int(frame_index) + 1,
        start_col="frame_start",
        end_col="frame_end",
    )
    if selected.empty:
        raise IndexError(f"Frame index {frame_index} is outside the video file table")

    row = selected.iloc[0]
    local_index = int(frame_index) - int(row["frame_start"])
    video_path = resolve_data_file(video_basepath, str(row["filename"]))
    return read_video_file_frame(video_path=video_path, frame_index=local_index)


def read_video_file_frame(
    *,
    video_path: str | Path,
    frame_index: int,
) -> np.ndarray:
    """Read one frame from one video file using file-local frame coordinates."""

    cv2 = _require_cv2()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise OSError(f"Could not open video file: {video_path}")
    try:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))
        ok, frame = cap.read()
    finally:
        cap.release()
    if not ok:
        raise OSError(f"Could not read local frame {frame_index} from {video_path}")
    return frame


def extract_video_roi_file_trace(
    *,
    video_path: str | Path,
    roi: dict[str, int],
) -> np.ndarray:
    """Extract mean ROI intensity across one video file.

    The returned array is in file-local frame order and does not depend on
    synchronization metadata.
    """

    x = int(roi["x"])
    y = int(roi["y"])
    w = int(roi["w"])
    h = int(roi["h"])
    if w <= 0 or h <= 0:
        raise ValueError("ROI width and height must be positive")

    cv2 = _require_cv2()
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise OSError(f"Could not open video file: {video_path}")
    values: list[float] = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            roi_pixels = frame[y : y + h, x : x + w]
            if roi_pixels.size == 0:
                raise ValueError(f"ROI {roi} is outside the loaded video frame")
            values.append(float(np.mean(roi_pixels)))
    finally:
        cap.release()

    return np.asarray(values, dtype=float)


def load_video_source_segment(
    *,
    file_info: pd.DataFrame,
    video_basepath: str | Path,
    global_start_frame: int,
    global_end_frame: int,
    frame_rate_hz: float,
    channel_id: str = "video",
) -> SourceSignal:
    """Load video frames in channel-wide source frame coordinates."""

    if global_end_frame <= global_start_frame:
        raise ValueError("global_end_frame must be greater than global_start_frame")

    selected = select_overlapping_files(
        file_info,
        global_start=global_start_frame,
        global_end=global_end_frame,
        start_col="frame_start",
        end_col="frame_end",
    )

    frames: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    cv2 = _require_cv2()
    for _, row in selected.iterrows():
        local_start, local_end, clipped_start, clipped_end = local_bounds_for_row(
            row,
            global_start=global_start_frame,
            global_end=global_end_frame,
            start_col="frame_start",
            count_col="num_frames",
        )
        if local_end <= local_start:
            continue
        video_path = resolve_data_file(video_basepath, str(row["filename"]))
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise OSError(f"Could not open video file: {video_path}")
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, local_start)
            current = local_start
            while current < local_end:
                ok, frame = cap.read()
                if not ok:
                    raise OSError(f"Could not read local frame {current} from {video_path}")
                frames.append(frame)
                current += 1
        finally:
            cap.release()
        indices.append(np.arange(clipped_start, clipped_end, dtype=np.int64))

    if not frames:
        values = np.empty((0,), dtype=np.uint8)
        source_indices = np.empty((0,), dtype=np.int64)
    else:
        values = np.stack(frames, axis=0)
        source_indices = np.concatenate(indices)

    return SourceSignal(
        values=values,
        source_indices=source_indices,
        source_rate_hz=float(frame_rate_hz),
        modality="video",
        channel_id=channel_id,
        source_index_name="frame",
    )


def extract_video_roi_source_trace(
    *,
    file_info: pd.DataFrame,
    video_basepath: str | Path,
    global_start_frame: int,
    global_end_frame: int,
    frame_rate_hz: float,
    roi: dict[str, int],
    channel_id: str = "video",
) -> SourceSignal:
    """Extract mean ROI intensity in channel-wide source frame coordinates."""

    x = int(roi["x"])
    y = int(roi["y"])
    w = int(roi["w"])
    h = int(roi["h"])
    if w <= 0 or h <= 0:
        raise ValueError("ROI width and height must be positive")
    if global_end_frame <= global_start_frame:
        raise ValueError("global_end_frame must be greater than global_start_frame")

    selected = select_overlapping_files(
        file_info,
        global_start=global_start_frame,
        global_end=global_end_frame,
        start_col="frame_start",
        end_col="frame_end",
    )

    roi_values: list[float] = []
    indices: list[np.ndarray] = []
    cv2 = _require_cv2()
    for _, row in selected.iterrows():
        local_start, local_end, clipped_start, clipped_end = local_bounds_for_row(
            row,
            global_start=global_start_frame,
            global_end=global_end_frame,
            start_col="frame_start",
            count_col="num_frames",
        )
        if local_end <= local_start:
            continue
        video_path = resolve_data_file(video_basepath, str(row["filename"]))
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise OSError(f"Could not open video file: {video_path}")
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, local_start)
            current = local_start
            while current < local_end:
                ok, frame = cap.read()
                if not ok:
                    raise OSError(f"Could not read local frame {current} from {video_path}")
                roi_pixels = frame[y : y + h, x : x + w]
                if roi_pixels.size == 0:
                    raise ValueError(f"ROI {roi} is outside the loaded video frame")
                roi_values.append(float(np.mean(roi_pixels)))
                current += 1
        finally:
            cap.release()
        indices.append(np.arange(clipped_start, clipped_end, dtype=np.int64))

    if roi_values:
        values = np.asarray(roi_values, dtype=float)
        source_indices = np.concatenate(indices)
    else:
        values = np.empty((0,), dtype=float)
        source_indices = np.empty((0,), dtype=np.int64)

    return SourceSignal(
        values=values,
        source_indices=source_indices,
        source_rate_hz=float(frame_rate_hz),
        modality="video",
        channel_id=channel_id,
        source_index_name="frame",
    )
