"""Unit tests for pure helpers in custom_components.hydros.api_hub."""

from __future__ import annotations

import pytest

from custom_components.hydros.api_hub import (
    _OverrideMeta,
    _classify_input,
    _coerce_level,
    _merge_payloads,
    _normalize_output_state,
    _output_states_match,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("off", 0),
        ("On", 1),
        ("AUTO", -1),
        (0, 0),
        (1, 1),
        (-1, -1),
        (7500, 7500),
        ("nonsense", 0),
    ],
)
def test_normalize_output_state(value, expected) -> None:
    assert _normalize_output_state(value) == expected


def test_coerce_level_maps_aliases_and_clamps() -> None:
    om = _OverrideMeta(key="k", name="Pump", otype="level", minimum=0, maximum=10000)
    assert _coerce_level("on", om) == 10000
    assert _coerce_level("off", om) == 0
    assert _coerce_level(50000, om) == 10000
    assert _coerce_level(2500, om) == 2500

    reversible = _OverrideMeta(key="k", name="Gyre", otype="level", minimum=-10000, maximum=10000)
    assert _coerce_level(-4000, reversible) == -4000


@pytest.mark.parametrize(
    ("expected", "observed", "match"),
    [
        (1, 10000, True),
        (1, 0, False),
        (0, 0, True),
        (0, 10000, False),
        (-1, 4200, True),  # returned to auto — any scheduled value is fine
        (7500, 7501, True),
        (7500, 9000, False),
    ],
)
def test_output_states_match(expected, observed, match) -> None:
    assert _output_states_match(expected, observed) is match


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [
        ("Temperature 1", {"senseValue": 25.8}, {"senseMode": "temp"}),
        ("pH", {"probeValue": 8.1, "probeRawValue": -300}, {"type": "probe", "probeMode": 1}),
        ("ORP", {"probeValue": 200}, {"type": "probe", "probeMode": 2}),
        ("Alky Alkalinity", {"value": 7.2}, {"type": "probe", "probeMode": 3}),
        ("Salinity", {"probeValue": 35}, {"senseMode": "salinity"}),
        ("ATO Level", {"senseValue": 1}, {"senseMode": "triplelevel"}),
        ("Widget", {"value": 3}, {}),
    ],
)
def test_classify_input(name, payload, expected) -> None:
    assert _classify_input(name, payload) == expected


def test_merge_payloads_deep_merges_and_clears_stale_alerts() -> None:
    base = {
        "Output": {"Return": {"valueState": 0, "alert": "old"}},
        "mode": "Normal",
    }
    incoming = {"Output": {"Return": {"valueState": 7500}}, "mode": "Feeding"}

    merged = _merge_payloads(base, incoming)

    assert merged["mode"] == "Feeding"
    assert merged["Output"]["Return"]["valueState"] == 7500
    # alert was present in base, absent in incoming -> dropped
    assert "alert" not in merged["Output"]["Return"]
