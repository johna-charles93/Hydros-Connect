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

PERCENT_HINT_WORDS: tuple[str, ...] = (
    "pump",
    "vortech",
    "wave",
    "flow",
    "speed",
    "0-10v",
    "o10v",
)


def _as_normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def _coerce_numeric(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_output_capabilities(
    output_meta: dict[str, Any] | None,
    output_payload: dict[str, Any] | None = None,
) -> dict[str, bool]:
    """Build a capability map for a Hydros output.

    The goal is to classify outputs from explicit config/payload behavior first,
    with type/family only as fallback hints for older payloads.
    """
    if not isinstance(output_meta, dict):
        output_meta = {}
    if not isinstance(output_payload, dict):
        output_payload = {}

    type_value = _as_normalized_text(output_meta.get("type"))
    family_value = _as_normalized_text(output_meta.get("family"))
    name_value = _as_normalized_text(output_meta.get("friendlyName") or output_meta.get("name"))

    payload_state = output_payload.get("valueState", output_payload.get("state"))
    payload_state_num = _coerce_numeric(payload_state)

    is_doser = False
    if "doser" in type_value or family_value in {"dose", "doser"}:
        is_doser = True

    supports_percent_control = False
    if type_value in VARIABLE_PUMP_OUTPUT_TYPES or family_value in VARIABLE_PUMP_OUTPUT_FAMILIES:
        supports_percent_control = True
    elif payload_state_num is not None and payload_state_num > 100:
        # Typical Hydros variable output states are sent as 0-10000 for 0-100%.
        supports_percent_control = True
    elif any(hint in type_value or hint in family_value or hint in name_value for hint in PERCENT_HINT_WORDS):
        # Fallback for configs that omit explicit variable-pump typing.
        supports_percent_control = True

    supports_binary_control = False
    if not supports_percent_control:
        if payload_state_num in {-1.0, 0.0, 1.0}:
            supports_binary_control = True
        elif payload_state_num is not None and payload_state_num >= 0 and payload_state_num <= 1:
            supports_binary_control = True
        elif isinstance(payload_state, str) and _as_normalized_text(payload_state) in {"on", "off", "auto"}:
            supports_binary_control = True
        elif any(key in output_meta for key in ("onTemp", "offTemp", "fallback", "outputDevice")):
            supports_binary_control = True
        elif type_value in BINARY_OUTPUT_TYPES or family_value in BINARY_OUTPUT_FAMILIES:
            supports_binary_control = True

    has_power_metrics = any(
        key in output_meta or key in output_payload
        for key in ("minPower", "maxPower", "powerAlertLevel", "powerI", "current", "voltageI", "frequency")
    )
    has_reservoir = "reservoir" in output_meta or "reservoir" in output_payload

    return {
        "is_doser": is_doser,
        "supports_binary_control": supports_binary_control,
        "supports_percent_control": supports_percent_control,
        "has_power_metrics": has_power_metrics,
        "has_reservoir": has_reservoir,
    }


def is_doser_output(output_meta: dict[str, Any] | None) -> bool:
    return bool(get_output_capabilities(output_meta).get("is_doser"))


def is_binary_output(output_meta: dict[str, Any] | None) -> bool:
    return bool(get_output_capabilities(output_meta).get("supports_binary_control"))


def is_variable_pump_output(output_meta: dict[str, Any] | None) -> bool:
    return bool(get_output_capabilities(output_meta).get("supports_percent_control"))


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
