"""Validate sync pulse consistency for one recorded session."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from multimodal_sync.config import load_config
from multimodal_sync.validation import validate_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate synchronization for one multimodal session.",
    )
    parser.add_argument(
        "-s",
        "--session",
        required=True,
        type=Path,
        help="Path to the session folder.",
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        help="Path to the session validation YAML config.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="Optional path for a validation log file.",
    )
    return parser.parse_args()


def configure_logging(log_file: Path | None) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, mode="w", encoding="utf-8"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )


def main() -> int:
    args = parse_args()
    configure_logging(args.log_file)
    logger = logging.getLogger(__name__)

    try:
        config = load_config(args.config)
        result = validate_session(session_basepath=args.session, config=config)
    except Exception:
        logger.exception("Session validation failed with an exception.")
        return 1

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())

