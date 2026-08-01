from __future__ import annotations

import io
import os
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image, UnidentifiedImageError

from manga_panels.errors import BadArchive, EmptyArchive, MissingDependency

_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in _IMG_EXT


def _natkey(name: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def unpack(path: str | Path) -> list[Image.Image]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".cbz" or ext == ".zip":
        return _unpack_zip(path)
    if ext == ".cbr" or ext == ".rar":
        return _unpack_rar(path)
    if ext in _IMG_EXT:                       # a bare image -> single page
        try:
            data = path.read_bytes()
        except OSError as e:
            raise BadArchive(f"cannot read {path.name}: {e}") from e
        return [_load(data)]
    raise ValueError(f"unsupported format: {path.suffix}")


def _load(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError) as e:
        raise BadArchive(f"invalid image in archive: {e}") from e


def load_image(path: str | Path) -> Image.Image:
    """Load a single image file as RGB (e.g. a --cover). BadArchive on failure."""
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise BadArchive(f"cannot read image {path}: {e}") from e
    return _load(data)


def read_comicinfo(path: str | Path) -> dict:
    """Title, creator and chapter marks from a ComicInfo.xml inside the archive.
    Chapters come from Page/@Bookmark — the standard field, so anything that
    writes ComicInfo can supply them and we invent no format of our own.

    Indices are read straight from Page/@Image and never derived from printed
    page numbers: a double-page spread stored as one image shifts the count
    mid-volume, so any fixed offset silently misplaces every later chapter.

    Metadata is a nicety, never a reason to fail: an absent, unreadable or
    malformed ComicInfo yields {}."""
    try:
        with zipfile.ZipFile(path) as z:
            name = next((n for n in z.namelist()
                         if n.lower().endswith("comicinfo.xml")), None)
            if name is None:
                return {}
            root = ET.fromstring(z.read(name))
    except Exception:                       # ponytail: any failure here means "no metadata"
        return {}

    def text(tag: str) -> str:
        return (root.findtext(tag) or "").strip()

    series, volume = text("Series"), text("Volume")
    title = f"{series} Vol. {volume}" if series and volume else series or text("Title")
    pages = root.find("Pages")
    # key=image index only: sorted() is stable, so two marks on the same page
    # keep document order instead of being re-broken by bookmark text — "keep
    # the first" (the caller's dedup) should mean "first in the file", not
    # "first alphabetically".
    chapters = sorted(
        (
            (int(p.get("Image")), (p.get("Bookmark") or "").strip())
            for p in (pages if pages is not None else [])
            if (p.get("Bookmark") or "").strip()
            and (p.get("Image") or "").lstrip("-").isdecimal()
        ),
        key=lambda c: c[0],
    )
    out = {"chapters": chapters}
    if title:
        out["title"] = title
    if text("Writer"):
        out["creator"] = text("Writer")
    return out if (title or chapters or out.get("creator")) else {}


def _unpack_zip(path: Path) -> list[Image.Image]:
    try:
        with zipfile.ZipFile(path) as z:
            names = sorted((n for n in z.namelist() if _is_image(n)), key=_natkey)
            imgs = [_load(z.read(n)) for n in names]
    except (zipfile.BadZipFile, zlib.error, RuntimeError, OSError, EOFError) as e:
        raise BadArchive(f"corrupt cbz/zip: {path.name}") from e
    if not imgs:
        raise EmptyArchive(f"no images in {path.name}")
    return imgs


def _unpack_rar(path: Path) -> list[Image.Image]:
    try:
        import rarfile
    except ImportError as e:
        raise MissingDependency(
            "CBR needs the 'cbr' extra: pip install 'manga-panels[cbr]' "
            "and the 'unrar' binary on the system"
        ) from e
    try:
        with rarfile.RarFile(path) as r:
            names = sorted((n for n in r.namelist() if _is_image(n)), key=_natkey)
            imgs = [_load(r.read(n)) for n in names]
    except (rarfile.Error, zlib.error, RuntimeError, OSError, EOFError) as e:
        raise BadArchive(f"corrupt cbr/rar: {path.name}") from e
    if not imgs:
        raise EmptyArchive(f"no images in {path.name}")
    return imgs


def _fit(img: Image.Image, max_width: int | None, *, upscale: bool = False) -> Image.Image:
    """Scale to max_width, keeping the aspect ratio. Shrinks only by default;
    with upscale=True it also grows an image narrower than max_width — needed for
    readers whose renderer refuses to scale up (the Xteink X4's firmware clamps
    its scale factor to 1.0, so a narrow panel would sit small and letterboxed)."""
    if max_width and (img.width > max_width or (upscale and img.width < max_width)):
        h = round(img.height * max_width / img.width)
        return img.resize((max_width, h), Image.LANCZOS)
    return img


def _rotate_wide(img: Image.Image, ratio: float | None) -> Image.Image:
    """Turn a landscape image 90° clockwise so it uses the screen's long axis;
    the reader turns the device anticlockwise to read it. A wide panel scaled to
    fit a narrow screen is unreadably small, and e-ink readers never rotate on
    their own. 0 or None disables."""
    if ratio and img.height > 0 and img.width / img.height > ratio:
        # PIL rotates anticlockwise, so 270° anticlockwise == 90° clockwise
        return img.transpose(Image.Transpose.ROTATE_270)
    return img


def _pad_aspect(img: Image.Image, aspect: float | None) -> Image.Image:
    """Pad with white to `aspect` (width/height), content centred on both axes.
    A reader that scales-to-fit leaves slack on one axis; one that centres
    horizontally but not vertically then strands the image at the top of the page
    (the Xteink X4's firmware does exactly this). Matching the screen's aspect
    leaves no slack, so there is nothing left to mis-place. White because it is
    the paper colour on e-ink, and flat white costs almost nothing in JPEG."""
    if not aspect or img.width <= 0 or img.height <= 0:
        return img
    w, h = img.size
    if w / h > aspect:
        new_w, new_h = w, round(w / aspect)
    else:
        new_w, new_h = round(h * aspect), h
    if (new_w, new_h) == (w, h):
        return img
    mode = img.mode if img.mode in ("L", "RGB") else "RGB"
    out = Image.new(mode, (new_w, new_h), 255 if mode == "L" else (255, 255, 255))
    out.paste(img if img.mode == mode else img.convert(mode),
              ((new_w - w) // 2, (new_h - h) // 2))
    return out


def _eink(img: Image.Image, *, grayscale: bool, gamma: float) -> Image.Image:
    """e-ink tweaks: grayscale (smaller + native to e-paper) and gamma (>1 darkens
    midtones for punchier contrast; 1.0 = off)."""
    if grayscale and img.mode != "L":
        img = img.convert("L")
    if gamma and gamma != 1.0:
        lut = [round(255 * (i / 255) ** gamma) for i in range(256)]
        img = img.point(lut * len(img.getbands()))
    return img


def _render(img: Image.Image, *, rotate_wide: float | None, pad_aspect: float | None,
            max_width: int | None, upscale: bool, grayscale: bool,
            gamma: float) -> Image.Image:
    """The per-image transform chain every output container shares. The order is
    load-bearing: rotate first so padding sees the final orientation, pad next so
    the fit sizes the padded frame, then fit, then the e-ink tweaks."""
    im = _rotate_wide(img, rotate_wide)
    im = _pad_aspect(im, pad_aspect)
    im = _fit(im, max_width, upscale=upscale)
    return _eink(im, grayscale=grayscale, gamma=gamma)


@contextmanager
def _atomic(out_path: Path):
    """Yield a temp path; on success swap it onto out_path atomically, on any
    failure (incl. KeyboardInterrupt) delete it. So a crash/kill/error mid-write
    never leaves a half-written, corrupt file — you get the complete file or none."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_name(out_path.name + ".tmp")   # same dir -> os.replace is atomic
    try:
        yield tmp
        os.replace(tmp, out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def pack(images: list[Image.Image], out_path: str | Path, *,
         fmt: str = "jpeg", quality: int = 90, max_width: int | None = None,
         grayscale: bool = False, gamma: float = 1.0, upscale: bool = False,
         rotate_wide: float | None = None, pad_aspect: float | None = None,
         page_starts: list[tuple[int, str]] | None = None,
         chapters: list[tuple[int, str]] | None = None,
         title: str | None = None, creator: str | None = None,
         rtl: bool = False) -> None:
    out_path = Path(out_path)
    fmt = fmt.lower()
    if fmt == "pdf":                              # a PDF file, one panel per page
        _pack_pdf(images, out_path, quality=quality, max_width=max_width,
                  grayscale=grayscale, gamma=gamma, upscale=upscale,
                  rotate_wide=rotate_wide, pad_aspect=pad_aspect,
                  page_starts=page_starts, chapters=chapters,
                  title=title, creator=creator)
        return
    if fmt == "epub":                             # one image per page, for epub-only readers
        _pack_epub(images, out_path, quality=quality, max_width=max_width,
                   grayscale=grayscale, gamma=gamma, upscale=upscale,
                   rotate_wide=rotate_wide, pad_aspect=pad_aspect,
                   page_starts=page_starts, chapters=chapters,
                   title=title, creator=creator, rtl=rtl)
        return
    if fmt in ("jpg", "jpeg"):
        # jpeg is already compressed: STORED avoids pointless zip recompression
        ext, pil_fmt, save_kw, compression = (
            "jpg", "JPEG", {"quality": quality}, zipfile.ZIP_STORED)
    elif fmt == "png":
        ext, pil_fmt, save_kw, compression = (
            "png", "PNG", {}, zipfile.ZIP_DEFLATED)
    else:
        raise ValueError(f"unknown image format: {fmt!r}")
    with _atomic(out_path) as tmp:
        with zipfile.ZipFile(tmp, "w", compression) as z:
            for i, img in enumerate(images, start=1):
                buf = io.BytesIO()
                im = _render(img, rotate_wide=rotate_wide, pad_aspect=pad_aspect,
                             max_width=max_width, upscale=upscale,
                             grayscale=grayscale, gamma=gamma)
                im.save(buf, pil_fmt, **save_kw)
                z.writestr(f"{i:04d}.{ext}", buf.getvalue())


def _pack_pdf(images: list[Image.Image], out_path: Path, *, quality: int,
              max_width: int | None, grayscale: bool, gamma: float,
              upscale: bool = False, rotate_wide: float | None = None,
              pad_aspect: float | None = None,
              page_starts: list[tuple[int, str]] | None = None,
              chapters: list[tuple[int, str]] | None = None,
              title: str | None = None, creator: str | None = None) -> None:
    """Embed each panel as a PDF page. img2pdf stores the JPEG bytes as-is (no
    re-encode), so no extra quality loss. For Kindle & other PDF-only readers."""
    try:
        import img2pdf
        import pikepdf
    except ImportError as e:
        raise MissingDependency(
            "PDF output needs the [pdf] extra: uv sync --extra pdf "
            "(or pip install 'manga-panels[pdf]')"
        ) from e
    jpegs = []
    for img in images:
        im = _render(img, rotate_wide=rotate_wide, pad_aspect=pad_aspect,
                     max_width=max_width, upscale=upscale,
                     grayscale=grayscale, gamma=gamma)
        if im.mode not in ("L", "RGB"):
            im = im.convert("RGB")
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality)
        jpegs.append(buf.getvalue())
    data = img2pdf.convert(jpegs)
    if not page_starts:
        with _atomic(out_path) as tmp:
            tmp.write_bytes(data)
        return
    # An outline is the only navigation a PDF has. pikepdf is a hard requirement
    # of img2pdf, so this costs no dependency, and libqpdf copies at the object
    # level: the embedded JPEGs are never re-encoded.
    chapter_at = {i: t for i, t in (chapters or [])}
    with pikepdf.open(io.BytesIO(data)) as pdf:
        if title:
            pdf.docinfo["/Title"] = title
        if creator:
            pdf.docinfo["/Author"] = creator
        with pdf.open_outline() as ol:
            parent = None
            for idx, label in page_starts:
                if idx in chapter_at:
                    parent = pikepdf.OutlineItem(chapter_at[idx], idx)
                    ol.root.append(parent)
                item = pikepdf.OutlineItem(label, idx)
                (parent.children if parent is not None else ol.root).append(item)
        with _atomic(out_path) as tmp:
            pdf.save(tmp)


_EPUB_CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

# Without these an image sits at the top-left of the flow: nothing tells the reader
# to centre it, to keep it inside the screen, or to give each panel its own page.
# Real Kindle use is what caught it.
# Only `max-*`, never `width`/`height`: these rules can shrink an image, never grow
# one, so a reader that already sizes images itself (the Xteink X4's firmware scales
# to fit and centres horizontally) cannot be pushed into upscaling something.
# `max-height: 100%` is belt-and-braces: per CSS 2.1 a percentage max-height is
# `none` when the containing block's height is auto, so it may well be inert — but
# it can only ever shrink, and we have no device here to measure it on.
_EPUB_CSS = (
    "html, body { margin: 0; padding: 0; text-align: center; }\n"
    "img { display: block; margin: 0 auto;\n"
    "      max-width: 100%; max-height: 100%;\n"
    "      page-break-after: always; }\n"
)


_EPUB_CHUNK = 20      # source pages per section when the book has no chapters

# Floor on source pages between section boundaries when chapters drive them.
# Below a real chapter (Monster's are ~20 source pages) but high enough that
# crossing sections stays rare. Without it, a ComicInfo that bookmarks scene
# breaks or extras every couple of pages reproduces — on every page turn — the
# same "indexing" stall the chapter-sized section above exists to avoid.
_EPUB_MIN_SECTION = 5

# Ceiling on source pages between section boundaries when chapters drive them
# — twice the chunk, not one, because a single chunk-width ceiling fires on
# real chapters too. Monster's real marks run 20-27 source pages apart (measured
# on the shipped volume, see test_epub_chapters_at_real_spacing_still_yield_one_
# section_each): at a ceiling of exactly _EPUB_CHUNK, every such gap "exceeds"
# it by a few pages, and forcing a boundary there means the *next* real mark's
# own floor check now measures from that forced boundary instead of the true
# previous one — an error that carries into the next gap and compounds, so a
# steady run of ~22-page chapters ends up cutting far more than one section per
# chapter. ponytail: a look-ahead ceiling (peek at the next mark before forcing
# a split) would track the chunk size exactly with no slack, but this only needs
# to turn "never bounded" into "eventually bounded" — doubling the chunk clears
# every real gap seen so far with margin and still turns a lone or wildly
# out-of-range mark's multi-hundred-page remainder into several sections
# instead of one.
_EPUB_SECTION_CEILING = _EPUB_CHUNK * 2


def _epub_sections(page_starts, chapters):
    """Section boundaries: the first image index of each section. Assumes
    page_starts is non-empty — the caller only calls this when there are pages
    to split.

    A section is what the reader indexes when you enter it, and the size is a
    real trade-off measured on the device: one section per image stalls on every
    page turn, and a single section for the whole volume never stops extending
    its index, which makes advancing unusable. A chapter (~20 source pages) pays
    once on entry and then flows. Without chapters, chunk at the same size.

    With chapters, _EPUB_SECTION_CEILING bounds every section from above too:
    once the gap since the last boundary reaches it, the next page opens a new
    section even without a chapter mark there. Otherwise a lone mark — or a
    ComicInfo that disagrees with the archive's page count, so almost every mark
    falls outside process_archive's range check and gets dropped — reproduces
    the single-section book that never stops indexing.

    A chapter within _EPUB_MIN_SECTION source pages of the previous boundary
    does not open its own section — it still appears in the table of contents
    (`_epub_nav` reads `chapters` directly, not this list), only the section
    split is skipped."""
    if not chapters:
        return [page_starts[k][0] for k in range(0, len(page_starts), _EPUB_CHUNK)]
    chapter_at = {idx for idx, _ in chapters}
    bounds, last_ord = [0], 0
    for o, (idx, _label) in enumerate(page_starts):
        if o == 0:
            continue
        if idx in chapter_at:
            if o - last_ord >= _EPUB_MIN_SECTION:
                bounds.append(idx)
                last_ord = o
        elif o - last_ord >= _EPUB_SECTION_CEILING:
            bounds.append(idx)
            last_ord = o
    return bounds


def _epub_nav(starts, chapters, page_ord, sec_of) -> str:
    """Nested table of contents: chapters at the top level, their pages beneath.
    Page entries point at an anchor inside the section rather than at a section of
    their own — that is what lets a section stay chapter-sized while the reader
    can still jump to a single page.

    Reads `chapters`, not the section titles: without chapters the sections are
    named after their first page, and nesting those would turn every twentieth
    page into a fake chapter."""
    chapter_at = dict(chapters)
    out, open_chapter = [], False
    for idx, label in starts:
        href = f"{sec_of[page_ord[idx]]}#pag{page_ord[idx]}"
        if idx in chapter_at:
            if open_chapter:
                out.append("</ol></li>")
            out.append(f'<li><a href="{href}">{escape(chapter_at[idx])}</a><ol>')
            open_chapter = True
        out.append(f'<li><a href="{href}">{escape(label)}</a></li>')
    if open_chapter:
        out.append("</ol></li>")
    return "".join(out)


def _pack_epub(images: list[Image.Image], out_path: Path, *, quality: int,
               max_width: int | None, grayscale: bool, gamma: float,
               upscale: bool = False, rotate_wide: float | None = None,
               pad_aspect: float | None = None,
               page_starts: list[tuple[int, str]] | None = None,
               chapters: list[tuple[int, str]] | None = None,
               title: str | None = None, creator: str | None = None,
               rtl: bool = False) -> None:
    """Write an EPUB 3. With `page_starts` the book
    is split into chapter-sized sections with an anchor at every source page, so
    the table of contents navigates by real manga page instead of by panel;
    without it, one image per document (the original shape).

    For readers that take neither CBZ nor PDF — the Xteink X4 reads epub/txt/bmp
    only. No dependency: an EPUB is a zip with a fixed layout."""
    book_title = title or out_path.stem
    esc_title = escape(book_title)
    # uuid5, not uuid4: re-processing the same file must yield the same id, or
    # the reader treats it as a new book and drops the reading position. Seeded
    # with out_path.stem too: two different archives can share a ComicInfo
    # title (e.g. same Series, no Volume tag) and must not collide on one id.
    uid = uuid.uuid5(uuid.NAMESPACE_URL, f"{book_title}\n{out_path.stem}")
    modified = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    starts = list(page_starts or [])
    chaps = list(chapters or [])
    # image index -> 1-based page ordinal, for the #pagK anchors
    page_ord = {idx: k for k, (idx, _) in enumerate(starts, start=1)}

    items, spine, docs = [], [], []
    if starts:
        secs = _epub_sections(starts, chaps)
        sec_of = {}                       # page ordinal -> section file name
        # ponytail: _epub_sections used to pair each boundary with a title
        # ("Início" for the untitled gap before the first chapter) that nothing
        # here ever read — plain boundaries are enough.
        for si, first in enumerate(secs, start=1):
            last = secs[si] if si < len(secs) else len(images)
            name = f"s{si:04d}.xhtml"
            body = []
            for j in range(first, last):
                if j in page_ord:
                    body.append(f'<a id="pag{page_ord[j]}"></a>')
                    sec_of[page_ord[j]] = name
                body.append(f'<img src="img/{j + 1:04d}.jpg" alt=""/>')
            docs.append((name, "".join(body)))
            items.append(f'    <item id="s{si:04d}" href="{name}" '
                         f'media-type="application/xhtml+xml"/>')
            spine.append(f'    <itemref idref="s{si:04d}"/>')
        nav_items = _epub_nav(starts, chaps, page_ord, sec_of)
    else:
        for i in range(1, len(images) + 1):
            docs.append((f"p{i:04d}.xhtml", f'<img src="img/{i:04d}.jpg" alt=""/>'))
            items.append(f'    <item id="p{i:04d}" href="p{i:04d}.xhtml" '
                         f'media-type="application/xhtml+xml"/>')
            spine.append(f'    <itemref idref="p{i:04d}"/>')
        nav_items = f'<li><a href="p0001.xhtml">{esc_title}</a></li>'

    for i in range(1, len(images) + 1):
        cover = ' properties="cover-image"' if i == 1 else ""
        items.append(f'    <item id="img{i:04d}" href="img/{i:04d}.jpg" '
                     f'media-type="image/jpeg"{cover}/>')

    meta = [f'    <dc:identifier id="bookid">urn:uuid:{uid}</dc:identifier>',
            f'    <dc:title>{esc_title}</dc:title>']
    if creator:
        meta.append(f'    <dc:creator>{escape(creator)}</dc:creator>')
    meta += ['    <dc:language>en</dc:language>',
             f'    <meta property="dcterms:modified">{modified}</meta>']

    opf = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
        'unique-identifier="bookid">',
        '  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">',
        *meta,
        '  </metadata>',
        '  <manifest>',
        '    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" '
        'properties="nav"/>',
        '    <item id="css" href="style.css" media-type="text/css"/>',
        *items,
        '  </manifest>',
        # ltr by default: one panel per page leaves no spread to pair, so rtl would
        # only flip which screen edge advances the book. Manga reading order is
        # inside the images, already linearised by the detector.
        f'  <spine page-progression-direction="{"rtl" if rtl else "ltr"}">',
        *spine,
        '  </spine>',
        '</package>',
        '',
    ])

    nav = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<html xmlns="http://www.w3.org/1999/xhtml" '
           'xmlns:epub="http://www.idpf.org/2007/ops">\n'
           f'<head><title>{esc_title}</title></head>\n'
           f'<body><nav epub:type="toc"><ol>{nav_items}</ol></nav></body>\n</html>\n')

    with _atomic(out_path) as tmp:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            # the spec requires mimetype to be the first entry and uncompressed
            z.writestr("mimetype", "application/epub+zip",
                       compress_type=zipfile.ZIP_STORED)
            z.writestr("META-INF/container.xml", _EPUB_CONTAINER)
            z.writestr("OEBPS/content.opf", opf)
            z.writestr("OEBPS/nav.xhtml", nav)
            z.writestr("OEBPS/style.css", _EPUB_CSS)
            for name, body in docs:
                z.writestr(f"OEBPS/{name}",
                           '<?xml version="1.0" encoding="utf-8"?>\n'
                           '<html xmlns="http://www.w3.org/1999/xhtml">\n'
                           f'<head><title>{esc_title}</title>'
                           '<link rel="stylesheet" type="text/css" href="style.css"/>'
                           '</head>\n'
                           f'<body>{body}</body>\n</html>\n')
            for i, img in enumerate(images, start=1):
                im = _render(img, rotate_wide=rotate_wide, pad_aspect=pad_aspect,
                             max_width=max_width, upscale=upscale,
                             grayscale=grayscale, gamma=gamma)
                if im.mode not in ("L", "RGB"):
                    im = im.convert("RGB")
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=quality)
                # jpeg is already compressed: STORED avoids pointless recompression
                z.writestr(f"OEBPS/img/{i:04d}.jpg", buf.getvalue(),
                           compress_type=zipfile.ZIP_STORED)
