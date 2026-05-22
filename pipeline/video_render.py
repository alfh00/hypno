import os
import subprocess
from pathlib import Path
from pipeline.logger import get_logger

# Font candidates for drawtext — fontconfig is broken on some Windows FFmpeg builds,
# so we resolve a fontfile path directly at runtime.
_FONT_CANDIDATES = [
    r"C:/Windows/Fonts/georgia.ttf",
    r"C:/Windows/Fonts/times.ttf",
    r"C:/Windows/Fonts/arial.ttf",
    r"C:/Windows/Fonts/calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",  # Linux
    "/System/Library/Fonts/Supplemental/Georgia.ttf",     # macOS
]


def _ffmpeg_font_spec() -> str:
    """
    Return a drawtext fontfile= clause pointing to the first available font,
    or an empty string (FFmpeg built-in fallback) if none are found.
    """
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            # FFmpeg filter escaping: backslash-escape the colon in Windows drive letter
            escaped = path.replace(":", "\\:")
            return f":fontfile='{escaped}'"
    logger.warning("No system font found for drawtext — using FFmpeg built-in fallback.")
    return ""

logger = get_logger(__name__)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def build_gradient_filter(colors: dict, width: int, height: int, duration: float) -> str:
    """
    Build an FFmpeg lavfi filter that generates the Drift gradient:
    bottom (warm amber) → lower_mid (burnt orange) → mid (dusty rose)
    → upper_mid (violet) → top (near black)

    Uses geq (per-pixel color evaluation) for smooth multi-stop gradients.
    """
    bottom    = hex_to_rgb(colors["bottom"])
    lower_mid = hex_to_rgb(colors["lower_mid"])
    mid       = hex_to_rgb(colors["mid"])
    upper_mid = hex_to_rgb(colors["upper_mid"])
    top       = hex_to_rgb(colors["top"])

    h = height

    def gradient_channel(idx):
        stops = [bottom[idx], lower_mid[idx], mid[idx], upper_mid[idx], top[idx]]
        n = len(stops) - 1

        expr = ""
        for i in range(n):
            t0 = i / n
            t1 = (i + 1) / n
            y0 = int(h * (1 - t1))
            y1 = int(h * (1 - t0))
            seg_t = f"clip((Y-{y0})/({y1}-{y0}+1),0,1)"
            val = f"({stops[i]}+({stops[i+1]}-{stops[i]})*{seg_t})"
            if i == 0:
                expr = val
            else:
                in_range = f"between(Y,{y0},{y1})"
                expr = f"if({in_range},{val},{expr})"
        return expr

    r_expr = gradient_channel(0)
    g_expr = gradient_channel(1)
    b_expr = gradient_channel(2)

    geq = f"geq=r='{r_expr}':g='{g_expr}':b='{b_expr}'"

    return (
        f"color=black:size={width}x{height}:rate=24:duration={duration},"
        f"format=rgb24,{geq}"
    )


def add_vignette_filter(base_filter: str, width: int, height: int, opacity: float) -> str:
    """
    Overlay a radial vignette/depth effect using a geq alpha layer.
    Applied when particle_count > 0 in config.
    """
    vignette = (
        f"[bg];color=black:size={width}x{height}:rate=24,format=rgba,"
        f"geq=r='0':g='0':b='0':"
        f"a='255*{opacity}*(1-hypot((X-{width//2})/{width//2},(Y-{height//2})/{height//2}))'[vign];"
        f"[bg][vign]overlay=format=auto"
    )
    return base_filter + vignette


def render_video(audio_path: Path, output_path: Path, config: dict) -> Path:
    """
    Generate the Drift gradient video and mux with mixed audio.
    Output: 1920x1080 MP4 H.264, ready for YouTube upload.
    """
    vid_cfg = config["video"]
    width   = vid_cfg["width"]
    height  = vid_cfg["height"]
    fps     = vid_cfg["fps"]
    colors  = vid_cfg["gradient_colors"]

    from pipeline.audio_mix import get_audio_duration_seconds
    duration = get_audio_duration_seconds(audio_path)

    logger.info(f"Rendering video — {width}x{height}, {duration:.0f}s")

    gradient_filter = build_gradient_filter(colors, width, height, duration)

    # Optional vignette overlay (enabled when particle_count > 0)
    if vid_cfg.get("particle_count", 0) > 0:
        gradient_filter = add_vignette_filter(
            gradient_filter, width, height,
            vid_cfg.get("particle_opacity", 0.18),
        )

    # Watermark drawtext filter
    watermark_filter = ""
    if vid_cfg.get("logo_watermark"):
        wm_text    = vid_cfg.get("watermark_text", "DRIFT")
        wm_opacity = vid_cfg.get("watermark_opacity", 0.25)
        watermark_filter = (
            f",drawtext=text='{wm_text}'"
            f":fontsize=48:fontcolor=white@{wm_opacity}"
            f":x=(w-text_w)/2:y=h-80"
            f"{_ffmpeg_font_spec()}:expansion=none"
        )

    full_filter = gradient_filter + watermark_filter

    ffmpeg_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", full_filter,
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_path),
    ]

    result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg video render failed:\n{result.stderr}")

    size_mb = output_path.stat().st_size / 1_000_000
    logger.info(f"Video rendered: {output_path} ({size_mb:.1f} MB)")

    return output_path
