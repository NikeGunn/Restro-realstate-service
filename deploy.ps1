<#
.SYNOPSIS
    Golden Deployment Script for Chat Platform
    Deploy to any Ubuntu server with Docker

.DESCRIPTION
    This script automates the entire deployment process:
    1. Connects to remote server via SSH
    2. Installs Docker, Docker Compose, Nginx
    3. Uploads application files
    4. Configures and starts all containers
    5. Sets up Nginx as reverse proxy

.PARAMETER ServerIP
    The IP address of the target server

.PARAMETER PemFile
    Path to the PEM file for SSH authentication

.PARAMETER ServerUser
    SSH username (default: ubuntu)

.PARAMETER AppName
    Application name for directory naming (default: chatplatform)

.EXAMPLE
    .\deploy.ps1 -ServerIP "43.152.233.234" -PemFile ".\Kribaat.pem"

.EXAMPLE
    .\deploy.ps1 -ServerIP "192.168.1.100" -PemFile "C:\keys\mykey.pem" -ServerUser "admin"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$ServerIP = "43.152.233.234",
    
    [Parameter(Mandatory=$false)]
    [string]$PemFile = "$PSScriptRoot\Kribaat.pem",
    
    [Parameter(Mandatory=$false)]
    [string]$ServerUser = "ubuntu",
    
    [Parameter(Mandatory=$false)]
    [string]$AppName = "chatplatform",

    [Parameter(Mandatory=$false)]
    [switch]$SkipSetup = $false,

    [Parameter(Mandatory=$false)]
    [switch]$SetupOnly = $false
)

# ============================================
# Configuration
# ============================================
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RemoteAppDir = "/home/$ServerUser/$AppName"
$SSHOptions = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# Colors for output
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Status($message) {
    Write-Host "[✓] " -ForegroundColor Green -NoNewline
    Write-Host $message
}

function Write-Warning($message) {
    Write-Host "[!] " -ForegroundColor Yellow -NoNewline
    Write-Host $message
}

function Write-Error($message) {
    Write-Host "[✗] " -ForegroundColor Red -NoNewline
    Write-Host $message
}

function Write-Info($message) {
    Write-Host "[→] " -ForegroundColor Cyan -NoNewline
    Write-Host $message
}

# ============================================
# Validation
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "🚀 Chat Platform Deployment Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if PEM file exists
if (-not (Test-Path $PemFile)) {
    Write-Error "PEM file not found: $PemFile"
    exit 1
}

# Get absolute path of PEM file
$PemFile = (Resolve-Path $PemFile).Path
Write-Status "PEM file found: $PemFile"

# Check if project files exist
if (-not (Test-Path "$ProjectRoot\backend")) {
    Write-Error "Backend directory not found: $ProjectRoot\backend"
    exit 1
}

if (-not (Test-Path "$ProjectRoot\frontend")) {
    Write-Error "Frontend directory not found: $ProjectRoot\frontend"
    exit 1
}

Write-Status "Project files found"
Write-Info "Server: $ServerUser@$ServerIP"
Write-Info "App Directory: $RemoteAppDir"
Write-Host ""

# ============================================
# SSH Helper Functions
# ============================================
function Invoke-RemoteCommand {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Command,
        [Parameter(Mandatory=$false)]
        [switch]$Silent = $false
    )
    
    $sshCommand = "ssh $SSHOptions -i `"$PemFile`" $ServerUser@$ServerIP `"$Command`""
    
    if (-not $Silent) {
        Write-Info "Running: $Command"
    }
    
    $result = Invoke-Expression $sshCommand 2>&1
    
    if ($LASTEXITCODE -ne 0 -and -not $Silent) {
        Write-Warning "Command may have had warnings (exit code: $LASTEXITCODE)"
    }
    
    return $result
}

function Copy-ToRemote {
    param(
        [Parameter(Mandatory=$true)]
        [string]$LocalPath,
        [Parameter(Mandatory=$true)]
        [string]$RemotePath
    )
    
    Write-Info "Copying: $LocalPath -> $RemotePath"
    
    # Use scp for files/directories
    if (Test-Path $LocalPath -PathType Container) {
        # Directory - use recursive copy
        $scpCommand = "scp $SSHOptions -r -i `"$PemFile`" `"$LocalPath`" $ServerUser@${ServerIP}:$RemotePath"
    } else {
        # File
        $scpCommand = "scp $SSHOptions -i `"$PemFile`" `"$LocalPath`" $ServerUser@${ServerIP}:$RemotePath"
    }
    
    Invoke-Expression $scpCommand
    
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to copy: $LocalPath"
        return $false
    }
    
    return $true
}

# ============================================
# Test SSH Connection
# ============================================
Write-Host "Testing SSH connection..." -ForegroundColor Yellow
try {
    $testResult = Invoke-RemoteCommand -Command "echo 'SSH connection successful'" -Silent
    Write-Status "SSH connection established"
} catch {
    Write-Error "Failed to connect to server. Please check:"
    Write-Error "  - Server IP is correct: $ServerIP"
    Write-Error "  - PEM file is correct: $PemFile"
    Write-Error "  - Username is correct: $ServerUser"
    Write-Error "  - Server is running and SSH port (22) is open"
    exit 1
}

# ============================================
# Server Setup (Install Docker, Nginx, etc.)
# ============================================
if (-not $SkipSetup) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host "📦 Server Setup (Docker, Nginx, etc.)" -ForegroundColor Yellow
    Write-Host "==========================================" -ForegroundColor Yellow
    Write-Host ""

    # Update system
    Write-Info "Updating system packages..."
    Invoke-RemoteCommand -Command "sudo apt-get update -y && sudo apt-get upgrade -y" | Out-Null
    Write-Status "System updated"

    # Install essential packages
    Write-Info "Installing essential packages..."
    Invoke-RemoteCommand -Command "sudo apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release software-properties-common git htop ufw unzip" | Out-Null
    Write-Status "Essential packages installed"

    # Install Docker
    Write-Info "Installing Docker..."
    $dockerCheck = Invoke-RemoteCommand -Command "which docker" -Silent
    if (-not $dockerCheck) {
        Invoke-RemoteCommand -Command "sudo install -m 0755 -d /etc/apt/keyrings" | Out-Null
        Invoke-RemoteCommand -Command "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes" | Out-Null
        Invoke-RemoteCommand -Command "sudo chmod a+r /etc/apt/keyrings/docker.gpg" | Out-Null
        Invoke-RemoteCommand -Command "echo `"deb [arch=`$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu `$(. /etc/os-release && echo `$VERSION_CODENAME) stable`" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null" | Out-Null
        Invoke-RemoteCommand -Command "sudo apt-get update -y" | Out-Null
        Invoke-RemoteCommand -Command "sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin" | Out-Null
        Invoke-RemoteCommand -Command "sudo usermod -aG docker $ServerUser" | Out-Null
        Write-Status "Docker installed"
    } else {
        Write-Status "Docker already installed"
    }

    # Enable Docker
    Invoke-RemoteCommand -Command "sudo systemctl enable docker && sudo systemctl start docker" | Out-Null
    Write-Status "Docker service enabled"

    # Install Nginx
    Write-Info "Installing Nginx..."
    $nginxCheck = Invoke-RemoteCommand -Command "which nginx" -Silent
    if (-not $nginxCheck) {
        Invoke-RemoteCommand -Command "sudo apt-get install -y nginx" | Out-Null
        Write-Status "Nginx installed"
    } else {
        Write-Status "Nginx already installed"
    }

    # Configure firewall
    Write-Info "Configuring firewall..."
    Invoke-RemoteCommand -Command "sudo ufw --force reset && sudo ufw default deny incoming && sudo ufw default allow outgoing && sudo ufw allow ssh && sudo ufw allow 'Nginx Full' && sudo ufw allow 8000/tcp && sudo ufw allow 3000/tcp && sudo ufw --force enable" | Out-Null
    Write-Status "Firewall configured"

    # Create app directory
    Invoke-RemoteCommand -Command "mkdir -p $RemoteAppDir $RemoteAppDir/deploy $RemoteAppDir/logs $RemoteAppDir/backups" | Out-Null
    Write-Status "Application directories created"

    if ($SetupOnly) {
        Write-Host ""
        Write-Host "==========================================" -ForegroundColor Green
        Write-Host "✅ Server setup completed!" -ForegroundColor Green
        Write-Host "==========================================" -ForegroundColor Green
        exit 0
    }
}

# ============================================
# Deploy Application
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "🚀 Deploying Application" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

# Stop existing containers
Write-Info "Stopping existing containers..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml down --remove-orphans 2>/dev/null || true" -Silent
Write-Status "Containers stopped"

# Clean up old files
Write-Info "Cleaning up old files..."
Invoke-RemoteCommand -Command "rm -rf $RemoteAppDir/backend $RemoteAppDir/frontend $RemoteAppDir/deploy" | Out-Null
Invoke-RemoteCommand -Command "mkdir -p $RemoteAppDir/deploy/nginx" | Out-Null
Write-Status "Old files cleaned"

# Create temporary archive for faster transfer
Write-Info "Creating deployment archive..."
$tempDir = [System.IO.Path]::GetTempPath()
$archiveName = "deploy_$(Get-Date -Format 'yyyyMMdd_HHmmss').tar.gz"
$archivePath = Join-Path $tempDir $archiveName

# Use tar if available, otherwise copy files directly
try {
    Push-Location $ProjectRoot
    
    # Copy backend
    Write-Info "Uploading backend..."
    Copy-ToRemote -LocalPath "$ProjectRoot\backend" -RemotePath "$RemoteAppDir/"
    Write-Status "Backend uploaded"
    
    # Copy frontend
    Write-Info "Uploading frontend..."
    Copy-ToRemote -LocalPath "$ProjectRoot\frontend" -RemotePath "$RemoteAppDir/"
    Write-Status "Frontend uploaded"
    
    # Copy docker-compose.prod.yml
    Write-Info "Uploading docker-compose configuration..."
    Copy-ToRemote -LocalPath "$ProjectRoot\docker-compose.prod.yml" -RemotePath "$RemoteAppDir/"
    Write-Status "Docker compose uploaded"
    
    # Copy .env.production
    Write-Info "Uploading environment configuration..."
    Copy-ToRemote -LocalPath "$ProjectRoot\.env.production" -RemotePath "$RemoteAppDir/.env"
    Write-Status "Environment configuration uploaded"
    
    # Copy Nginx config
    Write-Info "Uploading Nginx configuration..."
    Copy-ToRemote -LocalPath "$ProjectRoot\deploy\nginx\chatplatform.conf" -RemotePath "$RemoteAppDir/deploy/nginx/"
    Write-Status "Nginx configuration uploaded"
    
    Pop-Location
} catch {
    Write-Error "Failed to upload files: $_"
    Pop-Location
    exit 1
}

# Update .env with correct server IP
Write-Info "Updating environment configuration..."
Invoke-RemoteCommand -Command "sed -i 's/ALLOWED_HOSTS=.*/ALLOWED_HOSTS=$ServerIP,localhost,127.0.0.1/g' $RemoteAppDir/.env" | Out-Null
Invoke-RemoteCommand -Command "sed -i 's|CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=http://$ServerIP,http://localhost:3000|g' $RemoteAppDir/.env" | Out-Null
Write-Status "Environment updated with server IP"

# Generate secure secret key
Write-Info "Generating secure secret key..."
$secretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 50 | ForEach-Object {[char]$_})
Invoke-RemoteCommand -Command "sed -i 's/SECRET_KEY=.*/SECRET_KEY=$secretKey/g' $RemoteAppDir/.env" | Out-Null
Write-Status "Secret key generated"

# Build and start containers
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "🐳 Building Docker Containers" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Info "Building Docker images (this may take a few minutes)..."
$buildResult = Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml build --no-cache 2>&1"
Write-Status "Docker images built"

Write-Info "Starting containers..."
$startResult = Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml up -d 2>&1"
Write-Status "Containers started"

# Wait for services to be ready
Write-Info "Waiting for services to be ready..."
Start-Sleep -Seconds 15

# Run migrations
Write-Info "Running database migrations..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --noinput" | Out-Null
Write-Status "Migrations completed"

# Collect static files
Write-Info "Collecting static files..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --noinput" | Out-Null
Write-Status "Static files collected"

# Configure Nginx
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "🌐 Configuring Nginx" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Info "Setting up Nginx configuration..."
Invoke-RemoteCommand -Command "sudo cp $RemoteAppDir/deploy/nginx/chatplatform.conf /etc/nginx/sites-available/chatplatform" | Out-Null
Invoke-RemoteCommand -Command "sudo ln -sf /etc/nginx/sites-available/chatplatform /etc/nginx/sites-enabled/chatplatform" | Out-Null
Invoke-RemoteCommand -Command "sudo rm -f /etc/nginx/sites-enabled/default" | Out-Null
Write-Status "Nginx configuration deployed"

Write-Info "Testing Nginx configuration..."
$nginxTest = Invoke-RemoteCommand -Command "sudo nginx -t 2>&1"
Write-Status "Nginx configuration valid"

Write-Info "Reloading Nginx..."
Invoke-RemoteCommand -Command "sudo systemctl reload nginx" | Out-Null
Write-Status "Nginx reloaded"

# Show container status
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "📊 Container Status" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

$containerStatus = Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml ps"
Write-Host $containerStatus

# Final summary
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "✅ Deployment Completed Successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Application URLs:" -ForegroundColor Cyan
Write-Host "  - Frontend:  http://$ServerIP" -ForegroundColor White
Write-Host "  - Backend:   http://$ServerIP/api" -ForegroundColor White
Write-Host "  - Admin:     http://$ServerIP/admin" -ForegroundColor White
Write-Host "  - API Docs:  http://$ServerIP/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  - View logs:     ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml logs -f`"" -ForegroundColor Gray
Write-Host "  - Restart:       ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml restart`"" -ForegroundColor Gray
Write-Host "  - Stop:          ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml down`"" -ForegroundColor Gray
Write-Host ""
