#!/usr/bin/env bash
set -e

echo "=== 🚀 Updating Coldcalling Agent to Fireworks AI ==="
cd ~/Coldcalling

# 1. Clean untracked conflicting cache files
rm -f bookings/model_cache.json bookings/active_call.lock

# 2. Reset and fetch latest code from origin/main
git fetch origin main
git reset --hard origin/main

# 3. Clean up and set Fireworks AI configuration in voice_agent/.env
sed -i '/^FIREWORKS_API_KEY=/d' voice_agent/.env
sed -i '/^LLM_PROVIDER=/d' voice_agent/.env
sed -i '/^FIREWORKS_MODEL=/d' voice_agent/.env
sed -i '/catrt/d' voice_agent/.env

echo "FIREWORKS_API_KEY=fw_55p5CrYTUwqYfj5ABPuTbr" >> voice_agent/.env
echo "LLM_PROVIDER=fireworks" >> voice_agent/.env
echo "FIREWORKS_MODEL=accounts/fireworks/models/gpt-oss-120b" >> voice_agent/.env

echo "=== 📄 Verified .env tail ==="
tail -n 5 voice_agent/.env

# 4. Restart the voice-agent service cleanly
echo "=== 🔄 Restarting voice-agent.service ==="
sudo pkill -9 -f python || true
sudo systemctl restart voice-agent

echo "=== ✅ Done! Streaming logs below (Press Ctrl+C to exit log view) ==="
sudo journalctl -u voice-agent -f -o cat
