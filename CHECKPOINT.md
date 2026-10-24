# Gayatri AI Voice Agent — Milestone Checkpoint: `stamp-9`

**Saved Date**: October 24, 2026  
**Git Tag**: `stamp-9`  
**Git Branch**: `main`  
**Repository**: `https://github.com/MDAMANAHMAD/Coldcalling`  
**Production Web Dashboard**: `http://qualivo.duckdns.org` (or configured custom domain)

---

## 🌟 What Is Included & Working in `stamp-9`:

1. **Ultra-Fast & Stable Telephony Voice Pipeline**:
   - Immediate **"हॅलो?"** greeting with tuned 1.4s carrier audio delay so mobile phone audio hardware unmuting never swallows the opening word.
   - 3-tier fast shortcut matcher for the initial qualifying questions (Greeting -> Intro -> 1 BHK / 2 BHK -> Ready to Move / Under Construction) delivering pre-cached responses in < 150ms TTFB.
   - High-intelligence Gemini 2.5 Flash Lite brain for all free-form caller queries with sub-second response times.
   - Site visit date & time confirmation flow before storing to database and booking calendars.

2. **Accurate Speech-to-Text (STT) & Interruption Handling**:
   - Deepgram nova-2-general configured with 11 core high-impact Devanagari keywords (`CORE_STT_KEYWORDS`).
   - Phonetic correction map executed in Python memory (`on_user_input`), shrinking the Deepgram WebSocket connection URL from 15,538 bytes down to < 300 bytes, completely eliminating `aiohttp HTTP 400 Bad Request` edge rejections.
   - Silero VAD configured with `min_silence_duration = 0.70s` and `AgentSession(min_delay=0.65s)` to allow callers to pause naturally without Gayatri cutting them off mid-sentence.
   - Fixed 45-second blocking `caller_active` wait for instant call initialization.

3. **High-Performance Production Web Dashboard**:
   - Next.js Webpack production build configured to prevent Linux EC2 symlink panics with `venv/bin/python`.
   - In-memory dashboard cache (8–10s TTL) for instant call logs, statistics, and recording playback.
   - Dual-channel conversation audio recording and live call tracker (`scripts/track_live_calls.py`).

---

## 🔄 How to Restore / Retain `stamp-9` Anytime:

If you ever need to restore your entire project back to this exact working baseline:

### 1. View this exact version without changing your current work:
```bash
git checkout stamp-9
```

### 2. Reset your local code back to `stamp-9`:
```bash
git checkout main
git reset --hard stamp-9
git push origin main --force
```

### 3. Restore your AWS EC2 VPS to `stamp-9`:
```bash
cd ~/Coldcalling
git checkout stamp-9
sudo systemctl restart voice-agent.service
npm run build
sudo systemctl restart coldcalling-web.service
```

---

## Historical Milestones:
- `stamp-8`: Initial Hindi flow optimizations and latency reductions.
- `stamp-7` - `stamp-2`: Voice latency and dual-recording iterations.
- `v1.0.0-stable-perfect`: Original stable release (September 26, 2026).
