"""Intan digital input sync extraction helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

import numpy as np

from ..config import resolve_sync_detection_config
from ..files import require_directory
from ..media_info import compute_intan_file_info
from ..models import PulseChannelResult
from ..sync_pulses import detect_sync_pulses_from_chunks

logger = logging.getLogger(__name__)


def find_intan_recording_dir(
    intan_basepath: Path,
    recording_name: str | None = None,
) -> Path:
    """Find the Intan recording folder under a raw Intan base path."""

    intan_basepath = require_directory(intan_basepath)
    if recording_name:
        return require_directory(intan_basepath / recording_name)

    recording_dirs = sorted(p for p in intan_basepath.iterdir() if p.is_dir())
    if len(recording_dirs) != 1:
        raise ValueError(
            f"Expected exactly one Intan recording folder in {intan_basepath}, "
            f"found {len(recording_dirs)}"
        )
    return recording_dirs[0]


def iter_intan_digital_chunks(
    digitalin_path: Path,
    *,
    channel_id: int,
    chunk_size_samples: int | None,
) -> Iterator[tuple[int, np.ndarray]]:
    """Yield global sample offsets and one Intan digital input channel."""

    if not 0 <= channel_id <= 15:
        raise ValueError(f"Intan digital channel must be 0-15, got {channel_id}")

    if chunk_size_samples is None:
        logger.info("Reading full Intan digital input file: %s", digitalin_path.name)
        words = np.fromfile(digitalin_path, dtype=np.uint16)
        logger.info("Read Intan digital input file: %s samples", words.size)
        yield 0, (words & (1 << channel_id)) > 0
        return

    global_sample_start = 0
    bytes_to_read = int(chunk_size_samples) * np.dtype(np.uint16).itemsize
    chunk_index = 0
    logger.info(
        "Reading Intan digital input file in chunks: %s (chunk_size_samples=%s)",
        digitalin_path.name,
        chunk_size_samples,
    )
    with digitalin_path.open("rb") as stream:
        while True:
            raw = stream.read(bytes_to_read)
            if not raw:
                break
            words = np.frombuffer(raw, dtype=np.uint16)
            chunk_start = global_sample_start
            yield global_sample_start, (words & (1 << channel_id)) > 0
            global_sample_start += int(words.size)
            chunk_index += 1
            if chunk_index == 1 or chunk_index % 50 == 0:
                logger.info(
                    "Read Intan digital chunk %s: global_samples=%s-%s",
                    chunk_index,
                    chunk_start,
                    global_sample_start - 1,
                )
    logger.info(
        "Finished reading Intan digital input chunks: %s chunks, %s samples",
        chunk_index,
        global_sample_start,
    )


def validate_intan_digital_channel(
    *,
    session_basepath: Path,
    intan_config: dict,
    channel_config: dict,
    sync_rate_hz: float,
) -> PulseChannelResult:
    """Validate one configured Intan digital input channel."""

    channel_id = int(channel_config["channel_id"])
    base_dir = str(intan_config.get("intan_base_dir", "raw_intan"))
    recording_name = intan_config.get("recording_name")
    recording_dir = find_intan_recording_dir(session_basepath / base_dir, recording_name)
    digitalin_path = recording_dir / "digitalin.dat"
    if not digitalin_path.is_file():
        raise FileNotFoundError(f"Intan digitalin.dat not found: {digitalin_path}")

    sample_rate_hz = int(intan_config["intan_file_sr"])
    n_samples = digitalin_path.stat().st_size // np.dtype(np.uint16).itemsize
    file_info = compute_intan_file_info(recording_dir, n_samples)

    detection_config = resolve_sync_detection_config(
        channel_config,
        default_pulse_width_tolerance=0.01,
        default_infer_missing_pulses=False,
        default_chunk_size_samples=None,
    )
    logger.info(
        "Intan digital channel %s: recording=%s, samples=%s, sample_rate=%s Hz",
        channel_id,
        recording_dir.name,
        n_samples,
        sample_rate_hz,
    )
    logger.info(
        "Intan channel %s sync detection: tolerance=%s, infer_missing_pulses=%s, "
        "chunk_size_samples=%s",
        channel_id,
        detection_config.pulse_width_tolerance,
        detection_config.infer_missing_pulses,
        detection_config.chunk_size_samples,
    )

    pulse_result = detect_sync_pulses_from_chunks(
        iter_intan_digital_chunks(
            digitalin_path,
            channel_id=channel_id,
            chunk_size_samples=detection_config.chunk_size_samples,
        ),
        sample_rate_hz=sample_rate_hz,
        sync_rate_hz=sync_rate_hz,
        pulse_width_tolerance=detection_config.pulse_width_tolerance,
        infer_missing_pulses=detection_config.infer_missing_pulses,
        chunk_size_samples=detection_config.chunk_size_samples,
    )
    diagnostics = dict(pulse_result.diagnostics)
    diagnostics.update(
        {
            "recording_dir": recording_dir.name,
            "total_samples": int(n_samples),
            "digital_channel_id": channel_id,
        }
    )

    return PulseChannelResult(
        modality="intan",
        channel_id=str(channel_id),
        sample_rate_hz=sample_rate_hz,
        sync_data=pulse_result.sync_data,
        file_info=file_info,
        diagnostics=diagnostics,
        output_subdir=("intan", f"digital_channel_{channel_id}"),
        sync_data_filename="intan_sync_data.npy",
        file_info_filename="intan_file_info.csv",
    )
