"""Render a session-time-native demo video clip."""

from __future__ import annotations

import argparse
import logging
import tempfile
import time
from pathlib import Path

from multimodal_sync.config import config_root, load_config
from multimodal_sync.demo_video.audio import write_demo_audio_wav
from multimodal_sync.demo_video.context import DemoSessionContext
from multimodal_sync.demo_video.encoder import mux_video_and_audio, render_silent_video_mp4
from multimodal_sync.demo_video.renderer import DemoVideoRenderer
from multimodal_sync.demo_video.timeline import SessionRenderTimeline


logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a synchronized multimodal demo video clip.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--session", required=True, type=Path, help="Session basepath")
    parser.add_argument(
        "--session-config",
        required=True,
        type=Path,
        help="Analysis config describing the session data organization",
    )
    parser.add_argument(
        "--demo-video-config",
        required=True,
        type=Path,
        help="Demo-video layout and encoder config",
    )
    parser.add_argument(
        "--clip-start-session-s",
        required=True,
        type=float,
        help="Demo clip start time on the shared session clock",
    )
    parser.add_argument(
        "--clip-end-session-s",
        required=True,
        type=float,
        help="Demo clip end time on the shared session clock",
    )
    parser.add_argument("--output", required=True, type=Path, help="Output MP4 path")
    parser.add_argument("--no-overwrite", action="store_true", help="Do not overwrite output")
    parser.add_argument("--log-level", default="INFO", help="Python logging level")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper()),
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    start_wall_time = time.time()

    logger.info("Loading configs")
    logger.info("  session_config=%s", args.session_config)
    logger.info("  demo_video_config=%s", args.demo_video_config)
    session_config = load_config(args.session_config)
    demo_video_config = config_root(load_config(args.demo_video_config))

    context = DemoSessionContext(session_basepath=args.session, session_config=session_config)
    video_config = demo_video_config["video"]
    timeline = SessionRenderTimeline(
        clip_start_session_s=args.clip_start_session_s,
        clip_end_session_s=args.clip_end_session_s,
        output_fps=float(video_config.get("output_fps", video_config.get("framerate", 30))),
        playback_speed=float(video_config.get("playback_speed", 1.0)),
    )
    logger.info("Timeline: %s", timeline.to_dict())

    full_session_duration_s = context.full_session_duration_s()
    if timeline.clip_start_session_s < 0 or timeline.clip_end_session_s > full_session_duration_s:
        raise ValueError(
            "Requested clip is outside the sync-defined session: "
            f"clip={timeline.clip_start_session_s}-{timeline.clip_end_session_s}s, "
            f"full_session_duration_s={full_session_duration_s}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    overwrite = not args.no_overwrite
    if args.output.exists() and not overwrite:
        raise FileExistsError(f"Output already exists and --no-overwrite was set: {args.output}")

    renderer = DemoVideoRenderer(
        context=context,
        demo_video_config=demo_video_config,
        timeline=timeline,
    )
    try:
        with tempfile.TemporaryDirectory(prefix="multimodal_sync_demo_video_") as tmpdir:
            tmpdir_path = Path(tmpdir)
            temp_video_path = tmpdir_path / "silent_video.mp4"
            temp_audio_path = None

            if "audio_track" in demo_video_config and demo_video_config["audio_track"] is not None:
                temp_audio_path = tmpdir_path / "audio_track.wav"
                write_demo_audio_wav(
                    context=context,
                    timeline=timeline,
                    audio_config=demo_video_config["audio_track"],
                    output_wav_path=temp_audio_path,
                )
            else:
                logger.info("No audio_track configured; final video will be silent")

            render_silent_video_mp4(
                renderer=renderer,
                timeline=timeline,
                output_video_path=temp_video_path,
                encoder_config=demo_video_config.get("encoder", {}),
            )
            mux_video_and_audio(
                video_path=temp_video_path,
                audio_path=temp_audio_path,
                output_path=args.output,
                encoder_config=demo_video_config.get("encoder", {}),
                overwrite=overwrite,
            )
    finally:
        renderer.close()

    logger.info("Done in %.2f s", time.time() - start_wall_time)


if __name__ == "__main__":
    main()
