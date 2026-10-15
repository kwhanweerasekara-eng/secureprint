"""Sideways pages (a landscape document printed on portrait paper) are shown
upright, with the footer and watermark along the content's own bottom edge."""
import fitz

from tests.conftest import make_pdf

LINES = [
    "WSO2 COURSE COMPLETION CERTIFICATE",
    "This is to certify that Kehan Weerasekera (Intern)",
    "has successfully completed AI Gateway: Foundations",
]


def make_sideways_pdf(path, text_rotate):
    """A portrait page whose text was turned by the print system, the way
    macOS sends a landscape document printed with Auto Rotate."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    x = 120 if text_rotate == 270 else 475
    for i, line in enumerate(LINES):
        offset = 24 * i if text_rotate == 270 else -24 * i
        page.insert_text((x - offset, 120 if text_rotate == 270 else 720), line, fontsize=14, rotate=text_rotate)
    doc.save(str(path))
    return str(path)


def sanitize(engine, src, out, watermark=False):
    options = engine.processor.SanitizeOptions(
        require_masking=False,
        require_watermark=watermark,
        require_footer=True,
        watermark_text="PUBLIC",
        footer_text="PUBLIC | SecurePrint Demo Org PROTECTED | SP-TEST | 2026-10-15 06:00 UTC",
    )
    engine.processor.sanitize_document(src, out, [], options)
    return fitz.open(out)[0]


def footer_box(page):
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            if "SP-TEST" in "".join(s["text"] for s in line["spans"]):
                # get_text reports unrotated coordinates; map to the page as shown
                return fitz.Rect(line["bbox"]) * page.rotation_matrix
    return None


def test_upright_rotation_for_each_direction(engine, tmp_path):
    assert engine.orientation.upright_rotation(fitz.open(make_sideways_pdf(tmp_path / "down.pdf", 270))[0]) == 270
    assert engine.orientation.upright_rotation(fitz.open(make_sideways_pdf(tmp_path / "up.pdf", 90))[0]) == 90
    assert engine.orientation.upright_rotation(fitz.open(make_pdf(tmp_path / "plain.pdf", LINES))[0]) == 0


def test_little_text_is_left_alone(engine, tmp_path):
    doc = fitz.open()
    doc.new_page().insert_text((300, 100), "p. 3", rotate=270)
    assert engine.orientation.upright_rotation(doc[0]) == 0


def test_sideways_page_is_turned_and_footer_sits_under_content(engine, tmp_path):
    page = sanitize(engine, make_sideways_pdf(tmp_path / "cert.pdf", 270), str(tmp_path / "out.pdf"), watermark=True)

    assert page.rotation == 270
    assert page.rect.width > page.rect.height  # shown as landscape
    box = footer_box(page)
    assert box is not None
    box.normalize()
    assert box.y0 > page.rect.height - 40  # along the bottom edge as shown
    assert box.width > box.height  # running across the page, not up its side


def test_portrait_page_is_unchanged(engine, tmp_path):
    page = sanitize(engine, make_pdf(tmp_path / "plain.pdf", LINES), str(tmp_path / "out.pdf"), watermark=True)

    assert page.rotation == 0
    box = footer_box(page)
    assert box is not None
    assert box.y0 > page.rect.height - 40
