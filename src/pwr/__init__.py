"""PDF watermark remover engine (GUI-free)."""

from .models import (
    AnalyzeReport,
    Candidate,
    DocInfo,
    Hit,
    ImageSig,
    ManualRegion,
    MarkKind,
    Progress,
    Rect,
    RunReport,
)
from .pipeline import analyze, describe, render_page_png, sample_pages
from .manual import ManualRisk, assess_manual_region, parse_page_scope
from .remove import Cancelled, RemovalExecutor, default_output_path
from .verify import compare_pages, summarize

__all__ = [
    "AnalyzeReport",
    "Candidate",
    "Cancelled",
    "DocInfo",
    "Hit",
    "ImageSig",
    "ManualRegion",
    "ManualRisk",
    "MarkKind",
    "Progress",
    "Rect",
    "RemovalExecutor",
    "RunReport",
    "analyze",
    "assess_manual_region",
    "compare_pages",
    "default_output_path",
    "describe",
    "render_page_png",
    "parse_page_scope",
    "sample_pages",
    "summarize",
]
