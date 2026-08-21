import pytest
from manga_panels.config import load_config
from manga_panels.errors import MangaPanelsError
import manga_panels.config as config


def test_reads_defaults(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nquality = 80\nmax_width = 1264\n')
    assert load_config(str(cfg)) == ({"quality": 80, "max_width": 1264}, {})


def test_unknown_key_ignored_with_warning(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nformat = "png"\nbogus = 1\n')
    warned = []
    assert load_config(str(cfg), warn=warned.append) == ({"format": "png"}, {})
    assert warned                      # warned about the unknown key


def test_hyphen_key_normalized(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nkeep-first = 2\n')
    assert load_config(str(cfg)) == ({"keep_first": 2}, {})


def test_library_and_suffix_keys_accepted(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nlibrary = "/data/manga"\nsuffix = "_cut"\n')
    assert load_config(str(cfg)) == ({"library": "/data/manga", "suffix": "_cut"}, {})


def test_split_ratio_key_accepted(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nsplit-ratio = 1.0\n')
    assert load_config(str(cfg)) == ({"split_ratio": 1.0}, {})


def test_missing_explicit_raises(tmp_path):
    with pytest.raises(MangaPanelsError):
        load_config(str(tmp_path / "nope.toml"))


def test_bad_toml_raises(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text("this = = not toml")
    with pytest.raises(MangaPanelsError):
        load_config(str(cfg))


def test_no_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_DISCOVER", [tmp_path / "manga-panels.toml"])
    assert load_config(None) == ({}, {})     # no file -> no defaults


def test_config_accepts_upscale(tmp_path):
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text("[defaults]\nupscale = true\n")
    assert load_config(str(cfg)) == ({"upscale": True}, {})


def test_config_accepts_the_geometry_keys(tmp_path):
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text("[defaults]\nrotate_wide = 1.0\npad_aspect = 0.6\n")
    assert load_config(str(cfg)) == ({"rotate_wide": 1.0, "pad_aspect": 0.6}, {})


def test_reads_device_sections(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nquality = 85\n\n'
                   '[device.x4]\nquality = 80\nmax-width = 480\n')
    defaults, devices = load_config(str(cfg))
    assert defaults == {"quality": 85}
    assert devices == {"x4": {"quality": 80, "max_width": 480}}   # hyphen normalized too


def test_device_unknown_key_warns_with_the_section_name(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[device.x4]\nbogus = 1\n')
    warned = []
    _, devices = load_config(str(cfg), warn=warned.append)
    assert devices == {"x4": {}}
    assert warned and "[device.x4]" in warned[0]   # says WHICH section, not just the key


def test_device_section_cannot_set_device(tmp_path):
    # a profile pointing at another profile does nothing but read like it should
    cfg = tmp_path / "c.toml"
    cfg.write_text('[device.x4]\ndevice = "paperwhite"\n')
    warned = []
    _, devices = load_config(str(cfg), warn=warned.append)
    assert devices == {"x4": {}} and warned


def test_device_entry_that_is_not_a_table_is_ignored(tmp_path):
    # hand-written file: a bad shape must warn, not raise AttributeError
    cfg = tmp_path / "c.toml"
    cfg.write_text('[device]\nx4 = 5\n')
    warned = []
    _, devices = load_config(str(cfg), warn=warned.append)
    assert devices == {} and warned


def test_top_level_device_scalar_is_ignored(tmp_path):
    # the natural typo: `device` is a valid [defaults] key, so people write it
    # at the top of the file, outside any section -> data["device"] is a str,
    # not a table of tables. Must warn, not raise AttributeError, and must not
    # cost the user their [defaults].
    cfg = tmp_path / "c.toml"
    cfg.write_text('device = "x4"\n[defaults]\nquality = 80\n')
    warned = []
    defaults, devices = load_config(str(cfg), warn=warned.append)
    assert devices == {}
    assert warned
    assert defaults == {"quality": 80}


def test_example_toml_documents_every_config_key():
    """The shipped example is the config's documentation, and it silently rotted
    once already (7 flags missing). Both directions are checked: every key it
    mentions must be real, and every real key must be mentioned."""
    import re
    import tomllib
    from pathlib import Path
    from manga_panels.config import _KNOWN

    text = Path("manga-panels.example.toml").read_text(encoding="utf-8")
    tomllib.loads(text)                                  # must stay parseable
    # keys as written, live or commented out: `foo = ...` / `# foo = ...`
    # a key starts with a letter — that skips the `#  1072 = Kindle basic` rows
    # of the screen-width table, which are prose, not keys
    mentioned = set(re.findall(r"^#?\s*([a-z_]\w*)\s*=", text, re.M))
    assert mentioned <= _KNOWN, f"example documents unknown keys: {mentioned - _KNOWN}"
    assert _KNOWN <= mentioned, f"example is missing: {_KNOWN - mentioned}"
