import pytest
from manga_panels.config import load_config
from manga_panels.errors import MangaPanelsError
import manga_panels.config as config


def test_reads_defaults(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nquality = 80\nmax_width = 1264\n')
    assert load_config(str(cfg)) == {"quality": 80, "max_width": 1264}


def test_unknown_key_ignored_with_warning(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nformat = "png"\nbogus = 1\n')
    warned = []
    assert load_config(str(cfg), warn=warned.append) == {"format": "png"}
    assert warned                      # warned about the unknown key


def test_hyphen_key_normalized(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nkeep-first = 2\n')
    assert load_config(str(cfg)) == {"keep_first": 2}


def test_library_and_suffix_keys_accepted(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nlibrary = "/data/manga"\nsuffix = "_cut"\n')
    assert load_config(str(cfg)) == {"library": "/data/manga", "suffix": "_cut"}


def test_split_ratio_key_accepted(tmp_path):
    cfg = tmp_path / "c.toml"
    cfg.write_text('[defaults]\nsplit-ratio = 1.0\n')
    assert load_config(str(cfg)) == {"split_ratio": 1.0}


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
    assert load_config(None) == {}     # no file -> no defaults


def test_config_accepts_upscale(tmp_path):
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text("[defaults]\nupscale = true\n")
    assert load_config(str(cfg)) == {"upscale": True}


def test_config_accepts_the_geometry_keys(tmp_path):
    cfg = tmp_path / "manga-panels.toml"
    cfg.write_text("[defaults]\nrotate_wide = 1.0\npad_aspect = 0.6\n")
    assert load_config(str(cfg)) == {"rotate_wide": 1.0, "pad_aspect": 0.6}
