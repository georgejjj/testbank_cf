#!/bin/bash
# =============================================================
# TestBank Deployment Script
# Run this on your server: bash deploy/setup.sh testbank.yourdomain.com
# =============================================================

set -e

SUBDOMAIN=$1

if [ -z "$SUBDOMAIN" ]; then
    echo "Usage: bash deploy/setup.sh YOUR_SUBDOMAIN.YOUR_DOMAIN.COM"
    echo "Example: bash deploy/setup.sh testbank.example.com"
    exit 1
fi

echo "========================================="
echo "Deploying TestBank to $SUBDOMAIN"
echo "========================================="

PROJECT_DIR=$(cd "$(dirname "$0")/.." && pwd)
echo "Project directory: $PROJECT_DIR"

# Step 1: Install dependencies
echo ""
echo "[1/7] Installing Python dependencies..."
pip install --break-system-packages -r "$PROJECT_DIR/requirements.txt"

# Step 2: Django setup
echo ""
echo "[2/7] Running Django migrations & collecting static files..."
cd "$PROJECT_DIR"
python3 manage.py migrate --no-input
python3 manage.py collectstatic --no-input

# Step 3: Update Django settings
echo ""
echo "[3/7] Configuring Django for production..."
# Update ALLOWED_HOSTS (already set to ['*'] which works, but you can restrict)
# Update CSRF_TRUSTED_ORIGINS
sed -i "s|# 'https://testbank.yourdomain.com',|'https://$SUBDOMAIN',|" "$PROJECT_DIR/config/settings.py"

# Step 4: Install systemd service
echo ""
echo "[4/7] Setting up Gunicorn systemd service..."
# Fix paths in service file
sed -i "s|/home/georgejjj|$HOME|g" "$PROJECT_DIR/deploy/testbank.service"
sed -i "s|User=georgejjj|User=$(whoami)|g" "$PROJECT_DIR/deploy/testbank.service"
sed -i "s|Group=georgejjj|Group=$(whoami)|g" "$PROJECT_DIR/deploy/testbank.service"

# Find gunicorn path
GUNICORN_PATH=$(which gunicorn)
sed -i "s|/usr/local/bin/gunicorn|$GUNICORN_PATH|g" "$PROJECT_DIR/deploy/testbank.service"

sudo cp "$PROJECT_DIR/deploy/testbank.service" /etc/systemd/system/testbank.service
sudo systemctl daemon-reload
sudo systemctl enable testbank
sudo systemctl restart testbank

echo "   Gunicorn service started on port 8001"

# Step 5: Configure nginx
echo ""
echo "[5/7] Configuring nginx..."
# Update nginx config with subdomain and paths
sed "s|YOUR_SUBDOMAIN.YOUR_DOMAIN.COM|$SUBDOMAIN|g" "$PROJECT_DIR/deploy/nginx-testbank.conf" | \
    sed "s|/home/georgejjj/testbank|$PROJECT_DIR|g" | \
    sudo tee /etc/nginx/sites-available/testbank > /dev/null

# Enable site
sudo ln -sf /etc/nginx/sites-available/testbank /etc/nginx/sites-enabled/testbank

# Test and reload
sudo nginx -t
sudo systemctl reload nginx
echo "   Nginx configured for $SUBDOMAIN"

# Step 6: SSL with Let's Encrypt
echo ""
echo "[6/7] Setting up SSL..."
if command -v certbot &> /dev/null; then
    sudo certbot --nginx -d "$SUBDOMAIN" --non-interactive --agree-tos --redirect
    echo "   SSL certificate installed"
else
    echo "   certbot not found. Install it with: sudo apt install certbot python3-certbot-nginx"
    echo "   Then run: sudo certbot --nginx -d $SUBDOMAIN"
fi

# Step 7: DNS reminder
echo ""
echo "[7/7] DNS Setup"
echo "========================================="
echo ""
echo "Add this DNS record at your domain registrar:"
echo ""
echo "   Type: A"
echo "   Name: $(echo $SUBDOMAIN | cut -d. -f1)"
echo "   Value: $(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_SERVER_IP')"
echo "   TTL: 300"
echo ""
echo "========================================="
echo "Deployment complete!"
echo ""
echo "After DNS propagates (5-30 min), visit: https://$SUBDOMAIN"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status testbank     # Check status"
echo "  sudo systemctl restart testbank    # Restart app"
echo "  sudo journalctl -u testbank -f     # View logs"
echo "  python3 manage.py createsuperuser  # Create admin account"
echo "========================================="
