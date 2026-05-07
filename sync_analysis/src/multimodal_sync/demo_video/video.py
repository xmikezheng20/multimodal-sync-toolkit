"""Video reading helpers for demo video rendering."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..media_info import _require_cv2
from ..segments import resolve_data_file, select_overlapping_files


class SegmentedVideoFrameReader:
    """Read source frames from a segmented video channel."""

    def __init__(self, *, file_info: pd.DataFrame, video_basepath: str | Path):
        self.file_info = file_info.sort_values("frame_start").reset_index(drop=True)
        self.video_basepath = Path(video_basepath)
        self.cv2 = _require_cv2()
        self._current_frame_start: int | None = None
        self._current_frame_end: int | None = None
        self._current_next_source_frame: int | None = None
        self._cap = None

    def close(self) -> None:
        """Close any open video file."""

        if self._cap is not None:
            self._cap.release()
        self._cap = None
        self._current_frame_start = None
        self._current_frame_end = None
        self._current_next_source_frame = None

    def __del__(self) -> None:
        self.close()

    def read_source_frame(self, source_frame_index: int) -> np.ndarray:
        """Read one channel-wide source frame."""

        source_frame_index = int(source_frame_index)
        if not self._current_file_contains(source_frame_index):
            row = self._row_for_source_frame(source_frame_index)
            self._open_row(row)

        assert self._cap is not None
        assert self._current_frame_start is not None
        local_frame_index = source_frame_index - self._current_frame_start
        if self._current_next_source_frame != source_frame_index:
            self._cap.set(self.cv2.CAP_PROP_POS_FRAMES, local_frame_index)

        ok, frame = self._cap.read()
        if not ok:
            raise OSError(f"Could not read source frame {source_frame_index}")
        self._current_next_source_frame = source_frame_index + 1
        return frame

    def _current_file_contains(self, source_frame_index: int) -> bool:
        if self._cap is None:
            return False
        assert self._current_frame_start is not None
        assert self._current_frame_end is not None
        return self._current_frame_start <= source_frame_index < self._current_frame_end

    def _row_for_source_frame(self, source_frame_index: int) -> pd.Series:
        selected = select_overlapping_files(
            self.file_info,
            global_start=source_frame_index,
            global_end=source_frame_index + 1,
            start_col="frame_start",
            end_col="frame_end",
        )
        if selected.empty:
            raise IndexError(f"source_frame_index {source_frame_index} is outside video range")
        return selected.iloc[0]

    def _open_row(self, row: pd.Series) -> None:
        self.close()
        video_path = resolve_data_file(self.video_basepath, str(row["filename"]))
        cap = self.cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise OSError(f"Could not open video file: {video_path}")
        self._cap = cap
        self._current_frame_start = int(row["frame_start"])
        self._current_frame_end = int(row["frame_end"])
        self._current_next_source_frame = self._current_frame_start


def process_frame_for_display(frame_bgr: np.ndarray, processing: dict | None = None) -> np.ndarray:
    """Apply lightweight display processing and return RGB image data."""

    processing = processing or {}
    frame = frame_bgr

    if "crop" in processing:
        crop = processing["crop"]
        x = int(crop["x"])
        y = int(crop["y"])
        w = int(crop["w"])
        h = int(crop["h"])
        frame = frame[y : y + h, x : x + w]

    if "brightness" in processing or "contrast" in processing:
        cv2 = _require_cv2()
        alpha = float(processing.get("contrast", 1.0))
        beta = float(processing.get("brightness", 0.0))
        frame = cv2.convertScaleAbs(frame, alpha=alpha, beta=beta)

    cv2 = _require_cv2()
    if processing.get("colorspace", "rgb") == "gray":
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return np.stack([gray, gray, gray], axis=-1)
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
