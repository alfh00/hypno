from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from pipeline.logger import get_logger

logger = get_logger(__name__)

GRADIENT_COLORS = [
    (245, 169, 74),   # warm amber
    (224, 123, 63),   # burnt orange
    (196, 90, 106),   # dusty rose
    (123, 79, 166),   # violet
    (19, 16, 43),     # near black
]

# Font search paths in priority order (Linux → macOS → Windows)
_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",          # Linux
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Georgia.ttf",             # macOS
    "/System/Library/Fonts/Times.ttc",
    "C:/Windows/Fonts/georgia.ttf",                               # Windows
    "C:/Windows/Fonts/times.ttf",
    "C:/Windows/Fonts/cambria.ttc",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    logger.warning("No system serif font found — falling back to Pillow default bitmap font.")
    return ImageFont.load_default()


def make_gradient_image(width: int, height: int) -> Image.Image:
    img = Image.new("RGBA", (width, height))   # RGBA so alpha drawing works correctly
    draw = ImageDraw.Draw(img)
    n = len(GRADIENT_COLORS) - 1

    for y in range(height):
        t = y / height
        segment = min(int(t * n), n - 1)
        local_t = (t * n) - segment
        c0 = GRADIENT_COLORS[n - segment]
        c1 = GRADIENT_COLORS[n - segment - 1]
        r = int(c0[0] + (c1[0] - c0[0]) * local_t)
        g = int(c0[1] + (c1[1] - c0[1]) * local_t)
        b = int(c0[2] + (c1[2] - c0[2]) * local_t)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    return img


def generate_thumbnail(session_title: str, output_path: Path, config: dict) -> Path:
    """
    Generate a 1280x720 YouTube thumbnail:
    - Drift gradient background
    - Session title centered with drop shadow
    - DRIFT wordmark at bottom
    """
    W, H = 1280, 720
    img = make_gradient_image(W, H)   # RGBA image
    draw = ImageDraw.Draw(img)

    title_font = _load_font(72)
    sub_font   = _load_font(36)
    brand_font = _load_font(52)

    lines = session_title.split(" — ")
    y_center = H // 2 - 60

    for i, line in enumerate(lines):
        font = title_font if i == 0 else sub_font
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (W - text_w) // 2
        # drop shadow (semi-transparent black)
        draw.text((x + 2, y_center + i * 90 + 2), line, font=font, fill=(0, 0, 0, 120))
        # main text (warm cream)
        draw.text((x, y_center + i * 90), line, font=font, fill=(245, 232, 208, 255))

    brand = "DRIFT"
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    brand_w = bbox[2] - bbox[0]
    draw.text(((W - brand_w) // 2, H - 100), brand, font=brand_font, fill=(245, 232, 208, 160))

    # Convert to RGB for JPEG output
    final = img.convert("RGB")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.save(str(output_path), "JPEG", quality=95)
    logger.info(f"Thumbnail saved: {output_path}")

    return output_path
