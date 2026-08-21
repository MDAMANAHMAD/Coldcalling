#!/bin/bash
# Script to configure a 2GB swap file on Ubuntu-2 to optimize 1GB RAM performance

echo "⚙️ Checking current swap space..."
CURRENT_SWAP=$(swapon --show)

if [ -n "$CURRENT_SWAP" ]; then
    echo "✅ Swap space is already configured on this server:"
    echo "$CURRENT_SWAP"
    exit 0
fi

echo "🚀 Creating a 2GB swap file..."
sudo fallocate -l 2G /swapfile

if [ $? -ne 0 ]; then
    echo "⚠️ fallocate failed, trying dd method..."
    sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
fi

echo "🔒 Setting secure permissions..."
sudo chmod 600 /swapfile

echo "⚙️ Formatting swap file..."
sudo mkswap /swapfile

echo "🟢 Activating swap space..."
sudo swapon /swapfile

# Add to fstab for permanence across reboots
if ! grep -q "/swapfile" /etc/fstab; then
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo "✅ Added swap mount to /etc/fstab for persistent reboots."
fi

echo "📊 Verification:"
free -h
swapon --show

echo "🎉 2GB Swap configuration complete! Your 1GB server now has 3GB of total virtual memory."
