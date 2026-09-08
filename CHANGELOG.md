# Changelog

All notable changes to this project are documented in this file.

## Unreleased

## 0.6.2 - 2026-09-08

### Changed
- API config flow: the setup form now shows the underlying error detail (HTTP status / message) instead of only "Unable to reach the Hydros service", and distinguishes a server-side error (HTTP 5xx — often an inactive provider key) from a real connectivity failure.
- API client: `GET` requests retry once on a transient gateway failure (HTTP 502/503/504 or a dropped connection); writes are never retried automatically.

## 0.6.1 - 2026-09-08

### Fixed
- **HACS "add repository" failed for everyone** with `trailing comma is not allowed: line 11` — the `manifest.json` shipped in the v0.5.6 release was invalid JSON and no newer release existed. v0.6.x ships a valid manifest, and CI now validates every JSON file on each push, tags included. (#5)
- **Alexa routine scenes stuck in "unknown" state and not activatable.** The scene `unique_id` was derived from the editable display name, so renaming a scene in options orphaned the old entity (which then sat unavailable while Alexa still targeted it). Scene ids are now keyed on the config entry, target device, and preset slot only; renames keep the same entity and `entity_id`. Orphaned scene entities from older versions are removed automatically on startup and the original `scene.<name>` id is reclaimed. (#3)
- pH probe/`ph` sensors no longer set a `pH` unit, which is invalid for the `ph` device class and logged a warning for every probe.

## 0.6.0 - 2026-09-08

### Added
- Add support for the official CoralVue HYDROS Public API (`https://api.coralvuehydros.com`) as a second, recommended authentication path. Setup now starts with a menu: **Official HYDROS API** (provider key + device key) or **HYDROS account login** (the existing, now-deprecated email/password path).
- API path: per-device config entries keyed on the device key, REST polling every ~30s via a renewing session token, output/mode control through the overrides + command endpoints, first-class manual dosing via the `dose` command, read-only vs read/write key detection, and reauth support.
- Rebrand integration naming and metadata to Hydros Connect and update documentation/support URLs to the new repository.

### Changed
- Entity platforms now accept either hub implementation via a shared `HydrosHubBase`; the legacy account-credential path is unchanged.

### Known limitations (API path)
- No dosing-log endpoint in the Public API, so the per-doser "Dosed Today" sensors are not created when connected via the official API.
- The Public API is poll-only (no MQTT push); expect ~30s latency and standard staleness-window unavailability when polling stops or the device goes offline.
- Sensor typing (units / device class) for inputs is inferred from the input name and reported fields, since the API state document carries no `senseMode`/`probeMode`.
- Document a proven Alexa setup path using unique Hydros scene names plus Alexa routines for natural phrases like "set reef to feed mode".
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
- Add Alexa stats query guidance (sensor naming, exposure, and test phrases) to setup documentation.

### Changed
- Allow Alexa scene mode fields in integration options to be left blank so users can disable individual scenes without removing the whole feature.
- Expand `Validate Setup` report with Alexa stats readiness checks for common sensor types (temperature, pH, salinity, ORP), including unavailable-sensor warnings.

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
- Add a dedicated Known Limitations section covering cloud dependency, output schema variability, and remote-control opt-in behavior.
- Improve documentation and attribution clarity.

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
