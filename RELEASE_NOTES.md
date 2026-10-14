# Release notes

Paste the relevant section into the GitHub Release body when tagging.

---

## v0.6.7 — "Invalid thing name" resolved by CoralVue (2026-10-14)

CoralVue has fixed the backend bug behind
`500: Internal server error: Invalid thing name specified in request` on
`POST /device/state/session` (it hit collectives whose internal id contains a
space). Nothing in the integration had to change — the request was
spec-correct and the error reproduced with plain `curl`.

- **If you were affected:** update, then reload the Hydros Connect entry (or
  just wait — the poll loop retries session-start every ~15 minutes).
  Live data, temperature, pH, leak, and per-outlet power sensors come back
  once the session starts.
- **Dashboards:** some sensors are created fresh after recovery. If a card
  still shows `--` or `unavailable`, point it at the new entity
  (e.g. `…_ph` instead of `…_octo_4_right_ph_2`) and delete the orphaned one.

Thanks to everyone who added logs and curl repros to #6.

---

## v0.6.6 — Fix Configure-flow 500 and a setup-time backoff bypass (2026-09-19)

Two fixes, both surfaced by running with a live API session for a while:

- **Configure (options flow) 500 error.** Once the integration had real
  scene/mode names to show (Feeding, Normal, Water Change, etc.), opening
  **Configure** on the entry failed with `Config flow could not be loaded:
  500 Internal Server Error`. The scene-mode dropdowns used a schema
  (`vol.Any("", vol.In(...))`) that Home Assistant's frontend-schema
  converter can't handle. Replaced with a plain `vol.In(...)` selector that
  includes an explicit "(none)" choice — Configure loads normally again.
- **Session-start backoff bypass at setup.** 0.6.5 added a 15–60 minute
  backoff after a failed `POST /device/state/session` (capped at 5/hour by
  CoralVue). The regular poll loop respected it, but `async_setup()` did
  not — a config entry reload or HA restart during the backoff window could
  still fire a session-start request and erode the budget. Setup now checks
  the same gate and skips the session-start step if it's still inside the
  window, letting the poll loop pick it up once it clears.

No config changes needed — just update and restart.

---

## v0.6.5 — Fix session-start retry storm (2026-09-08)

If setup couldn't open a state session, the poll loop kept asking for a new one
every ~30 seconds — but `POST /device/state/session` is capped at **5 per hour
per device**, so it just kept getting `429` forever.

Now: after a failed session start the integration waits at least **15 minutes**
before trying again (doubling to a 60-minute ceiling on repeated rate-limit
responses), and skips the poll entirely — no HTTP call — while it's waiting.
Override-metadata fetches get a 5-minute retry floor on failure too.

If your entry hit this: update to v0.6.5, then **wait ~1 hour** for the session
budget to refill before re-enabling / reloading it, so the first attempt lands
clean.

---

## v0.6.4 — Degrade instead of stall; log API errors (2026-09-08)

For the API path, when `GET /device` works but a later setup call fails:

- the config entry **loads anyway** (entities unavailable) and retries in the
  background, instead of sitting on "Failed setup, will retry" with no detail;
- every API call is logged at debug, and any error response is logged at
  **warning** with the HTTP status and response body.

If you see `Invalid thing name specified in request` (or any other API error)
during setup: the warning log now names the exact endpoint and status. That
message came from CoralVue's backend and was fixed upstream on 2026-10-14 (see
v0.6.7 above and [issue #6](https://github.com/johna-charles93/Hydros-Connect/issues/6)).

---

## v0.6.3 — Tolerant /device parsing (2026-09-08)

Fixes API setup failing with **"Unexpected /device payload"** even though the
request reached CoralVue and came back.

- `GET /api/v1/device` is now parsed leniently: bare object, single-element
  list, `{"device": …}` / `{"devices": […]}` wrappers, and double-encoded JSON
  string bodies all work. The device id is read from any of `deviceId`,
  `device_id`, `id`, `mac`, `macAddress`, `thingName`.
- The same unwrapping applies to the state / overrides / override-metadata
  responses.
- If a payload still isn't recognised, its shape is logged and shown in the
  setup form — please attach that to a report on
  [issue #6](https://github.com/johna-charles93/Hydros-Connect/issues/6).

---

## v0.6.2 — API setup diagnostics (2026-09-08)

- The **Official HYDROS API** setup form now shows the real error (HTTP status /
  message) instead of a bare "Unable to reach the Hydros service", and tells a
  server-side error (HTTP 5xx — commonly an **inactive provider key**) apart
  from an actual network failure.
- The API client retries a `GET` once on a transient gateway error
  (HTTP 502/503/504 or a dropped connection).

If you hit "Unable to reach the HYDROS API" / a server error: check
**Settings → System → Logs** for a `custom_components.hydros` line with the HTTP
status, and confirm with CoralVue that your provider key is active — brand-new
keys can take a bit to propagate.

---

## v0.6.1 — Bug fixes (2026-09-08)

Small follow-up to v0.6.0.

- **HACS install fixed for everyone.** The `manifest.json` in the old v0.5.6
  release was invalid JSON (a trailing comma), and HACS reads that file from the
  latest release — so "add repository" failed with
  `trailing comma is not allowed: line 11`. v0.6.x ships a valid manifest and CI
  now validates every JSON file on each push. If HACS is still stuck, open the
  repo in HACS → 3-dot menu → **Update information** (or remove and re-add the
  custom repo). (#5)
- **Alexa routine scenes stuck in "unknown" and not activatable.** Scene ids were
  derived from the editable display name, so renaming a scene orphaned the old
  entity while Alexa kept targeting it. Scene identity is now stable across
  renames, orphaned scenes from older versions are cleaned up automatically on
  startup, and the original `scene.<name>` id is kept. After updating: restart
  HA, delete any leftover unavailable `scene.*` entities, then re-expose to Alexa
  and re-run discovery. (#3)
- pH sensors no longer set an invalid `pH` unit that logged a warning for every
  probe.

Note: a scene showing **"unknown" state is normal** — HA scenes report their
last-activated time and have no on/off state.

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
