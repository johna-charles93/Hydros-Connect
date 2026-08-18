# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Added
- Rebrand integration naming and metadata to Hydros Connect and update documentation/support URLs to the new repository.
- Add documentation for Home Assistant + Alexa mode-control setup using `hydros.change_mode` scripts, including multi-user guidance and safety recommendations.
- Add `examples/alexa_mode_scripts.yaml` with ready-to-copy Home Assistant scripts for mode voice control.
- Add a 5-minute Quick Start and Alexa troubleshooting section to both README files.
- Add README jump links plus test checklist and example Alexa phrases for faster onboarding.
- Add HYDROS visual routine automation blueprint for no-YAML mode workflows.
- Add integration Options UI controls for Alexa routine scenes (Feed, Maintenance, Custom) with optional auto-return behavior.
- Add Home Assistant scene entities generated from integration options for easier Alexa exposure.
- Add easy-setup defaults and dynamic mode dropdowns in integration options when mode data is available.
- Add a `Validate Setup` button entity that generates a persistent notification health report for common setup issues.
- Make Alexa scene auto-return scheduling restart-safe by persisting pending returns and restoring timers after Home Assistant restart.
- Add repository rebrand/ownership migration checklist documentation.
- Clarify Alexa voice-control prerequisites in documentation (Nabu Casa or self-hosted Alexa Smart Home setup).
- Add explicit Nabu Casa entity-exposure guidance and recommend exposing Hydros routine scenes for simpler Alexa setup.
- Add GitHub issue templates for bug reports and feature requests, including setup-validation diagnostics prompts.

## 0.4.0 - 2026-07-28

### Added
- Add on/off/auto select entities for binary outputs that support auto mode, providing full three-state control alongside mode-based control.

### Fixed
- Fix switch turn_off command failing due to sending string "off" instead of numeric value 0 to pyhydros library.
- Skip creating binary switch entities for outputs that have auto mode support (now only select entities are created for those).
- Fix auto mode detection in select entities: now properly detects AUTO capability via config metadata (onTemp, offTemp, fallback, outputDevice) and determines current state via override flag (false = auto, true = manual on/off).

## 0.3.9 - 2026-07-07

### Fixed
- Normalize variable-pump number entities back to a true 0-100% display range in Home Assistant controls and history.
- Rename numeric-only Hydros outputs to `Outlet N` so XP8-style numbered outlets are clearer in cards, controls, and activity logs.

## 0.3.8 - 2026-07-07

### Changed
- Upgrade service UX to support `entity_id` targeting for mode/output/doser actions while preserving `thing_id` and `output_key` backward compatibility.
- Add Hydros entity selectors in `services.yaml` for safer, easier service calls from Home Assistant UI.

## 0.3.7 - 2026-07-07

### Changed
- Replace output entity classification with capability-map driven logic that combines config metadata and live payload behavior.
- Update switch, number, binary sensor, and output sensor creation to use explicit per-output capability flags (`supports_binary_control`, `supports_percent_control`, `is_doser`) instead of direct type/family checks.

## 0.3.6 - 2026-07-07

### Added
- Add control command lifecycle tracking in `HydrosHub` and expose command status (`pending`, `api_acked`, `confirmed`, `timed_out`, `failed`) in mode, switch, and pump entity attributes.
- Add collective diagnostic sensors for API status, MQTT age, and pending command count.

### Changed
- Add control safety guardrails: output command cooldown, mode-change cooldown, and maximum computed manual-dose duration.
- Expand README documentation with diagnostics behavior and control safety notes.

## 0.3.5 - 2026-07-07

### Added
- Add explicit attribution to the original HA-Hydros project and maintainer in both top-level and integration README files.
- Add a dedicated Known Limitations section covering cloud dependency, output schema variability, and remote-control opt-in behavior.

### Fixed
- Improve binary output detection so common outlet/relay output types are exposed as switch entities when remote control is enabled.
- Correct variable-pump number entity value scaling to use the expected 0-100 range.

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
