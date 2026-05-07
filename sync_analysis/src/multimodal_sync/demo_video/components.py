"""Visual components for demo videos."""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .audio import load_audio_session_signal
from .context import DemoSessionContext
from .timeline import SessionRenderTimeline
from .video import SegmentedVideoFrameReader, process_frame_for_display


class DemoComponent(ABC):
    """Base class for components rendered against session time."""

    def __init__(
        self,
        *,
        ax,
        component_config: dict,
        context: DemoSessionContext,
        timeline: SessionRenderTimeline,
    ):
        self.ax = ax
        self.component_config = component_config
        self.context = context
        self.timeline = timeline
        self.component_id = str(component_config.get("id", component_config["type"]))
        self.init_static()

    @abstractmethod
    def init_static(self) -> None:
        """Create static artists once."""

    @abstractmethod
    def update(self, session_time_s: float) -> None:
        """Update dynamic artists for one session time."""

    def close(self) -> None:
        """Release resources owned by the component."""


class VideoComponent(DemoComponent):
    """Display one video source channel at the current session time."""

    def init_static(self) -> None:
        self.channel_id = str(self.component_config["channel_id"])
        self.processing = self.component_config.get("processing", {})
        self.video_timebase = self.context.video_timebase(self.channel_id)
        self.reader = SegmentedVideoFrameReader(
            file_info=self.context.video_file_info(self.channel_id),
            video_basepath=self.context.video_basepath(self.channel_id),
        )

        first_source_frame_index = self.video_timebase.session_time_to_frame(
            self.timeline.clip_start_session_s,
            round_index=True,
        )
        first_frame = self.reader.read_source_frame(first_source_frame_index)
        first_rgb = process_frame_for_display(first_frame, self.processing)

        self.image_artist = self.ax.imshow(first_rgb)
        self.ax.set_axis_off()
        if "title" in self.component_config:
            self.ax.set_title(str(self.component_config["title"]))

    def update(self, session_time_s: float) -> None:
        source_frame_index = self.video_timebase.session_time_to_frame(
            session_time_s,
            round_index=True,
        )
        frame = self.reader.read_source_frame(source_frame_index)
        self.image_artist.set_data(process_frame_for_display(frame, self.processing))

    def close(self) -> None:
        self.reader.close()


class AudioWaveformComponent(DemoComponent):
    """Display one audio source channel as a paged waveform in session time."""

    def init_static(self) -> None:
        self.channel_id = str(self.component_config["channel_id"])
        self.sample_channel = int(self.component_config.get("sample_channel", 0))
        self.page_duration_s = float(self.component_config.get("page_duration_s", 5.0))
        self.color = self.component_config.get("color", "tab:blue")
        self.max_plot_points = int(self.component_config.get("max_plot_points", 2000))
        self.current_page_start_session_s: float | None = None

        self.session_signal = load_audio_session_signal(
            context=self.context,
            channel_id=self.channel_id,
            sample_channel=self.sample_channel,
            clip_start_session_s=self.timeline.clip_start_session_s,
            clip_end_session_s=self.timeline.clip_end_session_s,
        )

        (self.waveform_line,) = self.ax.plot([], [], color=self.color)
        self.cursor_line = self.ax.axvline(
            self.timeline.clip_start_session_s,
            color=self.component_config.get("cursor_color", "black"),
            linewidth=float(self.component_config.get("cursor_linewidth", 1.0)),
        )
        self.ax.set_xlim(
            self.timeline.clip_start_session_s,
            self.timeline.clip_start_session_s + self.page_duration_s,
        )
        if "ylim" in self.component_config:
            self.ax.set_ylim(*self.component_config["ylim"])
        self.ax.set_xlabel("Session time (s)")
        self.ax.set_ylabel(self.component_config.get("ylabel", "Audio"))
        if "title" in self.component_config:
            self.ax.set_title(str(self.component_config["title"]))

    def update(self, session_time_s: float) -> None:
        page_start_session_s = self._page_start_for_session_time(session_time_s)
        page_end_session_s = page_start_session_s + self.page_duration_s
        if self.current_page_start_session_s != page_start_session_s:
            plot_times_s, plot_values = self._waveform_page(
                page_start_session_s,
                page_end_session_s,
            )
            self.waveform_line.set_data(plot_times_s, plot_values)
            self.ax.set_xlim(page_start_session_s, page_end_session_s)
            self.current_page_start_session_s = page_start_session_s
        self.cursor_line.set_xdata([session_time_s, session_time_s])

    def _page_start_for_session_time(self, session_time_s: float) -> float:
        offset_s = max(0.0, session_time_s - self.timeline.clip_start_session_s)
        page_index = int(np.floor(offset_s / self.page_duration_s))
        return self.timeline.clip_start_session_s + page_index * self.page_duration_s

    def _waveform_page(
        self,
        page_start_session_s: float,
        page_end_session_s: float,
    ) -> tuple[np.ndarray, np.ndarray]:
        mask = (
            (self.session_signal.session_times_s >= page_start_session_s)
            & (self.session_signal.session_times_s < page_end_session_s)
        )
        session_times_s = self.session_signal.session_times_s[mask]
        values = self.session_signal.values[mask]
        if session_times_s.size == 0:
            return np.asarray([page_start_session_s, page_end_session_s]), np.asarray([0.0, 0.0])
        return waveform_envelope_for_plot(
            session_times_s,
            values,
            page_start_session_s=page_start_session_s,
            page_end_session_s=page_end_session_s,
            max_plot_points=self.max_plot_points,
        )


def waveform_envelope_for_plot(
    session_times_s: np.ndarray,
    values: np.ndarray,
    *,
    page_start_session_s: float,
    page_end_session_s: float,
    max_plot_points: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Downsample dense waveform data into a min/max envelope for plotting."""

    session_times_s = np.asarray(session_times_s)
    values = np.asarray(values)
    if session_times_s.size <= max_plot_points:
        return session_times_s, values

    n_bins = max(1, max_plot_points // 2)
    bin_edges = np.linspace(page_start_session_s, page_end_session_s, n_bins + 1)
    bin_ids = np.searchsorted(bin_edges, session_times_s, side="right") - 1
    bin_ids = np.clip(bin_ids, 0, n_bins - 1)

    plot_times: list[float] = []
    plot_values: list[float] = []
    for bin_id in range(n_bins):
        bin_values = values[bin_ids == bin_id]
        if bin_values.size == 0:
            continue
        bin_center = 0.5 * (bin_edges[bin_id] + bin_edges[bin_id + 1])
        plot_times.extend([bin_center, bin_center])
        plot_values.extend([float(np.min(bin_values)), float(np.max(bin_values))])

    return np.asarray(plot_times), np.asarray(plot_values)


def build_component(
    *,
    ax,
    component_config: dict,
    context: DemoSessionContext,
    timeline: SessionRenderTimeline,
) -> DemoComponent:
    """Instantiate a visual component from config."""

    component_type = component_config["type"]
    if component_type == "video":
        return VideoComponent(
            ax=ax,
            component_config=component_config,
            context=context,
            timeline=timeline,
        )
    if component_type == "audio_waveform":
        return AudioWaveformComponent(
            ax=ax,
            component_config=component_config,
            context=context,
            timeline=timeline,
        )
    raise ValueError(f"Unknown demo video component type: {component_type}")
