# HACS Migration Notice

Hydros Connect has moved to a new maintained repository:

- New repository: https://github.com/johna-charles93/Hydros-Connect
- New repository: https://github.com/johna-charles93/Hydros-Connect

## What this means for users

- The integration domain remains `hydros`.
- Existing entities and automations should keep working.
- You should switch your HACS custom repository entry to the new URL.

## How to migrate in HACS

1. In Home Assistant, open HACS.
2. Remove the old custom repository entry if present.
3. Add custom repository:
   - URL: `https://github.com/johna-charles93/Hydros-Connect`
   - Category: Integration
4. Install/update to the latest Hydros Connect release.
5. Restart Home Assistant.

## Verify after update

- Hydros entities are available.
- Integration options open normally.
- Alexa routine scenes (if enabled) appear and can be exposed to Alexa.

## Support

- Issues and support: https://github.com/johna-charles93/Hydros-Connect/issues
