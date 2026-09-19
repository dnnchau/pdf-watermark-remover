"""Apply the user's selection to every page and write a clean copy."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass

import pymupdf

from .detect import page_items
from .fingerprint import image_key, image_sig, is_stub_image, to_rect
from .models import Candidate, ManualRegion, MarkKind, Progress, ProgressCb, Rect, RunReport


@dataclass(frozen=True)
class MarkGroup:
    """One selected text/vector mark: what it is made of and where it was seen."""

    contents: frozenset[str]
    rect: Rect


REDACT_PAD = 1.0
# Glyph boxes get only a hair of padding: the mark's own characters must go, the
# page text they sit on top of must stay.
TEXT_PAD = 0.3
DEFAULT_SUFFIX = "_clean"
# How far a mark may drift from where it was detected and still count as the same
# mark (the trial badge shifts ~17pt on some pages of a real book).
POSITION_TOLERANCE = 42.0


class Cancelled(Exception):
    """Raised when the caller aborts the run before the save step."""


def default_output_path(src: str, out_dir: str | None = None, suffix: str = DEFAULT_SUFFIX) -> str:
    folder, name = os.path.split(src)
    stem, ext = os.path.splitext(name)
    return os.path.join(out_dir or folder, f"{stem}{suffix}{ext}")


def unique_output_path(dst: str) -> str:
    """Never clobber an existing file: book_clean.pdf -> book_clean (2).pdf."""
    if not os.path.exists(dst):
        return dst
    stem, ext = os.path.splitext(dst)
    index = 2
    while os.path.exists(f"{stem} ({index}){ext}"):
        index += 1
    return f"{stem} ({index}){ext}"


def _graphics_mode(page: pymupdf.Page, rects: list[Rect], aggressive: bool) -> tuple[int, list[str]]:
    """Keep line art that merely crosses a redaction box unless asked otherwise."""
    warnings: list[str] = []
    crossing = []
    for drawing in page.get_drawings():
        d_rect = to_rect(drawing["rect"])
        for rect in rects:
            if d_rect.intersects(rect) and not rect.contains(d_rect):
                crossing.append(d_rect)
                break
    if crossing and not aggressive:
        warnings.append(
            f"Trang {page.number + 1}: {len(crossing)} nét vẽ chỉ chạm vùng xóa nên được giữ lại."
        )
    mode = (
        pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED
        if aggressive
        else pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED
    )
    return mode, warnings


def _remove_images(doc: pymupdf.Document, page: pymupdf.Page, keys: set[str]) -> int:
    removed = 0
    for entry in page.get_images(full=True):
        xref = entry[0]
        sig = image_sig(doc, xref)
        if is_stub_image(sig):
            continue
        if image_key(sig) in keys:
            page.delete_image(xref)
            removed += 1
    return removed


def _center_in(outer: Rect, inner: Rect) -> bool:
    cx = (inner.x0 + inner.x1) / 2
    cy = (inner.y0 + inner.y1) / 2
    return outer.x0 <= cx <= outer.x1 and outer.y0 <= cy <= outer.y1


@dataclass
class _Match:
    """The parts of one selected mark that were found on one page."""

    union: Rect
    text_rects: list[Rect]
    has_line_art: bool


def _match_page(page: pymupdf.Page, mark_groups: list[MarkGroup]) -> list[_Match]:
    """Find each selected mark's own parts on this page.

    Matching is on content within a tolerance of where the mark was seen: the same
    badge sits a few points off on some pages, and exact-position matching silently
    skipped those.
    """
    found: dict[int, _Match] = {}
    for item in page_items(page):
        for index, group in enumerate(mark_groups):
            if item.content not in group.contents:
                continue
            if not _center_in(group.rect.expand(POSITION_TOLERANCE), item.rect):
                continue
            match = found.get(index)
            if match is None:
                match = _Match(item.rect, [], False)
                found[index] = match
            else:
                match.union = match.union.union(item.rect)
            if item.kind is MarkKind.TEXT:
                match.text_rects.append(item.rect)
            else:
                match.has_line_art = True
            break
    return [found[index] for index in sorted(found)]


def _drop_overlapping_page_text(
    page: pymupdf.Page, mark_rects: list[Rect]
) -> tuple[list[Rect], int]:
    """Keep only the mark boxes that touch no page text of their own."""
    marked = {tuple(round(v, 1) for v in rect.as_tuple()) for rect in mark_rects}
    others = [
        to_rect(span["bbox"])
        for block in page.get_text("dict").get("blocks", ())
        if block.get("type") == 0
        for line in block.get("lines", ())
        for span in line.get("spans", ())
        if tuple(round(v, 1) for v in span["bbox"]) not in marked
    ]
    safe = [rect for rect in mark_rects if not any(rect.intersects(o) for o in others)]
    return safe, len(mark_rects) - len(safe)


def selection_keys(candidates: list[Candidate]) -> tuple[set[str], list[MarkGroup]]:
    """Image keys, plus one group per selected text/vector mark."""
    image_keys = {c.key for c in candidates if c.kind is MarkKind.IMAGE}
    mark_groups = [
        MarkGroup(frozenset(c.member_contents), c.rect)
        for c in candidates
        if c.kind is not MarkKind.IMAGE and c.member_contents
    ]
    return image_keys, mark_groups


def apply_to_page(
    doc: pymupdf.Document,
    page: pymupdf.Page,
    image_keys: set[str],
    mark_groups: list[MarkGroup],
    aggressive: bool = False,
    manual_rects: list[Rect] | None = None,
) -> tuple[int, int, list[str]]:
    """Remove the selected marks from one page. Returns (images, areas, warnings)."""
    images_removed = _remove_images(doc, page, image_keys) if image_keys else 0
    areas = 0
    warnings: list[str] = []

    if not mark_groups and not manual_rects:
        return images_removed, areas, warnings

    matches = _match_page(page, mark_groups) if mark_groups else []
    areas = len(matches)

    # Pass 1 - text. Two rules keep page content safe here:
    #  * box each part of the mark on its own, never the mark's whole area;
    #  * skip parts that sit on top of page text, because MuPDF drops the entire
    #    text span a redaction box touches - one watermark glyph over the start of
    #    a line would take the whole line with it.
    text_rects = [rect for match in matches for rect in match.text_rects]
    if text_rects and not aggressive:
        text_rects, kept = _drop_overlapping_page_text(page, text_rects)
        if kept:
            warnings.append(
                f"Trang {page.number + 1}: giữ lại {kept} phần watermark vì chúng nằm đè "
                "lên chữ của trang (xóa sẽ mất chữ)."
            )
    if text_rects:
        for rect in text_rects:
            page.add_redact_annot(
                pymupdf.Rect(*rect.expand(TEXT_PAD).as_tuple()), fill=False, cross_out=False
            )
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )

    # Pass 2 - line art: MuPDF only drops a path fully covered by one box, so this
    # needs the mark's whole box; text is left alone this time round.
    art_rects = [match.union for match in matches if match.has_line_art]
    if art_rects:
        mode, page_warnings = _graphics_mode(page, art_rects, aggressive)
        warnings.extend(page_warnings)
        for rect in art_rects:
            page.add_redact_annot(
                pymupdf.Rect(*rect.expand(REDACT_PAD).as_tuple()), fill=False, cross_out=False
            )
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=mode,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )

    # Manual regions intentionally remove everything they cover. The UI performs
    # a sampled content-risk check and asks for confirmation before this path runs.
    if manual_rects:
        for rect in manual_rects:
            page.add_redact_annot(
                pymupdf.Rect(*rect.as_tuple()), fill=(1, 1, 1), cross_out=False
            )
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_REMOVE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
            text=pymupdf.PDF_REDACT_TEXT_REMOVE,
        )
        areas += len(manual_rects)
    return images_removed, areas, warnings


class RemovalExecutor:
    """Runs a selection over a whole document; safe to call from a worker thread."""

    def __init__(self, aggressive_line_art: bool = False) -> None:
        self.aggressive_line_art = aggressive_line_art

    def run(
        self,
        src: str,
        dst: str,
        candidates: list[Candidate],
        manual_regions: list[ManualRegion] | None = None,
        on_progress: ProgressCb | None = None,
        cancel: threading.Event | None = None,
        allow_overwrite: bool = False,
        expected_size: int | None = None,
        expected_mtime: float | None = None,
    ) -> RunReport:
        manual_regions = manual_regions or []
        if not candidates and not manual_regions:
            raise ValueError("Chưa chọn watermark nào để xóa.")
        if os.path.abspath(src) == os.path.abspath(dst) and not allow_overwrite:
            raise ValueError("File xuất trùng file gốc. Hãy đổi tên hoặc thư mục xuất.")
        if os.path.exists(dst) and not allow_overwrite:
            raise ValueError(
                f"Đã tồn tại file {os.path.basename(dst)}. Hãy đổi tên/thư mục xuất "
                "hoặc cho phép ghi đè."
            )

        stat = os.stat(src)
        if expected_size is not None and stat.st_size != expected_size:
            raise ValueError(
                "File gốc đã thay đổi kể từ lúc phân tích. Hãy phân tích lại trước khi xóa."
            )
        if expected_mtime is not None and abs(stat.st_mtime - expected_mtime) > 1:
            raise ValueError(
                "File gốc đã thay đổi kể từ lúc phân tích. Hãy phân tích lại trước khi xóa."
            )

        image_keys, mark_groups = selection_keys(candidates)

        doc = pymupdf.open(src)
        # Write beside the target, then swap it in - a crash or cancel can never
        # leave a half-written PDF where the finished one should be.
        tmp = f"{dst}.part-{os.getpid()}"
        saved = False
        warnings: list[str] = []
        images_removed = 0
        areas_redacted = 0
        pages_touched = 0
        try:
            total = doc.page_count
            for index, page in enumerate(doc):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()

                removed, areas, page_warnings = apply_to_page(
                    doc,
                    page,
                    image_keys,
                    mark_groups,
                    self.aggressive_line_art,
                    [region.rect for region in manual_regions if region.applies_to(index)],
                )
                images_removed += removed
                areas_redacted += areas
                warnings.extend(page_warnings)

                if removed or areas:
                    pages_touched += 1
                if on_progress:
                    on_progress(
                        Progress("remove", index + 1, total, f"Trang {index + 1}/{total}")
                    )

            if cancel is not None and cancel.is_set():
                raise Cancelled()
            if on_progress:
                on_progress(Progress("save", 0, 0, "Đang ghi file (không thể hủy)…"))

            os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
            doc.save(tmp, garbage=4, deflate=True)
            saved = True
        finally:
            doc.close()
            if not saved and os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    warnings.append(f"Không xóa được file tạm {os.path.basename(tmp)}.")

        os.replace(tmp, dst)

        return RunReport(
            src=src,
            dst=dst,
            pages_touched=pages_touched,
            images_removed=images_removed,
            areas_redacted=areas_redacted,
            warnings=tuple(dict.fromkeys(warnings))[:20],
        )
