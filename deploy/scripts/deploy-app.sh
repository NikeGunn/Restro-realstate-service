#!/bin/bash
# ============================================
# Application Deployment Script
# ============================================

set -e

# Load environment variables
source /home/$USER/chatplatform/.env.production 2>/dev/null || true

APP_DIR="${APP_DIR:-/home/$USER/chatplatform}"
cd "$APP_DIR"

echo "=========================================="
echo "🚀 Deploying Application..."
echo "=========================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

# Stop existing containers
echo ""
echo "🛑 Stopping existing containers..."
docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true
print_status "Containers stopped"

# Pull latest images (if using registry) or build
echo ""
echo "🔨 Building Docker images..."
docker compose -f docker-compose.prod.yml build --no-cache
print_status "Images built"

# Start containers
echo ""
echo "🚀 Starting containers..."
docker compose -f docker-compose.prod.yml up -d
print_status "Containers started"

# Wait for database to be ready
echo ""
echo "⏳ Waiting for database..."
sleep 10
print_status "Database ready"

# Run migrations
echo ""
echo "📊 Running database migrations..."
docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --noinput
print_status "Migrations completed"

# Collect static files
echo ""
echo "📁 Collecting static files..."
docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --noinput
print_status "Static files collected"

# Configure Nginx
echo ""
echo "🌐 Configuring Nginx..."
sudo cp "$APP_DIR/deploy/nginx/chatplatform.conf" /etc/nginx/sites-available/chatplatform
sudo ln -sf /etc/nginx/sites-available/chatplatform /etc/nginx/sites-enabled/chatplatform
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test Nginx configuration
sudo nginx -t
sudo systemctl reload nginx
print_status "Nginx configured and reloaded"

# Show status
echo ""
echo "=========================================="
echo "📊 Container Status:"
echo "=========================================="
docker compose -f docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Deployment completed successfully!${NC}"
echo "=========================================="
echo ""
echo "Application URLs:"
echo "  - Frontend: http://$(hostname -I | awk '{print $1}')"
echo "  - Backend API: http://$(hostname -I | awk '{print $1}')/api"
echo "  - Admin: http://$(hostname -I | awk '{print $1}')/admin"
echo ""
