"""Synthetic PDFs that mimic the real watermark shapes found in the wild."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image, ImageDraw

PAGE_COUNT = 12
PAGE_W, PAGE_H = 595.0, 842.0


def _watermark_png(text: str = "SAMPLE 123") -> bytes:
    image = Image.new("RGBA", (356, 81), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.text((10, 25), text, fill=(128, 128, 128, 120))
    draw.rectangle((2, 2, 353, 78), outline=(128, 128, 128, 120), width=3)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def build_pdf(
    path: str,
    with_image_mark: bool = True,
    with_trial_badge: bool = True,
    pages: int = PAGE_COUNT,
) -> str:
    doc = pymupdf.open()
    png = _watermark_png()
    for index in range(pages):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.insert_text((72, 120), f"Question {index + 1}", fontsize=16)
        page.insert_text(
            (72, 160),
            f"Body copy unique to page {index + 1} lorem ipsum dolor sit amet.",
            fontsize=11,
        )
        # Legitimate repeated furniture: a running header and a page number.
        page.insert_text((72, 40), "HACKERS SAMPLE BOOK", fontsize=9)
        page.insert_text((PAGE_W / 2, PAGE_H - 40), f"{index + 1}", fontsize=9)

        if with_image_mark:
            page.insert_image(
                pymupdf.Rect(140, 300, 460, 560), stream=png, rotate=90, overlay=True
            )
        if with_trial_badge:
            page.draw_rect(
                pymupdf.Rect(4, 4, 74, 74), color=(0, 0, 0), fill=(1, 0.84, 0), width=1
            )
            page.insert_text((8, 30), "Click to BUY NOW!", fontsize=6)
            page.insert_text((8, 44), "www.pdf-xchange.com", fontsize=5)
            # Page content that happens to sit inside the badge's bounding box:
            # it must survive the badge being removed.
            page.insert_text((30, 66), f"keep{index}", fontsize=7)
    doc.save(path, garbage=4, deflate=True)
    doc.close()
    return path


@pytest.fixture
def marked_pdf(tmp_path) -> str:
    return build_pdf(str(tmp_path / "marked.pdf"))


@pytest.fixture
def clean_pdf(tmp_path) -> str:
    return build_pdf(
        str(tmp_path / "clean.pdf"), with_image_mark=False, with_trial_badge=False
    )
