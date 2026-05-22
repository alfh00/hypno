import glob
import os
import random
import shutil
import subprocess
from pathlib import Path
from pipeline.logger import get_logger

logger = get_logger(__name__)


def _find_bin(name: str) -> str:
    """
    Resolve the full path of an ffmpeg/ffprobe binary.
    Checks PATH first, then common Windows winget/install locations.
    Raises FileNotFoundError with an install hint if not found.
    """
    found = shutil.which(name)
    if found:
        return found

    # winget installs a shell alias under AppData\Local\Microsoft\WinGet\Links
    winget_links = os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Links\{name}.exe")
    if os.path.exists(winget_links):
        return winget_links

    # Common manual install locations on Windows
    for pattern in [
        rf"C:\ffmpeg\bin\{name}.exe",
        rf"C:\Program Files\ffmpeg\bin\{name}.exe",
        os.path.expandvars(rf"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\**\bin\{name}.exe"),
    ]:
        matches = glob.glob(pattern, recursive=True)
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"'{name}' not found. Install FFmpeg (winget install ffmpeg) "
        "and open a new terminal so the PATH update takes effect."
    )


# Resolve once at module load — avoids PATH issues across shell sessions
_FFPROBE = _find_bin("ffprobe")
_FFMPEG  = _find_bin("ffmpeg")


def get_audio_duration_seconds(path: Path) -> float:
    """Use ffprobe to get audio duration in seconds."""
    result = subprocess.run(
        [
            _FFPROBE, "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed on '{path}'.\n"
            "Make sure ffmpeg/ffprobe is installed and on PATH.\n"
            f"stderr: {result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError:
        raise RuntimeError(
            f"ffprobe returned unexpected output for '{path}': {raw!r}\n"
            "Expected a numeric duration in seconds."
        )


def pick_ambient_track(ambient_dir: Path) -> Path:
    """Randomly select an ambient track from the assets directory."""
    tracks = list(ambient_dir.glob("*.mp3")) + list(ambient_dir.glob("*.wav"))
    if not tracks:
        raise FileNotFoundError(
            f"No ambient audio files found in '{ambient_dir}'. "
            "Add at least one .mp3 or .wav file (binaural beats, nature sounds, etc.)"
        )
    chosen = random.choice(tracks)
    logger.info(f"Ambient track selected: {chosen.name}")
    return chosen


def mix_audio(voice_path: Path, output_path: Path, config: dict) -> Path:
    """
    Mix voice track with ambient background using FFmpeg.
    - Voice at 0 dB (reference)
    - Ambient at -22 dB under the voice
    - Fade in / fade out applied to both
    - Ambient loops if shorter than voice
    Returns path to mixed audio file.
    """
    audio_cfg = config["audio"]
    ambient_dir = Path(audio_cfg["ambient_dir"])
    ambient_track = pick_ambient_track(ambient_dir)

    voice_duration = get_audio_duration_seconds(voice_path)
    fade_in = audio_cfg["fade_in_seconds"]
    fade_out = audio_cfg["fade_out_seconds"]
    ambient_db = audio_cfg["ambient_volume_db"]

    logger.info(f"Mixing audio — voice duration: {voice_duration:.1f}s")

    ffmpeg_cmd = [
        _FFMPEG, "-y",
        "-i", str(voice_path),
        "-stream_loop", "-1", "-i", str(ambient_track),
        "-filter_complex",
        (
            f"[0:a]afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={voice_duration - fade_out}:d={fade_out}[voice];"
            f"[1:a]volume={ambient_db}dB,"
            f"atrim=0:{voice_duration},"
            f"afade=t=in:st=0:d={fade_in},"
            f"afade=t=out:st={voice_duration - fade_out}:d={fade_out}[ambient];"
            f"[voice][ambient]amix=inputs=2:duration=first[out]"
        ),
        "-map", "[out]",
        "-c:a", "libmp3lame",
        "-b:a", "192k",
        str(output_path),
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio mix failed:\n{result.stderr}")

    logger.info(f"Mixed audio saved: {output_path}")
    return output_path
