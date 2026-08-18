# Hydros Alexa Scene Activation - Debug Guide

## Current Status
- ✅ Scenes ARE being created in Home Assistant
- ✅ Scenes ARE exposed to Alexa Voice Assistants
- ❌ Scenes show "Unknown" state in entity list
- ❌ Voice commands don't activate scenes

## What v0.5.5 Adds
- **Comprehensive logging** at scene creation, activation, and error points
- **Icon and availability tracking** for better entity state management
- **Detailed error messages** when mode changes fail
- **Scene preset filtering debug messages** to help identify why scenes may or may not be created

## Step-by-Step Debugging

### Step 1: Enable Debug Logging
1. Open Home Assistant Settings
2. Go to **System → Logs**
3. Click **Logger** at the bottom
4. Add a custom logger:
   - **Logger name:** `custom_components.hydros.scene`
   - **Level:** `DEBUG`
5. Click **Create**

### Step 2: Test Scene Activation
Do this in order:

#### A. Manual HA Scene Activation (UI)
1. Go to **Settings → Devices & Services → Scenes**
2. Find your "Feed Mode" or "Maintenance Mode" scene
3. Click the three dots → **Trigger**
4. **Watch the HA Logs** in real-time for output

**Expected in logs (DEBUG level):**
```
Activating scene 'Feed Mode' -> mode 'Feeding' (thing_id=DEVICE_ID)
Scene 'Feed Mode' activated successfully, mode changed to 'Feeding'
```

**If you see errors:**
- Copy the full error message
- Check if `hub.async_change_mode()` is being called
- Verify the mode name matches available modes on your device

#### B. Manual Alexa Scene Activation
1. Open the **Alexa app** on your phone
2. Go to **Devices → All Devices**
3. Find "Feed Mode" or "Maintenance Mode"
4. Tap to open the scene card
5. Tap the **play button** to activate
6. **Watch HA Logs immediately** for activation messages

**If Alexa app doesn't show the scene:**
- Go back to HA: **Settings → Voice Assistants → Alexa → Expose**
- Verify your scenes have the **Alexa icon** showing they're exposed
- Toggle them OFF and back ON to refresh exposure
- Restart Alexa app

#### C. Alexa Voice Command
1. Say: "Alexa, activate Feed Mode"
2. Alexa should respond with activation
3. **Immediately check HA Logs** for scene activation

**If Alexa says "device not responding":**
- The scene wasn't found by Alexa
- Verify it's showing in Alexa app (Step B above)
- Try re-exposing the scene in HA

### Step 3: Interpret the Log Output

#### ✅ Success Scenario
```
[DEBUG] Created scene: Feed Mode (unique_id=..., mode=Feeding)
[DEBUG] Built 2 scene presets for thing_id=...
[INFO] Adding 2 Hydros Alexa scenes
[INFO] Activating scene 'Feed Mode' -> mode 'Feeding' (thing_id=...)
[DEBUG] Scene 'Feed Mode' activated successfully, mode changed to 'Feeding'
[DEBUG] Scene 'Feed Mode' scheduled auto-return to 'Normal' in 15 minutes
```

#### ⚠️ Scene Creation Issues
**If you see:** `[WARNING] No valid scene presets found for entry ...`

This means scenes aren't being created at all. Check:
1. Is `CONF_ENABLE_REMOTE_CONTROL` set to `True` in config?
2. Are scene names and modes filled in config?
3. Are mode names valid for your device?
4. Run this in HA Developer Tools → **Template**:
   ```
   {{ state_attr('scene.feed_mode', 'start_mode') if 'scene.feed_mode' in states else 'SCENE_NOT_FOUND' }}
   ```

#### ⚠️ Activation Issues
**If you see:** `[ERROR] Failed to activate scene 'Feed Mode': ...`

This means the scene exists but activation failed. Check:
1. The error message - does it mention the API call?
2. Is the mode name exact? (Check your device config in HYDROS app)
3. Is remote control enabled on your device in HYDROS app?
4. Are there any WiFi/connectivity issues?

**If you see:** `[WARNING] Failed to schedule return for scene...`

The scene activated but auto-return scheduling failed. This isn't critical - the scene still worked.

#### ❌ No Log Messages at All
If nothing appears in logs even after activation:
1. The scene entity might not be getting `async_activate()` called
2. Check if the entity even exists: Go to **Developer Tools → States**, search for "scene"
3. Try restarting Home Assistant
4. Check if remote control is enabled in integration config

### Step 4: Check Entity Details
1. Go to **Settings → Devices & Services → Entities**
2. Search for your device name (e.g., "90 Display")
3. Find scene entities
4. Click on one to see details:
   - **Entity ID** should be: `scene.feed_mode` or similar
   - **State** should be: `on` (if activated) or `off` (if not)
   - **Attributes** should show: `thing_id`, `start_mode`, `return_enabled`, etc.
5. **Report any unexpected attribute values** in GitHub issue #3

### Step 5: Verify Device Configuration
1. In your HYDROS mobile app, verify:
   - Your Hydros device has **Remote Control ENABLED**
   - Available modes match what you configured in HA
   - Example modes: "Feeding", "Maintenance", "Normal"
2. If mode names don't match exactly, scenes won't work
3. **Add as comment to issue #3** if mode names are different

## What to Include When Reporting Issues

If activation still fails, comment on [Issue #3](https://github.com/johna-charles93/Hydros-Connect/issues/3) with:

1. **Full log output** from DEBUG logs (copy-paste the entire activation attempt)
2. **Home Assistant version** (Settings → About)
3. **Hydros Connect version** (should be 0.5.5)
4. **Steps you took** to trigger activation
5. **Alexa app version** and device type (e.g., Echo Dot, Fire TV)
6. **Your device modes** (from HYDROS app Settings)
7. **Any error messages** shown by Alexa or HA

## Common Issues & Solutions

### Issue: Scenes Don't Show in Alexa App
- **Solution:** Re-expose in HA: Settings → Voice Assistants → Alexa → Expose (toggle OFF/ON)
- **Wait:** Up to 5 minutes for Alexa to refresh
- **Test:** Open Alexa app, go to Devices, search for your device name

### Issue: Alexa Says "Device Not Responding"
- **Solution:** Check logs for activation attempts (Step 3)
- **If no logs appear:** Scene entity isn't being found by Alexa
- **Check:** Device connectivity in HA (should show "Available")
- **Fix:** Reload integration (Settings → Devices & Services → Hydros → Menu → Reload)

### Issue: Scene Activates But Mode Doesn't Change
- **Solution:** Check mode name in logs (Step 3)
- **Verify:** Mode exists in HYDROS app
- **Check:** Remote control is enabled on device in HYDROS app
- **Test:** Change mode manually in HYDROS app to verify it works

### Issue: Scene Shows "Unknown" State
- **Expected:** Scenes don't have persistent state like sensors
- **This is normal** - don't worry about "Unknown"
- **Real test:** Does activation work? (that's what matters)

## Version Upgrade Instructions

If you're on v0.5.4 or earlier:

1. In Home Assistant, go to **HACS → Custom repositories**
2. Find "Hydros Connect"
3. Click it → **3-dot menu → Update**
4. Wait for download to complete
5. **Restart Home Assistant** (Settings → System → Restart)
6. Wait 2-3 minutes for services to fully load
7. Try activation again with logs enabled

## Next Steps (Feature Requests)

After scene activation works, the following v0.5.5+ features are planned:

- **Optional Scene Fields** (Issue #4) - only create scenes you need
- **Alexa Stats Queries** (Issue #4) - ask "Alexa, what's my tank temperature?"
- **Better scene state UI** - improve how scenes display in HA

## Still Having Issues?

1. ✅ Follow steps 1-5 above completely
2. ✅ Enable DEBUG logging before testing
3. ✅ Share **full log output** in Issue #3 on GitHub
4. ✅ Include device info and Alexa version
5. ✅ Be specific about **which test step failed** (1A, 1B, 1C, etc.)

The debug logs in v0.5.5 are designed to pinpoint exactly where activation fails!
