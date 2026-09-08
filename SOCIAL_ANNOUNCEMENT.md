# Shareable announcement — Hydros Connect v0.6.0

## Short version (Facebook / groups)

🐠 **Hydros Connect for Home Assistant — v0.6.0 is out, with official HYDROS API support.**

You can now connect your HYDROS controller to Home Assistant using CoralVue's
official Public API instead of your account password. When you add the
integration you pick **Official HYDROS API (recommended)** or the old **account
login**.

To use the API path:
1. Request your own provider key from CoralVue: coralvuehydros.com/api (pick the "unlisted" option).
2. Create a device key for each controller in the HYDROS app (read-only or read/write).
3. Add the integration in Home Assistant and paste both keys.

Existing setups keep working — no rush to switch. Free and open source, install
via HACS.

Repo: https://github.com/johna-charles93/Hydros-Connect
Questions/issues: https://github.com/johna-charles93/Hydros-Connect/issues

⚠️ As always: don't rely on this for life-support functions. Keep critical
control in HYDROS' native logic.

---

## Forum version (a bit longer)

**Hydros Connect v0.6.0 — official HYDROS API support**

Hydros Connect is a community Home Assistant integration for HYDROS aquarium
controllers (sensors, outputs, dosing, mode control, Alexa routine scenes).

v0.6.0 adds support for CoralVue's **official HYDROS Public API**, alongside the
existing account-login method. Setup now starts with a menu:

- **Official HYDROS API (recommended)** — you supply a *provider key* (request
  your own, unlisted, from CoralVue at coralvuehydros.com/api) and a *device key*
  you create per controller in the HYDROS app, choosing read-only or read/write.
  Nothing secret is bundled in the integration, so your rate-limit budget is
  yours alone.
- **HYDROS account login (deprecated)** — the original email/password path. Still
  works; expected to wind down as devices move to the official API. Existing
  installs are untouched.

Notes on the API path:
- State polls about every 30 seconds (no realtime push).
- One device key = one device; add the integration once per controller.
- The "Dosed Today" doser sensors aren't available (the API has no dosing-log
  endpoint). Manual dosing uses the controller's native dose command.

Install/update via HACS. Full notes: see RELEASE_NOTES.md and the README in the
repo.

Repo: https://github.com/johna-charles93/Hydros-Connect

Not affiliated with or endorsed by CoralVue. Don't use it for life-critical
control — keep that in the HYDROS controller.
