"""Image validation and dominant-colour extraction (PIL only, no GTK)."""

from __future__ import annotations

import colorsys
from pathlib import Path
from typing import List, Optional, Tuple

ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")
EXT_FOR_FORMAT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
RGB = Tuple[int, int, int]


def validate_image(path: Path) -> Optional[Tuple[str, int, int]]:
    """Return (format, width, height) if ``path`` is a complete JPEG/PNG/WebP, else None."""
    try:
        from PIL import Image

        with Image.open(path) as img:
            fmt = img.format
            width, height = img.size
            if fmt not in ALLOWED_FORMATS:
                return None
            img.verify()
        return fmt, width, height
    except Exception:  # noqa: BLE001 - unreadable/truncated/hostile file
        return None


def _luminance(c: RGB) -> float:
    def chan(v: int) -> float:
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = c
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(a: RGB, b: RGB) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def extract_palette(path: Path, count: int = 5) -> List[RGB]:
    """Most prominent colours of an image, most common first."""
    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((96, 96))
        q = img.quantize(colors=max(count * 2, 8), method=Image.Quantize.MEDIANCUT)
        pal = q.getpalette() or []
        counts = sorted(q.getcolors() or [], reverse=True)   # [(pixels, index)]
    out: List[RGB] = []
    for _n, idx in counts:
        c = (pal[idx * 3], pal[idx * 3 + 1], pal[idx * 3 + 2])
        if all(_dist(c, o) > 40 for o in out):
            out.append(c)
        if len(out) == count:
            break
    return out


def _dist(a: RGB, b: RGB) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def pick_accent(palette: List[RGB]) -> Optional[RGB]:
    """The most vivid, not-too-dark/light colour: what an accent should be."""
    best, best_score = None, 0.0
    for c in palette:
        h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in c))
        score = s * (1 - abs(l - 0.5) * 1.6)
        if score > best_score:
            best, best_score = c, score
    return best if best_score > 0.12 else None


def image_stats(path: Path) -> Tuple[float, float]:
    """(mean brightness 0..1, mean saturation 0..1) of a small copy of the image."""
    from PIL import Image

    with Image.open(path) as img:
        img = img.convert("RGB")
        img.thumbnail((64, 64))
        px = list(img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata())
    n = max(len(px), 1)
    lum = sum(0.299 * r + 0.587 * g + 0.114 * b for r, g, b in px) / (255 * n)
    sat = sum(colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)[1] for r, g, b in px) / n
    return lum, sat


def dominant_color_family(palette: List[RGB]) -> str:
    """Classify the dominant color into one of GNOME's 10 accent names."""
    accent = pick_accent(palette) or (palette[0] if palette else (128, 128, 128))
    h, l, s = colorsys.rgb_to_hls(*(v / 255 for v in accent))
    if s < 0.18:
        return "slate"
    deg = (h * 360) % 360
    if 345 <= deg or deg < 15:
        return "red"
    elif 15 <= deg < 42:
        return "orange" if l > 0.35 else "brown"
    elif 42 <= deg < 70:
        return "yellow" if l > 0.4 else "brown"
    elif 70 <= deg < 165:
        return "green"
    elif 165 <= deg < 195:
        return "teal"
    elif 195 <= deg < 260:
        return "blue"
    elif 260 <= deg < 305:
        return "purple"
    else:
        return "pink"


def apply_instant_filter(src_path: Path, dest_path: Path, filter_name: str) -> Path:
    """Apply an instant visual tweak (blur, dim, zen, dock_blur) and save to dest_path."""
    from PIL import Image, ImageEnhance, ImageFilter

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        if filter_name == "blur":
            img = img.filter(ImageFilter.GaussianBlur(radius=18))
        elif filter_name == "dim":
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.65)
        elif filter_name == "zen":
            # Dark AMOLED feel: dim and boost contrast
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.4)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.3)
        elif filter_name == "dock_blur":
            img = apply_dock_blur(img)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest_path, quality=95)
    return dest_path


def apply_dock_blur(img, position: str = "bottom", blur_ratio: float = 0.20, radius: int = 32):
    """Apply a frosted glass blur overlay specifically to the dock or panel region."""
    from PIL import ImageFilter

    w, h = img.size
    dock_h = int(h * blur_ratio)

    if position == "bottom":
        box = (0, h - dock_h, w, h)
    else:
        box = (0, 0, w, dock_h)

    crop = img.crop(box)
    blurred = crop.filter(ImageFilter.GaussianBlur(radius=radius))

    # Paste blurred strip back onto image
    result = img.copy()
    result.paste(blurred, box)
    return result


def apply_post_processing(src_path: Path, dest_path: Path, brightness: float = 1.0,
                          contrast: float = 1.0, saturation: float = 1.0) -> Path:
    """Adjust image brightness, contrast, and saturation."""
    from PIL import Image, ImageEnhance

    with Image.open(src_path) as img:
        img = img.convert("RGB")
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest_path, quality=95)
    return dest_path
