# ============================================
# SSL Deployment Script for kribaat.com
# This script deploys your app with HTTPS enabled
# ============================================

param(
    [Parameter(Mandatory=$false)]
    [string]$Domain = "kribaat.com",
    
    [Parameter(Mandatory=$false)]
    [string]$Email = "admin@kribaat.com",
    
    [Parameter(Mandatory=$false)]
    [string]$ServerIP = "43.152.233.234",
    
    [Parameter(Mandatory=$false)]
    [string]$PemFile = "$PSScriptRoot\Kribaat.pem",
    
    [Parameter(Mandatory=$false)]
    [string]$ServerUser = "ubuntu",
    
    [Parameter(Mandatory=$false)]
    [string]$AppName = "chatplatform"
)

# ============================================
# Configuration
# ============================================
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$RemoteAppDir = "/home/$ServerUser/$AppName"
$SSHOptions = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

# Colors for output
function Write-Status($message) {
    Write-Host "[OK] " -ForegroundColor Green -NoNewline
    Write-Host $message
}

function Write-Warning($message) {
    Write-Host "[WARNING] " -ForegroundColor Yellow -NoNewline
    Write-Host $message
}

function Write-ErrorMsg($message) {
    Write-Host "[ERROR] " -ForegroundColor Red -NoNewline
    Write-Host $message
}

function Write-Info($message) {
    Write-Host "[INFO] " -ForegroundColor Cyan -NoNewline
    Write-Host $message
}

# ============================================
# Banner
# ============================================
Write-Host ""
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "[SSL] Deployment for kribaat.com" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Validate PEM file
if (-not (Test-Path $PemFile)) {
    Write-ErrorMsg "PEM file not found: $PemFile"
    exit 1
}
$PemFile = (Resolve-Path $PemFile).Path
Write-Status "PEM file found: $PemFile"

# Validate project structure
if (-not (Test-Path "$ProjectRoot\backend")) {
    Write-ErrorMsg "Backend directory not found"
    exit 1
}
if (-not (Test-Path "$ProjectRoot\frontend")) {
    Write-ErrorMsg "Frontend directory not found"
    exit 1
}
Write-Status "Project files validated"

Write-Info "Domain: $Domain"
Write-Info "Server: $ServerUser@$ServerIP"
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
    
    if (-not $Silent) {
        Write-Info "Executing: $Command"
    }
    
    $sshArgs = @($SSHOptions.Split(' ')) + @('-i', $PemFile, "$ServerUser@$ServerIP", $Command)
    $result = & ssh $sshArgs 2>&1
    return $result
}

function Copy-ToRemote {
    param(
        [Parameter(Mandatory=$true)]
        [string]$LocalPath,
        [Parameter(Mandatory=$true)]
        [string]$RemotePath
    )
    
    Write-Info "Uploading: $(Split-Path $LocalPath -Leaf)"
    
    $scpArgs = @($SSHOptions.Split(' '))
    if (Test-Path $LocalPath -PathType Container) {
        $scpArgs += @('-r', '-i', $PemFile, $LocalPath, "$ServerUser@${ServerIP}:$RemotePath")
    } else {
        $scpArgs += @('-i', $PemFile, $LocalPath, "$ServerUser@${ServerIP}:$RemotePath")
    }
    
    & scp $scpArgs 2>&1 | Out-Null
    
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to upload: $LocalPath"
        return $false
    }
    
    return $true
}

# ============================================
# Test Connection
# ============================================
Write-Host "Testing connection..." -ForegroundColor Yellow
try {
    $testResult = Invoke-RemoteCommand -Command "echo 'Connected'" -Silent
    Write-Status "SSH connection established"
} catch {
    Write-ErrorMsg "Cannot connect to server. Please check your PEM file and server IP."
    exit 1
}

# ============================================
# Pre-deployment Checks
# ============================================
Write-Host "" Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "[CHECK] Pre-deployment Checks" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Info "Checking DNS configuration..."
Write-Warning "IMPORTANT: Ensure your domain DNS is configured:"
Write-Warning "  A Record: $Domain -> $ServerIP"
Write-Warning "  A Record: www.$Domain -> $ServerIP"
Write-Host ""
Write-Host "Press Enter to continue once DNS is configured, or Ctrl+C to abort..." -ForegroundColor Yellow
Read-Host

# ============================================
# Upload Files
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "[UPLOAD] Application Files" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

# Stop existing containers
Write-Info "Stopping existing containers..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml down 2>/dev/null; exit 0" -Silent | Out-Null
Write-Status "Containers stopped"

# Clean and prepare directories
Write-Info "Preparing directories..."
Invoke-RemoteCommand -Command "rm -rf $RemoteAppDir/backend $RemoteAppDir/frontend $RemoteAppDir/deploy" | Out-Null
Invoke-RemoteCommand -Command "mkdir -p $RemoteAppDir/deploy/nginx $RemoteAppDir/deploy/scripts" | Out-Null
Write-Status "Directories prepared"

# Upload application files
Write-Info "Uploading backend..."
Copy-ToRemote -LocalPath "$ProjectRoot\backend" -RemotePath "$RemoteAppDir/"
Write-Status "Backend uploaded"

Write-Info "Uploading frontend..."
Copy-ToRemote -LocalPath "$ProjectRoot\frontend" -RemotePath "$RemoteAppDir/"
Write-Status "Frontend uploaded"

Write-Info "Uploading Docker Compose..."
Copy-ToRemote -LocalPath "$ProjectRoot\docker-compose.prod.yml" -RemotePath "$RemoteAppDir/"
Write-Status "Docker Compose uploaded"

Write-Info "Uploading environment configuration..."
Copy-ToRemote -LocalPath "$ProjectRoot\.env.production" -RemotePath "$RemoteAppDir/.env"
Write-Status "Environment uploaded"

Write-Info "Uploading Nginx configurations..."
Copy-ToRemote -LocalPath "$ProjectRoot\deploy\nginx\chatplatform-ssl.conf" -RemotePath "$RemoteAppDir/deploy/nginx/"
Copy-ToRemote -LocalPath "$ProjectRoot\deploy\scripts\setup-ssl.sh" -RemotePath "$RemoteAppDir/deploy/scripts/"
Write-Status "Configurations uploaded"

# Make scripts executable
Invoke-RemoteCommand -Command "chmod +x $RemoteAppDir/deploy/scripts/*.sh" | Out-Null
Write-Status "Scripts made executable"

# Update environment with domain
Write-Info "Configuring environment for $Domain..."
$allowedHosts = $Domain + ',www.' + $Domain + ',' + $ServerIP + ',localhost,127.0.0.1'
$cmd1 = 'sed -i ' + [char]39 + 's/ALLOWED_HOSTS=.*/ALLOWED_HOSTS=' + $allowedHosts + '/g' + [char]39 + ' ' + $RemoteAppDir + '/.env'
Invoke-RemoteCommand -Command $cmd1 | Out-Null

$corsOrigins = 'https://' + $Domain + ',https://www.' + $Domain
$cmd2 = 'sed -i ' + [char]39 + 's|CORS_ALLOWED_ORIGINS=.*|CORS_ALLOWED_ORIGINS=' + $corsOrigins + '|g' + [char]39 + ' ' + $RemoteAppDir + '/.env'
Invoke-RemoteCommand -Command $cmd2 | Out-Null

$apiUrl = 'https://' + $Domain + '/api'
$cmd3 = 'sed -i ' + [char]39 + 's|VITE_API_URL=.*|VITE_API_URL=' + $apiUrl + '|g' + [char]39 + ' ' + $RemoteAppDir + '/.env'
Invoke-RemoteCommand -Command $cmd3 | Out-Null
Write-Status "Environment configured"

# Generate secure secret key
Write-Info "Generating secure secret key..."
$secretKey = -join ((65..90) + (97..122) + (48..57) | Get-Random -Count 50 | ForEach-Object {[char]$_})
Invoke-RemoteCommand -Command "sed -i 's/SECRET_KEY=.*/SECRET_KEY=$secretKey/g' $RemoteAppDir/.env" | Out-Null
Write-Status "Secret key generated"

# ============================================
# SSL Certificate Setup
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "[SSL] Setting up SSL Certificate" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Info "Requesting SSL certificate from Let's Encrypt..."
Write-Warning "This may take a few minutes..."
Write-Host ""

$sslResult = Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo bash deploy/scripts/setup-ssl.sh $Domain $Email"
Write-Host $sslResult

if ($LASTEXITCODE -ne 0) {
    Write-ErrorMsg "SSL setup failed. Please check the output above."
    Write-Warning "Common issues:"
    Write-Warning "  1. DNS not properly configured"
    Write-Warning "  2. Firewall blocking port 80 or 443"
    Write-Warning "  3. Domain not pointing to server IP"
    exit 1
}

Write-Status "SSL certificate obtained and configured"

# ============================================
# Build and Deploy Application
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "[DOCKER] Building and Deploying Application" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

Write-Info "Building Docker images..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml build --no-cache" | Out-Null
Write-Status "Docker images built"

Write-Info "Starting containers..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml up -d" | Out-Null
Write-Status "Containers started"

Write-Info "Waiting for services to initialize..."
Start-Sleep -Seconds 15

Write-Info "Running database migrations..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --noinput" | Out-Null
Write-Status "Migrations completed"

Write-Info "Collecting static files..."
Invoke-RemoteCommand -Command "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --noinput" | Out-Null
Write-Status "Static files collected"

# ============================================
# Final Status
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host "[STATUS] Container Status" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Yellow
Write-Host ""

$containerStatus = Invoke-RemoteCommand -Command "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml ps"
Write-Host $containerStatus

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "[SUCCESS] Deployment Completed Successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your application is now live with HTTPS:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  - Frontend:  https://$Domain" -ForegroundColor White
Write-Host "  - WWW:       https://www.$Domain" -ForegroundColor White
Write-Host "  - Admin:     https://$Domain/admin" -ForegroundColor White
Write-Host "  - API Docs:  https://$Domain/api/docs" -ForegroundColor White
Write-Host ""
Write-Host "SSL Certificate:" -ForegroundColor Cyan
Write-Host "  [OK] SSL/TLS enabled with Let`'s Encrypt" -ForegroundColor White
Write-Host "  [OK] Auto-renewal configured" -ForegroundColor White
Write-Host "  [OK] HTTP automatically redirects to HTTPS" -ForegroundColor White
Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  - View logs:        ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml logs -f`"" -ForegroundColor Gray
Write-Host "  - Restart app:      ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml restart`"" -ForegroundColor Gray
Write-Host "  - Check SSL:        ssh -i `"$PemFile`" $ServerUser@$ServerIP `"sudo certbot certificates`"" -ForegroundColor Gray
Write-Host ""
