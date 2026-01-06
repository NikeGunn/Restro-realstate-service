# ============================================
# DEPLOYMENT CONFIGURATION - EDIT THIS FILE
# ============================================

# Server Configuration
$SERVER_IP = "43.152.233.234"
$SERVER_USER = "ubuntu"
$PEM_FILE = "$PSScriptRoot\..\Kribaat.pem"

# Domain Configuration (leave empty if no domain, will use IP)
$DOMAIN_NAME = ""

# Application Ports
$FRONTEND_PORT = 3000
$BACKEND_PORT = 8000
$NGINX_HTTP_PORT = 80
$NGINX_HTTPS_PORT = 443

# Application Name (used for directory naming)
$APP_NAME = "chatplatform"

# Remote Paths
$REMOTE_APP_DIR = "/home/$SERVER_USER/$APP_NAME"
$REMOTE_DEPLOY_DIR = "/home/$SERVER_USER/$APP_NAME/deploy"

# Environment
$ENVIRONMENT = "production"

# SSL (set to $true if you have a domain and want SSL)
$ENABLE_SSL = $false

# Database Configuration
$POSTGRES_DB = "chatplatform"
$POSTGRES_USER = "chatplatform"
$POSTGRES_PASSWORD = "chatplatform123"
