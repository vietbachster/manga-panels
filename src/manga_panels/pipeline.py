from __future__ import annotations

from typing import Callable, Sequence

from PIL import Image

from manga_panels.archive import load_image, pack, read_comicinfo, unpack
from manga_panels.detect import Box
from manga_panels.errors import MangaPanelsError
from manga_panels.ml import MagiDetector
from manga_panels.split import split_wide


def crop_panels(page: Image.Image, boxes: list[Box]) -> list[Image.Image]:
    return [page.crop((x, y, x + w, y + h)) for (x, y, w, h) in boxes]


def _panel_imgs(page: Image.Image, box: Box, obstacles: list[list[float]],
                split_ratio: float | None) -> list[Image.Image]:
    """The panel crop — or, when it is too wide to read, the whole panel
    followed by its right-to-left slices. The whole panel is what gives the
    slices their context, which is why there is no overlap between them."""
    parts = split_wide(box, obstacles, max_ratio=split_ratio) if split_ratio else [box]
    if len(parts) == 1:
        return crop_panels(page, parts)
    return crop_panels(page, [box, *parts])       # ponytail: always "whole first", no knob


def _cover_box(size, cover_crop, cover_side: str) -> tuple[int, int, int, int]:
    """Where the front cover sits on a wide page 0: a fraction taken from
    `cover_side`, or an explicit (start, end) slice of the width — a manga jacket is
    flap + front + back, so the front cover is a middle band that no fraction from
    either edge can reach.

    Validated here and not only in the CLI: a value out of manga-panels.toml never
    passes through argparse, and a bad one used to yield a silent 1-pixel cover."""
    w, h = size
    if isinstance(cover_crop, (tuple, list)):
        try:
            a, b = (float(v) for v in cover_crop)
        except (TypeError, ValueError):
            raise MangaPanelsError(
                f"cover_crop slice must be two numbers, got {list(cover_crop)!r}") from None
        if not (0 <= a < b <= 1):            # rejects NaN too
            raise MangaPanelsError(
                f"cover_crop slice must be 0 <= start < end <= 1, got {a}:{b}")
        x0, x1 = round(w * a), round(w * b)
    else:
        try:
            f = float(cover_crop)
        except (TypeError, ValueError):
            raise MangaPanelsError(f"cover_crop must be a number, got {cover_crop!r}") from None
        if not 0 <= f <= 1:                  # rejects NaN too
            raise MangaPanelsError(f"cover_crop must be between 0 and 1, got {f}")
        cw = round(w * f)
        x0, x1 = (0, cw) if cover_side == "left" else (w - cw, w)
    x0 = max(0, min(w - 1, x0))
    x1 = max(x0 + 1, min(w, x1))             # always at least one column wide
    return (x0, 0, x1, h)


def process_archive(in_path, out_path, *, fmt: str = "jpeg", quality: int = 90,
                    page_pos: str = "before", max_width: int | None = None,
                    keep_first: int = 0, grayscale: bool = False, gamma: float = 1.0,
                    cover=None, cover_crop: float | Sequence[float] | None = None,
                    cover_side: str = "left",
                    split_ratio: float | None = None, upscale: bool = False,
                    rotate_wide: float | None = None, pad_aspect: float | None = None,
                    rtl: bool = False,
                    warn: Callable[[str], None] | None = None,
                    on_page: Callable[[int, int], None] | None = None) -> int:
    """Explode each page into panels in a new CBZ. Returns the total number of
    images written.
    - keep_first: the first N pages are kept whole (cover/front matter).
    - A page with <=1 panel (cover/splash) is emitted only once.
    - page_pos: 'before' (macro page before the panels), 'after', or 'off'.
    - split_ratio: cut panels wider than N:1 into vertical slices (None = off).
    - warn(msg): called when a ComicInfo chapter mark points outside the volume,
      or collides with another mark on the same page.
    - on_page(done, total): called after each processed page (progress)."""
    if page_pos not in ("before", "after", "off"):
        raise ValueError(f"invalid page_pos: {page_pos!r} (use before/after/off)")
    det = MagiDetector()
    pages = unpack(in_path)
    total = len(pages)
    out_imgs: list[Image.Image] = []
    page_starts: list[tuple[int, str]] = []
    page_at: dict[int, int] = {}        # source page index -> index into out_imgs
    cover_img = load_image(cover) if cover is not None else None
    if cover_img is None and cover_crop and pages:   # crop the front cover off a wide page 0
        cover_img = pages[0].crop(_cover_box(pages[0].size, cover_crop, cover_side))
    if cover_img is not None:                        # -> PDF page 1 / library thumbnail
        page_starts.append((len(out_imgs), "Capa"))
        out_imgs.append(cover_img)
    for i, page in enumerate(pages):
        page_at[i] = len(out_imgs)
        page_starts.append((len(out_imgs), f"Página {i + 1}"))
        if i < keep_first:                         # keep front matter whole
            out_imgs.append(page)
        else:
            boxes, obstacles = det.detect_split(page)   # already in reading order
            if len(boxes) <= 1:                    # cover/splash/spread -> once
                if not split_ratio:
                    # no splitting -> keep the same object, no full-page copy.
                    # This is the default path; routing it through _panel_imgs
                    # (crop_panels on a synthetic full-page box) would double
                    # peak RAM on volumes with many <=1-panel pages.
                    out_imgs.append(page)
                else:
                    whole = (0, 0, page.width, page.height)
                    out_imgs.extend(_panel_imgs(page, whole, obstacles, split_ratio))
            else:
                if page_pos == "before":
                    out_imgs.append(page)
                for b in boxes:
                    out_imgs.extend(_panel_imgs(page, b, obstacles, split_ratio))
                if page_pos == "after":
                    out_imgs.append(page)
        if on_page is not None:
            on_page(i + 1, total)
    meta = read_comicinfo(in_path)
    # ComicInfo indexes source pages; the packers work in output-image indices.
    # A mark outside the volume is dropped, but never silently: a chapter that
    # vanishes with no signal is worse than one that is obviously wrong. Two
    # marks on the same source page collide the same way once translated —
    # keep the first, warn naming the one dropped.
    chapters: list[tuple[int, str]] = []
    seen: dict[int, str] = {}
    for p, t in meta.get("chapters", []):
        if p not in page_at:
            if warn is not None:
                # p + 1 reads naturally for an out-of-range page (1-based, like
                # every other page number in this message); a negative p is not
                # a page at all, so name it as the raw index instead of letting
                # "+ 1" print a misleading "page 0" for p == -1.
                where = f"page {p + 1}" if p >= 0 else f"page index {p}"
                warn(f"chapter {t!r} points at {where}, which this archive "
                     f"does not have ({len(pages)} pages) — skipped")
            continue
        idx = page_at[p]
        if idx in seen:
            if warn is not None:
                warn(f"chapter {t!r} points at the same page as {seen[idx]!r} "
                     f"— keeping {seen[idx]!r}, {t!r} skipped")
            continue
        seen[idx] = t
        chapters.append((idx, t))
    pack(out_imgs, out_path, fmt=fmt, quality=quality, max_width=max_width,
         grayscale=grayscale, gamma=gamma, upscale=upscale,
         rotate_wide=rotate_wide, pad_aspect=pad_aspect,
         page_starts=page_starts, chapters=chapters, rtl=rtl,
         title=meta.get("title"), creator=meta.get("creator"))
    return len(out_imgs)
