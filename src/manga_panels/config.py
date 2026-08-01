"""Load defaults from a manga-panels.toml ([defaults] plus [device.<name>] tables).
The CLI wins."""
from __future__ import annotations

import tomllib
from pathlib import Path

from manga_panels.errors import MangaPanelsError

# accepted keys = argparse dests
_KNOWN = {"output", "library", "format", "quality", "max_width", "device",
          "grayscale", "gamma", "preview", "debug", "page", "keep_first",
          "cover", "cover_crop", "cover_side", "split_ratio", "upscale",
          "rotate_wide", "pad_aspect", "suffix", "overwrite"}

_DISCOVER = [
    Path("manga-panels.toml"),
    Path.home() / ".config" / "manga-panels" / "config.toml",
]


def _section(table: dict, label: str, known: set[str], warn) -> dict:
    """One TOML table -> argparse dests, dropping what we don't know with a warning.
    `label` names the section in that warning, so a typo in [device.x4] doesn't read
    like a typo in [defaults]."""
    out: dict = {}
    for k, v in table.items():
        key = k.replace("-", "_")
        if key in known:
            out[key] = v
        else:
            warn(f"config: unknown key ignored: {label}{k}")
    return out


def load_config(explicit_path: str | None = None, *, warn=print) -> tuple[dict, dict]:
    """Returns ([defaults], {device_name: {dest: value}}) from one read of the file."""
    if explicit_path is not None:
        path = Path(explicit_path)
        if not path.exists():
            raise MangaPanelsError(f"config not found: {explicit_path}")
    else:
        path = next((p for p in _DISCOVER if p.exists()), None)
        if path is None:
            return {}, {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, OSError) as e:
        raise MangaPanelsError(f"invalid config ({path}): {e}") from e
    defaults = _section(data.get("defaults", {}), "", _KNOWN, warn)
    devices: dict = {}
    for name, table in data.get("device", {}).items():
        if not isinstance(table, dict):
            warn(f"config: [device.{name}] is not a table, ignored")
            continue
        # a device section setting `device` would only point at another profile
        devices[name] = _section(table, f"[device.{name}] ", _KNOWN - {"device"}, warn)
    return defaults, devices
