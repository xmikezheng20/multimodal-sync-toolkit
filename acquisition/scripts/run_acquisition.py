"""Launch Bonsai and ffmpeg for triggered video acquisition.

The script starts a Bonsai workflow that writes raw camera frames to Windows
named pipes, then starts one ffmpeg process per enabled camera to encode those
frames on the fly.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WINDOWS_PIPE_PREFIX = "\\\\.\\pipe\\"
PIPE_POLL_INTERVAL_S = 0.1


def path_environment_key(env: dict[str, str]) -> str:
    for key in env:
        if key.upper() == "PATH":
            return key
    return "PATH"


def path_list_separator(path_value: str) -> str:
    if os.name == "nt":
        return ";"
    if ";" in path_value and any(
        len(entry) >= 2 and entry[1] == ":" for entry in path_value.split(";")
    ):
        return ";"
    return os.pathsep


def normalized_path_string(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").lower()


def is_under_prefix(path_entry: str, prefix: str) -> bool:
    entry = normalized_path_string(path_entry)
    root = normalized_path_string(prefix)
    return entry == root or entry.startswith(root + "/")


def conda_prefixes(env: dict[str, str]) -> list[str]:
    prefixes = []
    for key, value in env.items():
        if key.upper().startswith("CONDA_PREFIX") and value:
            prefixes.append(value)
    return sorted(set(prefixes), key=len, reverse=True)


def build_bonsai_environment(env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a subprocess environment for Bonsai without active conda DLL paths."""

    bonsai_env = dict(os.environ if env is None else env)
    prefixes = conda_prefixes(bonsai_env)
    if not prefixes:
        return bonsai_env

    path_key = path_environment_key(bonsai_env)
    separator = path_list_separator(bonsai_env.get(path_key, ""))
    path_entries = bonsai_env.get(path_key, "").split(separator)
    clean_entries = [
        entry
        for entry in path_entries
        if entry and not any(is_under_prefix(entry, prefix) for prefix in prefixes)
    ]
    bonsai_env[path_key] = separator.join(clean_entries)
    return bonsai_env


def count_removed_conda_path_entries(
    original_env: dict[str, str],
    clean_env: dict[str, str],
) -> int:
    path_key = path_environment_key(original_env)
    separator = path_list_separator(original_env.get(path_key, ""))
    original_entries = [
        entry for entry in original_env.get(path_key, "").split(separator) if entry
    ]
    clean_entries = [
        entry for entry in clean_env.get(path_key, "").split(separator) if entry
    ]
    return len(original_entries) - len(clean_entries)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Bonsai-triggered video acquisition with ffmpeg encoding.",
    )
    parser.add_argument(
        "-c",
        "--config",
        required=True,
        type=Path,
        help="Path to an acquisition YAML config.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print Bonsai and ffmpeg commands without launching them.",
    )
    return parser.parse_args()


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if not isinstance(config, dict):
        raise ValueError(f"Config did not parse as a mapping: {path}")
    return config


def require(mapping: dict[str, Any], key: str, section: str) -> Any:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"Missing required config field: {section}.{key}")
    return value


def resolve_path(value: str | Path, config_path: Path) -> Path:
    """Resolve paths relative to the repo root first, then the config folder."""
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    if len(expanded) >= 3 and expanded[1] == ":" and expanded[2] in ("/", "\\"):
        return Path(expanded)
    if expanded.startswith("\\\\"):
        return Path(expanded)

    raw = Path(expanded)
    if raw.is_absolute():
        return raw

    repo_candidate = REPO_ROOT / raw
    if repo_candidate.exists():
        return repo_candidate

    config_candidate = config_path.parent / raw
    if config_candidate.exists():
        return config_candidate

    return repo_candidate


def bool_for_bonsai(value: bool) -> str:
    return "True" if value else "False"


def build_bonsai_command(
    bonsai_exe: Path,
    workflow_path: Path,
    cameras: list[dict[str, Any]],
) -> list[str]:
    command = [str(bonsai_exe), str(workflow_path), "--start"]

    for index, camera in enumerate(cameras, start=1):
        box_name = f"Box{index}"
        enabled = bool(camera.get("enabled", True))
        serial_number = require(camera, "serial_number", f"video.cameras[{index - 1}]")
        command.append(f"-p:{box_name}.SerialNumber={serial_number}")
        command.append(f"-p:{box_name}.Enable={bool_for_bonsai(enabled)}")

    return command


def camera_label(camera: dict[str, Any], index: int) -> str:
    return f"video.cameras[{index}]"


def enabled_cameras(cameras: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [camera for camera in cameras if camera.get("enabled", True)]


def get_frame_rate_hz(session: dict[str, Any], video: dict[str, Any]) -> Any:
    frame_rate_hz = video.get("frame_rate_hz", session.get("sync_rate_hz"))
    if frame_rate_hz is None:
        raise ValueError("Set video.frame_rate_hz or session.sync_rate_hz")
    if float(frame_rate_hz) <= 0:
        raise ValueError("frame rate must be positive")
    return frame_rate_hz


def validate_video_config(
    video: dict[str, Any],
    cameras: list[dict[str, Any]],
    session: dict[str, Any],
) -> None:
    for key in ("frame_width", "frame_height", "input_pixel_format"):
        require(video, key, "video")

    if int(video["frame_width"]) <= 0 or int(video["frame_height"]) <= 0:
        raise ValueError("video.frame_width and video.frame_height must be positive")
    get_frame_rate_hz(session, video)

    segment_seconds = video.get("segment_seconds")
    if segment_seconds is not None and float(segment_seconds) <= 0:
        raise ValueError("video.segment_seconds must be positive when set")

    pipe_wait_timeout_s = float(video.get("pipe_wait_timeout_s", 60))
    if pipe_wait_timeout_s <= 0:
        raise ValueError("video.pipe_wait_timeout_s must be positive")

    build_ffmpeg_output_options(video)

    for index, camera in enumerate(cameras):
        label = camera_label(camera, index)
        require(camera, "name", label)
        require(camera, "serial_number", label)
        require(camera, "pipe_name", label)

    if not enabled_cameras(cameras):
        raise ValueError("At least one camera must be enabled")


def named_pipe_path(pipe_name: str) -> str:
    if pipe_name.startswith(WINDOWS_PIPE_PREFIX):
        return pipe_name
    return WINDOWS_PIPE_PREFIX + pipe_name


def pipe_exists(pipe_path: str) -> bool:
    pipe_name = pipe_path.rsplit("\\", 1)[-1]
    try:
        return pipe_name in os.listdir(r"\\.\pipe")
    except OSError:
        return Path(pipe_path).exists()


def start_ffmpeg_when_pipes_open(
    cameras: list[dict[str, Any]],
    ffmpeg_commands: list[list[str]],
    bonsai_process: subprocess.Popen,
    timeout_s: float,
) -> list[subprocess.Popen]:
    start = time.monotonic()
    started = [False for _ in cameras]
    processes: list[subprocess.Popen] = []

    try:
        while not all(started):
            if bonsai_process.poll() is not None:
                raise RuntimeError("Bonsai exited before opening all video pipes.")

            for index, (camera, command) in enumerate(
                zip(cameras, ffmpeg_commands, strict=True)
            ):
                if started[index]:
                    continue
                pipe_path = named_pipe_path(str(camera["pipe_name"]))
                if pipe_exists(pipe_path):
                    print(f"Starting ffmpeg for {camera['name']} from pipe: {pipe_path}")
                    processes.append(subprocess.Popen(command))
                    started[index] = True

            if time.monotonic() - start > timeout_s:
                missing = [
                    f"{camera['name']} ({named_pipe_path(str(camera['pipe_name']))})"
                    for camera, is_started in zip(cameras, started, strict=True)
                    if not is_started
                ]
                raise TimeoutError(
                    "Timed out waiting for video pipes: " + ", ".join(missing)
                )

            time.sleep(PIPE_POLL_INTERVAL_S)
    except Exception:
        for process in processes:
            terminate_process(process, "ffmpeg")
        raise

    return processes


def build_ffmpeg_output_options(video: dict[str, Any]) -> list[str]:
    """Build output-side ffmpeg options from the acquisition config."""

    config_options = video.get("ffmpeg_output_options")
    output_options: list[str] = []

    def option_flag(name: Any, section: str) -> str:
        flag = str(name)
        if not flag:
            raise ValueError(f"Empty ffmpeg option name in {section}")
        return flag if flag.startswith("-") else f"-{flag}"

    def add_named_option(name: Any, value: Any, section: str) -> None:
        flag = option_flag(name, section)

        if value is False:
            return
        if value is True or value is None:
            output_options.append(flag)
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                if item is not None:
                    output_options.extend([flag, str(item)])
            return

        output_options.extend([flag, str(value)])

    def add_options(options: Any, section: str) -> None:
        if options is None:
            return
        if isinstance(options, dict):
            for name, value in options.items():
                add_named_option(name, value, section)
            return
        if isinstance(options, list):
            for index, item in enumerate(options):
                item_section = f"{section}[{index}]"
                if isinstance(item, str):
                    output_options.append(item)
                elif isinstance(item, dict):
                    add_options(item, item_section)
                elif isinstance(item, (list, tuple)):
                    if not item:
                        continue
                    flag = option_flag(item[0], item_section)
                    output_options.append(flag)
                    output_options.extend(str(value) for value in item[1:] if value is not None)
                else:
                    raise ValueError(
                        f"{item_section} must be a string, mapping, or list/tuple; "
                        f"got {type(item).__name__}"
                    )
            return

        raise ValueError(
            f"{section} must be a mapping or list; got {type(options).__name__}"
        )

    add_options(config_options, "video.ffmpeg_output_options")
    return output_options


def output_path_for_camera(
    data_dir: Path,
    camera_name: str,
    timestamp: str,
    segment_seconds: Any,
    extension: str,
) -> Path:
    safe_name = camera_name.replace(" ", "_")
    if segment_seconds is None:
        return data_dir / f"{safe_name}_{timestamp}.{extension}"
    return data_dir / f"{safe_name}_{timestamp}_%05d.{extension}"


def build_ffmpeg_command(
    camera: dict[str, Any],
    video: dict[str, Any],
    data_dir: Path,
    timestamp: str,
    frame_rate_hz: Any,
) -> list[str]:
    camera_name = require(camera, "name", "video.cameras[]")
    pipe_name = require(camera, "pipe_name", f"video.cameras[{camera_name}]")
    pipe_path = named_pipe_path(str(pipe_name))

    width = require(video, "frame_width", "video")
    height = require(video, "frame_height", "video")
    input_pixel_format = require(video, "input_pixel_format", "video")

    segment_seconds = video.get("segment_seconds")
    extension = str(video.get("output_extension", "mp4")).lstrip(".")
    output_path = output_path_for_camera(
        data_dir=data_dir,
        camera_name=str(camera_name),
        timestamp=timestamp,
        segment_seconds=segment_seconds,
        extension=str(extension),
    )

    command = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        str(input_pixel_format),
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(frame_rate_hz),
        "-i",
        pipe_path,
    ]

    command.extend(build_ffmpeg_output_options(video))

    command.append("-an")

    if segment_seconds is not None:
        command.extend(
            [
                "-f",
                "segment",
                "-segment_time",
                str(segment_seconds),
                "-reset_timestamps",
                "1",
            ]
        )

    command.append(str(output_path))
    return command


def print_command(label: str, command: list[str]) -> None:
    print(f"{label}:")
    print("  " + subprocess.list2cmdline(command))


def print_acquisition_summary(
    config_path: Path,
    data_dir: Path,
    bonsai_exe: Path,
    bonsai_workflow: Path,
    session: dict[str, Any],
    video: dict[str, Any],
    cameras: list[dict[str, Any]],
    frame_rate_hz: Any,
) -> None:
    print("Acquisition config:")
    print(f"  config: {config_path}")
    print(f"  data_dir: {data_dir}")
    print(f"  bonsai_exe: {bonsai_exe}")
    print(f"  bonsai_workflow: {bonsai_workflow}")
    print(f"  sync_rate_hz: {session.get('sync_rate_hz')}")
    print("Video settings:")
    print(f"  frame_rate_hz: {frame_rate_hz}")
    print(
        "  frame_size: "
        f"{require(video, 'frame_width', 'video')}x{require(video, 'frame_height', 'video')}"
    )
    print(f"  input_pixel_format: {require(video, 'input_pixel_format', 'video')}")
    output_options = build_ffmpeg_output_options(video)
    if output_options:
        print(f"  ffmpeg_output_options: {subprocess.list2cmdline(output_options)}")
    else:
        print("  ffmpeg_output_options: (ffmpeg defaults)")
    print(f"  segment_seconds: {video.get('segment_seconds')}")
    print(f"  output_extension: {video.get('output_extension', 'mp4')}")
    print(f"  pipe_wait_timeout_s: {video.get('pipe_wait_timeout_s', 60)}")
    print("Cameras:")
    for index, camera in enumerate(cameras, start=1):
        enabled = bool(camera.get("enabled", True))
        print(
            "  "
            f"Box{index}: name={require(camera, 'name', camera_label(camera, index - 1))} "
            f"serial_number={require(camera, 'serial_number', camera_label(camera, index - 1))} "
            f"pipe={named_pipe_path(str(require(camera, 'pipe_name', camera_label(camera, index - 1))))} "
            f"enabled={enabled}"
        )


def terminate_process(process: subprocess.Popen, name: str) -> None:
    if process.poll() is not None:
        return
    print(f"Stopping {name}.")
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        print(f"{name} did not exit after terminate(); killing.")
        process.kill()


def wait_for_process_or_terminate(
    process: subprocess.Popen,
    name: str,
    *,
    timeout_s: float = 10,
) -> None:
    """Give a process time to finish cleanly before terminating it."""

    try:
        process.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        terminate_process(process, name)


def main() -> int:
    args = parse_args()
    config_path = args.config.resolve()
    config = load_config(config_path)

    paths = require(config, "paths", "config")
    session = config.get("session", {})
    if not isinstance(session, dict):
        raise ValueError("session must be a mapping when present")
    video = require(config, "video", "config")
    cameras = require(video, "cameras", "video")
    if not isinstance(cameras, list) or not cameras:
        raise ValueError("video.cameras must be a non-empty list")
    validate_video_config(video, cameras, session)
    frame_rate_hz = get_frame_rate_hz(session, video)

    data_dir = resolve_path(require(paths, "data_dir", "paths"), config_path)
    bonsai_exe = resolve_path(require(paths, "bonsai_exe", "paths"), config_path)
    bonsai_workflow = resolve_path(require(paths, "bonsai_workflow", "paths"), config_path)
    pipe_wait_timeout_s = float(video.get("pipe_wait_timeout_s", 60))

    active_cameras = enabled_cameras(cameras)

    print_acquisition_summary(
        config_path=config_path,
        data_dir=data_dir,
        bonsai_exe=bonsai_exe,
        bonsai_workflow=bonsai_workflow,
        session=session,
        video=video,
        cameras=cameras,
        frame_rate_hz=frame_rate_hz,
    )

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    bonsai_command = build_bonsai_command(bonsai_exe, bonsai_workflow, cameras)
    ffmpeg_commands = [
        build_ffmpeg_command(camera, video, data_dir, timestamp, frame_rate_hz)
        for camera in active_cameras
    ]

    print_command("Bonsai command", bonsai_command)
    for camera, command in zip(active_cameras, ffmpeg_commands, strict=True):
        print_command(f"ffmpeg command for {camera['name']}", command)

    if args.dry_run:
        return 0

    data_dir.mkdir(parents=True, exist_ok=True)

    bonsai_env = build_bonsai_environment()
    removed_path_entries = count_removed_conda_path_entries(os.environ, bonsai_env)
    if removed_path_entries:
        print(
            "Launching Bonsai with conda paths removed from PATH "
            f"({removed_path_entries} entries)."
        )

    bonsai_process = subprocess.Popen(bonsai_command, env=bonsai_env)
    ffmpeg_processes: list[subprocess.Popen] = []

    try:
        ffmpeg_processes = start_ffmpeg_when_pipes_open(
            cameras=active_cameras,
            ffmpeg_commands=ffmpeg_commands,
            bonsai_process=bonsai_process,
            timeout_s=pipe_wait_timeout_s,
        )

        while bonsai_process.poll() is None:
            time.sleep(1)

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        terminate_process(bonsai_process, "Bonsai")
        for process in ffmpeg_processes:
            wait_for_process_or_terminate(process, "ffmpeg")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
