"""Timeline helpers for session-time-native demo videos."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SessionRenderTimeline:
    """Mapping from output video frames to session time."""

    clip_start_session_s: float
    clip_end_session_s: float
    output_fps: float
    playback_speed: float = 1.0

    def __post_init__(self) -> None:
        if self.clip_end_session_s <= self.clip_start_session_s:
            raise ValueError("clip_end_session_s must be greater than clip_start_session_s")
        if self.output_fps <= 0:
            raise ValueError("output_fps must be positive")
        if self.playback_speed <= 0:
            raise ValueError("playback_speed must be positive")

    @property
    def clip_duration_session_s(self) -> float:
        """Duration of the selected demo clip measured on the session clock."""

        return float(self.clip_end_session_s - self.clip_start_session_s)

    @property
    def output_duration_s(self) -> float:
        """Duration of the rendered video file."""

        return float(self.clip_duration_session_s / self.playback_speed)

    @property
    def n_output_frames(self) -> int:
        """Number of output frames to render."""

        return max(1, int(np.ceil(self.output_duration_s * self.output_fps)))

    @property
    def output_frame_times_s(self) -> np.ndarray:
        """Output video frame times in seconds from the start of the rendered file."""

        return np.arange(self.n_output_frames, dtype=float) / float(self.output_fps)

    @property
    def clip_frame_session_times_s(self) -> np.ndarray:
        """Session times sampled by each output video frame."""

        return self.clip_start_session_s + self.output_frame_times_s * self.playback_speed

    def to_dict(self) -> dict[str, float | int]:
        """Return compact metadata for logs."""

        return {
            "clip_start_session_s": self.clip_start_session_s,
            "clip_end_session_s": self.clip_end_session_s,
            "clip_duration_session_s": self.clip_duration_session_s,
            "output_fps": self.output_fps,
            "playback_speed": self.playback_speed,
            "output_duration_s": self.output_duration_s,
            "n_output_frames": self.n_output_frames,
        }
