# HYDROS Official API Key Migration Plan

This document outlines a safe migration path from account credential auth to the official HYDROS Provider Key + Device Key model.

## Goals

- Preserve existing installs during migration.
- Add official API support in parallel.
- Move new users to key-based auth by default once stable.

## Proposed phases

1. Add parallel auth mode in config flow
- `Account credentials (legacy)`
- `Provider key + Device key (official)`

2. Implement official-key client path
- Device lookup
- State reads
- Mode/output write operations used by this integration

3. Feature parity validation
- Sensors
- Mode control
- Alexa routine scenes
- Recovery and retries under rate limits

4. Controlled default switch
- New installs default to official API keys.
- Existing installs continue on legacy mode until user migrates.

5. Deprecation messaging
- Add migration notices and timeline once HYDROS publishes firm deprecation guidance.

## UX requirements

- Keep setup non-developer friendly.
- Include copy/paste validation and permission checks.
- Expose clear errors for invalid key scopes (read-only vs read/write).

## Safety requirements

- Enforce least privilege by default (read-only unless control is explicitly enabled).
- Preserve current remote-control disclaimer behavior.
