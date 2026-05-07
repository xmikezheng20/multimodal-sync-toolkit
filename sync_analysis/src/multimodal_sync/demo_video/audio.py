"""Audio-track helpers for demo videos."""

from __future__ import annotations

import logging
import wave
from pathlib import Path

import numpy as np

from ..continuous import SessionSignal, map_source_signal_to_session_time
from ..modalities.audio import load_audio_source_segment
from .context import DemoSessionContext
from .timeline import SessionRenderTimeline

logger = logging.getLogger(__name__)


def load_audio_session_signal(
    *,
    context: DemoSessionContext,
    channel_id: str,
    sample_channel: int,
    clip_start_session_s: float,
    clip_end_session_s: float,
) -> SessionSignal:
    """Load one audio source channel over a session-time clip."""

    timebase = context.audio_timebase(channel_id)
    source_start_index, source_end_index = timebase.source_indices_for_window(
        clip_start_session_s,
        clip_end_session_s,
    )
    source_signal = load_audio_source_segment(
        file_info=context.audio_file_info(channel_id),
        audio_basepath=context.audio_basepath(channel_id),
        global_start_sample=source_start_index,
        global_end_sample=source_end_index,
        sample_rate_hz=context.audio_sample_rate_hz(),
        sample_channel=sample_channel,
        channel_id=channel_id,
    )
    return map_source_signal_to_session_time(source_signal, timebase)


def write_demo_audio_wav(
    *,
    context: DemoSessionContext,
    timeline: SessionRenderTimeline,
    audio_config: dict,
    output_wav_path: str | Path,
) -> Path:
    """Write a temporary WAV audio track for the demo clip."""

    output_wav_path = Path(output_wav_path)
    channel_id = str(audio_config["channel_id"])
    sample_channel = int(audio_config.get("sample_channel", 0))
    output_sample_rate_hz = int(audio_config.get("output_sample_rate_hz", 48000))
    normalize = bool(audio_config.get("normalize", True))

    logger.info("Preparing demo audio track")
    logger.info("  channel_id=%s sample_channel=%s", channel_id, sample_channel)
    logger.info("  output_sample_rate_hz=%s", output_sample_rate_hz)

    session_signal = load_audio_session_signal(
        context=context,
        channel_id=channel_id,
        sample_channel=sample_channel,
        clip_start_session_s=timeline.clip_start_session_s,
        clip_end_session_s=timeline.clip_end_session_s,
    )
    n_output_samples = max(1, int(np.ceil(timeline.output_duration_s * output_sample_rate_hz)))
    output_audio_times_s = np.arange(n_output_samples, dtype=float) / output_sample_rate_hz
    audio_sample_session_times_s = (
        timeline.clip_start_session_s + output_audio_times_s * timeline.playback_speed
    )
    audio_values = np.interp(
        audio_sample_session_times_s,
        session_signal.session_times_s,
        session_signal.values,
        left=0.0,
        right=0.0,
    )
    if normalize:
        peak = float(np.max(np.abs(audio_values))) if audio_values.size else 0.0
        if peak > 0:
            audio_values = 0.95 * audio_values / peak

    audio_int16 = np.asarray(np.clip(audio_values, -1.0, 1.0) * 32767, dtype="<i2")
    with wave.open(str(output_wav_path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(output_sample_rate_hz)
        wav_file.writeframes(audio_int16.tobytes())

    logger.info("Wrote temporary audio WAV: %s", output_wav_path)
    return output_wav_path
