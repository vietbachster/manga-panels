import zipfile
import numpy as np
from pathlib import Path
from PIL import Image
from manga_panels.pipeline import crop_panels, process_archive
from manga_panels.archive import pack, unpack


def _grid_page():
    arr = np.full((200, 200), 255, np.uint8)
    for (y, x) in [(20, 20), (20, 120), (120, 20), (120, 120)]:
        arr[y:y + 60, x:x + 60] = 0
    return Image.fromarray(arr, "L").convert("RGB")


def test_crop_returns_subimages():
    page = _grid_page()
    panels = crop_panels(page, [(20, 20, 60, 60), (120, 20, 60, 60)])
    assert [p.size for p in panels] == [(60, 60), (60, 60)]


def test_process_archive_explodes_panels(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)                     # 1 page, 4 panels
    out = tmp_path / "ch_panels.cbz"
    n = process_archive(src, out, page_pos="off")
    assert n == 4
    with zipfile.ZipFile(out) as z:
        assert len(z.namelist()) == 4


def test_process_archive_prepends_full_page(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)                     # 1 page 200x200, 4 panels
    out = tmp_path / "ch_panels.cbz"
    n = process_archive(src, out)                 # page_pos default = before
    assert n == 5                                 # full page + 4 panels
    imgs = unpack(out)
    assert imgs[0].size == (200, 200)             # macro first
    assert all(im.size != (200, 200) for im in imgs[1:])


def test_include_page_not_duplicated_when_whole_page(tmp_path):
    src = tmp_path / "blank.cbz"
    pack([Image.new("RGB", (100, 100), (255, 255, 255))], src)
    out = tmp_path / "out.cbz"
    assert process_archive(src, out) == 1         # 0 panels -> page once


def _gradient_page(w=64, h=48):
    # every pixel a distinct color (no row/column repeats), so an exact pixel
    # comparison catches a crop/shift/flip regression; luma stays >=128
    # everywhere so the fake detector finds zero dark blobs (0 panels).
    ys, xs = np.mgrid[0:h, 0:w]
    r = 150 + (xs * 3) % 100
    g = 150 + (ys * 5) % 100
    b = 150 + ((xs + ys) * 2) % 100
    arr = np.stack([r, g, b], axis=-1).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def test_zero_panel_page_pixel_identical_when_split_off(tmp_path):
    # regression: the <=1 panel branch now crops a synthetic full-page box
    # through _panel_imgs instead of appending `page` directly. With
    # split_ratio=None the two must be pixel-for-pixel identical.
    page = _gradient_page()
    src = tmp_path / "grad.cbz"
    pack([page], src, fmt="png")                  # lossless round-trip
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, fmt="png", split_ratio=None)
    assert n == 1                                 # 0 panels -> page once
    [got] = unpack(out)
    assert got.size == page.size
    assert got.mode == page.mode
    assert np.array_equal(np.asarray(got), np.asarray(page))


def _single_panel_page():
    # white page with ONE black rectangle and no internal gutter -> 1 panel
    arr = np.full((200, 200), 255, np.uint8)
    arr[40:160, 40:160] = 0
    return Image.fromarray(arr, "L").convert("RGB")


def test_single_panel_page_emitted_once(tmp_path):
    src = tmp_path / "sp.cbz"
    pack([_single_panel_page()], src)
    out = tmp_path / "out.cbz"
    assert process_archive(src, out) == 1         # 1 panel ~ page -> no duplicate


def test_single_panel_page_pixel_identical_when_split_off(tmp_path):
    # same regression guard as test_zero_panel_page_pixel_identical_when_split_off,
    # for the other shape of the <=1 panel branch (exactly 1 detected panel).
    page = _single_panel_page()
    src = tmp_path / "sp.cbz"
    pack([page], src, fmt="png")                  # lossless round-trip
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, fmt="png", split_ratio=None)
    assert n == 1                                 # 1 panel ~ page -> no duplicate
    [got] = unpack(out)
    assert got.size == page.size
    assert got.mode == page.mode
    assert np.array_equal(np.asarray(got), np.asarray(page))


def test_zero_panel_page_appended_by_identity_not_copy(tmp_path, monkeypatch):
    # Pixel-equality can't catch a regression here: cropping a page to its own
    # full bounding box is pixel-identical to the page whether or not that
    # crop is a fresh copy. Object identity is what tells "appended `page`"
    # apart from "appended a crop of it" -- and the no-copy path exists
    # specifically to avoid doubling peak RAM on <=1-panel pages (measured
    # 628MB -> 1176MB on a 40-page archive when this regressed).
    import manga_panels.pipeline as pipeline

    page = Image.new("RGB", (10, 10), (255, 255, 255))   # blank -> 0 panels
    captured = {}

    def _fake_pack(imgs, out, **kw):
        captured["imgs"] = imgs

    monkeypatch.setattr(pipeline, "unpack", lambda path: [page])
    monkeypatch.setattr(pipeline, "pack", _fake_pack)

    process_archive(tmp_path / "in.cbz", tmp_path / "out.cbz", split_ratio=None)

    assert captured["imgs"][0] is page             # same object, no full-page copy


def _wide_panels_page():
    # two wide panels stacked -> 2 boxes of 360x100 each (ratio 3.6)
    arr = np.full((400, 400), 255, np.uint8)
    arr[20:120, 20:380] = 0
    arr[220:320, 20:380] = 0
    return Image.fromarray(arr, "L").convert("RGB")


def test_split_ratio_emits_whole_panel_then_slices(tmp_path):
    src = tmp_path / "wide.cbz"
    pack([_wide_panels_page()], src)
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, page_pos="off", split_ratio=1.0)
    assert n == 10                                # 2 panels x (1 whole + 4 slices)
    imgs = unpack(out)
    assert imgs[0].size == (360, 100)             # the whole panel comes first
    assert [im.size for im in imgs[1:5]] == [(90, 100)] * 4


def test_split_ratio_off_changes_nothing(tmp_path):
    src = tmp_path / "wide.cbz"
    pack([_wide_panels_page()], src)
    out = tmp_path / "out.cbz"
    assert process_archive(src, out, page_pos="off") == 2


def test_split_ratio_also_splits_a_single_panel_page(tmp_path):
    src = tmp_path / "sp.cbz"
    pack([_single_panel_page()], src)             # 200x200 page, 1 panel -> page whole
    out = tmp_path / "out.cbz"
    assert process_archive(src, out, split_ratio=0.5) == 3   # whole page + 2 slices


def test_page_pos_after_puts_macro_last(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, page_pos="after")
    assert n == 5
    imgs = unpack(out)
    assert imgs[-1].size == (200, 200)            # macro last
    assert imgs[0].size != (200, 200)             # panel first


def test_process_archive_bad_page_pos_raises(tmp_path):
    import pytest
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    with pytest.raises(ValueError):
        process_archive(src, tmp_path / "o.cbz", page_pos="nope")


def test_keep_first_keeps_pages_whole(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([_grid_page(), _grid_page()], src)       # 2 pages of 4 panels
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, keep_first=1)   # 1st whole, 2nd cropped
    assert n == 6                                 # 1 (whole) + 5 (macro+4)
    imgs = unpack(out)
    assert imgs[0].size == (200, 200)             # 1st page whole, uncropped


def test_blank_page_falls_back_to_whole_page(tmp_path):
    src = tmp_path / "blank.cbz"
    pack([Image.new("RGB", (100, 100), (255, 255, 255))], src)
    out = tmp_path / "blank_panels.cbz"
    n = process_archive(src, out)
    assert n == 1                                  # never loses the page


def test_cli_processes_folder(tmp_path):
    from manga_panels.cli import main
    from manga_panels.archive import pack
    src_dir = tmp_path / "chapters"
    src_dir.mkdir()
    pack([_grid_page()], src_dir / "c1.cbz")
    out_dir = tmp_path / "out"
    rc = main([str(src_dir), "-o", str(out_dir)])
    assert rc == 0
    assert (out_dir / "c1_panels.cbz").exists()


def test_cli_empty_folder_does_not_create_output_dir(tmp_path):
    from manga_panels.cli import main
    empty_dir = tmp_path / "chapters"
    empty_dir.mkdir()
    out = tmp_path / "out"
    rc = main([str(empty_dir), "-o", str(out)])
    assert rc != 0
    assert not out.exists()


def test_cli_same_stem_different_ext_no_overwrite(tmp_path):
    from manga_panels.cli import main
    from manga_panels.archive import pack
    src_dir = tmp_path / "chapters"
    src_dir.mkdir()
    pack([_grid_page()], src_dir / "c1.cbz")
    pack([_grid_page()], src_dir / "c1.zip")
    out_dir = tmp_path / "out"
    rc = main([str(src_dir), "-o", str(out_dir)])
    assert rc == 0
    outputs = sorted(out_dir.iterdir())
    assert len(outputs) == 2
    for f in outputs:
        assert f.stat().st_size > 0
        with zipfile.ZipFile(f) as z:
            assert len(z.namelist()) == 5   # full page + 4 panels (--page default)


def test_cli_bracket_filename_does_not_crash(tmp_path):
    # real manga names use brackets ([c01], [web]); "/" never appears in a file
    # name (it's the OS path separator), so Rich's closing tag ([/x]) only reaches
    # us intact via another non-filesystem sink: an unknown key in the config toml.
    from manga_panels.cli import main
    src = tmp_path / "chapter [c01] [web].cbz"   # brackets look like Rich markup
    pack([_grid_page()], src)
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text('[defaults]\n"weird [c01] [/x]" = true\n')  # unknown key -> warn()
    rc = main([str(src), "--config", str(cfg)])   # must not raise MarkupError
    assert rc == 0
    assert (tmp_path / "chapter [c01] [web]_panels.cbz").exists()


def test_cli_magi_load_failure_reported_without_raising(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.ml as ml

    def _boom():
        from manga_panels.errors import MissingDependency
        raise MissingDependency("failed to import torch/transformers")

    monkeypatch.setattr(ml, "_load_magi", _boom)   # warmup blows up
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    rc = main([str(src)])
    assert rc != 0


def test_cli_batch_continues_past_bad_file(tmp_path):
    from manga_panels.cli import main
    src_dir = tmp_path / "in"
    src_dir.mkdir()
    pack([_grid_page()], src_dir / "good.cbz")
    (src_dir / "bad.cbz").write_bytes(b"not a zip")   # will fail to unpack
    out_dir = tmp_path / "out"
    rc = main([str(src_dir), "-o", str(out_dir)])
    assert rc != 0                                     # a file failed
    assert (out_dir / "good_panels.cbz").exists()      # but the good one got through


def test_cli_keyboardinterrupt_exits_clean(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.cli as cli

    def _boom(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "process_archive", _boom)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src)]) == 130                     # clean interrupt code, no traceback


def test_entry_exits_with_main_return_code(monkeypatch):
    import signal
    import pytest
    import manga_panels.cli as cli
    monkeypatch.setattr(cli, "main", lambda argv=None: 0)
    old = signal.getsignal(signal.SIGTERM)
    try:
        with pytest.raises(SystemExit) as e:
            cli._entry()
        assert e.value.code == 0
    finally:
        signal.signal(signal.SIGTERM, old)


def test_cli_debug_writes_debug_cbz(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    rc = main([str(src), "--debug"])
    assert rc == 0
    assert (tmp_path / "ch_debug.cbz").exists()
    assert not (tmp_path / "ch_panels.cbz").exists()


def test_cli_preview_writes_preview_cbz(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    rc = main([str(src), "--preview"])
    assert rc == 0
    assert (tmp_path / "ch_preview.cbz").exists()
    assert not (tmp_path / "ch_panels.cbz").exists()


def test_process_archive_on_page_called_per_page(tmp_path):
    calls = []
    src = tmp_path / "ch.cbz"
    pack([_grid_page(), _grid_page()], src)
    process_archive(src, tmp_path / "o.cbz",
                    on_page=lambda done, total: calls.append((done, total)))
    assert calls == [(1, 2), (2, 2)]


def test_cli_no_input_no_library_errors(monkeypatch):
    import manga_panels.config as config
    monkeypatch.setattr(config, "_DISCOVER", [])   # ignore any stray toml in cwd
    from manga_panels.cli import main
    assert main([]) != 0


def test_cli_no_input_uses_library_picker(tmp_path, monkeypatch):
    import manga_panels.config as config
    import manga_panels.browse as browse
    monkeypatch.setattr(config, "_DISCOVER", [])
    src = tmp_path / "Vol.01.cbz"
    pack([_grid_page()], src)
    monkeypatch.setattr(browse, "pick_from_library", lambda root, **kw: [src])
    from manga_panels.cli import main
    out_dir = tmp_path / "out"
    rc = main(["--library", str(tmp_path), "-o", str(out_dir)])
    assert rc == 0
    assert (out_dir / "Vol.01_panels.cbz").exists()


def test_process_archive_cover_is_first_page(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    cover = tmp_path / "cover.png"
    Image.new("RGB", (50, 70), (123, 0, 0)).save(cover)
    out = tmp_path / "out.cbz"
    n = process_archive(src, out, cover=str(cover), page_pos="off")
    imgs = unpack(out)
    assert imgs[0].size == (50, 70)                 # cover is page 1
    assert n == 5                                   # cover + 4 panels


def test_cli_cover(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    cover = tmp_path / "cover.png"
    Image.new("RGB", (50, 70), (9, 9, 9)).save(cover)
    assert main([str(src), "--cover", str(cover)]) == 0
    assert unpack(tmp_path / "ch_panels.cbz")[0].size == (50, 70)


def test_process_archive_cover_crop_from_wide_page(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([Image.new("RGB", (200, 100), (0, 0, 0)), _grid_page()], src)
    out = tmp_path / "out.cbz"
    process_archive(src, out, cover_crop=0.4)       # left 40% of the wide page 0
    assert unpack(out)[0].size == (80, 100)


def test_process_archive_cover_crop_right_side(tmp_path):
    src = tmp_path / "ch.cbz"
    pack([Image.new("RGB", (200, 100), (0, 0, 0)), _grid_page()], src)
    out = tmp_path / "out.cbz"
    process_archive(src, out, cover_crop=0.3, cover_side="right")
    assert unpack(out)[0].size == (60, 100)


def test_cli_cover_missing_errors(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--cover", str(tmp_path / "nope.png")]) != 0


def test_cli_grayscale_output(tmp_path):
    import io, zipfile
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--grayscale"]) == 0
    with zipfile.ZipFile(tmp_path / "ch_panels.cbz") as z:
        raw = Image.open(io.BytesIO(z.read(z.namelist()[0])))
    assert raw.mode == "L"


def test_cli_device_resolves_max_width(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.cli as cli
    captured = {}

    def spy(in_path, out, *, on_page=None, **kw):
        captured.update(kw)
        pack([Image.new("RGB", (4, 4))], out, fmt=kw.get("fmt", "jpeg"))
        return 1

    monkeypatch.setattr(cli, "process_archive", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--device", "scribe", "--grayscale"]) == 0
    assert captured["max_width"] == 1860 and captured["grayscale"] is True


def test_cli_device_x4_and_split_ratio(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.cli as cli
    captured = {}

    def spy(in_path, out, *, on_page=None, **kw):
        captured.update(kw)
        pack([Image.new("RGB", (4, 4))], out, fmt=kw.get("fmt", "jpeg"))
        return 1

    monkeypatch.setattr(cli, "process_archive", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--device", "x4", "--split-ratio", "1.0"]) == 0
    assert captured["max_width"] == 480 and captured["split_ratio"] == 1.0


def test_cli_rejects_nan_split_ratio(tmp_path):
    # nan <= 0 is False, so a naive guard lets it through; catch it here instead
    # of letting it fail late (after Magi loads) with an opaque ValueError.
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--split-ratio", "nan"]) == 1


def test_cli_format_pdf_writes_pdf(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    rc = main([str(src), "--format", "pdf"])
    assert rc == 0
    out = tmp_path / "ch_panels.pdf"
    assert out.exists() and out.read_bytes()[:5] == b"%PDF-"
    assert not (tmp_path / "ch_panels.cbz").exists()


def test_cli_custom_suffix(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--suffix", "_cut"]) == 0
    assert (tmp_path / "ch_cut.cbz").exists()


def test_cli_overwrite_replaces_source(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)                       # 1 page -> 4 panels
    assert len(unpack(src)) == 1
    assert main([str(src), "--overwrite"]) == 0
    assert not (tmp_path / "ch_panels.cbz").exists()   # no sibling written
    assert not (tmp_path / "ch.cbz.tmp").exists()      # temp cleaned up
    assert len(unpack(src)) == 5                        # source now holds macro + 4


def test_cli_empty_suffix_refuses_to_clobber_source(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--suffix", ""]) != 0    # out == source -> refuse
    assert len(unpack(src)) == 1                     # untouched


def test_cli_config_defaults_applied_and_cli_wins(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text('[defaults]\nformat = "png"\n')
    # config sets png; no flag -> png output
    out1 = tmp_path / "a.cbz"
    assert main([str(src), "-o", str(out1), "--config", str(cfg)]) == 0
    import zipfile
    with zipfile.ZipFile(out1) as z:
        assert z.namelist()[0].endswith(".png")
    # CLI flag beats the config
    out2 = tmp_path / "b.cbz"
    assert main([str(src), "-o", str(out2), "--config", str(cfg), "-f", "jpeg"]) == 0
    with zipfile.ZipFile(out2) as z:
        assert z.namelist()[0].endswith(".jpg")


def test_cli_format_epub_writes_epub(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--format", "epub"]) == 0
    out = tmp_path / "ch_panels.epub"
    assert out.exists()
    with zipfile.ZipFile(out) as z:
        assert z.infolist()[0].filename == "mimetype"
    assert not (tmp_path / "ch_panels.cbz").exists()


def test_cli_upscale_reaches_process_archive(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.cli as cli
    captured = {}

    def spy(in_path, out, *, on_page=None, **kw):
        captured.update(kw)
        pack([Image.new("RGB", (4, 4))], out, fmt=kw.get("fmt", "jpeg"))
        return 1

    monkeypatch.setattr(cli, "process_archive", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--device", "x4", "--upscale"]) == 0
    assert captured["upscale"] is True and captured["max_width"] == 480


def test_cli_preview_accepts_upscale(tmp_path):
    # --preview routes to a different function; upscale must not leak as a TypeError
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--preview", "--upscale", "--max-width", "300"]) == 0
    assert (tmp_path / "ch_preview.cbz").exists()


def test_cli_split_ratio_zero_means_no_split(tmp_path):
    # 0 is the "off" sentinel, so a device preset that turns splitting on can be
    # turned back off from the command line
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--split-ratio", "0", "-o", str(tmp_path / "zero.cbz")]) == 0
    assert main([str(src), "-o", str(tmp_path / "none.cbz")]) == 0
    assert len(unpack(tmp_path / "zero.cbz")) == len(unpack(tmp_path / "none.cbz"))


def test_cli_still_rejects_negative_and_nan_split_ratio(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--split-ratio", "-1"]) == 1
    assert main([str(src), "--split-ratio", "nan"]) == 1


def test_cli_geometry_flags_reach_process_archive(tmp_path, monkeypatch):
    from manga_panels.cli import main
    import manga_panels.cli as cli
    captured = {}

    def spy(in_path, out, *, on_page=None, **kw):
        captured.update(kw)
        pack([Image.new("RGB", (4, 4))], out, fmt=kw.get("fmt", "jpeg"))
        return 1

    monkeypatch.setattr(cli, "process_archive", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--rotate-wide", "1.0", "--pad-aspect", "3:5"]) == 0
    assert captured["rotate_wide"] == 1.0
    assert abs(captured["pad_aspect"] - 0.6) < 1e-9


def test_cli_preview_accepts_geometry_flags(tmp_path):
    # --preview routes to a different function; a one-sided param is a TypeError
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--preview", "--rotate-wide", "1.0", "--pad-aspect", "3:5"]) == 0
    assert (tmp_path / "ch_preview.cbz").exists()


def test_cli_debug_accepts_geometry_flags(tmp_path):
    # --debug routes to yet another function; a one-sided param is a TypeError
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--debug", "--rotate-wide", "1.0", "--pad-aspect", "3:5"]) == 0
    assert (tmp_path / "ch_debug.cbz").exists()


def test_cli_rejects_a_bad_pad_aspect(tmp_path):
    import pytest
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    for bad in ("3x5", "0:5", "5:0", "abc", "nan:5", "5:nan", "inf:5", "5:inf"):
        with pytest.raises(SystemExit) as e:      # argparse type error
            main([str(src), "--pad-aspect", bad])
        assert e.value.code == 2


def test_cli_rejects_a_negative_rotate_wide(tmp_path):
    from manga_panels.cli import main
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    assert main([str(src), "--rotate-wide", "-1"]) == 1
    assert main([str(src), "--rotate-wide", "nan"]) == 1


def test_page_starts_marks_every_source_page(tmp_path, monkeypatch):
    import manga_panels.pipeline as pl
    captured = {}
    real = pl.pack

    def spy(imgs, out, **kw):
        captured.update(kw)
        return real(imgs, out, **{k: v for k, v in kw.items()
                                  if k not in ("page_starts", "chapters",
                                               "title", "creator")})

    monkeypatch.setattr(pl, "pack", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page(), _grid_page()], src)      # 2 pages, 4 panels each
    process_archive(src, tmp_path / "out.cbz", page_pos="off")
    starts = captured["page_starts"]
    assert [lbl for _, lbl in starts] == ["Página 1", "Página 2"]
    assert [i for i, _ in starts] == [0, 4]      # 4 panels before page 2 begins


def test_page_starts_labels_the_cover(tmp_path, monkeypatch):
    import manga_panels.pipeline as pl
    captured = {}
    real = pl.pack

    def spy(imgs, out, **kw):
        captured.update(kw)
        return real(imgs, out, **{k: v for k, v in kw.items()
                                  if k not in ("page_starts", "chapters",
                                               "title", "creator")})

    monkeypatch.setattr(pl, "pack", spy)
    src = tmp_path / "ch.cbz"
    pack([_grid_page()], src)
    cov = tmp_path / "cov.png"
    Image.new("RGB", (20, 30)).save(cov)
    process_archive(src, tmp_path / "out.cbz", cover=str(cov), page_pos="off")
    assert captured["page_starts"][0] == (0, "Capa")


def test_chapters_are_resolved_to_image_indices(tmp_path, monkeypatch):
    # ComicInfo indexes SOURCE PAGES; the packers need indices into the output
    # image list, which is longer because each page explodes into panels
    import io as _io, zipfile as _zip
    import manga_panels.pipeline as pl
    src = tmp_path / "ch.cbz"
    with _zip.ZipFile(src, "w") as z:
        z.writestr("ComicInfo.xml",
                   '<ComicInfo><Pages><Page Image="1" Bookmark="Cap 2"/></Pages></ComicInfo>')
        for i in range(2):
            b = _io.BytesIO(); _grid_page().save(b, "PNG")
            z.writestr(f"{i:03d}.png", b.getvalue())
    captured = {}
    real = pl.pack

    def spy(imgs, out, **kw):
        captured.update(kw)
        return real(imgs, out, **{k: v for k, v in kw.items()
                                  if k not in ("page_starts", "chapters",
                                               "title", "creator")})

    monkeypatch.setattr(pl, "pack", spy)
    process_archive(src, tmp_path / "out.cbz", page_pos="off")
    assert captured["chapters"] == [(4, "Cap 2")]   # source page 1 starts at image 4


def test_chapter_outside_the_volume_is_dropped_with_a_warning(tmp_path):
    # a chapter that silently vanishes is worse than one that is obviously wrong
    import io as _io, zipfile as _zip
    src = tmp_path / "ch.cbz"
    with _zip.ZipFile(src, "w") as z:
        z.writestr("ComicInfo.xml",
                   '<ComicInfo><Pages><Page Image="99" Bookmark="Fantasma"/>'
                   '<Page Image="0" Bookmark="Real"/></Pages></ComicInfo>')
        b = _io.BytesIO(); _grid_page().save(b, "PNG")
        z.writestr("000.png", b.getvalue())
    said = []
    n = process_archive(src, tmp_path / "out.cbz", page_pos="off",
                        warn=said.append)
    assert n > 0
    assert len(said) == 1 and "Fantasma" in said[0]
