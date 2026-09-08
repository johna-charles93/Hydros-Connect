# HYDROS Official API Migration

Status of the move from reverse-engineered account auth to the official CoralVue
HYDROS Public API.

## Where things stand

The integration now supports **two auth paths**, chosen from a menu at the start
of setup:

| Path | Credentials | Transport | Status |
|------|-------------|-----------|--------|
| **Official HYDROS API** (`AUTH_MODE_API`) | per-user **provider key** + per-device **device key** | REST polling (`https://api.coralvuehydros.com`) | new, recommended |
| **HYDROS account login** (`AUTH_MODE_LEGACY`) | account email + password | Cognito + AWS IoT MQTT + signed S3 | unchanged, deprecated |

Legacy entries keep working untouched. New installs should use the official API.

## API path design

* **One config entry per device.** The device key is device-scoped, so
  `collective_ids` always has exactly one element. Multi-controller setups add
  the integration once per device. Unique id: `api:{deviceId}`.
* **Provider key is per-user**, entered by the user in the config flow. Nothing
  secret is shipped in the repo. Users request an *unlisted* provider key at
  <https://www.coralvuehydros.com/api/#request-provider-key> so their own quota
  is not consumed by other people's clients.
* **Polling.** `POST /api/v1/device/state/session` mints a 6-hour ES256 poll
  token; the hub polls `pollUrl` every ~30s and renews the session ~30 min
  before expiry (and on `401`). `404` from the state endpoint = device offline;
  entities fall `unavailable` on the normal staleness window.
* **Entity modelling** is synthesised (`api_hub._build_synth_config`) from
  `GET /api/v1/device/overrides/metadata` (output keys, `bool`/`level`/`flag`/`mode`
  types, ranges, `commands`) plus the live state document. The synthesised
  config mimics the S3-config shape the entity platforms already consume.
* **Control:**
  * mode → `POST /api/v1/device/overrides/mode/command {"command": <mode>}`
  * on/off (bool) → `PUT /api/v1/device/overrides {key: bool}`; "auto" → `DELETE /overrides/{key}`
  * pump speed (level) → `PUT /overrides {key: 0..10000}` (percent × 100, clamped to metadata range)
  * manual dose → `POST /overrides/{key}/command {"command":"dose","value": ml×10}` clamped to the `arg` bounds
  * all writes use `receipt=1` to confirm delivery; `get_command_status` /
    `get_pending_command_count` reflect it.
* **Permission.** The device key's read vs read/write level is probed at setup
  with an empty `PUT /overrides` (a documented no-op). Read-only keys record
  `CONF_KEY_PERMISSION=read`; control entities are suppressed and control calls
  raise a clear error.

## Known gaps / follow-ups

- **Dosing history.** No public logs endpoint → "Dosed Today" sensors are not
  created on the API path. Revisit if CoralVue adds one.
- **Input sensor typing.** The state document has no `senseMode`/`probeMode`, so
  units / device classes are inferred from the input name + reported fields
  (`api_hub._classify_input`). Rope-leak inputs can't be detected and won't
  become moisture binary sensors on the API path.
- **HMAC V2 auth** (`HYDROS-HMAC-SHA256 …`) is not implemented; the client uses
  V1 simple auth. V2 would reduce replay risk but still needs a client-side
  secret.
- **Legacy deprecation timeline** is not yet wired into user-facing repair
  issues — pending firm guidance from CoralVue on when the consumer backend
  path stops working.
- **iot_class** in the manifest is still `cloud_push` (accurate for the legacy
  path); the API path is polling.

## Open questions for CoralVue

1. When does the reverse-engineered `cv.hydros.link` / IoT MQTT path stop
   working for updated firmware?
2. Any endpoint (planned) for historical dosing logs?
3. How do multi-controller collectives map to device keys — one key per
   physical controller, or one per collective?
