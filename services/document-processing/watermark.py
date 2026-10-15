"""Applies a configurable diagonal classification watermark to every page.

Tiled across the page at a modest size/opacity (the way Google Docs / Microsoft
Purview sensitivity labels do it) rather than one oversized centered word -
readable as a security marking without obscuring the document underneath it.
"""
from __future__ import annotations

import fitz  # PyMuPDF


def apply_watermark(
    doc: fitz.Document,
    text: str = "RESTRICTED",
    opacity: float = 0.10,
    font_size: int = 26,
    angle: float = 45,
    color: tuple[float, float, float] = (0.62, 0.13, 0.13),
) -> None:
    for page in doc:
        # Drawing happens in unrotated coordinates; on a page shown rotated,
        # turn the text with the page so it slants the same way as on any other.
        rect = (page.rect * page.derotation_matrix).normalize()
        center = fitz.Point(rect.width / 2, rect.height / 2)
        mat = fitz.Matrix(1, 1).prerotate(angle + page.rotation)
        text_width = fitz.get_text_length(text, fontname="helv", fontsize=font_size)

        # Tile spacing: generous gaps so the pattern reads as a subtle texture,
        # staggering alternate rows so it doesn't line up into a grid.
        step_x = text_width + max(60.0, font_size * 2.2)
        step_y = font_size * 3.4

        # Oversize the tiled area beyond the page bounds so rotated text still
        # covers every corner.
        margin_x = rect.width * 0.35
        margin_y = rect.height * 0.35

        row = 0
        y = -margin_y
        while y < rect.height + margin_y:
            x_offset = (row % 2) * (step_x / 2)
            x = -margin_x + x_offset
            while x < rect.width + margin_x:
                insert_point = fitz.Point(x, y)
                pivot = fitz.Point(x + text_width / 2, y)
                page.insert_text(
                    insert_point,
                    text,
                    fontsize=font_size,
                    fontname="helv",
                    color=color,
                    fill_opacity=opacity,
                    morph=(pivot, mat),
                    render_mode=0,
                )
                x += step_x
            y += step_y
            row += 1

        # A single, slightly larger centered mark keeps the classification
        # readable at a glance even if the page is mostly whitespace.
        anchor_font_size = font_size * 1.6
        anchor_width = fitz.get_text_length(text, fontname="helv", fontsize=anchor_font_size)
        anchor_point = fitz.Point(center.x - anchor_width / 2, center.y)
        page.insert_text(
            anchor_point,
            text,
            fontsize=anchor_font_size,
            fontname="helv",
            color=color,
            fill_opacity=min(opacity * 1.8, 0.4),
            morph=(center, mat),
            render_mode=0,
        )
