"""PDF text + coordinate extraction using PyMuPDF.

Produces, for each page, a reconstructed reading-order text string together with
an offset->bbox index so that later regex matches on the text can be mapped back
to precise on-page bounding boxes for redaction.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import fitz  # PyMuPDF

MIN_TEXT_LAYER_CHARS = 10


@dataclass
class WordOffset:
    start: int
    end: int
    bbox: tuple[float, float, float, float]


@dataclass
class LineSpan:
    """One visual text line (a PDF block line - in a table, usually one cell)."""
    start: int
    end: int
    bbox: tuple[float, float, float, float]


@dataclass
class PageIndex:
    page: int
    text: str
    offsets: list[WordOffset] = field(default_factory=list)
    lines: list[LineSpan] = field(default_factory=list)


@dataclass
class ExtractionResult:
    page_count: int
    has_text_layer: bool
    pages: list[PageIndex]
    words: list[dict]  # flat list for the raw coordinate report (section 12)


def _build_page_index(page: fitz.Page, page_number: int) -> tuple[PageIndex, list[dict]]:
    raw_words = page.get_text("words")  # (x0,y0,x1,y1,text,block_no,line_no,word_no)
    raw_words.sort(key=lambda w: (w[5], w[6], w[7]))

    text_parts: list[str] = []
    offsets: list[WordOffset] = []
    flat_words: list[dict] = []
    pos = 0
    prev_block = prev_line = None

    for x0, y0, x1, y1, wtext, block_no, line_no, _word_no in raw_words:
        if prev_block is not None:
            if block_no != prev_block or line_no != prev_line:
                text_parts.append("\n")
            else:
                text_parts.append(" ")
            pos += 1
        start = pos
        text_parts.append(wtext)
        pos += len(wtext)
        end = pos
        offsets.append(WordOffset(start=start, end=end, bbox=(x0, y0, x1, y1)))
        flat_words.append({"page": page_number, "text": wtext, "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)]})
        prev_block, prev_line = block_no, line_no

    full_text = "".join(text_parts)
    return PageIndex(page=page_number, text=full_text, offsets=offsets, lines=_group_lines(offsets, full_text)), flat_words


def _group_lines(offsets: list[WordOffset], text: str) -> list[LineSpan]:
    lines: list[LineSpan] = []
    current: list[WordOffset] = []
    for o in offsets:
        if current and text[current[-1].end:o.start] == "\n":
            lines.append(_line_from(current))
            current = []
        current.append(o)
    if current:
        lines.append(_line_from(current))
    return lines


def _line_from(words: list[WordOffset]) -> LineSpan:
    return LineSpan(
        start=words[0].start,
        end=words[-1].end,
        bbox=(min(w.bbox[0] for w in words), min(w.bbox[1] for w in words),
              max(w.bbox[2] for w in words), max(w.bbox[3] for w in words)),
    )


def extract_document(pdf_path: str) -> ExtractionResult:
    doc = fitz.open(pdf_path)
    pages: list[PageIndex] = []
    all_words: list[dict] = []
    total_chars = 0

    try:
        for i in range(doc.page_count):
            page = doc[i]
            page_index, flat_words = _build_page_index(page, i)
            pages.append(page_index)
            all_words.extend(flat_words)
            total_chars += len(page_index.text.strip())
    finally:
        doc.close()

    has_text_layer = total_chars >= MIN_TEXT_LAYER_CHARS

    return ExtractionResult(
        page_count=len(pages),
        has_text_layer=has_text_layer,
        pages=pages,
        words=all_words,
    )


def bbox_for_span(page_index: PageIndex, start: int, end: int) -> tuple[float, float, float, float] | None:
    """Union the bounding boxes of every word overlapping the [start, end) text span."""
    matched = [o for o in page_index.offsets if not (o.end <= start or o.start >= end)]
    if not matched:
        return None
    x0 = min(o.bbox[0] for o in matched)
    y0 = min(o.bbox[1] for o in matched)
    x1 = max(o.bbox[2] for o in matched)
    y1 = max(o.bbox[3] for o in matched)
    return (x0, y0, x1, y1)


def bboxes_for_span(page_index: PageIndex, start: int, end: int) -> list[tuple[float, float, float, float]]:
    """Return one bbox per visual line so multi-line matches get tight per-line
    rectangles instead of one oversized union box."""
    matched = [o for o in page_index.offsets if not (o.end <= start or o.start >= end)]
    if not matched:
        return []

    LINE_TOLERANCE = 3.0
    matched.sort(key=lambda o: (o.bbox[1], o.bbox[0]))

    lines: list[list[WordOffset]] = []
    for o in matched:
        if lines and abs(o.bbox[1] - lines[-1][0].bbox[1]) < LINE_TOLERANCE:
            lines[-1].append(o)
        else:
            lines.append([o])

    result = []
    for group in lines:
        x0 = min(o.bbox[0] for o in group)
        y0 = min(o.bbox[1] for o in group)
        x1 = max(o.bbox[2] for o in group)
        y1 = max(o.bbox[3] for o in group)
        result.append((x0, y0, x1, y1))
    return result
