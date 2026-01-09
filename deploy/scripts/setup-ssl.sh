#!/bin/bash
# ============================================
# SSL Certificate Setup Script using Let's Encrypt
# ============================================

set -e

# Disable interactive prompts
export DEBIAN_FRONTEND=noninteractive

# Configuration
DOMAIN="${1:-kribaat.com}"
EMAIL="${2:-admin@kribaat.com}"
APP_DIR="${APP_DIR:-/home/$USER/chatplatform}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo "=========================================="
echo "🔒 Setting up SSL for $DOMAIN"
echo "=========================================="

# Check if domain is provided
if [ -z "$DOMAIN" ]; then
    print_error "Domain name is required!"
    echo "Usage: $0 <domain> [email]"
    exit 1
fi

# Install Certbot
echo ""
echo "Installing Certbot..."
if ! command -v certbot &> /dev/null; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -y -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq certbot python3-certbot-nginx
    print_status "Certbot installed"
else
    print_warning "Certbot already installed"
fi

# Create webroot directory for Let's Encrypt verification
echo ""
echo "Creating webroot directory..."
sudo mkdir -p /var/www/certbot
sudo chown -R www-data:www-data /var/www/certbot
print_status "Webroot directory created"

# Create temporary nginx config for certificate issuance
echo ""
echo "Setting up temporary Nginx configuration..."
sudo tee /etc/nginx/sites-available/certbot-temp > /dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Let\'s Encrypt verification';
        add_header Content-Type text/plain;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/certbot-temp /etc/nginx/sites-enabled/certbot-temp
sudo rm -f /etc/nginx/sites-enabled/default /etc/nginx/sites-enabled/chatplatform 2>/dev/null || true

# Test and reload nginx
sudo nginx -t
sudo systemctl reload nginx
print_status "Temporary Nginx configuration active"

# Obtain SSL certificate
echo ""
echo "Obtaining SSL certificate from Let's Encrypt..."
echo "This may take a moment..."

sudo certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "$EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    --force-renewal \
    -d "$DOMAIN" \
    -d "www.$DOMAIN"

if [ $? -eq 0 ]; then
    print_status "SSL certificate obtained successfully!"
else
    print_error "Failed to obtain SSL certificate"
    print_warning "Please ensure:"
    print_warning "  1. Your domain DNS is pointing to this server IP"
    print_warning "  2. Ports 80 and 443 are open in firewall"
    print_warning "  3. No other service is using port 80"
    exit 1
fi

# Set up auto-renewal
echo ""
echo "Setting up automatic certificate renewal..."
sudo systemctl enable certbot.timer 2>/dev/null || true
sudo systemctl start certbot.timer 2>/dev/null || true

# Create renewal hook to reload nginx
sudo mkdir -p /etc/letsencrypt/renewal-hooks/deploy
sudo tee /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh > /dev/null <<'EOF'
#!/bin/bash
systemctl reload nginx
EOF
sudo chmod +x /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
print_status "Auto-renewal configured"

# Install SSL nginx configuration
echo ""
echo "Installing SSL Nginx configuration..."
sudo cp "$APP_DIR/deploy/nginx/chatplatform-ssl.conf" /etc/nginx/sites-available/chatplatform
sudo ln -sf /etc/nginx/sites-available/chatplatform /etc/nginx/sites-enabled/chatplatform
sudo rm -f /etc/nginx/sites-enabled/certbot-temp /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test nginx configuration
sudo nginx -t
if [ $? -eq 0 ]; then
    sudo systemctl reload nginx
    print_status "SSL Nginx configuration active"
else
    print_error "Nginx configuration test failed"
    exit 1
fi

# Verify SSL certificate
echo ""
echo "Verifying SSL certificate..."
CERT_EXPIRY=$(sudo certbot certificates -d "$DOMAIN" 2>/dev/null | grep "Expiry Date" | head -1)
echo "   $CERT_EXPIRY"

echo ""
echo "=========================================="
echo -e "${GREEN}[SUCCESS] SSL Setup Completed!${NC}"
echo "=========================================="
echo ""
echo "Your site is now accessible at:"
echo "  🔒 https://$DOMAIN"
echo "  🔒 https://www.$DOMAIN"
echo ""
echo "Certificate details:"
echo "  Location: /etc/letsencrypt/live/$DOMAIN/"
echo "  Auto-renewal: Enabled (checks twice daily)"
echo ""
echo "Important commands:"
echo "  - Check certificate status: sudo certbot certificates"
echo "  - Renew manually: sudo certbot renew"
echo "  - Test renewal: sudo certbot renew --dry-run"
echo ""
