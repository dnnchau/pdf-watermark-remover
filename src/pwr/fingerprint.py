"""Content fingerprints used to recognise the same mark across pages."""

from __future__ import annotations

import hashlib
import re

import pymupdf

from .models import ImageSig, Rect

# Images this small are PyMuPDF's leftover stubs from a previous delete_image().
STUB_MAX_SIDE = 2
# Only the head of a compressed stream is hashed - enough to separate images,
# cheap enough to run on every page of a 90MB scan.
HASH_PREFIX_BYTES = 64 * 1024
# Cross-page matching quantises geometry onto this grid (points).
POSITION_GRID = 6.0

_WS = re.compile(r"\s+")


def _key(doc: pymupdf.Document, xref: int, name: str, default: str = "") -> str:
    try:
        kind, value = doc.xref_get_key(xref, name)
    except Exception:
        return default
    if kind == "null":
        return default
    return str(value)


def image_sig(doc: pymupdf.Document, xref: int) -> ImageSig:
    """Fingerprint an image XObject without decoding its pixels."""
    try:
        raw = doc.xref_stream_raw(xref)
    except Exception:
        raw = b""
    digest = hashlib.md5(
        len(raw).to_bytes(8, "little") + raw[:HASH_PREFIX_BYTES]
    ).hexdigest()
    return ImageSig(
        width=int(_key(doc, xref, "Width", "0") or 0),
        height=int(_key(doc, xref, "Height", "0") or 0),
        colorspace=_key(doc, xref, "ColorSpace"),
        bpc=int(_key(doc, xref, "BitsPerComponent", "0") or 0),
        has_alpha=bool(_key(doc, xref, "SMask")),
        filter=_key(doc, xref, "Filter"),
        digest=digest,
    )


def is_stub_image(sig: ImageSig) -> bool:
    """True for the 1x1 transparent placeholder left behind by delete_image()."""
    return sig.width <= STUB_MAX_SIDE and sig.height <= STUB_MAX_SIDE


def text_norm(text: str) -> str:
    """Whitespace- and case-insensitive form used for cross-page text matching."""
    return _WS.sub("", text).lower()


def quantize(value: float, grid: float = POSITION_GRID) -> int:
    return int(round(value / grid))


def image_key(sig: ImageSig) -> str:
    return f"img:{sig.width}x{sig.height}:{sig.digest[:16]}"


def cluster_key(kind: str, rect: Rect, text: str) -> str:
    """Position+content key so the same badge on another page maps to one candidate."""
    squashed = text_norm(text)[:48]
    return (
        f"{kind}:{quantize(rect.x0)},{quantize(rect.y0)},"
        f"{quantize(rect.width)},{quantize(rect.height)}:{squashed}"
    )


def to_rect(raw) -> Rect:
    x0, y0, x1, y1 = (float(v) for v in raw)
    return Rect(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def is_rotated(transform) -> bool:
    """A non-zero b/c pair in the placement matrix means rotation or skew."""
    if transform is None:
        return False
    b, c = float(transform[1]), float(transform[2])
    return abs(b) > 1e-6 or abs(c) > 1e-6
