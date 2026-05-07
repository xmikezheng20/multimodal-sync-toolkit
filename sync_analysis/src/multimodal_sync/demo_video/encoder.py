"""ffmpeg encoding helpers for demo videos."""

from __future__ import annotations

import logging
import shutil
import sys
from pathlib import Path

import ffmpeg

from .renderer import DemoVideoRenderer
from .timeline import SessionRenderTimeline

logger = logging.getLogger(__name__)


def resolve_ffmpeg_binary() -> str:
    """Find an ffmpeg executable."""

    direct = shutil.which("ffmpeg")
    if direct is not None:
        return direct
    env_candidate = Path(sys.executable).resolve().parent / "ffmpeg"
    if env_candidate.is_file():
        return str(env_candidate)
    raise RuntimeError("ffmpeg executable not found")


def render_silent_video_mp4(
    *,
    renderer: DemoVideoRenderer,
    timeline: SessionRenderTimeline,
    output_video_path: str | Path,
    encoder_config: dict,
) -> Path:
    """Render visual frames to a temporary silent MP4."""

    output_video_path = Path(output_video_path)
    ffmpeg_bin = resolve_ffmpeg_binary()
    video_encoder_config = encoder_config.get("video", {})
    codec = video_encoder_config.get("codec", "libx264")
    pix_fmt = video_encoder_config.get("pix_fmt", "yuv420p")
    options = dict(video_encoder_config.get("options", {}))
    options.setdefault("preset", "medium")
    options.setdefault("crf", 23)

    in_video = ffmpeg.input(
        "pipe:0",
        format="rawvideo",
        pix_fmt="rgb24",
        s=f"{renderer.canvas_width_px}x{renderer.canvas_height_px}",
        r=timeline.output_fps,
    )
    output_options = {
        "vcodec": codec,
        "pix_fmt": pix_fmt,
        "r": timeline.output_fps,
        **options,
    }
    stream = ffmpeg.output(in_video, str(output_video_path), **output_options).overwrite_output()
    logger.info("Rendering silent video: %s", output_video_path)
    logger.info("ffmpeg command: %s", " ".join(stream.compile(cmd=ffmpeg_bin)))
    process = stream.run_async(cmd=ffmpeg_bin, pipe_stdin=True, pipe_stderr=True)
    assert process.stdin is not None

    try:
        for output_frame_index, session_time_s in enumerate(timeline.clip_frame_session_times_s):
            frame = renderer.render_frame(float(session_time_s))
            process.stdin.write(frame.tobytes())
            if output_frame_index == 0 or (output_frame_index + 1) % 100 == 0:
                logger.info(
                    "Rendered frame %s/%s at session_time_s=%.3f",
                    output_frame_index + 1,
                    timeline.n_output_frames,
                    session_time_s,
                )
    except BrokenPipeError as exc:
        stderr_text = _close_process_and_read_stderr(process)
        raise RuntimeError(f"ffmpeg pipe broke while rendering video: {stderr_text}") from exc

    stderr_text = _close_process_and_read_stderr(process)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg failed while rendering video: {stderr_text}")

    logger.info("Wrote temporary silent video: %s", output_video_path)
    return output_video_path


def mux_video_and_audio(
    *,
    video_path: str | Path,
    audio_path: str | Path | None,
    output_path: str | Path,
    encoder_config: dict,
    overwrite: bool,
) -> Path:
    """Mux temporary video and optional audio into the final output MP4."""

    video_path = Path(video_path)
    output_path = Path(output_path)
    ffmpeg_bin = resolve_ffmpeg_binary()
    in_video = ffmpeg.input(str(video_path))

    mux_options = dict(encoder_config.get("mux_options", {}))
    mux_options.setdefault("movflags", "+faststart")
    if audio_path is None:
        stream = ffmpeg.output(
            in_video,
            str(output_path),
            vcodec="copy",
            **mux_options,
        )
    else:
        audio_encoder_config = encoder_config.get("audio", {})
        audio_codec = audio_encoder_config.get("codec", "aac")
        audio_options = dict(audio_encoder_config.get("options", {}))
        in_audio = ffmpeg.input(str(audio_path))
        stream = ffmpeg.output(
            in_video.video,
            in_audio.audio,
            str(output_path),
            vcodec="copy",
            acodec=audio_codec,
            **audio_options,
            **mux_options,
        )

    if overwrite:
        stream = stream.overwrite_output()
    logger.info("Muxing final demo video: %s", output_path)
    logger.info("ffmpeg command: %s", " ".join(stream.compile(cmd=ffmpeg_bin)))
    _, stderr = stream.run(cmd=ffmpeg_bin, capture_stdout=True, capture_stderr=True)
    if stderr:
        logger.debug("ffmpeg stderr: %s", stderr.decode("utf-8", "replace").strip())
    logger.info("Wrote final demo video: %s", output_path)
    return output_path


def _close_process_and_read_stderr(process) -> str:
    if process.stdin and not process.stdin.closed:
        process.stdin.close()
    stderr_text = ""
    if process.stderr is not None:
        stderr_text = process.stderr.read().decode("utf-8", "replace")
    process.wait()
    return stderr_text.strip()
