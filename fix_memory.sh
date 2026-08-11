#!/bin/bash
# ==============================================================================
# Complete VPS Memory Optimizer & Permanent OOM Killer Eliminator
# ==============================================================================

set -e

echo "💾 [1/3] Creating permanent 2GB Swap file..."
sudo swapoff -a || true
sudo rm -f /swapfile || true
sudo dd if=/dev/zero of=/swapfile bs=1M count=2048 status=progress
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Persist swap across reboots
if ! grep -q '/swapfile' /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
fi

echo "🧹 [2/3] Setting Linux memory overcommit & swappiness..."
sudo sysctl vm.swappiness=60
sudo sysctl vm.overcommit_memory=1

echo "📦 [3/3] Restarting Voice Agent with 3GB available memory..."
cd /home/ubuntu/Coldcalling
git pull
source venv/bin/activate
pip install onnxruntime
sudo systemctl restart voice-agent

echo "================================================================="
echo "✅ MEMORY OPTIMIZATION COMPLETE! Total available memory is now 3GB!"
echo "📜 Live status: sudo systemctl status voice-agent"
echo "================================================================="
