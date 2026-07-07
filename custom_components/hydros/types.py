from __future__ import annotations

from typing import Any

BINARY_OUTPUT_TYPES: set[str] = {
    "smartdoser",
    "simpledoser",
    "constant",
    "heater",
    "chiller",
    "returnpump",
    "return_pump",
    "calciumreactor",
    "calcium_reactor",
    "kalkreactor",
    "kalk_reactor",
    "rodifilter",
    "rodi_filter",
    "protein_skimmer",
    "proteinskimmer",
    "ozonegenerator",
    "ozone_generator",
    "feeder",
    "ato",
    "automaticwaterchange",
    "automatic_water_change",
    # Standard outlet / relay types found on Hydros XP8 and similar hardware
    "outlet",
    "relay",
    "switch",
    "plug",
    "smartplug",
    "poweroutlet",
    "power_outlet",
}

BINARY_OUTPUT_FAMILIES: set[str] = {
    "doser",
    "dose",
    "constant",
    "heater",
    "chiller",
    "return",
    "returnpump",
    "filter",
    "skimmer",
    "reactor",
    "feeder",
    "ato",
    "awc",
    # Standard outlet / relay families
    "outlet",
    "relay",
    "switch",
    "plug",
    "power",
}

VARIABLE_PUMP_OUTPUT_TYPES: set[str] = {
    "o10vpump",
}

VARIABLE_PUMP_OUTPUT_FAMILIES: set[str] = {
    "vpump",
}


def is_doser_output(output_meta: dict[str, Any] | None) -> bool:
    if not isinstance(output_meta, dict):
        return False
    type_value = str(output_meta.get("type") or "").strip().lower()
    family_value = str(output_meta.get("family") or "").strip().lower()
    if "doser" in type_value:
        return True
    if family_value in {"dose", "doser"}:
        return True
    return False


def is_binary_output(output_meta: dict[str, Any] | None) -> bool:
    if not isinstance(output_meta, dict):
        return False
    type_value = str(output_meta.get("type") or "").strip().lower()
    family_value = str(output_meta.get("family") or "").strip().lower()

    # Variable pumps are never binary outputs
    if type_value and type_value in VARIABLE_PUMP_OUTPUT_TYPES:
        return False
    if family_value and family_value in VARIABLE_PUMP_OUTPUT_FAMILIES:
        return False

    if type_value and type_value in BINARY_OUTPUT_TYPES:
        return True
    if family_value and family_value in BINARY_OUTPUT_FAMILIES:
        return True
    if "doser" in type_value:
        return True

    # Fallback: any output with a non-empty type or family that isn't a variable
    # pump is assumed to be an on/off controllable output (e.g. unknown outlet
    # types from new Hydros hardware revisions).
    if type_value or family_value:
        return True

    return False


def is_variable_pump_output(output_meta: dict[str, Any] | None) -> bool:
    if not isinstance(output_meta, dict):
        return False
    type_value = str(output_meta.get("type") or "").strip().lower()
    family_value = str(output_meta.get("family") or "").strip().lower()
    if type_value and type_value in VARIABLE_PUMP_OUTPUT_TYPES:
        return True
    if family_value and family_value in VARIABLE_PUMP_OUTPUT_FAMILIES:
        return True
    return False


def coerce_int(value: Any) -> int | None:
    """Coerce a value to int, returning None on failure."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
