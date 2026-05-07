"""Video frame-count validation helpers."""

from __future__ import annotations

import logging
from pathlib import Path

from ..files import require_files
from ..media_info import compute_video_file_info
from ..models import FrameChannelResult

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

