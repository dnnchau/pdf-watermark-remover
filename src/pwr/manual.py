"""Page-scope parsing and safety checks for user-drawn removal regions."""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf

from .fingerprint import to_rect
from .models import ManualRegion, Rect


def parse_page_scope(scope: str, page_count: int, current_page: int) -> tuple[int, ...]:
    """Parse `all`, odd/even, or human one-based ranges such as `1-4,8`."""
    if page_count <= 0:
        return ()
    value = scope.strip().lower()
    if not value or value in {"current", "hiện tại", "trang hiện tại"}:
        return (max(0, min(page_count - 1, current_page)),)
    if value in {"all", "tất cả", "tat ca", "*"}:
        return tuple(range(page_count))
    if value in {"odd", "lẻ", "le"}:
        return tuple(index for index in range(page_count) if (index + 1) % 2 == 1)
    if value in {"even", "chẵn", "chan"}:
        return tuple(index for index in range(page_count) if (index + 1) % 2 == 0)

    pages: set[int] = set()
    for part in value.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text) if start_text else 1
            end = int(end_text) if end_text else page_count
            if start > end:
                start, end = end, start
            pages.update(range(max(1, start) - 1, min(page_count, end)))
        else:
            page = int(part)
            if 1 <= page <= page_count:
                pages.add(page - 1)
    if not pages:
        raise ValueError("Phạm vi trang không hợp lệ. Ví dụ: 1-5,8 hoặc tất cả.")
    return tuple(sorted(pages))


@dataclass(frozen=True)
class ManualRisk:
    pages_checked: int
    text_hits: int
    image_hits: int
    drawing_hits: int

    @property
    def total(self) -> int:
        return self.text_hits + self.image_hits + self.drawing_hits

    def message(self) -> str:
        if not self.total:
            return f"Không thấy nội dung nền trong vùng trên {self.pages_checked} trang mẫu."
        return (
            f"Cảnh báo: vùng vẽ chạm {self.text_hits} khối chữ, {self.image_hits} ảnh "
            f"và {self.drawing_hits} nét vẽ trên {self.pages_checked} trang mẫu."
        )


def assess_manual_region(path: str, region: ManualRegion, sample_limit: int = 12) -> ManualRisk:
    """Sample the selected pages and report content that a hard redaction may remove."""
    chosen = list(region.pages)
    if len(chosen) > sample_limit:
        step = (len(chosen) - 1) / max(1, sample_limit - 1)
        chosen = sorted({chosen[round(index * step)] for index in range(sample_limit)})

    text_hits = image_hits = drawing_hits = 0
    doc = pymupdf.open(path)
    try:
        for page_no in chosen:
            if not 0 <= page_no < doc.page_count:
                continue
            page = doc[page_no]
            rect = region.rect
            text_hits += sum(
                1
                for block in page.get_text("blocks")
                if len(block) >= 4 and rect.intersects(Rect(*map(float, block[:4])))
            )
            image_hits += sum(
                1
                for image in page.get_image_info()
                if image.get("bbox") and rect.intersects(Rect(*map(float, image["bbox"])))
            )
            drawing_hits += sum(
                1 for drawing in page.get_drawings() if rect.intersects(to_rect(drawing["rect"]))
            )
    finally:
        doc.close()
    return ManualRisk(len(chosen), text_hits, image_hits, drawing_hits)
