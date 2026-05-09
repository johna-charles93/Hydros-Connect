# Changelog

All notable changes to this project are documented in this file.

## 0.3.1 - 2026-05-08

### Added
- Support for Skimmer outputs on variable pumps (`type: o10vPump`, `family: vPump`).

### Fixed
- Normalize variable-pump `valueState` as a percentage by dividing by 100 (for example: `4500` -> `45.0%`).
- Prevent variable-pump `valueState` from being interpreted as binary on/off labels.

## 0.3.0 - 2026-04-06

### Fixed
- Add support for changing Hydros' mode. This requires to enable remote control under the integration's configuration (and to accept the risks).

## 0.2.0 - 2026-01-30

### Added
- Initial public custom integration release with config flow, sensors, and MQTT-backed status updates.
