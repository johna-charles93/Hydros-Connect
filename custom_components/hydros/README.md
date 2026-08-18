# Hydros Connect (Custom Integration)

<img src="logo.png" alt="Hydros DIY" width="300" />

## Summary
Custom Home Assistant integration for Hydros controllers. It connects to the Hydros cloud API to expose inputs, outputs, dosing history, and device health in Home Assistant.

This repository is a community fork based on the original HA-Hydros project by Bitf1ip:
https://github.com/Bitf1ip/ha-hydros

All credit for the original architecture and baseline integration belongs to the original creator.

![Example](dashboard.png)

By default, this integration is monitoring-first. Remote control can be enabled explicitly in integration options.

⚠️ DO NOT rely on this integration's automations for life-critical functions (e.g temperature control, pumps) or when equipment/property damage can occur (e.g flood).

⚠️ This integration require internet to function and integrate with Hydros' cloud. Network issues will cause sensors to become unavailable (and automation to fail).

🛡️Leverage Hydros' own controller features for such functions as they have built-in resiliency for network & power outages and built-in safeguards.

Example of good usage for this integration includes: long term metrics, triggering alerts, automation to non life supporting 3rd party devices (e.g light, smart switch).

## Jump To

- [Quick Start (Alexa Mode Control in ~5 Minutes)](#quick-start-alexa-mode-control-in-5-minutes)
- [Managed in HA Settings (No YAML)](#managed-in-ha-settings-no-yaml)
- [Alexa Voice Control (Mode Changes)](#alexa-voice-control-mode-changes)
- [Visual Routine Builder (No YAML)](#visual-routine-builder-no-yaml)
- [Troubleshooting](#troubleshooting)
- [Sample Scripts File](../../examples/alexa_mode_scripts.yaml)
- [Automation Blueprint](../../blueprints/automation/hydros/hydros_mode_routine.yaml)
- [Rebrand and Repo Ownership](../../REPO_OWNERSHIP_MIGRATION.md)
- [HACS Migration Notice](../../HACS_MIGRATION_NOTICE.md)

## Quick Start (Alexa Mode Control in ~5 Minutes)

1. Enable **Remote control** in Hydros integration options and accept the disclaimer.
2. Copy scripts from `../../examples/alexa_mode_scripts.yaml` into Home Assistant scripts.
3. Replace `select.my_collective_mode` and mode names with your own Hydros values.
4. Expose those scripts to Alexa (Home Assistant Cloud or your Alexa bridge setup).
5. Create Alexa routines (for example: "set reef to feed mode" -> `Hydros Mode Feed`).

If you are adding this to an existing setup, keep critical life-support controls in native Hydros logic.

## Managed in HA Settings (No YAML)

You can now manage user-facing Alexa routine controls directly in:

- Home Assistant -> Settings -> Devices & Services -> Hydros -> Configure

From this options screen, users can:

- Enable/disable Alexa routine scenes.
- Select the target collective.
- Set scene names and mode mappings for Feed, Maintenance, and one Custom scene.
- Configure optional auto-return mode and return delay.

These scene entities are generated automatically and can be exposed to Alexa without editing YAML.

## Attribution

- Original project and maintainer: Bitf1ip, HA-Hydros
- Original repository: https://github.com/Bitf1ip/ha-hydros
- Current maintained repository: https://github.com/johna-charles93/Hydros-Connect
- This fork extends the original integration with controller selection and optional remote control improvements while keeping monitoring-first behavior by default.

## Known Limitations

- Cloud dependency: internet and Hydros cloud API availability are required.
- Output schemas can vary by Hydros model and firmware, so some output types may require additional compatibility updates.
- Remote control is optional and disabled by default; users must explicitly enable it in integration options.
- Home Assistant should not be treated as the primary safety controller for critical aquarium systems.
- Command confirmations depend on cloud and MQTT roundtrip timing; temporary `timed_out` statuses can happen during connectivity degradation.

## Capabilities

- **Config flow**: Username/password login and collective or standalone selection.
- **Capability-map entity modeling**: Output entities are derived from per-output capability flags built from config + live payload behavior.
- **Remote control (optional)**:
  - Collective mode control via a select entity.
  - Binary output control via switch entities.
  - Variable pump speed control via number entities (0-100%).
  - Manual service calls for output state, pump speed, mode changes, and manual dosing.
  - Service actions support `entity_id` selectors (recommended) as well as legacy `thing_id`/`output_key` fields.
  - Entity attributes expose command lifecycle (`pending`, `api_acked`, `confirmed`, `timed_out`, `failed`).
  - Command guardrails: output/mode cooldowns and a max computed manual-dose runtime.
  - Requires enabling **Remote control** in integration options and accepting the disclaimer.
- **Sensors**:
  - Hydros inputs (temp, probe, triple-level, etc.) with units and transforms.
  - Output measurements (power, voltage, current, frequency, reservoir where present).
  - Doser totals (**Dosed Today**) from the Hydros logs API.
  - Collective health (MQTT online/offline) and current mode.
  - Collective diagnostics: API status, MQTT age, and pending command count.
  - Collective alerts summary sensor (aggregates per-sensor alerts).
  - Debug sample sensor (stores latest S3 config + MQTT payload snapshot).
- **Binary sensors**:
  - Binary outputs (e.g., relays/outlets).
  - Rope leak inputs as binary sensors.
- **Periodic refresh**:
  - Entity list refresh every 30 minutes to remove stale entities, while dosing log are pull every 5 minutes.

## Alexa Voice Control (Mode Changes)

This integration can support Alexa-driven mode changes through Home Assistant. This is the recommended approach for multi-user support because each user connects their own Home Assistant instance to their own Alexa account.

### Requirements

- Remote control is enabled in integration options.
- A Hydros mode select entity exists (for example: `select.my_collective_mode`).
- Home Assistant is linked to Alexa (via Home Assistant Cloud or an equivalent Alexa bridge setup).

### Step 1: Create one script per mode

Add scripts in Home Assistant that call the `hydros.change_mode` service.

You can start from the ready-to-copy sample file: `../../examples/alexa_mode_scripts.yaml`

```yaml
script:
  hydros_mode_normal:
    alias: Hydros Mode Normal
    sequence:
      - service: hydros.change_mode
        data:
          entity_id: select.my_collective_mode
          mode: Normal

  hydros_mode_feed:
    alias: Hydros Mode Feed
    sequence:
      - service: hydros.change_mode
        data:
          entity_id: select.my_collective_mode
          mode: Feeding

  hydros_mode_maintenance:
    alias: Hydros Mode Maintenance
    sequence:
      - service: hydros.change_mode
        data:
          entity_id: select.my_collective_mode
          mode: Maintenance
```

Replace `select.my_collective_mode` and mode names with values from your own Hydros setup.

### Step 2: Expose scripts to Alexa

- Expose those scripts/scenes to Alexa.
- In the Alexa app, create routines such as:
  - "set reef to feed mode" -> run `Hydros Mode Feed`
  - "set reef to normal mode" -> run `Hydros Mode Normal`
  - "set reef to maintenance mode" -> run `Hydros Mode Maintenance`

### Safety recommendations

- Keep critical life-support behavior in native Hydros logic.
- Use explicit voice phrases and avoid ambiguous names.
- Consider routine-only access for risky actions.
- Configure mode timeouts in Hydros so systems return to a safe default mode.

### Troubleshooting

- Alexa cannot find Hydros scripts:
  - Confirm scripts are exposed to Alexa.
  - Run Alexa device discovery again.
  - If needed, remove stale duplicates in Alexa and rediscover.

- Routine runs but mode does not change:
  - Verify `entity_id` points to your Hydros mode select entity.
  - Verify mode names match Hydros exactly (case/spelling).
  - Confirm Hydros remote control is enabled in integration options.

- Hydros mode select entity is missing:
  - Remote control may be disabled.
  - Re-enable remote control and reload the integration.

- Voice command works inconsistently or shows delayed updates:
  - Cloud/API/MQTT latency can delay confirmation.
  - Check integration diagnostic sensors (API status, MQTT age, pending commands).
  - Keep cooldowns between repeated voice commands.

### Test Checklist

- In Home Assistant, run `script.hydros_mode_feed` manually from Developer Tools.
- Confirm the Hydros mode select entity changes to your target mode.
- Wait for the configured mode timeout behavior (if set) and verify expected recovery.
- Confirm the script is exposed to Alexa, then run Alexa device discovery.
- Create one routine and test with voice before adding more phrases.
- If command status remains pending/timed_out, check API status and MQTT age sensors.

### Example Alexa Phrases

- "Alexa, set reef to feed mode"
- "Alexa, set reef to maintenance mode"
- "Alexa, set reef to normal mode"
- "Alexa, start reef feed mode"

Use short, distinct phrases and avoid words that sound similar to device names in your home.

## Visual Routine Builder (No YAML)

You can create HYDROS routines in Home Assistant's visual automation editor without editing YAML.

Use the included blueprint:

- `../../blueprints/automation/hydros/hydros_mode_routine.yaml`

What this blueprint does:

- Lets users pick any trigger in the UI (time, button press, sensor state, webhook, etc.).
- Changes HYDROS to a selected start mode.
- Optionally returns to another mode after a delay.

### Import and Use Blueprint

1. In Home Assistant, go to **Settings -> Automations & Scenes -> Blueprints**.
2. Import blueprint from this file:
  - `../../blueprints/automation/hydros/hydros_mode_routine.yaml`
3. Create an automation from that blueprint.
4. Choose trigger(s), HYDROS mode entity, start mode, and optional return settings.
5. Save and run a manual test from the automation UI.

This gives users a drag-and-drop style routine workflow while keeping logic inside Home Assistant.

## Notes
- Credentials are stored in Home Assistant config entries.
- Debug samples are stored in memory (not persisted).
- Manual dose service computes run time from the doser flowRate metadata and toggles the output on, then off.

## ⚠️ Safety Warning & Disclaimer 

Hydros Connect is provided “as is” and “with all faults”, without warranty of any kind, express or implied. The author makes no representations or guarantees regarding safety, suitability, accuracy, reliability, availability, or fitness for any particular purpose.

This software is not designed, tested, or intended for safety-critical, life-supporting, or fail-safe control systems. Do not rely on this integration for life-critical functions (e.g. temperature control, circulation, oxygenation) or for scenarios where equipment failure could result in property damage (e.g. floods, electrical hazards, or fire).

Use of this software is entirely at your own risk. Improper configuration, software defects, network outages, cloud service changes, or unexpected behavior may result in equipment malfunction, property damage, or loss of aquatic life.

Always validate behavior in a controlled or non-critical environment before enabling automations. For critical functions, use Hydros’ native controller features, which are specifically designed with local control, redundancy, and safety safeguards.

In no event shall the author be liable for any direct, indirect, incidental, special, exemplary, or consequential damages arising from the use of, or inability to use, this software.

Nothing in this project constitutes professional, electrical, or safety advice.

This project is an independent, community-driven effort and is not affiliated with, authorized, maintained, or endorsed by CoralVue or Hydros. “Hydros” and “CoralVue” are trademarks of their respective owners and are used for identification purposes only.

## License

Licensed under MIT license
