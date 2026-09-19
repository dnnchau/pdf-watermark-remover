"""Facade tying sampling, detection, scoring and thumbnails together."""

from __future__ import annotations

import os
import random

import pymupdf

from .detect import count_image_pages, detect_images, detect_marks
from .models import (
    AnalyzeReport,
    Candidate,
    DocInfo,
    ManualRegion,
    MarkKind,
    Progress,
    ProgressCb,
    Rect,
)
from .scoring import score_all

SAMPLE_BUDGET = 24
SAMPLE_SEED = 20260918
THUMB_DPI = 110
THUMB_PAD = 16


def sample_pages(page_count: int, budget: int = SAMPLE_BUDGET) -> list[int]:
    """Deterministic spread: head, tail, evenly spaced middle, plus a seeded pinch."""
    if page_count <= budget:
        return list(range(page_count))

    picked = {0, 1, 2, page_count - 3, page_count - 2, page_count - 1}
    remaining = budget - len(picked) - 2
    if remaining > 0:
        step = page_count / (remaining + 1)
        picked.update(int(step * (i + 1)) for i in range(remaining))

    rng = random.Random(SAMPLE_SEED)
    while len(picked) < budget:
        picked.add(rng.randrange(page_count))
    return sorted(p for p in picked if 0 <= p < page_count)[:budget]


def doc_info(path: str, doc: pymupdf.Document) -> DocInfo:
    stat = os.stat(path)
    first = doc[0].rect if doc.page_count else pymupdf.Rect(0, 0, 0, 0)
    has_annots = any(next(page.annots(), None) is not None for page in doc.pages(0, 5))
    return DocInfo(
        path=path,
        page_count=doc.page_count,
        size_bytes=stat.st_size,
        mtime=stat.st_mtime,
        is_encrypted=doc.is_encrypted,
        has_annots=has_annots,
        page_width=first.width,
        page_height=first.height,
    )


def render_page_png(
    doc: pymupdf.Document, page_no: int, dpi: int = 100, clip: Rect | None = None
) -> bytes:
    page = doc[page_no]
    rect = pymupdf.Rect(*clip.as_tuple()) & page.rect if clip else None
    pix = page.get_pixmap(dpi=dpi, clip=rect)
    return pix.tobytes("png")


def render_page_after(
    path: str,
    page_no: int,
    candidates: list[Candidate],
    manual_regions: list[ManualRegion] | None = None,
    dpi: int = 100,
) -> bytes:
    """Render one page as it will look once the selection is removed."""
    from .remove import apply_to_page, selection_keys

    image_keys, mark_groups = selection_keys(candidates)
    doc = pymupdf.open(path)
    try:
        page = doc[page_no]
        apply_to_page(
            doc,
            page,
            image_keys,
            mark_groups,
            manual_rects=[
                region.rect for region in (manual_regions or []) if region.applies_to(page_no)
            ],
        )
        page = doc.reload_page(page)
        return page.get_pixmap(dpi=dpi).tobytes("png")
    finally:
        doc.close()


def _thumbnail(doc: pymupdf.Document, candidate: Candidate) -> bytes | None:
    if not candidate.hits:
        return None
    hit = candidate.hits[len(candidate.hits) // 2]
    clip = hit.rect.expand(THUMB_PAD)
    if clip.area <= 0:
        return None
    try:
        return render_page_png(doc, hit.page_no, dpi=THUMB_DPI, clip=clip)
    except Exception:
        return None


def analyze(
    path: str, on_progress: ProgressCb | None = None, want_thumbnails: bool = True
) -> AnalyzeReport:
    """Scan a document and report every repeated element a user might want gone."""

    def emit(phase: str, current: int, total: int, detail: str = "") -> None:
        if on_progress:
            on_progress(Progress(phase, current, total, detail))

    doc = pymupdf.open(path)
    try:
        warnings: list[str] = []
        if doc.is_encrypted:
            raise ValueError("File PDF được bảo vệ bằng mật khẩu, không thể xử lý.")
        if doc.page_count == 0:
            raise ValueError("File PDF không có trang nào.")

        info = doc_info(path, doc)
        if info.has_annots:
            warnings.append(
                "Tài liệu có annotation/form - việc xóa chữ hoặc hình vector sẽ ghi lại nội dung trang."
            )

        sampled = sample_pages(doc.page_count)
        emit("analyze", 1, 4, "Đang quét ảnh chèn")
        images = detect_images(doc, sampled, doc.page_count)

        emit("analyze", 2, 4, "Đang quét chữ và hình vector")
        marks = detect_marks(doc, sampled, doc.page_count)

        emit("analyze", 3, 4, "Đang đếm số trang chính xác")
        sigs = {c.key: c.sig for c in images if c.sig is not None}
        if sigs:
            counts = count_image_pages(doc, sigs)
            images = [
                c.with_exact_count(counts.get(c.key, c.pages_seen), doc.page_count)
                if c.key in counts
                else c
                for c in images
            ]

        candidates = score_all(images + marks, info.page_width, info.page_height)

        if want_thumbnails:
            emit("analyze", 4, 4, "Đang tạo ảnh xem trước")
            candidates = [c.with_thumbnail(_thumbnail(doc, c)) for c in candidates]

        return AnalyzeReport(
            doc=info,
            candidates=tuple(candidates),
            sampled_pages=tuple(sampled),
            warnings=tuple(warnings),
        )
    finally:
        doc.close()


KIND_LABELS = {
    MarkKind.IMAGE: "Ảnh chèn",
    MarkKind.TEXT: "Chữ lặp",
    MarkKind.VECTOR: "Hình vector",
    MarkKind.BADGE: "Huy hiệu",
}


def position_label(candidate: Candidate, page_w: float, page_h: float) -> str:
    """Where on the page it sits - the only way to tell two look-alikes apart."""
    if not page_w or not page_h:
        return ""
    cx = (candidate.rect.x0 + candidate.rect.x1) / 2 / page_w
    cy = (candidate.rect.y0 + candidate.rect.y1) / 2 / page_h
    vertical = "trên" if cy < 0.28 else ("dưới" if cy > 0.72 else "giữa")
    horizontal = "trái" if cx < 0.33 else ("phải" if cx > 0.67 else "")
    if vertical == "giữa" and not horizontal:
        return "giữa trang"
    if not horizontal:
        return "mép trên" if vertical == "trên" else "mép dưới"
    return f"góc {vertical}-{horizontal}" if vertical != "giữa" else f"cạnh {horizontal}"


def readable_text(candidate: Candidate) -> str:
    return " ".join((candidate.label or candidate.text).split())


def describe(candidate: Candidate, page_w: float = 0.0, page_h: float = 0.0) -> str:
    """Short human label for the candidate cards."""
    parts = [KIND_LABELS[candidate.kind]]
    where = position_label(candidate, page_w, page_h)
    if where:
        parts.append(where)

    if candidate.kind is MarkKind.IMAGE and candidate.sig is not None:
        detail = f"{candidate.sig.width}×{candidate.sig.height}"
        if candidate.sig.has_alpha:
            detail += ", trong suốt"
        if any(hit.rotated for hit in candidate.hits):
            detail += ", xoay chéo"
        parts.append(detail)
    else:
        text = readable_text(candidate)
        if text:
            parts.append(f'"{text[:40]}"' + ("…" if len(text) > 40 else ""))
    return " · ".join(parts)
