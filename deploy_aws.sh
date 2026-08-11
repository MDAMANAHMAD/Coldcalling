#!/bin/bash
# ==============================================================================
# AWS Mumbai Voice AI Worker One-Click Auto-Deploy Script
# ==============================================================================

set -e

echo "🚀 [1/4] Updating system packages and installing Docker..."
sudo apt-get update -y
sudo apt-get install -y git curl docker.io docker-compose-v2

echo "🐳 [2/4] Enabling and starting Docker daemon..."
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER || true

echo "📦 [3/4] Building Voice AI Agent Container..."
sudo docker compose build --no-cache

echo "🚀 [4/4] Starting 24/7 Background Voice Agent Daemon..."
sudo docker compose down || true
sudo docker compose up -d

echo "================================================================="
echo "✅ DEPLOYMENT COMPLETE! Voice AI Agent is now running 24/7 in AWS Mumbai!"
echo "📜 View live server logs anytime: sudo docker compose logs -f"
echo "================================================================="
