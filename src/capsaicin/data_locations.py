"""Exact, auditable local relocation; never select files by ambiguous basename."""

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def path_key(value):
    return str(value).replace("\\", "/").rstrip("/").casefold()


class DataLocator:
    def __init__(self, config=None):
        self.root = ROOT
        self.config = (
            config
            if config is not None
            else (
                os.environ.get("CAPSAICIN_DATA_LOCATIONS")
                or (
                    ROOT / "config/local.json"
                    if (ROOT / "config/local.json").exists()
                    else ROOT / "config/data_locations.json"
                )
            )
        )
        self.settings = (
            json.loads(Path(self.config).read_text(encoding="utf-8"))
            if Path(self.config).exists()
            else {}
        )
        self.index = None

    def resolve(self, value):
        p = self.local_path(value)
        absolute = p if p.is_absolute() else self.root / p
        if self.settings.get("active"):
            if self.index is None:
                self.index = json.loads(
                    self.local_path(self.settings["path_index"]).read_text(
                        encoding="utf-8"
                    )
                )
            name = next(
                (self.index[k] for k in self.alias_keys(value) if k in self.index), None
            )
            if name:
                target = self.local_path(name)
                if not target.is_file():
                    raise FileNotFoundError(f"Migrated file unavailable: {target}")
                return target
            if path_key(value).startswith("f:/"):
                raise FileNotFoundError(
                    f"External source not in verified D: index: {value}"
                )
        return absolute

    def local_path(self, value):
        """Relocate only explicitly registered repository roots, never basenames."""
        raw = str(value).replace("\\", "/")
        for old in self.settings.get("repository_root_aliases", []):
            prefix = str(old).replace("\\", "/").rstrip("/")
            if raw.casefold() == prefix.casefold() or raw.casefold().startswith(
                prefix.casefold() + "/"
            ):
                suffix = raw[len(prefix) :].lstrip("/")
                if ".." in suffix.split("/"):
                    raise ValueError("Parent traversal in relocated path")
                return self.root / suffix
        if re.match(r"^[A-Za-z]:/", raw) and not Path(raw).is_absolute():
            # External source names may be resolved only by the exact data index.
            return Path(raw)
        return Path(value)

    def alias_keys(self, value):
        p = self.local_path(value)
        absolute = p if p.is_absolute() else self.root / p
        keys = [path_key(value), path_key(absolute)]
        try:
            suffix = absolute.relative_to(self.root).as_posix()
            keys.extend(
                path_key(str(old).rstrip("/\\") + "/" + suffix)
                for old in self.settings.get("repository_root_aliases", [])
            )
        except ValueError:
            pass
        return keys

    def config_path(self, value):
        p = self.local_path(value)
        absolute = p if p.is_absolute() else self.root / p
        overrides = self.settings.get("config_overrides", {})
        target = next(
            (overrides[k] for k in self.alias_keys(value) if k in overrides), absolute
        )
        return self.local_path(target)


_locator = None


def locator():
    global _locator
    if _locator is None:
        _locator = DataLocator()
    return _locator


def resolve_input(value):
    return locator().resolve(value)


def execution_config(value):
    return locator().config_path(value)


def local_path(value):
    return locator().local_path(value)


def relocation_evidence():
    """Files to hash alongside analysis code in future run manifests."""
    loc = locator()
    files = [Path(__file__)]
    if Path(loc.config).is_file():
        files.append(Path(loc.config))
    if loc.settings.get("active"):
        files.append(loc.local_path(loc.settings["path_index"]))
    return files
