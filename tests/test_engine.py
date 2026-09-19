import os

import pymupdf
import pytest

from pwr import (
    ManualRegion,
    MarkKind,
    Rect,
    RemovalExecutor,
    analyze,
    assess_manual_region,
    compare_pages,
    default_output_path,
    parse_page_scope,
)
from pwr.fingerprint import ImageSig, cluster_key, image_sig, is_stub_image, text_norm
from pwr.pipeline import sample_pages


class TestFingerprint:
    def test_same_image_gets_same_key_across_pages(self, marked_pdf):
        doc = pymupdf.open(marked_pdf)
        sigs = [
            image_sig(doc, entry[0])
            for page in doc
            for entry in page.get_images(full=True)
        ]
        doc.close()
        assert len(sigs) >= 2
        assert len({s.digest for s in sigs}) == 1

    def test_stub_detection(self):
        assert is_stub_image(ImageSig(1, 1, "", 8, True, "", "x"))
        assert not is_stub_image(ImageSig(356, 81, "", 8, True, "", "x"))

    def test_text_norm_ignores_case_and_space(self):
        assert text_norm(" Click to BUY  NOW! ") == "clicktobuynow!"

    def test_cluster_key_is_position_tolerant(self):
        a = cluster_key("t", Rect(10.0, 10.0, 40.0, 20.0), "x")
        b = cluster_key("t", Rect(11.5, 11.0, 41.0, 21.0), "x")
        assert a == b


class TestPlacements:
    def test_each_image_keeps_its_own_geometry(self, tmp_path):
        """Two same-sized images must not swap bbox/rotation with each other."""
        import io

        from PIL import Image

        from pwr.detect import page_image_placements
        from pwr.fingerprint import is_rotated

        def png(color):
            buffer = io.BytesIO()
            Image.new("RGB", (120, 60), color).save(buffer, format="PNG")
            return buffer.getvalue()

        path = str(tmp_path / "two.pdf")
        doc = pymupdf.open()
        page = doc.new_page(width=400, height=400)
        page.insert_image(pymupdf.Rect(20, 20, 140, 80), stream=png((255, 0, 0)))
        page.insert_image(pymupdf.Rect(200, 200, 260, 320), stream=png((0, 0, 255)), rotate=90)
        doc.save(path)
        doc.close()

        doc = pymupdf.open(path)
        placements = page_image_placements(doc[0])
        doc.close()

        assert len(placements) == 2
        upright = [p for p in placements if not is_rotated(p["transform"])]
        rotated = [p for p in placements if is_rotated(p["transform"])]
        assert len(upright) == 1 and len(rotated) == 1
        assert upright[0]["bbox"][0] < 100, "upright image keeps the left-hand box"
        assert rotated[0]["bbox"][0] > 150, "rotated image keeps the right-hand box"


class TestSampling:
    def test_small_doc_samples_every_page(self):
        assert sample_pages(9) == list(range(9))

    def test_large_doc_is_bounded_and_covers_ends(self):
        picked = sample_pages(290)
        assert len(picked) <= 24
        assert picked[0] == 0
        assert picked[-1] == 289
        assert picked == sorted(set(picked))


class TestManualRegions:
    def test_page_scope_supports_ranges_and_keywords(self):
        assert parse_page_scope("1-3, 6", 8, 0) == (0, 1, 2, 5)
        assert parse_page_scope("tất cả", 4, 0) == (0, 1, 2, 3)
        assert parse_page_scope("lẻ", 5, 0) == (0, 2, 4)
        assert parse_page_scope("", 5, 3) == (3,)

    def test_manual_region_only_removes_selected_pages(self, clean_pdf, tmp_path):
        region = ManualRegion(Rect(60, 105, 240, 175), (1,), "2")
        dst = str(tmp_path / "manual.pdf")

        RemovalExecutor().run(clean_pdf, dst, [], manual_regions=[region])

        doc = pymupdf.open(dst)
        try:
            assert "Question 1" in doc[0].get_text()
            assert "Question 2" not in doc[1].get_text()
            assert "Question 3" in doc[2].get_text()
        finally:
            doc.close()

    def test_manual_region_reports_content_risk(self, clean_pdf):
        region = ManualRegion(Rect(60, 105, 240, 175), (0, 1), "1-2")
        risk = assess_manual_region(clean_pdf, region)
        assert risk.text_hits >= 2


class TestDetection:
    def test_finds_image_and_badge_marks(self, marked_pdf):
        report = analyze(marked_pdf)
        kinds = {c.kind for c in report.candidates}
        assert MarkKind.IMAGE in kinds
        assert {MarkKind.BADGE, MarkKind.TEXT, MarkKind.VECTOR} & kinds

    def test_image_mark_is_auto_checked(self, marked_pdf):
        report = analyze(marked_pdf)
        images = [c for c in report.candidates if c.kind is MarkKind.IMAGE]
        assert images and images[0].auto_check
        assert images[0].sig.has_alpha
        assert images[0].pages_seen == images[0].page_count

    def test_trial_badge_is_auto_checked(self, marked_pdf):
        report = analyze(marked_pdf)
        trial = [c for c in report.candidates if "pdf-xchange" in c.text.lower()]
        assert trial and trial[0].auto_check

    def test_clean_document_auto_selects_nothing(self, clean_pdf):
        report = analyze(clean_pdf)
        assert report.auto_selected_keys() == ()

    def test_running_header_is_listed_but_not_auto_checked(self, clean_pdf):
        report = analyze(clean_pdf)
        headers = [c for c in report.candidates if "HACKERS" in c.text]
        assert headers, "repeated header should still be offered to the user"
        assert not headers[0].auto_check


class TestRemoval:
    def test_removes_selection_and_keeps_content(self, marked_pdf, tmp_path):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        dst = str(tmp_path / "out.pdf")

        run = RemovalExecutor().run(marked_pdf, dst, selected)

        assert os.path.exists(dst)
        assert run.images_removed >= 1
        after = pymupdf.open(dst)
        try:
            assert after.page_count == report.doc.page_count
            text = after[3].get_text()
            assert "Question 4" in text
            assert "pdf-xchange" not in text.lower()
            live_images = [
                e
                for e in after[3].get_images(full=True)
                if not is_stub_image(image_sig(after, e[0]))
            ]
            assert live_images == []
        finally:
            after.close()

    def test_pixel_diff_confined_to_marks(self, marked_pdf, tmp_path):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        dst = str(tmp_path / "out.pdf")
        RemovalExecutor().run(marked_pdf, dst, selected)

        rects = [c.rect for c in selected]
        diffs = compare_pages(marked_pdf, dst, [1, 5, 9], rects)

        assert diffs
        assert all(d.ok for d in diffs), [d.changed_outside for d in diffs]
        assert any(d.changed_inside > 0.01 for d in diffs)

    def test_badge_loses_both_its_text_and_its_line_art(self, marked_pdf, tmp_path):
        """Per-part boxes leave the badge drawing behind; the union box removes it."""
        report = analyze(marked_pdf)
        badge = [
            c
            for c in report.candidates
            if c.kind in (MarkKind.BADGE, MarkKind.VECTOR, MarkKind.TEXT)
            and "pdf-xchange" in c.text.lower()
        ]
        assert badge, "fixture should carry a trial badge"
        dst = str(tmp_path / "out.pdf")

        RemovalExecutor().run(marked_pdf, dst, badge)

        after = pymupdf.open(dst)
        try:
            page = after[2]
            text = page.get_text()
            assert page.get_drawings() == [], "badge line art must be gone"
            assert "pdf-xchange" not in text.lower()
            assert "Question 3" in text, "page content must survive"
            assert "keep2" in text, "content inside the badge box must survive too"
        finally:
            after.close()

    def test_refuses_empty_selection(self, marked_pdf, tmp_path):
        with pytest.raises(ValueError):
            RemovalExecutor().run(marked_pdf, str(tmp_path / "x.pdf"), [])

    def test_refuses_to_overwrite_source(self, marked_pdf):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        with pytest.raises(ValueError):
            RemovalExecutor().run(marked_pdf, marked_pdf, selected)

    def test_detects_source_changed_since_analysis(self, marked_pdf, tmp_path):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        with pytest.raises(ValueError, match="đã thay đổi"):
            RemovalExecutor().run(
                marked_pdf,
                str(tmp_path / "out.pdf"),
                selected,
                expected_size=report.doc.size_bytes + 1,
            )

    def test_rerun_on_output_is_idempotent(self, marked_pdf, tmp_path):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        dst = str(tmp_path / "out.pdf")
        RemovalExecutor().run(marked_pdf, dst, selected)

        second = analyze(dst)
        assert second.auto_selected_keys() == ()

    def test_default_output_path_adds_suffix(self, tmp_path):
        src = str(tmp_path / "book.pdf")
        assert default_output_path(src).endswith("book_clean.pdf")

    def test_refuses_to_clobber_an_existing_output(self, marked_pdf, tmp_path):
        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        dst = tmp_path / "taken.pdf"
        dst.write_bytes(b"precious")

        with pytest.raises(ValueError, match="Đã tồn tại"):
            RemovalExecutor().run(marked_pdf, str(dst), selected)
        assert dst.read_bytes() == b"precious"

    def test_unique_output_path_walks_past_taken_names(self, tmp_path):
        from pwr.remove import unique_output_path

        first = tmp_path / "book_clean.pdf"
        first.write_bytes(b"x")
        second = unique_output_path(str(first))
        assert second.endswith("book_clean (2).pdf")

    def test_cancel_leaves_no_partial_file(self, marked_pdf, tmp_path):
        import threading

        from pwr.remove import Cancelled

        report = analyze(marked_pdf)
        selected = [c for c in report.candidates if c.auto_check]
        dst = tmp_path / "out.pdf"
        cancel = threading.Event()
        cancel.set()

        with pytest.raises(Cancelled):
            RemovalExecutor().run(marked_pdf, str(dst), selected, cancel=cancel)

        assert not dst.exists()
        assert list(tmp_path.glob("*.part*")) == []
