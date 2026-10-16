import re
from typing import Optional, Tuple

# hOCR-style coordinates regex and surface extraction primitives
BBOX_RE = re.compile(r'\bbbox\s*=\s*"([^"]*)"')
SURFACE_RE = re.compile(r"<surface\b[^>]*>", re.IGNORECASE)
LRX_RE = re.compile(r'(\blrx\s*=\s*")([^"]*)(")')
LRY_RE = re.compile(r'(\blry\s*=\s*")([^"]*)(")')

# Quirk repair: TEITOK opens <name> but occasionally closes with </n>
_NAME_CLOSE_RE = re.compile(r"</n\s*>")


def unit_per_inch(unit: str) -> Optional[float]:
    if unit == "inch1200":
        return 1200.0
    if unit == "mm10":
        return 254.0
    if unit == "pt":  # PDF points: a born-digital record's pages[].canvas.unit
        return 72.0
    return None


def dpi_scale(
    unit: str, dpi: Optional[float], alto_dpi: Optional[float] = None
) -> Tuple[float, float]:
    if not dpi:
        return 1.0, 1.0
    upi = unit_per_inch(unit)
    if upi:
        return float(dpi) / upi, float(dpi) / upi
    if unit == "pixel":
        adpi = alto_dpi or dpi
        if not adpi:
            return 1.0, 1.0
        return float(dpi) / float(adpi), float(dpi) / float(adpi)
    return 1.0, 1.0


def scale_bbox_coords(value: str, sx: float, sy: float, dx: float = 0.0, dy: float = 0.0) -> str:
    parts = value.split()
    if len(parts) != 4:
        return value
    try:
        x1, y1, x2, y2 = map(float, parts)
        nx1 = round((x1 - dx) * sx)
        ny1 = round((y1 - dy) * sy)
        nx2 = round((x2 - dx) * sx)
        ny2 = round((y2 - dy) * sy)
        return f"{nx1} {ny1} {nx2} {ny2}"
    except ValueError:
        return value


def fix_name_close_tags(text: str) -> Tuple[str, int]:
    """Repairs malformed </n> to </name>, returning (fixed_text, replacement_count)."""
    return _NAME_CLOSE_RE.subn("</name>", text)


def set_surface_extent(text: str, w: int, h: int) -> str:
    def repl(m: "re.Match[str]") -> str:
        tag = LRX_RE.sub(rf"\g<1>{w}\g<3>", m.group(0))
        tag = LRY_RE.sub(rf"\g<1>{h}\g<3>", tag)
        return tag

    return SURFACE_RE.sub(repl, text)


def rewrite_bboxes(text: str, scale_fn) -> str:
    def repl(m: "re.Match[str]") -> str:
        return f'bbox="{scale_fn(m.group(1))}"'

    return BBOX_RE.sub(repl, text)


def detect_source_size(xml_text: str) -> Tuple[Optional[int], Optional[int], Optional[str]]:
    """Return (width, height, source_kind) of the document's coordinate space."""
    for surf in SURFACE_RE.findall(xml_text):
        mx = LRX_RE.search(surf)
        my = LRY_RE.search(surf)
        if mx and my:
            try:
                w = int(round(float(mx.group(2))))
                h = int(round(float(my.group(2))))
                if w > 0 and h > 0:
                    return w, h, "surface"
            except ValueError:
                continue

    max_x = max_y = 0.0
    for raw in BBOX_RE.findall(xml_text):
        parts = raw.split()
        if len(parts) != 4:
            continue
        try:
            _, _, x2, y2 = (float(p) for p in parts)
            max_x = max(max_x, x2)
            max_y = max(max_y, y2)
        except ValueError:
            continue

    if max_x > 0 and max_y > 0:
        return int(round(max_x)), int(round(max_y)), "bbox-extent"

    return None, None, None
