from __future__ import annotations

from typing import Any


def _iter_mode_items(source: Any) -> list[tuple[Any, Any]]:
    if isinstance(source, dict):
        return list(source.items())
    if isinstance(source, list):
        return [(idx, item) for idx, item in enumerate(source)]
    return []


def extract_mode_options(config: dict[str, Any] | None) -> list[str]:
    """Extract user-facing mode labels from a Hydros config payload."""
    if not isinstance(config, dict):
        return []

    options: list[str] = []

    mode_sources: list[Any] = []
    for key in ("Mode", "mode", "Modes", "modes"):
        if key in config:
            mode_sources.append(config.get(key))

    option_block = config.get("Option")
    if isinstance(option_block, dict):
        for key, value in option_block.items():
            if "mode" not in str(key).lower():
                continue
            if isinstance(value, (dict, list)):
                mode_sources.append(value)

    for mode_source in mode_sources:
        for mode_key, mode_meta in _iter_mode_items(mode_source):
            mode_id = str(mode_key).strip()
            if not mode_id and not isinstance(mode_meta, dict):
                continue

            if isinstance(mode_meta, dict):
                if bool(mode_meta.get("invisible") or mode_meta.get("hidden")):
                    continue
                mode_id = str(
                    mode_meta.get("mode")
                    or mode_meta.get("id")
                    or mode_meta.get("modeId")
                    or mode_meta.get("modeID")
                    or mode_meta.get("value")
                    or mode_meta.get("key")
                    or mode_id
                ).strip() or str(mode_key).strip()
                option = (
                    str(
                        mode_meta.get("friendlyName")
                        or mode_meta.get("name")
                        or mode_meta.get("label")
                        or mode_meta.get("modeName")
                        or mode_meta.get("title")
                        or mode_meta.get("text")
                        or mode_id
                    )
                    .strip()
                    or mode_id
                )
            else:
                option = str(mode_meta).strip() or mode_id

            if not option:
                continue
            if option not in options:
                options.append(option)

    return options
