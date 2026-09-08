# Hydros Connect (Custom Integration)

<img src="logo.png" alt="Hydros Connect" width="240" />

Home Assistant integration for CoralVue **HYDROS** aquarium controllers —
inputs, outputs, dosing, device health, mode/output control, and Alexa routine
scenes.

**The full documentation lives in the repository root README:**
👉 https://github.com/johna-charles93/Hydros-Connect#readme

It covers:

- **Setup — choosing an authentication method**
  ([Official HYDROS API](https://github.com/johna-charles93/Hydros-Connect#setup-choose-an-authentication-method)
  vs the deprecated account login)
- Alexa mode control (scripts and no-YAML scene setup)
- Alexa stats queries
- The visual routine blueprint
- Troubleshooting (including scene "unknown" state and Alexa discovery)

Other docs:

- [Release notes](../../RELEASE_NOTES.md) · [Changelog](../../CHANGELOG.md)
- [Official API migration plan](../../API_KEY_MIGRATION_PLAN.md)
- [HACS migration notice](../../HACS_MIGRATION_NOTICE.md)
- Issues / support: https://github.com/johna-charles93/Hydros-Connect/issues

---

## ⚠️ Safety

Do **not** rely on this integration for life-critical functions (temperature,
circulation, oxygenation) or anything where a failure could cause property
damage (floods, electrical hazards). It depends on the internet and a cloud
service; outages make entities unavailable and automations fail.

Keep critical control in the HYDROS controller's native logic, which has local
control, redundancy, and safeguards this integration cannot replicate. Set
timeouts on your HYDROS modes so a missed command self-corrects.

Provided "as is", without warranty. Not affiliated with, authorized, or
endorsed by CoralVue. "HYDROS" and "CoralVue" are trademarks of their
respective owners. Licensed under MIT.
