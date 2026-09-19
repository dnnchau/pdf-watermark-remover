"""Find elements that repeat across pages - the shape every watermark has."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass

import pymupdf

from .fingerprint import (
    cluster_key,
    image_key,
    image_sig,
    is_rotated,
    is_stub_image,
    quantize,
    text_norm,
    to_rect,
)
from .models import Candidate, Hit, ImageSig, MarkKind, Rect

# An element must show up on at least this share of sampled pages to be a candidate.
MIN_COVERAGE = 0.55
# Spans/drawings closer than this merge into one logical mark (e.g. a trial badge).
CLUSTER_PAD_MIN = 4.0
CLUSTER_PAD_FACTOR = 0.6
# Text longer than this is body copy, not a watermark line.
MAX_MARK_TEXT = 120
# Clustering compares pairs, so a page stuffed with spans is capped to stay fast.
MAX_ITEMS_PER_PAGE = 1200
MAX_CLUSTER_INPUT = 600


@dataclass(frozen=True)
class _Item:
    key: str
    kind: MarkKind
    rect: Rect
    text: str
    content: str = ""


@dataclass
class _Group:
    key: str
    kind: MarkKind
    text: str
    content: str
    rects: list[Rect]
    pages: dict[int, Rect]

    def median_rect(self) -> Rect:
        mid = sorted(self.rects, key=lambda r: (r.x0, r.y0))[len(self.rects) // 2]
        return mid


def page_items(page: pymupdf.Page) -> list[_Item]:
    """Text spans and vector drawings of one page, keyed by position + content."""
    items: list[_Item] = []

    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", ()):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", ()):
            for span in line.get("spans", ()):
                raw = span.get("text", "")
                if not raw.strip():
                    continue
                rect = to_rect(span["bbox"])
                content = f"t:{text_norm(raw)}:{round(rect.width / 3)}"
                items.append(
                    _Item(cluster_key("t", rect, raw), MarkKind.TEXT, rect, raw, content)
                )

    for drawing in page.get_drawings():
        rect = to_rect(drawing["rect"])
        if rect.area <= 0:
            continue
        paint = f"{drawing.get('type', '')}{drawing.get('fill')}{drawing.get('color')}"
        content = f"v:{paint}:{round(rect.width / 3)}x{round(rect.height / 3)}"
        items.append(
            _Item(cluster_key("v" + paint, rect, ""), MarkKind.VECTOR, rect, "", content)
        )

    return items[:MAX_ITEMS_PER_PAGE]


def _median_span_height(items: list[_Item]) -> float:
    heights = sorted(i.rect.height for i in items if i.kind is MarkKind.TEXT)
    if not heights:
        return 0.0
    return heights[len(heights) // 2]


def collect_groups(
    doc: pymupdf.Document, sampled: list[int]
) -> tuple[list[_Group], float]:
    """Group identical items by key across the sampled pages."""
    groups: dict[str, _Group] = {}
    pad_hint = 0.0
    for page_no in sampled:
        page = doc[page_no]
        items = page_items(page)
        pad_hint = max(pad_hint, _median_span_height(items))
        for item in items:
            group = groups.get(item.key)
            if group is None:
                group = _Group(item.key, item.kind, item.text, item.content, [], {})
                groups[item.key] = group
            group.rects.append(item.rect)
            known = group.pages.get(page_no)
            group.pages[page_no] = item.rect if known is None else known.union(item.rect)
    pad = max(CLUSTER_PAD_MIN, CLUSTER_PAD_FACTOR * pad_hint)
    return list(groups.values()), pad


def _repeated(groups: list[_Group], sampled_count: int) -> list[_Group]:
    threshold = max(2, int(round(MIN_COVERAGE * sampled_count)))
    repeated = [
        g
        for g in groups
        if len(g.pages) >= threshold and len(text_norm(g.text)) <= MAX_MARK_TEXT
    ]
    # Most-repeated first, so the cap keeps the strongest watermark signals.
    repeated.sort(key=lambda g: -len(g.pages))
    return repeated[:MAX_CLUSTER_INPUT]


def cluster_groups(groups: list[_Group], pad: float) -> list[list[_Group]]:
    """Union-find over padded bounding boxes, so a badge becomes one candidate."""
    order = sorted(range(len(groups)), key=lambda i: groups[i].median_rect().x0)
    parent = list(range(len(groups)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[rj] = ri

    for a in range(len(order)):
        ia = order[a]
        ra = groups[ia].median_rect().expand(pad)
        for b in range(a + 1, len(order)):
            ib = order[b]
            rb = groups[ib].median_rect().expand(pad)
            if rb.x0 > ra.x1:
                break
            if ra.intersects(rb):
                union(ia, ib)

    buckets: dict[int, list[_Group]] = defaultdict(list)
    for i in range(len(groups)):
        buckets[find(i)].append(groups[i])
    return list(buckets.values())


def _cluster_candidate(
    cluster: list[_Group], sampled: list[int], page_count: int
) -> Candidate:
    rect = cluster[0].median_rect()
    for group in cluster[1:]:
        rect = rect.union(group.median_rect())

    per_page: dict[int, Rect] = {}
    for group in cluster:
        for page_no, page_rect in group.pages.items():
            known = per_page.get(page_no)
            per_page[page_no] = page_rect if known is None else known.union(page_rect)

    texts = [g for g in cluster if g.kind is MarkKind.TEXT]
    vectors = [g for g in cluster if g.kind is MarkKind.VECTOR]
    if texts and vectors:
        kind = MarkKind.BADGE
    elif texts:
        kind = MarkKind.TEXT
    else:
        kind = MarkKind.VECTOR

    ordered = sorted(texts, key=lambda g: (g.median_rect().y0, g.median_rect().x0))
    text = "".join(g.text for g in ordered).strip()
    words = [g.text.strip() for g in ordered if len(g.text.strip()) > 1]
    label = " ".join(words).strip()

    member_keys = "|".join(sorted(g.key for g in cluster))
    key = f"cl:{kind.value}:{hashlib.md5(member_keys.encode()).hexdigest()[:16]}"

    hits = tuple(
        Hit(page_no=p, rect=r) for p, r in sorted(per_page.items())
    )
    return Candidate(
        key=key,
        kind=kind,
        rect=rect,
        hits=hits,
        pages_seen=len(per_page),
        pages_sampled=len(sampled),
        page_count=page_count,
        text=text,
        label=label,
        member_keys=tuple(sorted(g.key for g in cluster)),
        member_contents=tuple(sorted({g.content for g in cluster if g.content})),
    )


def detect_marks(
    doc: pymupdf.Document, sampled: list[int], page_count: int
) -> list[Candidate]:
    """Repeated text/vector marks (trial badges, stamps, headers, footers)."""
    groups, pad = collect_groups(doc, sampled)
    repeated = _repeated(groups, len(sampled))
    if not repeated:
        return []
    return [
        _cluster_candidate(cluster, sampled, page_count)
        for cluster in cluster_groups(repeated, pad)
    ]


def page_image_placements(page: pymupdf.Page) -> list[dict]:
    """Where each image xref is actually drawn, asked per xref so no guessing."""
    result = []
    for entry in page.get_images(full=True):
        xref, width, height = entry[0], entry[2], entry[3]
        try:
            placements = page.get_image_rects(xref, transform=True)
        except Exception:
            placements = []
        if not placements:
            result.append(
                {"xref": xref, "width": width, "height": height, "bbox": None, "transform": None}
            )
            continue
        for rect, matrix in placements:
            result.append(
                {
                    "xref": xref,
                    "width": width,
                    "height": height,
                    "bbox": tuple(rect),
                    "transform": (matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f),
                }
            )
    return result


def detect_images(
    doc: pymupdf.Document, sampled: list[int], page_count: int
) -> list[Candidate]:
    """Images that repeat byte-identically across pages."""
    groups: dict[str, dict] = {}
    for page_no in sampled:
        page = doc[page_no]
        page_area = page.rect.get_area() or 1.0
        for placement in page_image_placements(page):
            sig = image_sig(doc, placement["xref"])
            if is_stub_image(sig):
                continue
            key = image_key(sig)
            bbox = placement["bbox"]
            rect = to_rect(bbox) if bbox else Rect(0, 0, 0, 0)
            group = groups.setdefault(
                key,
                {"sig": sig, "hits": [], "pages": set(), "area_ratio": 0.0, "rotated": False},
            )
            group["hits"].append(
                Hit(
                    page_no=page_no,
                    rect=rect,
                    xref=placement["xref"],
                    rotated=is_rotated(placement["transform"]),
                )
            )
            group["pages"].add(page_no)
            group["area_ratio"] = max(group["area_ratio"], rect.area / page_area)
            group["rotated"] = group["rotated"] or is_rotated(placement["transform"])

    threshold = max(2, int(round(MIN_COVERAGE * len(sampled))))
    candidates = []
    for key, group in groups.items():
        if len(group["pages"]) < threshold:
            continue
        rect = group["hits"][0].rect
        for hit in group["hits"][1:]:
            rect = rect.union(hit.rect)
        candidates.append(
            Candidate(
                key=key,
                kind=MarkKind.IMAGE,
                rect=rect,
                hits=tuple(group["hits"]),
                pages_seen=len(group["pages"]),
                pages_sampled=len(sampled),
                page_count=page_count,
                sig=group["sig"],
            )
        )
    return candidates


def count_image_pages(doc: pymupdf.Document, sigs: dict[str, ImageSig]) -> dict[str, int]:
    """Exact per-document page counts, cheap because sizes filter the hashing."""
    wanted = {(s.width, s.height) for s in sigs.values()}
    counts: dict[str, int] = {key: 0 for key in sigs}
    for page in doc:
        seen_on_page: set[str] = set()
        for entry in page.get_images(full=True):
            if (entry[2], entry[3]) not in wanted:
                continue
            key = image_key(image_sig(doc, entry[0]))
            if key in counts:
                seen_on_page.add(key)
        for key in seen_on_page:
            counts[key] += 1
    return counts
