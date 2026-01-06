#!/bin/bash
# ============================================
# Server Initial Setup Script
# Ubuntu 24.04 LTS - Docker, Docker Compose, Nginx
# ============================================

set -e

echo "=========================================="
echo "🚀 Starting Server Setup..."
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

# Update system
echo ""
echo "📦 Updating system packages..."
sudo apt-get update -y
sudo apt-get upgrade -y
print_status "System updated"

# Install essential packages
echo ""
echo "📦 Installing essential packages..."
sudo apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    git \
    htop \
    ufw \
    fail2ban \
    unzip
print_status "Essential packages installed"

# Install Docker
echo ""
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the repository to Apt sources
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -y
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    
    # Add current user to docker group
    sudo usermod -aG docker $USER
    
    print_status "Docker installed successfully"
else
    print_warning "Docker already installed"
fi

# Enable Docker service
sudo systemctl enable docker
sudo systemctl start docker
print_status "Docker service enabled and started"

# Install Nginx
echo ""
echo "🌐 Installing Nginx..."
if ! command -v nginx &> /dev/null; then
    sudo apt-get install -y nginx
    print_status "Nginx installed successfully"
else
    print_warning "Nginx already installed"
fi

# Configure UFW Firewall
echo ""
echo "🔥 Configuring firewall..."
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw allow 8000/tcp  # Backend API (for development/debugging)
sudo ufw allow 3000/tcp  # Frontend (for development/debugging)
sudo ufw --force enable
print_status "Firewall configured"

# Configure fail2ban
echo ""
echo "🛡️ Configuring fail2ban..."
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
print_status "Fail2ban configured"

# Create application directory
echo ""
echo "📁 Creating application directories..."
APP_DIR="${APP_DIR:-/home/$USER/chatplatform}"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/deploy"
mkdir -p "$APP_DIR/logs"
mkdir -p "$APP_DIR/backups"
print_status "Application directories created at $APP_DIR"

# Set permissions
sudo chown -R $USER:$USER "$APP_DIR"
print_status "Permissions set"

# Clean up
echo ""
echo "🧹 Cleaning up..."
sudo apt-get autoremove -y
sudo apt-get clean
print_status "Cleanup complete"

echo ""
echo "=========================================="
echo -e "${GREEN}✅ Server setup completed!${NC}"
echo "=========================================="
echo ""
echo "Important notes:"
echo "  - You may need to log out and back in for Docker group changes to take effect"
echo "  - UFW firewall is now active"
echo "  - Docker and Nginx are installed and running"
echo ""
