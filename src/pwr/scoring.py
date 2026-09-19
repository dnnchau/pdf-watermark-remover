"""Confidence scoring - decides what gets pre-ticked and what merely gets listed."""

from __future__ import annotations

import re

from .models import Candidate, MarkKind

TRIAL_SIGNALS = re.compile(
    r"clicktobuynow|pdf-?xchange|evaluation(copy|version)?|trialversion|demoversion"
    r"|createdwith|unregisteredversion|foxit|wondershare|ilovepdf|smallpdf|sejda"
    r"|pdfelement|nitropro|watermark",
    re.IGNORECASE,
)
PAGE_NUMBERISH = re.compile(r"^[\d\s.,\-/]+$")

AUTO_CHECK_MIN = 0.75
HIGH_COVERAGE = 0.90
LOW_COVERAGE = 0.60
MARGIN_BAND = 0.12
FOOTER_MAX_HEIGHT = 0.05
OVERLAY_MIN_AREA = 0.005
OVERLAY_MAX_AREA = 0.25
# An opaque image filling this much of the page is the page itself, not a mark.
PAGE_SCAN_MIN_AREA = 0.50


def _in_margin_band(candidate: Candidate, page_w: float, page_h: float) -> bool:
    rect = candidate.rect
    top = rect.y1 < page_h * MARGIN_BAND
    bottom = rect.y0 > page_h * (1 - MARGIN_BAND)
    left = rect.x1 < page_w * MARGIN_BAND
    right = rect.x0 > page_w * (1 - MARGIN_BAND)
    return top or bottom or left or right


def _is_rotated_alpha_overlay(candidate: Candidate, page_w: float, page_h: float) -> bool:
    if candidate.kind is not MarkKind.IMAGE or candidate.sig is None:
        return False
    if not candidate.sig.has_alpha:
        return False
    if not any(hit.rotated for hit in candidate.hits):
        return False
    page_area = (page_w * page_h) or 1.0
    ratio = candidate.rect.area / page_area
    return OVERLAY_MIN_AREA <= ratio <= OVERLAY_MAX_AREA


def _is_alpha_overlay(candidate: Candidate, page_w: float, page_h: float) -> bool:
    if candidate.kind is not MarkKind.IMAGE or candidate.sig is None:
        return False
    if not candidate.sig.has_alpha:
        return False
    page_area = (page_w * page_h) or 1.0
    ratio = candidate.rect.area / page_area
    return OVERLAY_MIN_AREA <= ratio <= OVERLAY_MAX_AREA


def _is_page_scan(candidate: Candidate, page_w: float, page_h: float) -> bool:
    """A big opaque image is the scanned page itself - never a watermark."""
    if candidate.kind is not MarkKind.IMAGE or candidate.sig is None:
        return False
    if candidate.sig.has_alpha:
        return False
    page_area = (page_w * page_h) or 1.0
    return candidate.rect.area / page_area >= PAGE_SCAN_MIN_AREA


def score_candidate(
    candidate: Candidate, page_w: float, page_h: float, largest_image_key: str | None
) -> Candidate:
    score = 0.30
    reasons: list[str] = []

    coverage = candidate.coverage
    if coverage >= HIGH_COVERAGE:
        score += 0.35
        reasons.append(f"xuất hiện trên {coverage:.0%} số trang")
    elif coverage < LOW_COVERAGE:
        score -= 0.25
        reasons.append("ít lặp lại giữa các trang")

    trial = bool(TRIAL_SIGNALS.search(candidate.text.replace(" ", "")))
    if trial:
        score += 0.45
        reasons.append("chứa chuỗi quảng cáo phần mềm dùng thử")

    rotated_alpha = _is_rotated_alpha_overlay(candidate, page_w, page_h)
    if rotated_alpha:
        score += 0.30
        reasons.append("ảnh trong suốt đặt xoay chéo đè lên nội dung")
    elif _is_alpha_overlay(candidate, page_w, page_h):
        score += 0.15
        reasons.append("ảnh trong suốt đè lên trang")

    if candidate.kind is not MarkKind.IMAGE and _in_margin_band(candidate, page_w, page_h):
        page_area_h = candidate.rect.height / (page_h or 1.0)
        if page_area_h < FOOTER_MAX_HEIGHT and not trial:
            score -= 0.40
            reasons.append("dáng đầu trang/chân trang (có thể là nội dung gốc)")

    if candidate.text and PAGE_NUMBERISH.match(candidate.text.strip()):
        score -= 0.30
        reasons.append("chỉ gồm chữ số - có thể là số trang")

    is_scan = _is_page_scan(candidate, page_w, page_h) or (
        largest_image_key is not None
        and candidate.key == largest_image_key
        and candidate.sig is not None
        and not candidate.sig.has_alpha
    )
    if is_scan:
        score -= 0.35
        reasons.append("ảnh nền khổ lớn - nhiều khả năng là bản scan nội dung")

    score = max(0.0, min(1.0, score))
    auto = score >= AUTO_CHECK_MIN and (trial or rotated_alpha) and not is_scan
    return candidate.with_score(score, auto, reasons)


def score_all(
    candidates: list[Candidate], page_w: float, page_h: float
) -> list[Candidate]:
    images = [c for c in candidates if c.kind is MarkKind.IMAGE]
    largest_key = max(images, key=lambda c: c.rect.area).key if images else None
    scored = [score_candidate(c, page_w, page_h, largest_key) for c in candidates]
    return sorted(scored, key=lambda c: (-c.score, -c.coverage))
