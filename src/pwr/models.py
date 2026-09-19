"""Immutable data structures shared by the detection and removal engine."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Callable, Sequence


class MarkKind(str, Enum):
    IMAGE = "image"
    TEXT = "text"
    VECTOR = "vector"
    BADGE = "badge"


@dataclass(frozen=True)
class ImageSig:
    """Content fingerprint of an embedded image, stable across pages."""

    width: int
    height: int
    colorspace: str
    bpc: int
    has_alpha: bool
    filter: str
    digest: str


@dataclass(frozen=True)
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float:
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        return self.y1 - self.y0

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def expand(self, pad: float) -> "Rect":
        return Rect(self.x0 - pad, self.y0 - pad, self.x1 + pad, self.y1 + pad)

    def union(self, other: "Rect") -> "Rect":
        return Rect(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )

    def intersects(self, other: "Rect") -> bool:
        return not (
            self.x1 < other.x0
            or other.x1 < self.x0
            or self.y1 < other.y0
            or other.y1 < self.y0
        )

    def contains(self, other: "Rect") -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and self.x1 >= other.x1
            and self.y1 >= other.y1
        )

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class Hit:
    """One concrete occurrence of a candidate on one page."""

    page_no: int
    rect: Rect
    xref: int = 0
    rotated: bool = False


@dataclass(frozen=True)
class Candidate:
    """A repeated element the user may choose to remove."""

    key: str
    kind: MarkKind
    rect: Rect
    hits: tuple[Hit, ...]
    pages_seen: int
    pages_sampled: int
    page_count: int
    text: str = ""
    # Readable part of `text`: characters scattered along a path (circular badge
    # art) concatenate into noise, so display uses whole words only.
    label: str = ""
    member_keys: tuple[str, ...] = ()
    # Position-free signatures of the parts, so a mark shifted a few points on
    # some pages is still recognised there.
    member_contents: tuple[str, ...] = ()
    sig: ImageSig | None = None
    score: float = 0.0
    auto_check: bool = False
    reasons: tuple[str, ...] = ()
    thumbnail_png: bytes | None = None

    @property
    def coverage(self) -> float:
        if self.pages_sampled <= 0:
            return 0.0
        return self.pages_seen / self.pages_sampled

    @property
    def estimated_pages(self) -> int:
        """How many pages of the whole document this is expected to touch."""
        return max(1, round(self.coverage * self.page_count))

    def with_score(self, score: float, auto_check: bool, reasons: Sequence[str]) -> "Candidate":
        return replace(self, score=score, auto_check=auto_check, reasons=tuple(reasons))

    def with_thumbnail(self, png: bytes | None) -> "Candidate":
        return replace(self, thumbnail_png=png)

    def with_exact_count(self, pages_seen: int, pages_sampled: int) -> "Candidate":
        return replace(self, pages_seen=pages_seen, pages_sampled=pages_sampled)


@dataclass(frozen=True)
class DocInfo:
    path: str
    page_count: int
    size_bytes: int
    mtime: float
    is_encrypted: bool
    has_annots: bool
    page_width: float
    page_height: float


@dataclass(frozen=True)
class AnalyzeReport:
    doc: DocInfo
    candidates: tuple[Candidate, ...]
    sampled_pages: tuple[int, ...]
    warnings: tuple[str, ...] = ()

    def auto_selected_keys(self) -> tuple[str, ...]:
        return tuple(c.key for c in self.candidates if c.auto_check)


@dataclass(frozen=True)
class Progress:
    phase: str
    current: int
    total: int
    detail: str = ""

    @property
    def ratio(self) -> float:
        return self.current / self.total if self.total else 0.0


@dataclass(frozen=True)
class RunReport:
    src: str
    dst: str
    pages_touched: int
    images_removed: int
    areas_redacted: int
    warnings: tuple[str, ...] = field(default=())


ProgressCb = Callable[[Progress], None]
