# Release notes

Paste the relevant section into the GitHub Release body when tagging.

---

## v0.6.0 — Official HYDROS API support (2026-09-08)

Hydros Connect now works with CoralVue's **official HYDROS Public API**, alongside
the existing account-login path. This lines up with CoralVue's API launch and the
firmware rollout on 8 September 2026.

### Highlights

- **Two ways to connect.** When you add the integration you pick an
  authentication method:
  - **Official HYDROS API (recommended)** — a *provider key* (you request your
    own from CoralVue) plus a *device key* (you create in the HYDROS app, per
    device, read-only or read/write).
  - **HYDROS account login (deprecated)** — the original email/password path.
    Still works, but expected to stop functioning as devices move to the
    official API. Existing setups are untouched.
- **Nothing secret ships in this repo.** Each user brings their own keys, so no
  one integration's rate-limit budget is shared across everybody.
- **Full feature parity on the API path:** input/output sensors, binary sensors,
  mode select, output on/off/auto, variable-pump speed, manual dosing (now via
  the controller's native `dose` command), command delivery confirmation, the
  Alexa routine scenes, and the Validate Setup button.
- **Reauth flow** if the stored keys are ever rejected.

### Known limitations on the API path

- The Public API has **no dosing-log endpoint**, so the per-doser **"Dosed
  Today"** sensors are not created when connected via the API. (The legacy path
  keeps them.)
- **Poll-only** — state refreshes about every 30 seconds; there's no real-time
  push. Entities go unavailable on the normal staleness window if the device
  goes offline or polling stops.
- Input sensor **units / device classes are inferred from the input name** and
  the fields it reports, because the API state document doesn't include
  `senseMode` / `probeMode`. Rope-leak inputs aren't detected on this path.
- One **device key = one device**, so multi-controller setups add the
  integration once per device.

### How to move to the API path

1. Update Hydros Connect to v0.6.0 in HACS and restart Home Assistant.
2. Request your own **provider key** at
   <https://www.coralvuehydros.com/api/#request-provider-key> (choose the
   *unlisted* option for personal use).
3. In the **HYDROS app**, create a **device key** for each controller
   (Read & write for control, Read only for monitoring).
4. **Settings → Devices & Services → Add Integration → Hydros**, choose
   **Official HYDROS API**, and paste both keys. Repeat per device.
5. Your existing account-login entry can stay as-is or be removed once the API
   entry is verified.

Full setup details are in the [README](README.md); design notes and open
questions are in [API_KEY_MIGRATION_PLAN.md](API_KEY_MIGRATION_PLAN.md).

### Upgrade notes

- Existing account-login (legacy) config entries continue to work with no
  changes.
- `manifest.json` version is `0.6.0`; integration domain is unchanged (`hydros`).
