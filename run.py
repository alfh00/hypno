#!/usr/bin/env python3
"""
Drift Pipeline — single run entry point.

Usage:
    python run.py                         # normal run, weighted random topic
    python run.py --type deep_sleep       # force a specific session type
    python run.py --dry-run               # skip YouTube upload
    python run.py --local                 # use local LLM (LM Studio) + skip upload
    python run.py --local --type anxiety_release  # local LLM, forced type
"""

import argparse
import uuid
import traceback
from pathlib import Path
from datetime import datetime

import yaml
from dotenv import load_dotenv

from pipeline.logger import get_logger
from pipeline.topics import pick_session
from pipeline.script_gen import generate_script
from pipeline.tts import render_tts
from pipeline.audio_mix import mix_audio
from pipeline.video_render import render_video
from pipeline.thumbnail import generate_thumbnail
from pipeline.upload import upload_to_youtube

load_dotenv()
logger = get_logger("drift.run")


def load_config(path: str = "./config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def run_pipeline(config: dict, force_type: str = None) -> dict:
    run_id  = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    run_dir = Path(config["pipeline"]["output_dir"]) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    backend = "local LLM" if config["pipeline"].get("use_local_llm") else "Claude"
    dry_run = config["pipeline"].get("dry_run", False)

    logger.info(f"=== Drift run started: {run_id} | backend={backend} | dry_run={dry_run} ===")

    session = pick_session(config, force_type=force_type)

    script      = generate_script(session, config)
    script_path = run_dir / "script.txt"
    script_path.write_text(script, encoding="utf-8")

    voice_path = run_dir / "voice.mp3"
    render_tts(script, voice_path, config)

    mixed_path = run_dir / "mixed.mp3"
    mix_audio(voice_path, mixed_path, config)

    video_path = run_dir / "video.mp4"
    render_video(mixed_path, video_path, config)

    thumbnail_path = run_dir / "thumbnail.jpg"
    generate_thumbnail(session.youtube_title, thumbnail_path, config)

    video_id = upload_to_youtube(video_path, thumbnail_path, session, config)

    result = {
        "run_id":        run_id,
        "session_type":  session.session_type,
        "theme":         session.theme,
        "youtube_title": session.youtube_title,
        "video_id":      video_id,
        "run_dir":       str(run_dir),
    }

    logger.info(f"=== Run complete: {result} ===")
    return result


def main():
    parser = argparse.ArgumentParser(description="Drift pipeline runner")
    parser.add_argument("--type",    help="Force a specific session type")
    parser.add_argument("--dry-run", action="store_true", help="Skip YouTube upload")
    parser.add_argument(
        "--local",
        action="store_true",
        help=(
            "Use local LLM (LM Studio / Ollama) for script generation instead of Claude. "
            "Also implies --dry-run (no upload). "
            "Configure endpoint in config.yaml [local_llm] or via LOCAL_LLM_BASE_URL / LOCAL_LLM_MODEL env vars."
        ),
    )
    parser.add_argument("--config", default="./config.yaml", help="Config file path")
    args = parser.parse_args()

    config = load_config(args.config)

    if args.local:
        config["pipeline"]["use_local_llm"] = True
        config["pipeline"]["dry_run"] = True   # never upload when running locally
        logger.info("Local mode: using LM Studio backend, upload disabled.")

    if args.dry_run:
        config["pipeline"]["dry_run"] = True

    try:
        run_pipeline(config, force_type=args.type)
    except Exception:
        logger.error("Pipeline failed:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
