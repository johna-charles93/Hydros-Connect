from custom_components.hydros.mode_utils import extract_mode_options


def test_extract_mode_options_from_mode_dict() -> None:
    config = {
        "Mode": {
            "normal": {"friendlyName": "Normal"},
            "feed": {"friendlyName": "Feeding"},
        }
    }

    assert extract_mode_options(config) == ["Normal", "Feeding"]


def test_extract_mode_options_skips_hidden() -> None:
    config = {
        "Mode": {
            "normal": {"friendlyName": "Normal"},
            "secret": {"friendlyName": "Secret", "hidden": True},
        }
    }

    assert extract_mode_options(config) == ["Normal"]


def test_extract_mode_options_dedupes() -> None:
    config = {
        "Mode": {
            "normal": {"friendlyName": "Normal"},
        },
        "Option": {
            "modeOptions": {
                "normal": {"friendlyName": "Normal"},
                "maintenance": {"friendlyName": "Maintenance"},
            }
        },
    }

    assert extract_mode_options(config) == ["Normal", "Maintenance"]
