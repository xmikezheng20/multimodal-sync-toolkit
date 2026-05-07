"""Media metadata helpers used by session validation."""

from __future__ import annotations

import wave
from pathlib import Path
from typing import Iterable

import pandas as pd


def count_audio_samples(path: str | Path) -> int:
    """Count audio sample frames in a WAV file."""

    with wave.open(str(path), "rb") as wav_file:
        return int(wav_file.getnframes())


def get_audio_sample_rate(path: str | Path) -> int:
    """Read the sampling rate from a WAV file."""

    with wave.open(str(path), "rb") as wav_file:
        return int(wav_file.getframerate())


def get_audio_num_channels(path: str | Path) -> int:
    """Read the number of channels from a WAV file."""

    with wave.open(str(path), "rb") as wav_file:
        return int(wav_file.getnchannels())


def compute_audio_file_info(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Create per-file sample offsets for a sequence of WAV files."""

    rows = []
    sample_start = 0
    for path_like in paths:
        path = Path(path_like)
        num_samples = count_audio_samples(path)
        sample_end = sample_start + num_samples
        rows.append(
            {
                "filename": path.name,
                "sample_start": sample_start,
                "sample_end": sample_end,
                "num_samples": num_samples,
                "sample_rate": get_audio_sample_rate(path),
                "num_channels": get_audio_num_channels(path),
            }
        )
        sample_start = sample_end
    return pd.DataFrame(rows)


def _require_cv2():
    try:
        import cv2
    except ImportError as exc:
        raise ImportError(
            "Video validation requires opencv-python-headless. "
            "Install the sync_analysis video or all extra."
        ) from exc
    return cv2


def count_video_frames(path: str | Path) -> int:
    """Count frames in a video file with OpenCV metadata."""

    cv2 = _require_cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise OSError(f"Could not open video file: {path}")
    try:
        return int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    finally:
        cap.release()


def get_video_fps(path: str | Path) -> float:
    """Read video FPS with OpenCV metadata."""

    cv2 = _require_cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise OSError(f"Could not open video file: {path}")
    try:
        return float(cap.get(cv2.CAP_PROP_FPS))
    finally:
        cap.release()


def compute_video_file_info(paths: Iterable[str | Path]) -> pd.DataFrame:
    """Create per-file frame offsets for a sequence of video files."""

    rows = []
    frame_start = 0
    for path_like in paths:
        path = Path(path_like)
        num_frames = count_video_frames(path)
        frame_end = frame_start + num_frames
        rows.append(
            {
                "filename": path.name,
                "frame_start": frame_start,
                "frame_end": frame_end,
                "num_frames": num_frames,
                "fps": get_video_fps(path),
            }
        )
        frame_start = frame_end
    return pd.DataFrame(rows)


def compute_intan_file_info(recording_dir: str | Path, num_samples: int) -> pd.DataFrame:
    """Create one Intan digital input file-info row."""

    recording_dir = Path(recording_dir)
    return pd.DataFrame(
        [
            {
                "dirname": recording_dir.name,
                "sample_start": 0,
                "sample_end": int(num_samples),
                "num_samples": int(num_samples),
            }
        ]
    )

