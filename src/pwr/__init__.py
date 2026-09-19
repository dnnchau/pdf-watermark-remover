"""PDF watermark remover engine (GUI-free)."""

from .models import (
    AnalyzeReport,
    Candidate,
    DocInfo,
    Hit,
    ImageSig,
    MarkKind,
    Progress,
    Rect,
    RunReport,
)
from .pipeline import analyze, describe, render_page_png, sample_pages
from .remove import Cancelled, RemovalExecutor, default_output_path
from .verify import compare_pages, summarize

__all__ = [
    "AnalyzeReport",
    "Candidate",
    "Cancelled",
    "DocInfo",
    "Hit",
    "ImageSig",
    "MarkKind",
    "Progress",
    "Rect",
    "RemovalExecutor",
    "RunReport",
    "analyze",
    "compare_pages",
    "default_output_path",
    "describe",
    "render_page_png",
    "sample_pages",
    "summarize",
]
