"""Turn a wallpaper's colours into libadwaita accent overrides (adaptive theme)."""

from __future__ import annotations

import colorsys
from typing import List, Optional

from .imaging import RGB, contrast_ratio, dominant_color_family, pick_accent

DEFAULT_TINTS = ("#7c3aed", "#db2777", "#0ea5e9")


def _hex(c: RGB) -> str:
    return "#%02x%02x%02x" % c


def to_hex(c: RGB) -> str:
    return _hex(c)


def to_hex_list(palette: List[RGB]) -> List[str]:
    return [_hex(c) for c in palette]


def palette_gnome_accent(palette: List[RGB]) -> str:
    """Map the wallpaper palette to GNOME's accent color enum."""
    return dominant_color_family(palette)


def _with_lightness(c: RGB, lightness: float, sat_floor: float = 0.0) -> RGB:
    h, _l, s = colorsys.rgb_to_hls(*(v / 255 for v in c))
    r, g, b = colorsys.hls_to_rgb(h, max(0.0, min(1.0, lightness)), max(s, sat_floor))
    return (round(r * 255), round(g * 255), round(b * 255))


def accent_set(palette: List[RGB], dark: bool) -> Optional[dict]:
    """Colours for @accent_bg_color / @accent_color / @accent_fg_color + tints."""
    accent = pick_accent(palette)
    if accent is None:
        return None
    bg = _with_lightness(accent, 0.52 if dark else 0.46, sat_floor=0.35)
    fg = (255, 255, 255) if contrast_ratio(bg, (255, 255, 255)) >= 3.0 else (20, 20, 20)
    # Standalone accent is used as text on the neutral window background.
    text = _with_lightness(accent, 0.72 if dark else 0.32, sat_floor=0.35)
    tints = [bg] + [c for c in palette if c != accent][:2]
    while len(tints) < 3:
        tints.append(bg)
    return {"bg": bg, "fg": fg, "text": text, "tints": tints[:3]}


def build_css(palette: Optional[List[RGB]], dark: bool) -> str:
    """CSS for the dynamic provider. Empty palette -> defaults (no override)."""
    s = accent_set(palette, dark) if palette else None
    if s is None:
        a, b, c = DEFAULT_TINTS
        return f"@define-color vw_tint_a {a};\n@define-color vw_tint_b {b};\n@define-color vw_tint_c {c};\n"
    a, b, c = (_hex(x) for x in s["tints"])
    return (
        f"@define-color accent_bg_color {_hex(s['bg'])};\n"
        f"@define-color accent_color {_hex(s['text'])};\n"
        f"@define-color accent_fg_color {_hex(s['fg'])};\n"
        f"@define-color vw_tint_a {a};\n@define-color vw_tint_b {b};\n@define-color vw_tint_c {c};\n"
    )
