"""Matplotlib renderer for demo video frames."""

from __future__ import annotations

import logging

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle

from .components import build_component
from .context import DemoSessionContext
from .timeline import SessionRenderTimeline

logger = logging.getLogger(__name__)


class DemoVideoRenderer:
    """Render configured visual components at session timepoints."""

    def __init__(
        self,
        *,
        context: DemoSessionContext,
        demo_video_config: dict,
        timeline: SessionRenderTimeline,
    ):
        self.context = context
        self.demo_video_config = demo_video_config
        self.timeline = timeline
        self.video_config = demo_video_config["video"]
        self.canvas_width_px = int(self.video_config["canvas_px"]["w"])
        self.canvas_height_px = int(self.video_config["canvas_px"]["h"])
        self.dpi = int(self.video_config.get("dpi", 100))

        self.figure = Figure(
            figsize=(self.canvas_width_px / self.dpi, self.canvas_height_px / self.dpi),
            dpi=self.dpi,
            facecolor=self.video_config.get("background_color", "white"),
        )
        self.canvas = FigureCanvasAgg(self.figure)
        self.components = []

        logger.info(
            "Initializing demo video renderer: %sx%s px, %s component(s)",
            self.canvas_width_px,
            self.canvas_height_px,
            len(self.video_config.get("components", [])),
        )
        for component_config in self.video_config.get("components", []):
            ax = self._add_component_axes(component_config)
            component = build_component(
                ax=ax,
                component_config=component_config,
                context=self.context,
                timeline=self.timeline,
            )
            self.components.append(component)
            logger.info(
                "  component id=%s type=%s",
                component_config.get("id", "<unnamed>"),
                component_config["type"],
            )

    def render_frame(self, session_time_s: float) -> np.ndarray:
        """Render one RGB frame for one session time."""

        for component in self.components:
            component.update(session_time_s)
        return figure_to_rgb(self.canvas)

    def close(self) -> None:
        """Release resources owned by visual components."""

        for component in self.components:
            component.close()
        self.figure.clear()

    def preview_frame(
        self,
        *,
        session_time_s: float,
        show_component_bounds: bool = False,
    ) -> np.ndarray:
        """Render one preview frame, optionally with component rectangles."""

        rgb = self.render_frame(session_time_s).copy()
        if show_component_bounds:
            rgb = draw_component_bounds(rgb, self.video_config.get("components", []))
        return rgb

    def _add_component_axes(self, component_config: dict):
        return self.figure.add_axes(
            rect_px_to_axes_bounds(
                component_config["rect_px"],
                canvas_width_px=self.canvas_width_px,
                canvas_height_px=self.canvas_height_px,
            )
        )


def rect_px_to_axes_bounds(
    rect_px: dict,
    *,
    canvas_width_px: int,
    canvas_height_px: int,
) -> list[float]:
    """Convert bottom-left pixel rectangle to Matplotlib axes bounds."""

    x = float(rect_px["x"]) / canvas_width_px
    y = float(rect_px["y"]) / canvas_height_px
    w = float(rect_px["w"]) / canvas_width_px
    h = float(rect_px["h"]) / canvas_height_px
    return [x, y, w, h]


def figure_to_rgb(canvas: FigureCanvasAgg) -> np.ndarray:
    """Render a Matplotlib canvas and return an RGB array."""

    canvas.draw()
    buffer = np.frombuffer(canvas.buffer_rgba(), dtype=np.uint8)
    height, width = canvas.get_width_height()[::-1]
    return buffer.reshape((height, width, 4))[..., :3].copy()


def draw_component_bounds(rgb: np.ndarray, components: list[dict]) -> np.ndarray:
    """Draw bottom-left component rectangles onto a rendered preview image."""

    # Use a throwaway Matplotlib figure so preview drawing does not mutate the renderer.
    height, width = rgb.shape[:2]
    fig = Figure(figsize=(width / 100, height / 100), dpi=100)
    canvas = FigureCanvasAgg(fig)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(rgb)
    ax.set_axis_off()
    for component_config in components:
        rect = component_config["rect_px"]
        x = rect["x"]
        # Matplotlib axes placement uses bottom-left coordinates, while RGB array
        # display uses top-left image coordinates.
        y = height - rect["y"] - rect["h"]
        ax.add_patch(
            Rectangle(
                (x, y),
                rect["w"],
                rect["h"],
                fill=False,
                edgecolor="red",
                linewidth=2,
            )
        )
    canvas.draw()
    buffer = np.frombuffer(canvas.buffer_rgba(), dtype=np.uint8)
    return buffer.reshape((height, width, 4))[..., :3].copy()
