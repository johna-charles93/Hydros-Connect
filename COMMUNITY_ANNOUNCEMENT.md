# 🎉 Hydros Connect: Moved, Improved, and Ready for the Official API

Hi everyone! We have some exciting news to share about Hydros in Home Assistant.

## 📦 The Big Move

The integration has moved to a **new home** and been rebranded as **Hydros Connect**. This is part of preparing for official API support that CoralVue is launching. The good news? If you're already using it, **migration is simple and automatic** — HACS will guide you, and we've put together step-by-step docs if you need them.

**New Repo:** [johna-charles93/Hydros-Connect](https://github.com/johna-charles93/Hydros-Connect)

---

## ✨ What's New in v0.5.2

We've focused on making Hydros easier to use for everyone, especially those who aren't into YAML automation:

### 1. **No-YAML Alexa Setup**
- You can now set up Alexa routine scenes **entirely through Home Assistant Settings**. No scripts, no automations to write.
- Pick your modes, get instant scene entities, and tell Alexa about them in seconds.
- Perfect for: *"Alexa, feeding mode" → automatic return to previous mode after 30 mins*.

### 2. **Validate Setup Button**
- Added a new button entity on your Hydros device that runs health checks.
- Tap it → get a report on what's working, what needs attention, and what might break.
- Great for troubleshooting or confirming everything is configured correctly.

### 3. **Restart-Safe Auto-Return**
- Scheduled scene returns now survive Home Assistant restarts.
- Previously, if HA rebooted during a timed return, you'd have to wait and hope. Now it just works.

---

## 🚀 The Official API is Coming

CoralVue just launched their official developer API and is inviting integrations to migrate. This is actually **good news**, but it does involve some changes:

### What's Changing

The old auth method was:
- Account email + password (legacy)

The new auth method will be:
- **Provider Key** (issued by CoralVue for registered integrations like this one)
- **Device Key** (you create in the HYDROS app, per device, with specific permissions)

### Why This is Better

✅ **More secure**: Keys are per-device and per-integration, not your account password  
✅ **More flexible**: You choose read-only vs. read-write per device  
✅ **Better rate limits**: Official tier has solid limits (60 lookups/min, 10 state updates/min)  
✅ **Ongoing support**: Official API means official SLAs and developer support  

### What We're Planning

1. **Phase 1 (Current)**: Both auth methods work side-by-side. You can stick with account credentials.
2. **Phase 2 (TBD)**: New installs default to the official API. Existing users still on legacy mode.
3. **Phase 3 (TBD, many months away)**: Deprecation timeline once CoralVue confirms one.

**You won't be forced to migrate overnight.** We'll give plenty of notice.

### What You Need to Know

- **No action needed yet** — keep using what you have.
- **Setup will be slightly different** — instead of entering your account email/password, you'll create API keys in the HYDROS app and paste them into Home Assistant.
- **More granular permissions** — you'll choose what each key can do, which is more secure.
- **Rate limits are fair** — designed for personal/pro use. If you're just polling your tank, you won't hit them.

---

## 🔗 Where to Find Help

- **Migration guide:** [HACS Migration Instructions](https://github.com/johna-charles93/Hydros-Connect/blob/main/HACS_MIGRATION_NOTICE.md)
- **Full setup & Alexa docs:** [README](https://github.com/johna-charles93/Hydros-Connect/blob/main/custom_components/hydros/README.md)
- **API migration roadmap:** [API Key Migration Plan](https://github.com/johna-charles93/Hydros-Connect/blob/main/API_KEY_MIGRATION_PLAN.md)
- **Report issues or ask questions:** [GitHub Issues](https://github.com/johna-charles93/Hydros-Connect/issues)
- **HYDROS Developer forum:** [coralvuehydros.com](https://forum.coralvuehydros.com/forums/hydros-developer-api.36/)

---

## ❓ FAQ

**Q: Do I need to move right now?**  
A: No. HACS will let you know when the old repo stops being maintained. That's when you should migrate.

**Q: Will my setup break?**  
A: No. We're doing this carefully. Existing installs stay on the legacy auth method until you're ready to switch.

**Q: Is the official API reliable?**  
A: Yes. It's a new launch from CoralVue, and they're supporting it officially with rate limits, docs, and a developer forum.

**Q: I'm not comfortable with APIs and keys. Can I just use my password?**  
A: For now, yes. You can keep using account credentials. But the official API is actually *easier* conceptually — one key per tank, not your whole account password.

**Q: What if I want to stay on the old method forever?**  
A: We understand, but CoralVue has indicated account credential auth is being sunset. We don't have a hard date yet, but migration will be necessary eventually. We'll give you plenty of time.

---

## 🙏 Thanks

Big thanks to everyone using Hydros in Home Assistant. Your feedback drives these improvements. We're committed to keeping this integration beginner-friendly while supporting power users who want official API features.

**Questions?** Drop them in the GitHub issues or reply here. Let's make reef automation better together.

Happy automating! 🐠
