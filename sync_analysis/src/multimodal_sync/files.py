"""Filesystem helpers for session validation."""

from __future__ import annotations

from pathlib import Path


def require_directory(path: str | Path) -> Path:
    """Return `path` as a Path if it exists and is a directory."""

    resolved = Path(path)
    if not resolved.is_dir():
        raise FileNotFoundError(f"Directory not found: {resolved}")
    return resolved


def list_files(path: str | Path, suffix: str | tuple[str, ...]) -> list[Path]:
    """List files in `path` with a suffix or suffix tuple."""

    base = require_directory(path)
    suffixes = (suffix,) if isinstance(suffix, str) else suffix
    suffixes = tuple(s.lower() for s in suffixes)
    return sorted(
        p for p in base.iterdir() if p.is_file() and p.suffix.lower() in suffixes
    )


def require_files(path: str | Path, suffix: str | tuple[str, ...]) -> list[Path]:
    """List matching files and raise if none are found."""

    files = list_files(path, suffix)
    if not files:
        raise FileNotFoundError(f"No {suffix} files found in: {path}")
    return files


def ensure_directory(path: str | Path) -> Path:
    """Create `path` if needed and return it as a Path."""

    resolved = Path(path)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved

