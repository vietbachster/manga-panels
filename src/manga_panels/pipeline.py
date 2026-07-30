from __future__ import annotations

from typing import Callable

from PIL import Image

from manga_panels.archive import load_image, pack, unpack
from manga_panels.detect import Box
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


def process_archive(in_path, out_path, *, fmt: str = "jpeg", quality: int = 90,
                    page_pos: str = "before", max_width: int | None = None,
                    keep_first: int = 0, grayscale: bool = False, gamma: float = 1.0,
                    cover=None, cover_crop: float | None = None, cover_side: str = "left",
                    split_ratio: float | None = None, upscale: bool = False,
                    on_page: Callable[[int, int], None] | None = None) -> int:
    """Explode each page into panels in a new CBZ. Returns the total number of
    images written.
    - keep_first: the first N pages are kept whole (cover/front matter).
    - A page with <=1 panel (cover/splash) is emitted only once.
    - page_pos: 'before' (macro page before the panels), 'after', or 'off'.
    - split_ratio: cut panels wider than N:1 into vertical slices (None = off).
    - on_page(done, total): called after each processed page (progress)."""
    if page_pos not in ("before", "after", "off"):
        raise ValueError(f"invalid page_pos: {page_pos!r} (use before/after/off)")
    det = MagiDetector()
    pages = unpack(in_path)
    total = len(pages)
    out_imgs: list[Image.Image] = []
    cover_img = load_image(cover) if cover is not None else None
    if cover_img is None and cover_crop and pages:   # crop the front cover off a wide page 0
        w, h = pages[0].size
        cw = max(1, min(w, round(w * cover_crop)))
        box = (0, 0, cw, h) if cover_side == "left" else (w - cw, 0, w, h)
        cover_img = pages[0].crop(box)
    if cover_img is not None:                        # -> PDF page 1 / library thumbnail
        out_imgs.append(cover_img)
    for i, page in enumerate(pages):
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
    pack(out_imgs, out_path, fmt=fmt, quality=quality, max_width=max_width,
         grayscale=grayscale, gamma=gamma, upscale=upscale)
    return len(out_imgs)
