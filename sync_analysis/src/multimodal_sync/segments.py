"""Helpers for selecting ranges from segmented acquisition files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def select_overlapping_files(
    file_info: pd.DataFrame,
    *,
    global_start: int,
    global_end: int,
    start_col: str,
    end_col: str,
) -> pd.DataFrame:
    """Select file-info rows overlapping a half-open global index window."""

    if global_end <= global_start:
        raise ValueError("global_end must be greater than global_start")
    required = {start_col, end_col, "filename"}
    missing = required - set(file_info.columns)
    if missing:
        raise ValueError(f"file_info missing required columns: {sorted(missing)}")

    mask = (file_info[end_col] > global_start) & (file_info[start_col] < global_end)
    return file_info.loc[mask].sort_values(start_col)


def local_bounds_for_row(
    row: pd.Series,
    *,
    global_start: int,
    global_end: int,
    start_col: str,
    count_col: str,
) -> tuple[int, int, int, int]:
    """Return local and clipped global bounds for one file-info row."""

    file_start = int(row[start_col])
    count = int(row[count_col])
    file_end = file_start + count
    clipped_start = max(global_start, file_start)
    clipped_end = min(global_end, file_end)
    local_start = clipped_start - file_start
    local_end = clipped_end - file_start
    return local_start, local_end, clipped_start, clipped_end


def resolve_data_file(basepath: str | Path, filename: str) -> Path:
    """Resolve a file-info filename against a data directory.

    The exact filename is preferred. If it is not present, files sharing the
    same stem are accepted so file-info tables can omit or normalize suffixes.
    """

    basepath = Path(basepath)
    exact = basepath / filename
    if exact.is_file():
        return exact

    stem = Path(filename).stem
    matches = sorted(p for p in basepath.glob(f"{stem}*") if p.is_file())
    if not matches:
        raise FileNotFoundError(f"Could not resolve {filename!r} under {basepath}")
    return matches[0]
