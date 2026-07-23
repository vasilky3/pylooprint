"""Parsing of the Bambu/Orca ``CONFIG_BLOCK`` embedded in every plate G-code.

This is a *common* modification step: every supported printer stores its slicer
settings the same way, as ``; name = value`` comment lines between
``; CONFIG_BLOCK_START`` and ``; CONFIG_BLOCK_END``.
"""

from __future__ import annotations

import re
from typing import Mapping, Sequence, Union

ConfigValue = Union[str, list]
ConfigMap = Mapping[str, ConfigValue]

_ENTRY_RE = re.compile(r"^;\s*([a-zA-Z_][a-zA-Z0-9_]*)(?:\[(\d+)\])?\s*=\s*(.+)$")


def parse_config_block(config_text: str) -> dict[str, ConfigValue]:
    """Turn a ``CONFIG_BLOCK`` into a name -> value / list-of-values map."""
    config: dict[str, ConfigValue] = {}
    if not config_text:
        return config

    for line in config_text.split("\n"):
        match = _ENTRY_RE.match(line)
        if not match:
            continue
        name, array_index, value = match.group(1), match.group(2), match.group(3).strip()

        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        is_list = "," in value and '"' not in value and "'" not in value
        items = [v.strip() for v in value.split(",") if v.strip()] if is_list else []

        if array_index is not None:
            _set_indexed(config, name, int(array_index), value)
        elif len(items) > 1:
            config[name] = items
        else:
            config[name] = value

    return config


def _set_indexed(config: dict[str, ConfigValue], name: str, index: int, value: str) -> None:
    slot = config.get(name)
    if not isinstance(slot, list):
        slot = []
        config[name] = slot
    while len(slot) <= index:
        slot.append("")
    slot[index] = value


def config_value(
    config: ConfigMap,
    name: str,
    index: int | str | None = None,
    initial_extruder: str = "0",
) -> str | None:
    """Read one value, resolving per-extruder lists the way the slicer does."""
    value = config.get(name)
    if not value:
        return None
    if isinstance(value, list):
        idx = int(index) if index is not None else int(initial_extruder or "0")
        picked = value[idx] if 0 <= idx < len(value) else ""
        if not picked:
            picked = value[0] if value else ""
        return picked or None
    return value


def config_list(config: ConfigMap, name: str) -> Sequence[str] | None:
    """Read a value only when it really is a list."""
    value = config.get(name)
    return value if isinstance(value, list) else None
