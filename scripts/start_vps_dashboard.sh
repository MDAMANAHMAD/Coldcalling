#!/bin/bash
set -e

echo "=========================================================="
echo "🚀 Setting up Next.js Cold Calling Dashboard on VPS..."
echo "=========================================================="

cd ~/Coldcalling

# 1. Install Node.js 20 & npm if not installed
if ! command -v node &> /dev/null || ! command -v npm &> /dev/null; then
  echo "📦 Installing Node.js 20 LTS and npm..."
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi

echo "✅ Node version: $(node -v)"
echo "✅ NPM version: $(npm -v)"

# 2. Install dependencies & build
echo "📦 Installing npm dependencies..."
npm install

echo "🔨 Building Next.js production bundle..."
npm run build

# 3. Create & start systemd background service
echo "⚙️ Creating coldcalling-web.service..."
sudo tee /etc/systemd/system/coldcalling-web.service > /dev/null << 'EOF'
[Unit]
Description=Next.js Cold Calling Web Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/Coldcalling
EnvironmentFile=/home/ubuntu/Coldcalling/.env
ExecStart=/bin/bash -c "npm start -- -p 3000"
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable coldcalling-web
sudo systemctl restart coldcalling-web

echo "=========================================================="
echo "🎉 SUCCESS! Cold Calling Dashboard is running 24/7!"
echo "🌐 Open in your browser: http://13.126.109.207:3000"
echo "=========================================================="
sudo systemctl status coldcalling-web --no-pager
