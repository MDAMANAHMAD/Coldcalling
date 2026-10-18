#!/bin/bash
set -e

DOMAIN=$1
EMAIL=$2

if [ -z "$DOMAIN" ]; then
  echo "Usage: sudo bash scripts/setup_ssl_domain.sh <your-domain.duckdns.org> [email]"
  echo "Example: sudo bash scripts/setup_ssl_domain.sh gayatri-calling.duckdns.org yourname@gmail.com"
  exit 1
fi

if [ -z "$EMAIL" ]; then
  EMAIL="admin@$DOMAIN"
fi

echo "=========================================================="
echo "🔒 Setting up HTTPS & Custom Domain: $DOMAIN"
echo "=========================================================="

# 1. Install Nginx and Certbot
echo "📦 Installing Nginx and Certbot..."
sudo apt-get update
sudo apt-get install -y nginx certbot python3-certbot-nginx

# Ensure local firewall allows HTTP, HTTPS, and port 3000
if command -v ufw &> /dev/null; then
  sudo ufw allow 80/tcp || true
  sudo ufw allow 443/tcp || true
  sudo ufw allow 3000/tcp || true
fi

# 2. Configure Nginx reverse proxy to Next.js on port 3000
echo "⚙️ Configuring Nginx reverse proxy for $DOMAIN..."
sudo tee /etc/nginx/sites-available/$DOMAIN > /dev/null << EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default

# Test Nginx configuration
sudo nginx -t
sudo systemctl reload nginx

# 3. Obtain and install SSL certificate using Certbot
echo "📜 Requesting Free SSL Certificate from Let's Encrypt..."
sudo certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m $EMAIL --redirect

echo "=========================================================="
echo "🎉 SUCCESS! Your dashboard is now SECURE with HTTPS!"
echo "🌐 Open in browser: https://$DOMAIN"
echo "=========================================================="
