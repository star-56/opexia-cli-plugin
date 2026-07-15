# pxcore/renderer/ — deterministic text -> PNG, pure standard library.
#
# render() lays monospace glyphs onto a greyscale page at the profile's geometry, clamps to
# the resample cap (so we never pay for pixels the model won't ingest), and — when imaging a
# reference block — pulls any embedded EXACT spans (ids, paths, hashes) out into a verbatim
# text factsheet that travels beside the image. The picture carries the bulk; the factsheet
# carries the things a vision model must not be trusted to reproduce.
from __future__ import annotations

import re
from typing import List, Tuple

from pxcore.renderer import png as pngmod
from pxcore.renderer.font import CELL, glyph_bitmap
from pxcore.types import Geometry, Rendered

_INK, _BG = 0, 255            # black text on white — maximum contrast for a vision encoder


# --- exact-span extraction (the factsheet) ----------------------------------
# These are the token classes a vision channel silently confabulates. Anything matching goes
# to the factsheet as verbatim text even when the surrounding block is imaged.
_EXACT_PATTERNS = [
    re.compile(r"\b[0-9a-fA-F]{8,}\b"),                      # hex ids / hashes
    re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
               r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),         # UUID
    re.compile(r"(?:[A-Za-z]:)?[/\\][\w.\-/\\]+\.\w+"),      # file paths
    re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b"),                   # ERROR_CODES / CONSTS
    re.compile(r":\d+:\d+|:\d+\b"),                          # line:col refs
]


def extract_exact_spans(text: str, limit: int = 200) -> List[str]:
    seen: List[str] = []
    for pat in _EXACT_PATTERNS:
        for m in pat.findall(text):
            s = m if isinstance(m, str) else m[0]
            if s and s not in seen:
                seen.append(s)
                if len(seen) >= limit:
                    return seen
    return seen


def build_factsheet(text: str) -> str:
    spans = extract_exact_spans(text)
    if not spans:
        return ""
    return "Exact identifiers (verbatim, not in the image):\n" + "\n".join(spans)


# --- layout + raster --------------------------------------------------------

def _wrap(text: str, cols: int) -> List[str]:
    out: List[str] = []
    for line in text.replace("\t", "    ").split("\n"):
        if not line:
            out.append("")
            continue
        while len(line) > cols:
            out.append(line[:cols])
            line = line[cols:]
        out.append(line)
    return out


def _clamp_geometry(g: Geometry, rows_needed: int, cols_needed: int) -> Geometry:
    """Size the page to the CONTENT in BOTH dimensions (not a fixed page), clamped to the
    resample cap. Blank pixels are paid for the same as inked ones, so a block of narrow lines
    must not pay for a full-width page, and a short block must not pay for a full-height one.
    Rendering above the cap pays for pixels the model never ingests, so both edges are bounded."""
    needed_h = max(g.cell_h + 2 * g.pad, rows_needed * g.cell_h + 2 * g.pad)
    needed_w = max(g.cell_w + 2 * g.pad, cols_needed * g.cell_w + 2 * g.pad)
    page_h = min(needed_h, g.resample_cap)
    page_w = min(needed_w, g.page_w, g.resample_cap)
    return Geometry(page_w, page_h, g.cell_w, g.cell_h, g.resample_cap, g.pad)


def _max_rows(geometry: Geometry) -> int:
    return max(1, (geometry.resample_cap - 2 * geometry.pad) // geometry.cell_h)


def fits_one_page(text: str, geometry: Geometry) -> bool:
    """Does the whole block fit one capped page? If not, the caller must keep it as text OR
    paginate it (see paginate) — silently truncating imaged content would drop data with no
    error, the exact failure this product exists to avoid."""
    return len(_wrap(text, geometry.cols)) <= _max_rows(geometry)


def paginate(text: str, geometry: Geometry) -> List[str]:
    """Split a block into page-sized text chunks, each guaranteed to fit ONE capped page.

    Wrapping-aware: the block is wrapped to the page width first, then its rows are grouped
    into pages of at most _max_rows(geometry) rows. A block that already fits one page returns
    [text] unchanged (so the single-page path stays byte-identical — cache-safe). This is what
    lets an oversized block image across MULTIPLE pages instead of falling to keep-text: every
    row lands on exactly one page, so there is no silent truncation. Each returned chunk, when
    re-wrapped by render() at the same width, is a no-op re-wrap and therefore fits_one_page."""
    lines = _wrap(text, geometry.cols)
    mr = _max_rows(geometry)
    if len(lines) <= mr:
        return [text]
    return ["\n".join(lines[i:i + mr]) for i in range(0, len(lines), mr)]


def _blank_page(w: int, h: int) -> List[bytearray]:
    return [bytearray([_BG] * w) for _ in range(h)]


def _draw_char(page: List[bytearray], ch: str, x0: int, y0: int,
               cell_w: int, cell_h: int, page_w: int, page_h: int) -> None:
    bmp = glyph_bitmap(ch)                        # 8x8 of 0/1
    sx = cell_w / CELL
    sy = cell_h / CELL
    for gy in range(CELL):
        for gx in range(CELL):
            if not bmp[gy][gx]:
                continue
            # nearest-neighbour scale the 8x8 glyph into the cell (no anti-alias, on purpose)
            for py in range(int(gy * sy), int((gy + 1) * sy) or int(gy * sy) + 1):
                yy = y0 + py
                if yy < 0 or yy >= page_h:
                    continue
                rowbuf = page[yy]
                for px in range(int(gx * sx), int((gx + 1) * sx) or int(gx * sx) + 1):
                    xx = x0 + px
                    if 0 <= xx < page_w:
                        rowbuf[xx] = _INK


def _tokens_for(w: int, h: int) -> int:
    """Anthropic's documented image-token estimate: ~ (width_px * height_px) / 750. This is
    the real billed cost of the image, and it is what makes the savings figure honest — a
    picture is not free, and the gate only wins when the text it replaces costs more."""
    return max(1, round((w * h) / 750.0))


def render(text: str, geometry: Geometry, *, with_factsheet: bool = True) -> Rendered:
    cols = geometry.cols
    lines = _wrap(text, cols)
    longest = max((len(ln) for ln in lines), default=1)
    g = _clamp_geometry(geometry, len(lines), longest)
    page = _blank_page(g.page_w, g.page_h)

    max_rows = g.rows
    for r, line in enumerate(lines[:max_rows]):
        y0 = g.pad + r * g.cell_h
        for c, ch in enumerate(line):
            if ch == " ":
                continue
            x0 = g.pad + c * g.cell_w
            _draw_char(page, ch, x0, y0, g.cell_w, g.cell_h, g.page_w, g.page_h)

    png_bytes = pngmod.encode_gray8(g.page_w, g.page_h, page)
    factsheet = build_factsheet(text) if with_factsheet else ""
    return Rendered(png=png_bytes, factsheet=factsheet, width=g.page_w, height=g.page_h,
                    est_image_tokens=_tokens_for(g.page_w, g.page_h))
