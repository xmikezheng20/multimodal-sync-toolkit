"""Session context used by demo video components."""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import config_root, get_sync_rate_hz
from ..timebase import FrameTimebase, SyncTimebase

logger = logging.getLogger(__name__)


class DemoSessionContext:
    """Loaded session metadata and timebases for demo video rendering.

    Modality-specific readers live in their own modules. This context only
    resolves paths, file-info tables, and source-to-session timebases.
    """

    def __init__(self, *, session_basepath: str | Path, session_config: dict):
        self.session_basepath = Path(session_basepath)
        self.session_config = config_root(session_config)
        self.sync_rate_hz = get_sync_rate_hz(self.session_config)
        self.sync_basepath = self.session_basepath / "sync"
        self._audio_file_info: dict[str, pd.DataFrame] = {}
        self._video_file_info: dict[str, pd.DataFrame] = {}
        self._audio_timebases: dict[str, SyncTimebase] = {}

        logger.info("Loaded demo session context")
        logger.info("  session_basepath=%s", self.session_basepath)
        logger.info("  sync_rate_hz=%s", self.sync_rate_hz)

    @property
    def session_id(self) -> str:
        """Session folder name."""

        return self.session_basepath.name

    @property
    def audio_config(self) -> dict:
        return self.session_config.get("audio", {})

    @property
    def video_config(self) -> dict:
        return self.session_config.get("video", {})

    def audio_sample_rate_hz(self) -> float:
        """Return the configured audio sample rate."""

        return float(self.audio_config["audio_file_sr"])

    def video_frame_rate_hz(self) -> float:
        """Return the configured video frame rate."""

        return float(self.video_config["video_file_sr"])

    def audio_basepath(self, channel_id: str) -> Path:
        base_dir = self.audio_config.get("audio_base_dir", "raw_audio")
        return self.session_basepath / base_dir / channel_id

    def video_basepath(self, channel_id: str) -> Path:
        base_dir = self.video_config.get("video_base_dir", "raw_video")
        return self.session_basepath / base_dir / channel_id

    def audio_file_info(self, channel_id: str) -> pd.DataFrame:
        """Load audio file-info table for one source channel."""

        if channel_id not in self._audio_file_info:
            path = self.sync_basepath / "audio" / channel_id / "audio_file_info.csv"
            self._audio_file_info[channel_id] = pd.read_csv(path, index_col=0)
        return self._audio_file_info[channel_id]

    def video_file_info(self, channel_id: str) -> pd.DataFrame:
        """Load video file-info table for one source channel."""

        if channel_id not in self._video_file_info:
            path = self.sync_basepath / "video" / channel_id / "video_file_info.csv"
            self._video_file_info[channel_id] = pd.read_csv(path, index_col=0)
        return self._video_file_info[channel_id]

    def audio_timebase(self, channel_id: str) -> SyncTimebase:
        """Load source-to-session timebase for one audio source channel."""

        if channel_id not in self._audio_timebases:
            path = self.sync_basepath / "audio" / channel_id / "audio_sync_data.npy"
            self._audio_timebases[channel_id] = SyncTimebase.from_sync_data(
                np.load(path),
                source_rate_hz=self.audio_sample_rate_hz(),
                source_index_name="sample",
            )
        return self._audio_timebases[channel_id]

    def video_timebase(self, channel_id: str) -> FrameTimebase:
        """Return source-to-session timebase for one triggered video source channel."""

        _ = channel_id
        return FrameTimebase(sync_rate_hz=self.sync_rate_hz)

    def full_session_duration_s(self) -> float:
        """Estimate full sync-defined session duration from available sync data."""

        audio_channels = self.audio_config.get("channels", [])
        for channel_cfg in audio_channels:
            channel_id = str(channel_cfg["channel_id"])
            sync_path = self.sync_basepath / "audio" / channel_id / "audio_sync_data.npy"
            if sync_path.is_file():
                sync_data = np.load(sync_path)
                return float((sync_data[-1, 3] + 1) / self.sync_rate_hz)

        video_channels = self.video_config.get("channels", [])
        if video_channels:
            channel_id = str(video_channels[0]["channel_id"])
            file_info = self.video_file_info(channel_id)
            return float(file_info["frame_end"].max() / self.sync_rate_hz)

        raise ValueError("Could not estimate session duration: no audio or video sync data found")
