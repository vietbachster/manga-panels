import io
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from PIL import Image
from manga_panels.archive import unpack, pack


def _make_cbz(path: Path, n: int) -> None:
    with zipfile.ZipFile(path, "w") as z:
        for i in range(n):
            img = Image.new("RGB", (10, 10), (i * 10, 0, 0))
            p = path.parent / f"tmp_{i}.png"
            img.save(p)
            z.write(p, f"{i:03d}.png")
            p.unlink()


def test_unpack_reads_pages_in_order(tmp_path):
    cbz = tmp_path / "ch.cbz"
    _make_cbz(cbz, 3)
    pages = unpack(cbz)
    assert len(pages) == 3
    assert pages[0].size == (10, 10)
    assert pages[0].mode == "RGB"


def test_unpack_natural_sort_non_padded(tmp_path):
    import zipfile
    from PIL import Image
    cbz = tmp_path / "np.cbz"
    order = [1, 2, 10, 11]           # lexicographic would give 1,10,11,2
    with zipfile.ZipFile(cbz, "w") as z:
        for i in order:
            img = Image.new("RGB", (4, 4), (i, 0, 0))   # red channel = page number
            p = tmp_path / f"p{i}.png"
            img.save(p); z.write(p, f"{i}.png"); p.unlink()
    pages = unpack(cbz)
    reds = [px.getpixel((0, 0))[0] for px in pages]
    assert reds == [1, 2, 10, 11]


def test_unpack_single_image(tmp_path):
    p = tmp_path / "page.png"
    Image.new("RGB", (30, 40), (0, 0, 0)).save(p)
    pages = unpack(p)
    assert len(pages) == 1
    assert pages[0].size == (30, 40) and pages[0].mode == "RGB"


def test_pack_roundtrip_jpeg_default(tmp_path):
    imgs = [Image.new("RGB", (8, 8), (0, i * 5, 0)) for i in range(4)]
    out = tmp_path / "out.cbz"
    pack(imgs, out)                      # default = jpeg
    with zipfile.ZipFile(out) as z:
        names = sorted(z.namelist())
    assert names == ["0001.jpg", "0002.jpg", "0003.jpg", "0004.jpg"]
    assert len(unpack(out)) == 4


def test_pack_png_format(tmp_path):
    imgs = [Image.new("RGB", (8, 8), (0, 0, 0)) for _ in range(2)]
    out = tmp_path / "out.cbz"
    pack(imgs, out, fmt="png")
    with zipfile.ZipFile(out) as z:
        assert sorted(z.namelist()) == ["0001.png", "0002.png"]


def test_jpeg_quality_knob_affects_size(tmp_path):
    # lower quality -> smaller file (proves --quality is wired up)
    import numpy as np
    arr = np.random.default_rng(0).integers(0, 256, (128, 128, 3), dtype="uint8")
    img = Image.fromarray(arr, "RGB")
    lo = tmp_path / "lo.cbz"; hi = tmp_path / "hi.cbz"
    pack([img], lo, fmt="jpeg", quality=30)
    pack([img], hi, fmt="jpeg", quality=95)
    assert lo.stat().st_size < hi.stat().st_size


def test_pack_bad_format_raises(tmp_path):
    import pytest
    with pytest.raises(ValueError):
        pack([Image.new("RGB", (4, 4))], tmp_path / "x.cbz", fmt="webp")


def test_pack_max_width_downscales_wide(tmp_path):
    wide = Image.new("RGB", (2000, 1000), (10, 20, 30))
    out = tmp_path / "o.cbz"
    pack([wide], out, max_width=800)
    assert unpack(out)[0].size == (800, 400)      # aspect ratio preserved


def test_pack_max_width_leaves_narrow_untouched(tmp_path):
    narrow = Image.new("RGB", (500, 900), (0, 0, 0))
    out = tmp_path / "o.cbz"
    pack([narrow], out, max_width=800)
    assert unpack(out)[0].size == (500, 900)      # never upscales


def test_pack_max_width_none_keeps_size(tmp_path):
    im = Image.new("RGB", (2000, 1000), (0, 0, 0))
    out = tmp_path / "o.cbz"
    pack([im], out)                                # default = no limit
    assert unpack(out)[0].size == (2000, 1000)


def test_unpack_empty_archive_raises(tmp_path):
    import pytest, zipfile
    from manga_panels.errors import EmptyArchive
    cbz = tmp_path / "empty.cbz"
    with zipfile.ZipFile(cbz, "w") as z:
        z.writestr("readme.txt", "no images")
    with pytest.raises(EmptyArchive):
        unpack(cbz)


def test_unpack_corrupt_archive_raises(tmp_path):
    import pytest
    from manga_panels.errors import BadArchive
    cbz = tmp_path / "bad.cbz"
    cbz.write_bytes(b"not a zip")
    with pytest.raises(BadArchive):
        unpack(cbz)


def test_pack_grayscale_stored_as_L(tmp_path):
    import io, zipfile
    out = tmp_path / "g.cbz"
    pack([Image.new("RGB", (10, 10), (200, 50, 50))], out, grayscale=True)
    with zipfile.ZipFile(out) as z:
        raw = Image.open(io.BytesIO(z.read(z.namelist()[0])))
    assert raw.mode == "L"                          # stored grayscale, not RGB


def test_eink_gamma_darkens_midtones():
    from manga_panels.archive import _eink
    mid = Image.new("L", (4, 4), 128)
    assert _eink(mid, grayscale=False, gamma=1.8).getpixel((0, 0)) < 128   # darkened
    assert _eink(mid, grayscale=False, gamma=1.0).getpixel((0, 0)) == 128  # 1.0 = off


def test_pack_pdf_output(tmp_path):
    imgs = [Image.new("RGB", (20, 30), (0, 0, 0)) for _ in range(3)]
    out = tmp_path / "o.pdf"
    pack(imgs, out, fmt="pdf")
    assert out.read_bytes()[:5] == b"%PDF-"        # valid PDF
    assert not (tmp_path / "o.pdf.tmp").exists()    # atomic, temp cleaned


def test_pack_pdf_missing_dep_raises(tmp_path, monkeypatch):
    import sys, pytest
    from manga_panels.errors import MissingDependency
    monkeypatch.setitem(sys.modules, "img2pdf", None)   # import img2pdf -> ImportError
    with pytest.raises(MissingDependency, match="pdf"):
        pack([Image.new("RGB", (4, 4))], tmp_path / "o.pdf", fmt="pdf")


def test_pack_atomic_no_partial_file_on_failure(tmp_path):
    import pytest

    class _Boom:                                   # an "image" that blows up on save
        def save(self, *a, **k):
            raise RuntimeError("boom")

    out = tmp_path / "o.cbz"
    with pytest.raises(RuntimeError):
        pack([Image.new("RGB", (4, 4)), _Boom()], out)
    assert not out.exists()                        # atomic: never a half-written cbz
    assert not (tmp_path / "o.cbz.tmp").exists()   # temp cleaned up


def test_unpack_corrupt_entry_data_raises(tmp_path):
    import io, pytest, zipfile
    from PIL import Image
    from manga_panels.errors import BadArchive
    cbz = tmp_path / "corrupt_entry.cbz"
    buf = io.BytesIO(); Image.new("RGB", (20, 20), (200, 0, 0)).save(buf, "PNG")
    with zipfile.ZipFile(cbz, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("0001.png", buf.getvalue())
    data = bytearray(cbz.read_bytes())
    for i in range(50, 90):            # corrupt the middle of the deflate stream
        data[i] ^= 0xFF
    cbz.write_bytes(data)
    with pytest.raises(BadArchive):    # wrapped zlib.error, not a raw traceback
        unpack(cbz)


def test_fit_shrinks_a_wide_image():
    from manga_panels.archive import _fit
    assert _fit(Image.new("RGB", (200, 100)), 50).size == (50, 25)


def test_fit_does_not_grow_by_default():
    from manga_panels.archive import _fit
    assert _fit(Image.new("RGB", (40, 20)), 100).size == (40, 20)


def test_fit_grows_when_upscale_is_on():
    from manga_panels.archive import _fit
    assert _fit(Image.new("RGB", (40, 20)), 100, upscale=True).size == (100, 50)


def test_fit_with_upscale_still_shrinks_a_wide_image():
    from manga_panels.archive import _fit
    assert _fit(Image.new("RGB", (200, 100)), 50, upscale=True).size == (50, 25)


def test_fit_without_max_width_returns_the_same_object():
    from manga_panels.archive import _fit
    im = Image.new("RGB", (40, 20))
    assert _fit(im, None, upscale=True) is im


def test_pack_threads_upscale_to_the_images(tmp_path):
    out = tmp_path / "up.cbz"
    pack([Image.new("RGB", (40, 20))], out, fmt="png", max_width=100, upscale=True)
    assert unpack(out)[0].size == (100, 50)


_OPF = {"opf": "http://www.idpf.org/2007/opf"}
_DC = "{http://purl.org/dc/elements/1.1/}"


def _epub(tmp_path, n=3, **kw):
    out = tmp_path / "vol.epub"
    pack([Image.new("RGB", (40, 20)) for _ in range(n)], out, fmt="epub", **kw)
    return out


def test_epub_mimetype_is_first_and_stored(tmp_path):
    # the EPUB spec requires this exact first entry, uncompressed
    with zipfile.ZipFile(_epub(tmp_path)) as z:
        first = z.infolist()[0]
        assert first.filename == "mimetype"
        assert first.compress_type == zipfile.ZIP_STORED
        assert z.read("mimetype") == b"application/epub+zip"


def test_epub_container_points_at_an_existing_opf(tmp_path):
    with zipfile.ZipFile(_epub(tmp_path)) as z:
        root = ET.fromstring(z.read("META-INF/container.xml"))
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        assert root.find(".//c:rootfile", ns).get("full-path") in z.namelist()


def test_epub_spine_lists_every_page_in_order(tmp_path):
    with zipfile.ZipFile(_epub(tmp_path, n=3)) as z:
        root = ET.fromstring(z.read("OEBPS/content.opf"))
    refs = [e.get("idref") for e in root.findall(".//opf:spine/opf:itemref", _OPF)]
    assert refs == ["p0001", "p0002", "p0003"]


def test_epub_spine_is_right_to_left(tmp_path):
    with zipfile.ZipFile(_epub(tmp_path)) as z:
        root = ET.fromstring(z.read("OEBPS/content.opf"))
    assert root.find(".//opf:spine", _OPF).get("page-progression-direction") == "rtl"


def test_epub_first_image_is_the_cover(tmp_path):
    with zipfile.ZipFile(_epub(tmp_path, n=3)) as z:
        root = ET.fromstring(z.read("OEBPS/content.opf"))
    covers = [e.get("href") for e in root.findall(".//opf:manifest/opf:item", _OPF)
              if e.get("properties") == "cover-image"]
    assert covers == ["img/0001.jpg"]


def test_epub_every_page_references_an_image_that_exists(tmp_path):
    with zipfile.ZipFile(_epub(tmp_path, n=3)) as z:
        names = set(z.namelist())
        for i in (1, 2, 3):
            assert f'src="img/{i:04d}.jpg"' in z.read(f"OEBPS/p{i:04d}.xhtml").decode()
            assert f"OEBPS/img/{i:04d}.jpg" in names


def test_epub_title_with_an_ampersand_stays_valid_xml(tmp_path):
    out = tmp_path / "Tom & Jerry.epub"
    pack([Image.new("RGB", (10, 10))], out, fmt="epub")
    with zipfile.ZipFile(out) as z:
        root = ET.fromstring(z.read("OEBPS/content.opf"))   # raises if malformed
    assert root.find(f".//{_DC}title").text == "Tom & Jerry"


def test_epub_identifier_is_stable_across_runs(tmp_path):
    # a re-processed volume must keep its id, or the reader loses reading progress
    ids = []
    for run in ("a", "b"):
        out = tmp_path / run / "vol.epub"
        pack([Image.new("RGB", (10, 10))], out, fmt="epub")
        with zipfile.ZipFile(out) as z:
            root = ET.fromstring(z.read("OEBPS/content.opf"))
        ids.append(root.find(f".//{_DC}identifier").text)
    assert ids[0] == ids[1] and ids[0].startswith("urn:uuid:")


def test_epub_applies_max_width_and_upscale(tmp_path):
    out = tmp_path / "vol.epub"
    pack([Image.new("RGB", (40, 20))], out, fmt="epub", max_width=100, upscale=True)
    with zipfile.ZipFile(out) as z:
        assert Image.open(io.BytesIO(z.read("OEBPS/img/0001.jpg"))).size == (100, 50)


def test_rotate_wide_turns_a_landscape_image():
    from manga_panels.archive import _rotate_wide
    assert _rotate_wide(Image.new("L", (200, 100)), 1.0).size == (100, 200)


def test_rotate_wide_leaves_a_narrow_image_alone():
    from manga_panels.archive import _rotate_wide
    im = Image.new("L", (200, 100))
    assert _rotate_wide(im, 3.0) is im          # ratio 2.0 is under the 3.0 threshold


def test_rotate_wide_is_clockwise():
    # A wrong direction still produces a correctly-sized image, so size proves
    # nothing. Mark the top-left corner: 90 deg clockwise sends it to the top-right.
    from manga_panels.archive import _rotate_wide
    im = Image.new("L", (4, 2), 255)
    im.putpixel((0, 0), 0)
    out = _rotate_wide(im, 1.0)
    black = [(x, y) for y in range(out.height) for x in range(out.width)
             if out.getpixel((x, y)) == 0]
    assert black == [(out.width - 1, 0)]


def test_rotate_wide_off_returns_the_same_object():
    from manga_panels.archive import _rotate_wide
    im = Image.new("L", (200, 100))
    assert _rotate_wide(im, None) is im
    assert _rotate_wide(im, 0) is im


def test_pad_aspect_pads_height_when_image_is_too_wide():
    from manga_panels.archive import _pad_aspect
    assert _pad_aspect(Image.new("L", (100, 100)), 0.5).size == (100, 200)


def test_pad_aspect_pads_width_when_image_is_too_tall():
    from manga_panels.archive import _pad_aspect
    assert _pad_aspect(Image.new("L", (100, 100)), 2.0).size == (200, 100)


def test_pad_aspect_centres_the_content():
    # the whole point: a reader that does not centre vertically must find nothing
    # left over to mis-place
    from manga_panels.archive import _pad_aspect
    im = Image.new("L", (100, 100), 0)          # black content on white padding
    out = _pad_aspect(im, 0.5)                  # -> 100x200, 50px of pad total
    col = [out.getpixel((50, y)) for y in range(out.height)]
    top = col.index(0)
    bottom = out.height - 1 - col[::-1].index(0)
    assert abs(top - (out.height - 1 - bottom)) <= 1


def test_pad_aspect_fills_with_white_and_keeps_the_content():
    from manga_panels.archive import _pad_aspect
    im = Image.new("L", (100, 100), 0)
    out = _pad_aspect(im, 0.5)
    assert out.getpixel((50, 0)) == 255         # padding is white
    assert out.getpixel((50, out.height // 2)) == 0   # content survived


def test_pad_aspect_noop_returns_the_same_object():
    from manga_panels.archive import _pad_aspect
    im = Image.new("L", (60, 100))              # already 0.6
    assert _pad_aspect(im, 0.6) is im
    assert _pad_aspect(im, None) is im


def test_render_chain_produces_a_screen_sized_image(tmp_path):
    # the whole point, end to end: a 3:1 landscape panel becomes a 3:5 portrait
    # image that exactly fills a 480x800 screen
    out = tmp_path / "geo.cbz"
    pack([Image.new("RGB", (1500, 500), (0, 0, 0))], out, fmt="png",
         rotate_wide=1.0, pad_aspect=3 / 5, max_width=480, upscale=True)
    assert unpack(out)[0].size == (480, 800)


def test_render_order_rotates_before_padding(tmp_path):
    # 400x100 with rotate 1.0 and aspect 0.5:
    #   rotate first -> 100x400, then pad width  -> 200x400   (correct)
    #   pad first    -> 400x800, then no rotation -> 400x800   (wrong order)
    # The two differ, so this actually pins the order down.
    out = tmp_path / "order.cbz"
    pack([Image.new("RGB", (400, 100))], out, fmt="png",
         rotate_wide=1.0, pad_aspect=0.5)
    assert unpack(out)[0].size == (200, 400)


def test_render_chain_reaches_the_epub_container(tmp_path):
    # regression: _pack_epub must forward rotate_wide/pad_aspect into _render,
    # same as the cbz path above — nothing else exercises this
    out = tmp_path / "geo.epub"
    pack([Image.new("RGB", (1500, 500), (0, 0, 0))], out, fmt="epub",
         rotate_wide=1.0, pad_aspect=3 / 5, max_width=480, upscale=True)
    with zipfile.ZipFile(out) as z:
        img = Image.open(io.BytesIO(z.read("OEBPS/img/0001.jpg")))
    assert img.size == (480, 800)


def test_render_chain_reaches_the_pdf_container(tmp_path):
    # regression: _pack_pdf must forward rotate_wide/pad_aspect into _render too
    import pytest
    pytest.importorskip("img2pdf")
    import pikepdf

    out = tmp_path / "geo.pdf"
    pack([Image.new("RGB", (1500, 500), (0, 0, 0))], out, fmt="pdf",
         rotate_wide=1.0, pad_aspect=3 / 5, max_width=480, upscale=True)
    with pikepdf.open(out) as pdf:
        raw = next(iter(pdf.pages[0].get_images().values()))
        img = pikepdf.PdfImage(raw).as_pil_image()
    assert img.size == (480, 800)


def _cbz_with_comicinfo(path, xml, n_images=3):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("ComicInfo.xml", xml)
        for i in range(n_images):
            buf = io.BytesIO()
            Image.new("RGB", (10, 10)).save(buf, "PNG")
            z.writestr(f"{i:03d}.png", buf.getvalue())


_CI_FULL = """<?xml version="1.0" encoding="utf-8"?>
<ComicInfo><Series>Monster</Series><Volume>4</Volume><Writer>Naoki Urasawa</Writer>
<Pages>
  <Page Image="0" Type="FrontCover"/>
  <Page Image="1" Bookmark="Kapitel 51. Richard"/>
  <Page Image="2" Bookmark="Kapitel 52. A Prova"/>
</Pages></ComicInfo>
"""


def test_read_comicinfo_returns_title_creator_and_chapters(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, _CI_FULL)
    got = read_comicinfo(p)
    assert got["title"] == "Monster Vol. 4"
    assert got["creator"] == "Naoki Urasawa"
    assert got["chapters"] == [(1, "Kapitel 51. Richard"), (2, "Kapitel 52. A Prova")]


def test_read_comicinfo_ignores_pages_without_a_bookmark(tmp_path):
    # the FrontCover entry has no Bookmark and must not become a chapter
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, _CI_FULL)
    assert all(t for _, t in read_comicinfo(p)["chapters"])


def test_read_comicinfo_without_the_file_is_empty(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    with zipfile.ZipFile(p, "w") as z:
        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, "PNG")
        z.writestr("000.png", buf.getvalue())
    assert read_comicinfo(p) == {}


def test_read_comicinfo_with_broken_xml_is_empty(tmp_path):
    # metadata is a nicety; a corrupt ComicInfo must never fail the run
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, "<ComicInfo><Series>oops")
    assert read_comicinfo(p) == {}


def test_read_comicinfo_falls_back_to_title_then_series(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, "<ComicInfo><Title>Só o título</Title></ComicInfo>")
    assert read_comicinfo(p)["title"] == "Só o título"


def test_read_comicinfo_chapters_are_sorted_by_image(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Image="5" Bookmark="B"/><Page Image="2" Bookmark="A"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p)["chapters"] == [(2, "A"), (5, "B")]


def test_read_comicinfo_whitespace_only_bookmark_is_not_a_chapter(tmp_path):
    # bug: the filter tested the raw attribute for truthiness, but the tuple is
    # built with .strip() — so a whitespace-only Bookmark slipped through as an
    # empty-title chapter instead of being ignored like "no bookmark at all"
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Series>S</Series><Pages>'
                           '<Page Image="1" Bookmark="   "/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p)["chapters"] == []


def test_read_comicinfo_non_decimal_unicode_digit_does_not_raise(tmp_path):
    # bug: str.isdigit() accepts characters like superscript "²" that int()
    # cannot parse, and that int() call sits outside the try/except — so a
    # malformed Image attribute could raise out of a function documented to
    # never fail on bad metadata
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Image="²" Bookmark="Weird"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p) == {}          # malformed entry skipped, no raise


def test_read_comicinfo_page_without_image_attribute_is_skipped(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Bookmark="No Image attr"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p) == {}


def test_read_comicinfo_non_numeric_image_is_skipped(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Image="abc" Bookmark="Not a number"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p) == {}


def test_read_comicinfo_negative_image_is_kept(tmp_path):
    # negative indices are out of scope to reject here (needs the real page
    # count, computed by the next task) — this just pins today's behaviour
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Image="-1" Bookmark="Negative"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p)["chapters"] == [(-1, "Negative")]


def test_read_comicinfo_duplicate_image_values_both_kept(tmp_path):
    from manga_panels.archive import read_comicinfo
    p = tmp_path / "v.cbz"
    _cbz_with_comicinfo(p, '<ComicInfo><Pages>'
                           '<Page Image="3" Bookmark="First"/>'
                           '<Page Image="3" Bookmark="Second"/>'
                           '</Pages></ComicInfo>')
    assert read_comicinfo(p)["chapters"] == [(3, "First"), (3, "Second")]


def test_read_comicinfo_nonexistent_path_is_empty():
    from manga_panels.archive import read_comicinfo
    assert read_comicinfo("/no/such/path/v.cbz") == {}


def _epub_struct(tmp_path, n_images, page_starts, chapters=None, **kw):
    out = tmp_path / "vol.epub"
    pack([Image.new("RGB", (40, 20)) for _ in range(n_images)], out, fmt="epub",
         page_starts=page_starts, chapters=chapters, **kw)
    return zipfile.ZipFile(out)


def test_epub_sections_follow_the_chapters(tmp_path):
    starts = [(i, f"Página {i + 1}") for i in range(9)]   # spacing clears the section floor
    z = _epub_struct(tmp_path, 9, starts, chapters=[(5, "Capítulo 2")])
    root = ET.fromstring(z.read("OEBPS/content.opf"))
    refs = [e.get("idref") for e in root.findall(".//opf:spine/opf:itemref", _OPF)]
    assert refs == ["s0001", "s0002"]           # before chapter 2, and chapter 2 on
    assert 'src="img/0006.jpg"' in z.read("OEBPS/s0002.xhtml").decode()


def test_epub_without_chapters_chunks_every_20_pages(tmp_path):
    starts = [(i, f"Página {i + 1}") for i in range(45)]
    z = _epub_struct(tmp_path, 45, starts)
    root = ET.fromstring(z.read("OEBPS/content.opf"))
    refs = [e.get("idref") for e in root.findall(".//opf:spine/opf:itemref", _OPF)]
    assert refs == ["s0001", "s0002", "s0003"]  # 45 pages -> 20 + 20 + 5


def test_epub_closely_spaced_chapters_collapse_but_all_appear_in_nav(tmp_path):
    # marks every 2 source pages must not reproduce the near-single-page
    # section swarm — the very "indexing on every page turn" failure the
    # chapter-sized section was built to avoid — but none may vanish from the toc
    n = 40
    starts = [(i, f"Página {i + 1}") for i in range(n)]
    chapters = [(i, f"Cap {i}") for i in range(0, n, 2)]      # 20 marks, 2 pages apart
    z = _epub_struct(tmp_path, n, starts, chapters=chapters)
    root = ET.fromstring(z.read("OEBPS/content.opf"))
    refs = [e.get("idref") for e in root.findall(".//opf:spine/opf:itemref", _OPF)]
    assert len(refs) < len(chapters)               # far fewer sections than chapter marks
    text = z.read("OEBPS/nav.xhtml").decode()
    for _, title in chapters:
        assert title in text                       # every chapter still one click away


def test_epub_normally_spaced_chapters_each_get_a_section(tmp_path):
    # ~20 pages apart is real chapter spacing (Monster) — the floor must leave
    # this alone, it only collapses the pathological close-spacing case above
    n = 60
    starts = [(i, f"Página {i + 1}") for i in range(n)]
    chapters = [(0, "Cap 1"), (20, "Cap 2"), (40, "Cap 3")]
    z = _epub_struct(tmp_path, n, starts, chapters=chapters)
    root = ET.fromstring(z.read("OEBPS/content.opf"))
    refs = [e.get("idref") for e in root.findall(".//opf:spine/opf:itemref", _OPF)]
    assert len(refs) == 3


def test_epub_puts_an_anchor_before_every_source_page(tmp_path):
    z = _epub_struct(tmp_path, 6, [(0, "Página 1"), (2, "Página 2"), (4, "Página 3")])
    body = z.read("OEBPS/s0001.xhtml").decode()
    for k in (1, 2, 3):
        assert f'id="pag{k}"' in body
    assert body.index('id="pag1"') < body.index('id="pag2"') < body.index('id="pag3"')


def test_epub_nav_nests_pages_under_their_chapter(tmp_path):
    starts = [(i, f"Página {i + 1}") for i in range(10)]  # spacing clears the section floor
    z = _epub_struct(tmp_path, 10, starts, chapters=[(5, "Capítulo 2")])
    nav = ET.fromstring(z.read("OEBPS/nav.xhtml"))   # raises if the nesting broke the XML
    text = z.read("OEBPS/nav.xhtml").decode()
    assert "Capítulo 2" in text
    assert 's0002.xhtml#pag6' in text                # page link is an anchor, not a section


def test_epub_nav_is_flat_without_chapters(tmp_path):
    z = _epub_struct(tmp_path, 4, [(0, "Página 1"), (2, "Página 2")])
    text = z.read("OEBPS/nav.xhtml").decode()
    ET.fromstring(text)
    assert text.count("<ol>") == 1 and "Página 2" in text


def test_epub_uses_comicinfo_title_and_creator(tmp_path):
    z = _epub_struct(tmp_path, 2, [(0, "Página 1")],
                     title="Monster Vol. 4", creator="Naoki Urasawa")
    root = ET.fromstring(z.read("OEBPS/content.opf"))
    # findtext without ".//" only checks direct children of <package>, but dc:title
    # lives inside <metadata> (the OPF schema requires it) — same fix the existing
    # test_epub_title_with_an_ampersand_stays_valid_xml already needed.
    assert root.findtext(f".//{_DC}title") == "Monster Vol. 4"
    assert root.findtext(f".//{_DC}creator") == "Naoki Urasawa"


def test_epub_without_page_starts_keeps_one_xhtml_per_image(tmp_path):
    out = tmp_path / "old.epub"
    pack([Image.new("RGB", (10, 10)) for _ in range(3)], out, fmt="epub")
    with zipfile.ZipFile(out) as z:
        assert "OEBPS/p0003.xhtml" in z.namelist()
