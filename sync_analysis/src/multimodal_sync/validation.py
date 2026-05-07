"""Session validation coordinator."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import config_root, get_sync_rate_hz
from .files import ensure_directory, require_directory
from .modalities.audio import validate_audio_channel
from .modalities.intan import validate_intan_digital_channel
from .modalities.video import validate_video_channel
from .models import FrameChannelResult, PulseChannelResult, ValidationResult

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_json_safe(v) for v in value]
    return value


def _result_output_dir(sync_dir: Path, result: PulseChannelResult | FrameChannelResult) -> Path:
    return ensure_directory(sync_dir.joinpath(*result.output_subdir))


def write_result_outputs(
    sync_dir: Path,
    result: PulseChannelResult | FrameChannelResult,
) -> None:
    """Write one channel result to the sync folder."""

    output_dir = _result_output_dir(sync_dir, result)
    result.file_info.to_csv(output_dir / result.file_info_filename)
    logger.info("Saved file info: %s", output_dir / result.file_info_filename)

    if isinstance(result, PulseChannelResult):
        np.save(output_dir / result.sync_data_filename, result.sync_data)
        logger.info("Saved sync data: %s", output_dir / result.sync_data_filename)


def build_counts_table(
    pulse_results: list[PulseChannelResult],
    frame_results: list[FrameChannelResult],
) -> pd.DataFrame:
    """Build the modality count comparison table."""

    rows = []
    for result in pulse_results:
        rows.append(
            {
                "modality": result.modality,
                "channel_id": result.channel_id,
                "count_type": "sync_pulses",
                "validation_count": result.validation_count,
            }
        )
    for result in frame_results:
        rows.append(
            {
                "modality": result.modality,
                "channel_id": result.channel_id,
                "count_type": "frames",
                "validation_count": result.validation_count,
            }
        )
    return pd.DataFrame(rows)


def build_pulse_diagnostics_table(
    pulse_results: list[PulseChannelResult],
) -> pd.DataFrame:
    """Build a flat diagnostics table for all pulse channels."""

    rows = []
    for result in pulse_results:
        row = {
            "modality": result.modality,
            "channel_id": result.channel_id,
        }
        row.update(result.diagnostics)
        rows.append(row)
    return pd.DataFrame(rows)


def _counts_match(counts: pd.DataFrame) -> bool:
    if counts.empty:
        return False
    return counts["validation_count"].nunique() == 1


def validate_session(
    *,
    session_basepath: str | Path,
    config: dict[str, Any],
    overwrite: bool = True,
) -> ValidationResult:
    """Validate sync consistency for one recorded session."""

    session_path = require_directory(session_basepath)
    root = config_root(config)
    sync_rate_hz = get_sync_rate_hz(root)
    sync_dir = ensure_directory(session_path / "sync")

    logger.info("Validating session: %s", session_path)
    logger.info("Global session sync rate: %s Hz", sync_rate_hz)
    logger.info("Sync outputs will be written to: %s", sync_dir)
    if not overwrite and any(sync_dir.iterdir()):
        raise FileExistsError(f"Sync directory is not empty and overwrite=False: {sync_dir}")

    pulse_results: list[PulseChannelResult] = []
    frame_results: list[FrameChannelResult] = []

    audio_config = root.get("audio")
    if audio_config:
        logger.info("Processing audio channels")
        for channel_config in audio_config.get("channels", []):
            if not channel_config.get("contains_sync_signal", False):
                logger.info(
                    "Skipping audio channel %s because contains_sync_signal is false",
                    channel_config.get("channel_id"),
                )
                continue
            result = validate_audio_channel(
                session_basepath=session_path,
                audio_config=audio_config,
                channel_config=channel_config,
                sync_rate_hz=sync_rate_hz,
            )
            pulse_results.append(result)
            write_result_outputs(sync_dir, result)
            log_pulse_result(result)

    video_config = root.get("video")
    if video_config:
        logger.info("Processing video channels")
        for channel_config in video_config.get("channels", []):
            result = validate_video_channel(
                session_basepath=session_path,
                video_config=video_config,
                channel_config=channel_config,
            )
            frame_results.append(result)
            write_result_outputs(sync_dir, result)

    intan_config = root.get("intan")
    if intan_config:
        logger.info("Processing Intan digital channels")
        for channel_config in intan_config.get("digital_channels", []):
            if not channel_config.get("contains_sync_signal", False):
                logger.info(
                    "Skipping Intan digital channel %s because contains_sync_signal is false",
                    channel_config.get("channel_id"),
                )
                continue
            result = validate_intan_digital_channel(
                session_basepath=session_path,
                intan_config=intan_config,
                channel_config=channel_config,
                sync_rate_hz=sync_rate_hz,
            )
            pulse_results.append(result)
            write_result_outputs(sync_dir, result)
            log_pulse_result(result)

    counts = build_counts_table(pulse_results, frame_results)
    diagnostics = build_pulse_diagnostics_table(pulse_results)
    success = _counts_match(counts)

    counts.to_csv(sync_dir / "validation_counts.csv", index=False)
    diagnostics.to_csv(sync_dir / "pulse_diagnostics.csv", index=False)
    logger.info("Saved validation counts: %s", sync_dir / "validation_counts.csv")
    logger.info("Saved pulse diagnostics: %s", sync_dir / "pulse_diagnostics.csv")
    write_summary_json(
        sync_dir / "validation_summary.json",
        session_path=session_path,
        sync_rate_hz=sync_rate_hz,
        counts=counts,
        diagnostics=diagnostics,
        success=success,
    )
    log_count_comparison(counts, success)

    return ValidationResult(
        session_basepath=str(session_path),
        sync_rate_hz=sync_rate_hz,
        pulse_channels=pulse_results,
        frame_channels=frame_results,
        counts=counts,
        pulse_diagnostics=diagnostics,
        success=success,
    )


def log_pulse_result(result: PulseChannelResult) -> None:
    """Log a compact human-readable pulse-channel summary."""

    d = result.diagnostics
    logger.info(
        "%s %s sync pulses: candidates=%s, valid=%s, rejected=%s, "
        "inferred_count=%s, missing_inferred=%s",
        result.modality,
        result.channel_id,
        d.get("candidate_pulses"),
        d.get("valid_pulses"),
        d.get("rejected_pulses"),
        d.get("inferred_pulse_count"),
        d.get("missing_inferred_pulses"),
    )
    logger.info(
        "%s %s sync settings: sample_rate=%s Hz, sync_rate=%s Hz, "
        "pulse_width_tolerance=%s, infer_missing_pulses=%s, chunk_size_samples=%s",
        result.modality,
        result.channel_id,
        d.get("sample_rate_hz"),
        d.get("sync_rate_hz"),
        d.get("pulse_width_tolerance"),
        d.get("infer_missing_pulses"),
        d.get("chunk_size_samples"),
    )
    logger.info(
        "%s %s nominal-rate timing: first=%s s, last=%s s, "
        "median_interval=%s s, min_interval=%s s, max_interval=%s s",
        result.modality,
        result.channel_id,
        d.get("first_rising_time_nominal_s"),
        d.get("last_rising_time_nominal_s"),
        d.get("median_interval_nominal_s"),
        d.get("min_interval_nominal_s"),
        d.get("max_interval_nominal_s"),
    )
    logger.info(
        "%s %s sample-space timing: first_rising_sample=%s, last_rising_sample=%s, "
        "median_interval_samples=%s, min_interval_samples=%s, max_interval_samples=%s, "
        "median_pulse_width_samples=%s",
        result.modality,
        result.channel_id,
        d.get("first_rising_sample"),
        d.get("last_rising_sample"),
        d.get("median_interval_samples"),
        d.get("min_interval_samples"),
        d.get("max_interval_samples"),
        d.get("median_pulse_width_samples"),
    )

    rejected = int(d.get("rejected_pulses") or 0)
    missing = int(d.get("missing_inferred_pulses") or 0)
    nonunit = int(d.get("nonunit_intervals") or 0)
    interval_deviation = int(d.get("interval_deviation_count") or 0)
    infer_missing = bool(d.get("infer_missing_pulses"))

    if rejected:
        logger.warning(
            "%s %s rejected %s candidate pulse(s) by pulse-width tolerance.",
            result.modality,
            result.channel_id,
            rejected,
        )
    if missing and infer_missing:
        logger.warning(
            "%s %s inferred %s missing sync pulse(s) from %s non-unit interval(s).",
            result.modality,
            result.channel_id,
            missing,
            nonunit,
        )
    elif nonunit and not infer_missing:
        logger.warning(
            "%s %s detected %s non-unit interval(s), but missing-pulse inference is disabled.",
            result.modality,
            result.channel_id,
            nonunit,
        )
    if interval_deviation:
        logger.warning(
            "%s %s had %s interval(s) deviating by more than 10%% of the expected sync interval.",
            result.modality,
            result.channel_id,
            interval_deviation,
        )


def log_count_comparison(counts: pd.DataFrame, success: bool) -> None:
    """Log final cross-modality count comparison."""

    logger.info("Validation count comparison:")
    for _, row in counts.iterrows():
        logger.info(
            "  %s:%s %s = %s",
            row["modality"],
            row["channel_id"],
            row["count_type"],
            row["validation_count"],
        )
    if success:
        logger.info("Session validation passed: all validation counts match.")
    else:
        logger.error("Session validation failed: validation counts do not match.")


def write_summary_json(
    path: Path,
    *,
    session_path: Path,
    sync_rate_hz: float,
    counts: pd.DataFrame,
    diagnostics: pd.DataFrame,
    success: bool,
) -> None:
    """Write a compact JSON validation summary."""

    summary = {
        "session_basepath": str(session_path),
        "sync_rate_hz": sync_rate_hz,
        "success": bool(success),
        "counts": counts.to_dict(orient="records"),
        "pulse_diagnostics": diagnostics.to_dict(orient="records"),
    }
    path.write_text(json.dumps(_json_safe(summary), indent=2), encoding="utf-8")
    logger.info("Saved validation summary: %s", path)
