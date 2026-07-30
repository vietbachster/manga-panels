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
