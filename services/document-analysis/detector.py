"""Regex + keyword based sensitive-data detection.

No machine learning. Every detection is produced deterministically from a
regex pattern or a keyword dictionary entry loaded by the caller (typically
sourced from the database, seeded from config/patterns.json and
config/keywords.json).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from extractor import ExtractionResult, PageIndex, bbox_for_span, bboxes_for_span


@dataclass
class PatternRule:
    name: str
    category: str
    pattern: str
    priority: int = 50
    requires_keyword_context: bool = False
    context_keywords: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass
class Detection:
    category: str
    page: int
    bbox: tuple[float, float, float, float] | None
    bboxes: list[tuple[float, float, float, float]] = field(default_factory=list)
    value: str = ""  # raw matched text - kept only in-memory for this request
    source: str = ""  # "regex" or "keyword"
    rule_name: str = ""


def _luhn_valid(digits: str) -> bool:
    digits = re.sub(r"\D", "", digits)
    if len(digits) < 12:
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# (prefix_range_start, prefix_range_end, digit_length) per major card network.
# A match must fall in one of these IIN/BIN ranges in addition to passing Luhn -
# this is the same two-factor check real card scanners use, and meaningfully
# cuts false positives versus Luhn alone (roughly 1 in 10 random numbers is
# Luhn-valid by chance).
_CARD_NETWORK_RANGES: list[tuple[int, int, set[int]]] = [
    (4000, 4999, {13, 16, 19}),  # Visa
    (5100, 5599, {16}),  # Mastercard (legacy range)
    (2221, 2720, {16}),  # Mastercard (2017+ range)
    (3400, 3499, {15}),  # Amex
    (3700, 3799, {15}),  # Amex
    (6011, 6011, {16, 19}),  # Discover
    (6440, 6499, {16, 19}),  # Discover
    (6500, 6599, {16, 19}),  # Discover
    (3000, 3059, {14}),  # Diners Club
    (3600, 3699, {14}),  # Diners Club
    (3800, 3899, {14}),  # Diners Club
    (3528, 3589, {16}),  # JCB
]


def _card_network_valid(digits: str) -> bool:
    digits = re.sub(r"\D", "", digits)
    if not digits:
        return False
    prefix4 = int(digits[:4]) if len(digits) >= 4 else -1
    length = len(digits)
    return any(lo <= prefix4 <= hi and length in lengths for lo, hi, lengths in _CARD_NETWORK_RANGES)


def _nic_new_format_plausible(value: str) -> bool:
    """The new-format Sri Lankan NIC encodes a 4-digit birth year followed by
    a 3-digit day-of-year (1-366 for men, 501-866 for women). A bare 12-digit
    number that can't possibly be a valid date-of-birth encoding is almost
    certainly something else (an account number, a PO number, a serial, ...),
    so this rejects it rather than flag a false positive."""
    digits = re.sub(r"\D", "", value)
    if len(digits) != 12:
        return False
    year = int(digits[:4])
    if not 1900 <= year <= 2030:
        return False
    day_component = int(digits[4:7])
    return 1 <= day_component <= 366 or 501 <= day_component <= 866


class ClaimedRanges:
    """Tracks already-claimed character ranges per page so higher-priority
    patterns win overlapping matches (e.g. a card number should not also be
    reported as a bank account and a bare NIC)."""

    def __init__(self) -> None:
        self._ranges: dict[int, list[tuple[int, int, int]]] = {}

    def is_claimed(self, page: int, start: int, end: int) -> bool:
        for cs, ce, _prio in self._ranges.get(page, []):
            if not (end <= cs or start >= ce):
                return True
        return False

    def claim(self, page: int, start: int, end: int, priority: int) -> None:
        self._ranges.setdefault(page, []).append((start, end, priority))


_TERM_CACHE: dict[str, re.Pattern] = {}


def _term_regex(term: str) -> re.Pattern:
    """Whole-word, case-insensitive match, so "account" does not fire on
    "Accounts Executive" or "accounts@company.lk"."""
    compiled = _TERM_CACHE.get(term)
    if compiled is None:
        compiled = re.compile(r"(?<![a-z0-9])" + re.escape(term.lower().strip()) + r"(?![a-z0-9])")
        _TERM_CACHE[term] = compiled
    return compiled


def _has_term(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(_term_regex(t).search(lowered) for t in terms if t.strip())


MAX_LABEL_CHARS = 40  # a table header or form label, not a paragraph


def _cell_context(page_index: PageIndex, start: int, end: int) -> str:
    """Text a human would read as the label of a value laid out in a table or
    form: the cell(s) to its left on the same row, and the nearest column
    header above it. PDF extraction returns each cell as its own line, so the
    same-line check alone misses "Account no. | 1234567890" and a "Gross pay"
    column. A header is a short line with no digits; a "label: value" line
    above (such as "password: x1") is a value, not a header, so it can't
    lend its label to the next line down."""
    box = bbox_for_span(page_index, start, end)
    if box is None:
        return ""
    x0, y0, x1, y1 = box
    mid_y = (y0 + y1) / 2
    parts: list[str] = []
    header, header_y = None, None
    for line in page_index.lines:
        if line.start <= start < line.end:
            continue
        lx0, ly0, lx1, ly1 = line.bbox
        label = page_index.text[line.start:line.end]
        if len(label) > MAX_LABEL_CHARS:
            continue
        if ly0 <= mid_y <= ly1 and lx1 <= x0 + 2:
            parts.append(label)
        elif ly1 <= y0 + 1 and lx0 < x1 and lx1 > x0 and not any(ch.isdigit() for ch in label):
            if header_y is None or ly1 > header_y:
                header, header_y = label, ly1
    if header:
        parts.append(header)
    return "\n".join(parts)


def _line_context(text: str, pos: int) -> str:
    """The value's own line plus the tail of the line before it, so a label at
    the end of a wrapped sentence ("...your basic salary") still counts for an
    amount at the start of the next line. Only the part of the previous line
    after its last digit is used: in "Bank Account Number: 12345678" the label
    already has its value and must not claim the next line's number too."""
    line_start = text.rfind("\n", 0, pos) + 1
    line_end = text.find("\n", pos)
    if line_end == -1:
        line_end = len(text)
    context = text[line_start:line_end]
    if line_start:
        prev_start = text.rfind("\n", 0, line_start - 1) + 1
        prev = text[prev_start:line_start - 1]
        tail = re.split(r"\d", prev)[-1]
        context = tail + "\n" + context
    return context


def detect(
    extraction: ExtractionResult,
    rules: list[PatternRule],
    keywords: dict[str, list[str]],
) -> list[Detection]:
    detections: list[Detection] = []
    claimed = ClaimedRanges()

    ordered_rules = sorted([r for r in rules if r.enabled], key=lambda r: -r.priority)

    for page_index in extraction.pages:
        text = page_index.text
        if not text.strip():
            continue

        for rule in ordered_rules:
            try:
                compiled = re.compile(rule.pattern)
            except re.error:
                continue

            for m in compiled.finditer(text):
                start, end = m.start(), m.end()
                if claimed.is_claimed(page_index.page, start, end):
                    continue

                matched_text = m.group(0)

                # Card numbers must pass Luhn and a network range check. A short
                # card-category match is a security code (CVV), which has no checksum.
                is_card_number = len(re.sub(r"\D", "", matched_text)) >= 12
                if rule.category == "card" and is_card_number and not (
                        _luhn_valid(matched_text) and _card_network_valid(matched_text)):
                    continue

                if rule.name == "new_nic" and not _nic_new_format_plausible(matched_text):
                    continue

                if rule.requires_keyword_context:
                    if not (_has_term(_line_context(text, start), rule.context_keywords)
                            or _has_term(_cell_context(page_index, start, end), rule.context_keywords)):
                        continue

                bbox = bbox_for_span(page_index, start, end)
                multi = bboxes_for_span(page_index, start, end)
                claimed.claim(page_index.page, start, end, rule.priority)
                detections.append(
                    Detection(
                        category=rule.category,
                        page=page_index.page,
                        bbox=bbox,
                        bboxes=multi,
                        value=matched_text.strip(),
                        source="regex",
                        rule_name=rule.name,
                    )
                )

        # Keyword dictionary pass (phrase search, case-insensitive).
        # Keywords are field labels ("salary", "account", "passport") that
        # signal a category is present — they feed risk scoring but are NOT
        # redaction targets, so bbox is intentionally left empty.
        lowered = text.lower()
        for category, terms in keywords.items():
            for term in terms:
                if not term.strip():
                    continue
                for m in _term_regex(term).finditer(lowered):
                    start, end = m.start(), m.end()
                    if claimed.is_claimed(page_index.page, start, end):
                        continue
                    claimed.claim(page_index.page, start, end, 10)
                    detections.append(
                        Detection(
                            category=category,
                            page=page_index.page,
                            bbox=None,
                            bboxes=[],
                            value=text[start:end],
                            source="keyword",
                            rule_name=term,
                        )
                    )

    return detections


def summarize_categories(detections: list[Detection]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in detections:
        counts[d.category] = counts.get(d.category, 0) + 1
    return counts


def value_categories(detections: list[Detection]) -> set[str]:
    """Categories backed by at least one matched value, not just a keyword."""
    return {d.category for d in detections if d.source == "regex"}
