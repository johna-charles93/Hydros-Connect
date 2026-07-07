# HA-Hydros (Custom Integration)

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

## Attribution

- Original project and maintainer: Bitf1ip, HA-Hydros
- Original repository: https://github.com/Bitf1ip/ha-hydros
- This fork extends the original integration with controller selection and optional remote control improvements while keeping monitoring-first behavior by default.

## Known Limitations

- Cloud dependency: internet and Hydros cloud API availability are required.
- Output schemas can vary by Hydros model and firmware, so some output types may require additional compatibility updates.
- Remote control is optional and disabled by default; users must explicitly enable it in integration options.
- Home Assistant should not be treated as the primary safety controller for critical aquarium systems.
- Command confirmations depend on cloud and MQTT roundtrip timing; temporary `timed_out` statuses can happen during connectivity degradation.

## Capabilities

- **Config flow**: Username/password login and collective or standalone selection.
- **Remote control (optional)**:
  - Collective mode control via a select entity.
  - Binary output control via switch entities.
  - Variable pump speed control via number entities (0-100%).
  - Manual service calls for output state, pump speed, mode changes, and manual dosing.
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

## Notes
- Credentials are stored in Home Assistant config entries.
- Debug samples are stored in memory (not persisted).
- Manual dose service computes run time from the doser flowRate metadata and toggles the output on, then off.

## ⚠️ Safety Warning & Disclaimer 

HA-Hydros is provided “as is” and “with all faults”, without warranty of any kind, express or implied. The author makes no representations or guarantees regarding safety, suitability, accuracy, reliability, availability, or fitness for any particular purpose.

This software is not designed, tested, or intended for safety-critical, life-supporting, or fail-safe control systems. Do not rely on this integration for life-critical functions (e.g. temperature control, circulation, oxygenation) or for scenarios where equipment failure could result in property damage (e.g. floods, electrical hazards, or fire).

Use of this software is entirely at your own risk. Improper configuration, software defects, network outages, cloud service changes, or unexpected behavior may result in equipment malfunction, property damage, or loss of aquatic life.

Always validate behavior in a controlled or non-critical environment before enabling automations. For critical functions, use Hydros’ native controller features, which are specifically designed with local control, redundancy, and safety safeguards.

In no event shall the author be liable for any direct, indirect, incidental, special, exemplary, or consequential damages arising from the use of, or inability to use, this software.

Nothing in this project constitutes professional, electrical, or safety advice.

This project is an independent, community-driven effort and is not affiliated with, authorized, maintained, or endorsed by CoralVue or Hydros. “Hydros” and “CoralVue” are trademarks of their respective owners and are used for identification purposes only.

## License

Licensed under MIT license
