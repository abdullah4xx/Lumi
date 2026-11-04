"""Search-text helpers: Arabic -> English translation for the (English) wallpaper sources, and text matching."""

from __future__ import annotations

import re
from typing import Iterable

_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
_MARKS_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u0640]")     # tashkeel + tatweel
_TOKEN_RE = re.compile(r"[\w\-]+", re.UNICODE)

# Keys are written in the normalised form (see normalize_ar): no marks, alef/yaa/taa-marbuta folded, no leading "ال".
_AR_EN = {
    "طبيعه": "nature", "بحر": "sea", "محيط": "ocean", "شاطي": "beach", "موج": "wave", "جبل": "mountain",
    "جبال": "mountains", "غابه": "forest", "شجره": "tree", "اشجار": "trees", "زهره": "flower", "ورد": "flowers",
    "زهور": "flowers", "نهر": "river", "بحيره": "lake", "شلال": "waterfall", "صحراء": "desert", "صحرا": "desert",
    "جزيره": "island", "وادي": "valley", "سماء": "sky", "غيوم": "clouds", "سحاب": "clouds", "مطر": "rain",
    "ثلج": "snow", "شتاء": "winter", "صيف": "summer", "خريف": "autumn", "ربيع": "spring", "شروق": "sunrise",
    "غروب": "sunset", "شمس": "sun", "قمر": "moon", "نجوم": "stars", "نجم": "star", "ليل": "night", "فجر": "dawn",
    "ضباب": "fog", "نار": "fire", "جليد": "ice", "فضاء": "space", "مجره": "galaxy", "كوكب": "planet",
    "كواكب": "planets", "سديم": "nebula", "ارض": "earth", "رائد": "astronaut", "صاروخ": "rocket",
    "مدينه": "city", "مدن": "city", "برج": "tower", "جسر": "bridge", "قلعه": "castle", "طريق": "road",
    "شارع": "street", "عمارات": "skyscraper", "عماره": "architecture", "بيت": "house", "سياره": "car",
    "سيارات": "cars", "دراجه": "motorcycle", "قطار": "train", "طياره": "airplane", "سفينه": "ship",
    "قطه": "cat", "قطط": "cats", "كلب": "dog", "اسد": "lion", "نمر": "tiger", "ذئب": "wolf", "حصان": "horse",
    "خيل": "horse", "نسر": "eagle", "صقر": "falcon", "طائر": "bird", "طيور": "birds", "فراشه": "butterfly",
    "تنين": "dragon", "دب": "bear", "ثعلب": "fox", "غزال": "deer", "فيل": "elephant", "دلفين": "dolphin",
    "سمكه": "fish", "انمي": "anime", "كرتون": "cartoon", "لعبه": "game", "العاب": "gaming", "روبوت": "robot",
    "سايبربانك": "cyberpunk", "نيون": "neon", "مستقبل": "futuristic", "خيال": "fantasy", "تجريدي": "abstract",
    "مجرد": "abstract", "بسيط": "minimal", "مينيمال": "minimal", "اسود": "black", "ظلام": "dark", "مظلم": "dark",
    "ابيض": "white", "احمر": "red", "ازرق": "blue", "اخضر": "green", "اصفر": "yellow", "بنفسجي": "purple",
    "برتقالي": "orange", "وردي": "pink", "رمادي": "gray", "ذهبي": "gold", "الوان": "colorful", "رسم": "painting",
    "فن": "art", "رقمي": "digital", "ثلاثي": "3d", "قديم": "vintage", "كلاسيكي": "classic", "موسيقي": "music",
    "جيتار": "guitar", "قهوه": "coffee", "طعام": "food", "كتاب": "books", "مكتبه": "library", "حديقه": "garden",
    "حقل": "field", "مزرعه": "farm", "كهف": "cave", "بركان": "volcano", "عاصفه": "storm", "برق": "lightning",
    "قوس": "rainbow", "ماء": "water", "ازهار": "flowers", "سيارة": "car", "خلفيه": "wallpaper", "خلفيات": "wallpaper",
}


def has_arabic(text: str) -> bool:
    return bool(_ARABIC_RE.search(text or ""))


def normalize_ar(text: str) -> str:
    """Fold spelling variants so 'أ/إ/آ', 'ى/ي', 'ة/ه' and diacritics never stop a match."""
    s = _MARKS_RE.sub("", text or "")
    for src, dst in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        s = s.replace(src, dst)
    return s


def _lookup(word: str):
    w = normalize_ar(word)
    candidates = [w]
    if w.startswith("ال") and len(w) > 3:
        candidates.append(w[2:])
    if w.startswith("و") and len(w) > 3:                    # "وبحر" = "and sea"
        candidates += [w[1:], w[3:] if w[1:].startswith("ال") else w[1:]]
    for c in candidates:
        if c in _AR_EN:
            return _AR_EN[c]
        if c.endswith("ات") and c[:-2] + "ه" in _AR_EN:       # plural: "اشجار"-style fallbacks
            return _AR_EN[c[:-2] + "ه"]
    return None


def translate_query(text: str) -> str:
    """Arabic words -> English (the wallpaper APIs are English-only). English text is returned unchanged.
    Unknown Arabic words are preserved so translation does not silently erase parts of the search."""
    text = (text or "").strip()
    if not has_arabic(text):
        return text
    out, understood = [], False
    for tok in _TOKEN_RE.findall(text):
        if has_arabic(tok):
            en = _lookup(tok)
            if en:
                out.append(en)
                understood = True
            else:
                out.append(tok)
        else:
            out.append(tok)
    return " ".join(dict.fromkeys(out)) if understood else text


def matches(query: str, fields: Iterable[str]) -> bool:
    """Every word of ``query`` must appear in the fields (accent-, case- and spelling-insensitive, Arabic or English;
    Arabic words also match their English translation)."""
    haystack = normalize_ar(" ".join(f for f in fields if f)).lower()
    for word in _TOKEN_RE.findall(query or ""):
        w = normalize_ar(word).lower()
        if w in haystack:
            continue
        en = _lookup(word) if has_arabic(word) else None
        if en and en in haystack:
            continue
        return False
    return True
