#!/bin/bash
# ==============================================================================
# Ultra-Fast Native Python Host Runner (Instant 15s Setup)
# ==============================================================================

set -e

echo "🚀 [1/3] Installing Python environment and audio utilities..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv ffmpeg curl

echo "🐍 [2/3] Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "📦 [3/3] Installing LiveKit, Groq, and ElevenLabs voice plugins..."
pip install --upgrade pip
pip install -r voice_agent/requirements.txt

# Create systemd service for 24/7 autonomous background execution
echo "⚙️ Creating 24/7 background system service..."
sudo tee /etc/systemd/system/voice-agent.service > /dev/null << EOF
[Unit]
Description=LiveKit Voice AI Cold Calling Agent
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$(pwd)
EnvironmentFile=$(pwd)/.env
ExecStart=$(pwd)/venv/bin/python voice_agent/agent.py start
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable voice-agent
sudo systemctl restart voice-agent

echo "================================================================="
echo "✅ DEPLOYMENT COMPLETE! Voice Agent is running 24/7 on AWS Mumbai!"
echo "📜 Check status anytime: sudo systemctl status voice-agent"
echo "📜 View live logs anytime: sudo journalctl -u voice-agent -f"
echo "================================================================="
