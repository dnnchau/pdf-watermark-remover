"""Prove that a cleaned file lost the watermark and nothing else."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pymupdf

from .models import Rect

DIFF_THRESHOLD = 8
# A clean run must not disturb more than this share of pixels outside the marks.
MAX_OUTSIDE_RATIO = 0.002


@dataclass(frozen=True)
class PageDiff:
    page_no: int
    changed_inside: float
    changed_outside: float

    @property
    def ok(self) -> bool:
        return self.changed_outside <= MAX_OUTSIDE_RATIO


def _render(doc: pymupdf.Document, page_no: int, dpi: int) -> np.ndarray:
    pix = doc[page_no].get_pixmap(dpi=dpi)
    array = np.frombuffer(pix.samples, dtype=np.uint8)
    return array.reshape(pix.height, pix.width, pix.n).astype(np.int16)


def _mask(shape: tuple[int, int], rects: list[Rect], dpi: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    scale = dpi / 72.0
    for rect in rects:
        y0 = max(0, int(rect.y0 * scale) - 2)
        y1 = min(shape[0], int(rect.y1 * scale) + 2)
        x0 = max(0, int(rect.x0 * scale) - 2)
        x1 = min(shape[1], int(rect.x1 * scale) + 2)
        if y1 > y0 and x1 > x0:
            mask[y0:y1, x0:x1] = True
    return mask


def compare_pages(
    src: str, dst: str, pages: list[int], removed_rects: list[Rect], dpi: int = 100
) -> list[PageDiff]:
    """Changed-pixel ratios inside vs outside the removed regions."""
    before = pymupdf.open(src)
    after = pymupdf.open(dst)
    try:
        diffs: list[PageDiff] = []
        for page_no in pages:
            if page_no >= before.page_count or page_no >= after.page_count:
                continue
            a = _render(before, page_no, dpi)
            b = _render(after, page_no, dpi)
            if a.shape != b.shape:
                diffs.append(PageDiff(page_no, 1.0, 1.0))
                continue
            changed = np.abs(a - b).sum(axis=2) > DIFF_THRESHOLD
            mask = _mask(changed.shape, removed_rects, dpi)
            inside_total = int(mask.sum()) or 1
            outside_total = int((~mask).sum()) or 1
            diffs.append(
                PageDiff(
                    page_no=page_no,
                    changed_inside=float(changed[mask].sum()) / inside_total,
                    changed_outside=float(changed[~mask].sum()) / outside_total,
                )
            )
        return diffs
    finally:
        before.close()
        after.close()


def summarize(diffs: list[PageDiff]) -> str:
    if not diffs:
        return "Không có trang nào được đối chiếu."
    worst = max(d.changed_outside for d in diffs)
    inside = sum(d.changed_inside for d in diffs) / len(diffs)
    status = "an toàn" if all(d.ok for d in diffs) else "CẢNH BÁO"
    return (
        f"Đã đối chiếu {len(diffs)} trang mẫu — {status}: "
        f"{inside:.1%} pixel thay đổi trong vùng watermark, "
        f"{worst:.2%} ngoài vùng."
    )
