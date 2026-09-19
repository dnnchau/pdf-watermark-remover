"""Command line front end - same engine the GUI uses."""

from __future__ import annotations

import argparse
import os
import sys

from pwr import (
    RemovalExecutor,
    analyze,
    compare_pages,
    default_output_path,
    describe,
    summarize,
)
from pwr.remove import unique_output_path
from pwr.models import Progress


def _progress(progress: Progress) -> None:
    if progress.total:
        print(f"\r  {progress.phase}: {progress.detail or ''} "
              f"{progress.ratio:.0%}   ", end="", file=sys.stderr, flush=True)
    else:
        print(f"\r  {progress.detail}   ", end="", file=sys.stderr, flush=True)


def _print_candidates(report) -> None:
    print(f"\nTài liệu: {report.doc.path}")
    print(f"  {report.doc.page_count} trang · {report.doc.size_bytes / 1024 / 1024:.1f} MB")
    for warning in report.warnings:
        print(f"  ! {warning}")
    if not report.candidates:
        print("  Không tìm thấy phần tử lặp lại nào.")
        return
    print(f"\n{'#':>3} {'TICK':5} {'ĐIỂM':>5} {'TRANG':>10}  MÔ TẢ")
    for index, candidate in enumerate(report.candidates, 1):
        tick = " [x] " if candidate.auto_check else " [ ] "
        pages = f"{candidate.estimated_pages}/{candidate.page_count}"
        print(f"{index:>3} {tick} {candidate.score:>5.2f} {pages:>10}  {describe(candidate)}")
        for reason in candidate.reasons:
            print(f"{'':>26}- {reason}")


def _select(report, spec: str | None):
    if spec in (None, "", "auto"):
        return [c for c in report.candidates if c.auto_check]
    if spec == "all":
        return list(report.candidates)
    picked = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            picked.update(range(int(start), int(end) + 1))
        elif part:
            picked.add(int(part))
    return [c for i, c in enumerate(report.candidates, 1) if i in picked]


def cmd_analyze(args: argparse.Namespace) -> int:
    _print_candidates(analyze(args.pdf, on_progress=_progress))
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    report = analyze(args.pdf, on_progress=_progress)
    _print_candidates(report)
    selected = _select(report, args.select)
    if not selected:
        print("\nKhông có mục nào được chọn. Dùng --select 1,3 hoặc --select all.")
        return 1

    dst = args.out or default_output_path(args.pdf)
    if not args.overwrite:
        unique = unique_output_path(dst)
        if unique != dst:
            print(f"\nĐã có {os.path.basename(dst)} nên lưu thành {os.path.basename(unique)}.")
            dst = unique
    print(f"\nĐang xóa {len(selected)} mục → {dst}")
    run = RemovalExecutor(aggressive_line_art=args.aggressive).run(
        args.pdf,
        dst,
        selected,
        on_progress=_progress,
        allow_overwrite=args.overwrite,
        expected_size=report.doc.size_bytes,
        expected_mtime=report.doc.mtime,
    )
    print(
        f"\nXong: {run.pages_touched} trang, {run.images_removed} ảnh, "
        f"{run.areas_redacted} vùng chữ/vector."
    )
    for warning in run.warnings[:5]:
        print(f"  ! {warning}")

    pages = [h.page_no for c in selected for h in c.hits][:3]
    diffs = compare_pages(args.pdf, run.dst, pages, [c.rect for c in selected])
    print(summarize(diffs))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    report = analyze(args.pdf, want_thumbnails=False)
    rects = [c.rect for c in report.candidates if c.auto_check] or [
        c.rect for c in report.candidates
    ]
    pages = list(report.sampled_pages[:5])
    print(summarize(compare_pages(args.pdf, args.other, pages, rects)))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pwr", description="Xóa watermark khỏi file PDF")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Liệt kê watermark tìm được")
    p_analyze.add_argument("pdf")
    p_analyze.set_defaults(func=cmd_analyze)

    p_apply = sub.add_parser("apply", help="Xóa watermark đã chọn")
    p_apply.add_argument("pdf")
    p_apply.add_argument("-o", "--out", help="File xuất (mặc định: <tên>_clean.pdf)")
    p_apply.add_argument(
        "-s", "--select", default="auto", help="auto | all | danh sách số, ví dụ 1,3-5"
    )
    p_apply.add_argument(
        "--aggressive", action="store_true", help="Xóa cả nét vẽ chỉ chạm vùng watermark"
    )
    p_apply.add_argument(
        "--overwrite", action="store_true", help="Cho phép ghi đè file xuất đã tồn tại"
    )
    p_apply.set_defaults(func=cmd_apply)

    p_verify = sub.add_parser("verify", help="So sánh file gốc với file đã xử lý")
    p_verify.add_argument("pdf")
    p_verify.add_argument("other")
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, OSError) as error:
        print(f"\nLỗi: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
