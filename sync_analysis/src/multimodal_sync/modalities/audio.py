"""Audio sync extraction helpers."""

from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from ..config import resolve_sync_detection_config
from ..continuous import SourceSignal
from ..files import require_files
from ..media_info import compute_audio_file_info, get_audio_num_channels
from ..models import PulseChannelResult
from ..segments import local_bounds_for_row, resolve_data_file, select_overlapping_files
from ..sync_pulses import detect_sync_pulses_from_chunks

logger = logging.getLogger(__name__)


def _require_soundfile():
    try:
        import soundfile as sf
    except ImportError as exc:
        raise ImportError(
            "Audio segment loading requires soundfile. Install the sync_analysis audio or all extra."
        ) from exc
    return sf


def iter_audio_lsb_chunks(
    wav_paths: list[Path],
    *,
    sample_channel: int,
    chunk_size_samples: int | None,
) -> Iterator[tuple[int, np.ndarray]]:
    """Yield global sample offsets and LSB chunks from one or more WAV files."""

    global_sample_start = 0
    for file_index, wav_path in enumerate(wav_paths, start=1):
        with wave.open(str(wav_path), "rb") as wav_file:
            sample_width = wav_file.getsampwidth()
            if sample_width != 2:
                raise ValueError(
                    f"Expected 16-bit WAV for LSB sync extraction, got "
                    f"{8 * sample_width}-bit file: {wav_path}"
                )
            n_channels = wav_file.getnchannels()
            if not 0 <= sample_channel < n_channels:
                raise ValueError(
                    f"sample_channel {sample_channel} is out of range for "
                    f"{n_channels}-channel file: {wav_path}"
                )
            total_frames = wav_file.getnframes()
            frames_remaining = total_frames
            read_size = chunk_size_samples or total_frames
            logger.info(
                "Reading audio sync file %s/%s: %s (%s samples, chunk_size_samples=%s)",
                file_index,
                len(wav_paths),
                wav_path.name,
                total_frames,
                chunk_size_samples,
            )

            chunk_index = 0
            while frames_remaining > 0:
                n_to_read = min(read_size, frames_remaining)
                raw = wav_file.readframes(n_to_read)
                if not raw:
                    break

                samples = np.frombuffer(raw, dtype="<i2")
                if n_channels > 1:
                    samples = samples.reshape(-1, n_channels)[:, sample_channel]
                lsb = (samples & 1) > 0
                chunk_start = global_sample_start
                yield chunk_start, lsb

                n_read = int(lsb.size)
                global_sample_start += n_read
                frames_remaining -= n_read
                chunk_index += 1
                if chunk_index == 1 or frames_remaining == 0 or chunk_index % 25 == 0:
                    logger.info(
                        "Read audio sync chunk %s from %s: global_samples=%s-%s",
                        chunk_index,
                        wav_path.name,
                        chunk_start,
                        global_sample_start - 1,
                    )


def validate_audio_channel(
    *,
    session_basepath: Path,
    audio_config: dict,
    channel_config: dict,
    sync_rate_hz: float,
) -> PulseChannelResult:
    """Validate one configured audio channel."""

    channel_id = str(channel_config["channel_id"])
    base_dir = str(audio_config.get("audio_base_dir", "raw_audio"))
    channel_dir = session_basepath / base_dir / channel_id
    wav_paths = require_files(channel_dir, ".wav")
    file_info = compute_audio_file_info(wav_paths)

    expected_sample_rate = int(audio_config["audio_file_sr"])
    observed_rates = sorted(set(int(v) for v in file_info["sample_rate"]))
    if observed_rates != [expected_sample_rate]:
        raise ValueError(
            f"Audio sample-rate mismatch for {channel_id}: expected "
            f"{expected_sample_rate}, found {observed_rates}"
        )

    sample_channel = int(channel_config.get("sample_channel", 0))
    first_n_channels = get_audio_num_channels(wav_paths[0])
    logger.info(
        "Audio channel %s: %s WAV file(s), sample_rate=%s Hz, sample_channel=%s/%s",
        channel_id,
        len(wav_paths),
        expected_sample_rate,
        sample_channel,
        first_n_channels,
    )

    default_chunk_size = expected_sample_rate * 60
    detection_config = resolve_sync_detection_config(
        channel_config,
        default_pulse_width_tolerance=0.01,
        default_infer_missing_pulses=True,
        default_chunk_size_samples=default_chunk_size,
    )
    logger.info(
        "Audio channel %s sync detection: tolerance=%s, infer_missing_pulses=%s, "
        "chunk_size_samples=%s",
        channel_id,
        detection_config.pulse_width_tolerance,
        detection_config.infer_missing_pulses,
        detection_config.chunk_size_samples,
    )

    pulse_result = detect_sync_pulses_from_chunks(
        iter_audio_lsb_chunks(
            wav_paths,
            sample_channel=sample_channel,
            chunk_size_samples=detection_config.chunk_size_samples,
        ),
        sample_rate_hz=expected_sample_rate,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=detection_config.pulse_width_tolerance,
        infer_missing_pulses=detection_config.infer_missing_pulses,
        chunk_size_samples=detection_config.chunk_size_samples,
    )
    diagnostics = dict(pulse_result.diagnostics)
    diagnostics.update(
        {
            "files": len(wav_paths),
            "total_samples": int(file_info["num_samples"].sum()),
            "sample_channel": sample_channel,
        }
    )

    return PulseChannelResult(
        modality="audio",
        channel_id=channel_id,
        sample_rate_hz=expected_sample_rate,
        sync_data=pulse_result.sync_data,
        file_info=file_info,
        diagnostics=diagnostics,
        output_subdir=("audio", channel_id),
        sync_data_filename="audio_sync_data.npy",
        file_info_filename="audio_file_info.csv",
    )


def load_audio_source_segment(
    *,
    file_info: pd.DataFrame,
    audio_basepath: str | Path,
    global_start_sample: int,
    global_end_sample: int,
    sample_rate_hz: float,
    sample_channel: int | None = None,
    modality: str = "audio",
    channel_id: str = "audio",
) -> SourceSignal:
    """Load an audio segment in channel-wide source sample coordinates."""

    if global_end_sample <= global_start_sample:
        raise ValueError("global_end_sample must be greater than global_start_sample")
    sf = _require_soundfile()

    selected = select_overlapping_files(
        file_info,
        global_start=global_start_sample,
        global_end=global_end_sample,
        start_col="sample_start",
        end_col="sample_end",
    )

    segments: list[np.ndarray] = []
    indices: list[np.ndarray] = []
    for _, row in selected.iterrows():
        local_start, local_end, clipped_start, clipped_end = local_bounds_for_row(
            row,
            global_start=global_start_sample,
            global_end=global_end_sample,
            start_col="sample_start",
            count_col="num_samples",
        )
        if local_end <= local_start:
            continue
        audio_path = resolve_data_file(audio_basepath, str(row["filename"]))
        data, observed_sr = sf.read(
            audio_path,
            start=local_start,
            frames=local_end - local_start,
            always_2d=False,
        )
        if int(round(observed_sr)) != int(round(sample_rate_hz)):
            raise ValueError(
                f"Audio sample-rate mismatch for {audio_path}: expected "
                f"{sample_rate_hz}, found {observed_sr}"
            )
        if sample_channel is not None and np.ndim(data) == 2:
            data = data[:, int(sample_channel)]
        elif sample_channel is not None and int(sample_channel) != 0:
            raise ValueError(
                f"sample_channel={sample_channel} requested for single-channel file {audio_path}"
            )

        segments.append(np.asarray(data))
        indices.append(np.arange(clipped_start, clipped_end, dtype=np.int64))

    if not segments:
        values = np.empty((0,), dtype=float)
        source_indices = np.empty((0,), dtype=np.int64)
    else:
        values = np.concatenate(segments, axis=0)
        source_indices = np.concatenate(indices)

    return SourceSignal(
        values=values,
        source_indices=source_indices,
        source_rate_hz=float(sample_rate_hz),
        modality=modality,
        channel_id=channel_id,
        source_index_name="sample",
    )
