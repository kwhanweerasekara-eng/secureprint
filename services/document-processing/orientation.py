"""Turns sideways pages upright before the watermark and footer are stamped.

A landscape document printed on portrait paper reaches SecurePrint as a
portrait page with its text running down or up the page (the print system
rotated it to fit). Stamping that page as-is puts the footer along the short
edge, sideways to the content. Setting the page's display rotation instead
shows the content upright and gives the footer and watermark the content's
own bottom edge. The page content itself is not changed.
"""
from __future__ import annotations

import fitz  # PyMuPDF

# Display rotation that makes text running in this direction read left to right.
_ROTATION_FOR_DIRECTION = {
    (0, 1): 270,   # text runs down the page
    (0, -1): 90,   # text runs up the page
    (-1, 0): 180,  # upside down
}

MIN_CHARACTERS = 20  # too little text to judge (e.g. a scan): leave the page alone
MIN_SHARE = 0.6      # sideways text must clearly dominate


def upright_rotation(page: fitz.Page) -> int:
    """Rotation to apply to an unrotated page so its text reads upright, or 0."""
    counts: dict[tuple[int, int], int] = {}
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            direction = (round(line["dir"][0]), round(line["dir"][1]))
            counts[direction] = counts.get(direction, 0) + sum(len(s["text"].strip()) for s in line["spans"])
    total = sum(counts.values())
    if total < MIN_CHARACTERS:
        return 0
    direction, chars = max(counts.items(), key=lambda item: item[1])
    if direction not in _ROTATION_FOR_DIRECTION or chars / total < MIN_SHARE:
        return 0
    return _ROTATION_FOR_DIRECTION[direction]


def straighten_pages(doc: fitz.Document) -> int:
    """Turn every sideways page upright. Pages that already carry a rotation are
    left as they are. Returns the number of pages turned."""
    turned = 0
    for page in doc:
        if page.rotation:
            continue
        rotation = upright_rotation(page)
        if rotation:
            page.set_rotation(rotation)
            turned += 1
    return turned
