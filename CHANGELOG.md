# Changelog

All notable changes to this project are documented in this file.

## 0.3.4 - 2026-05-24

### Added
- Add a new `XP8 Total Power` sensor sourced from MQTT health payloads (`health.*.acPower.powerI`), scaled by the existing `powerI` factor (`/10`) to report watts.

## 0.3.3 - 2026-05-22

### Added
- Support for HACS!

### Fixed
- Fix crash during mode-change failure recovery: `select.py` called `async_force_status_from_api` and `invalidate_collective_config` on `HydrosHub`, but neither method existed. When a mode change failed, the recovery path raised `AttributeError` before the original API error could be logged. Both methods are now implemented: `invalidate_collective_config` drops the stale cached config so the next read re-fetches from the cloud; `async_force_status_from_api` pulls authoritative status from the REST API, merges it into the status cache, and dispatches the per-thing signal so dependent entities refresh. (Ported from [JLay2026/ha-hydros@4d98d25](https://github.com/JLay2026/ha-hydros/commit/4d98d254f6ef6a1a30338f8984aef87f68475858) — credit to [@JLay2026](https://github.com/JLay2026).)

## 0.3.2 - 2026-05-08

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
