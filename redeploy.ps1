<#
.SYNOPSIS
    Quick Redeploy Script for Code Updates
    Use this when you've made code changes and want to redeploy

.DESCRIPTION
    This script updates your deployed application with code changes:
    1. Uploads updated backend/frontend code
    2. Rebuilds only changed containers
    3. Restarts services
    4. NO server setup (faster)

.PARAMETER ServerIP
    The IP address of the target server

.PARAMETER PemFile
    Path to the PEM file for SSH authentication

.PARAMETER Component
    Which component to redeploy: All, Backend, Frontend (default: All)

.EXAMPLE
    .\redeploy.ps1
    (Uses default server and redeploys everything)

.EXAMPLE
    .\redeploy.ps1 -Component Frontend
    (Only redeploys frontend)

.EXAMPLE
    .\redeploy.ps1 -ServerIP "43.152.233.234" -PemFile ".\Kribaat.pem"
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
    [ValidateSet("All", "Backend", "Frontend")]
    [string]$Component = "All"
)

# ============================================
# Configuration
# ============================================
$ErrorActionPreference = "Stop"
$RemoteAppDir = "/home/$ServerUser/$AppName"
$SSHOptions = @(
    "-o", "StrictHostKeyChecking=no",
    "-o", "UserKnownHostsFile=/dev/null",
    "-o", "LogLevel=ERROR"
)

# Colors for output
function Write-Status($message) {
    Write-Host "[OK] " -ForegroundColor Green -NoNewline
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
# Header
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Quick Redeploy - Code Updates" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""
Write-Info "Server: $ServerUser@$ServerIP"
Write-Info "Component: $Component"
Write-Host ""

# Validate PEM file
if (-not (Test-Path $PemFile)) {
    Write-ErrorMsg "PEM file not found: $PemFile"
    exit 1
}
$PemFile = (Resolve-Path $PemFile).Path

# Test SSH connection
Write-Info "Testing connection..."
try {
    $null = ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "echo Connected"
    Write-Status "Connected to server"
} catch {
    Write-ErrorMsg "Failed to connect to $ServerIP"
    exit 1
}

# ============================================
# Upload Code
# ============================================
Write-Host ""
Write-Host "Uploading updated code..." -ForegroundColor Yellow

if ($Component -eq "All" -or $Component -eq "Backend") {
    Write-Info "Uploading backend (this may take a minute)..."
    scp @SSHOptions -r -i "$PemFile" "$PSScriptRoot\backend" "${ServerUser}@${ServerIP}:$RemoteAppDir/"
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Backend upload failed"
        exit 1
    }
    Write-Status "Backend uploaded"
}

if ($Component -eq "All" -or $Component -eq "Frontend") {
    Write-Info "Uploading frontend (this may take a minute)..."
    
    # Ensure .env.production exists
    if (-not (Test-Path "$PSScriptRoot\frontend\.env.production")) {
        Write-Info "Creating frontend .env.production..."
        "VITE_API_URL=/api" | Out-File -FilePath "$PSScriptRoot\frontend\.env.production" -Encoding ASCII
    }
    
    scp @SSHOptions -r -i "$PemFile" "$PSScriptRoot\frontend" "${ServerUser}@${ServerIP}:$RemoteAppDir/"
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Frontend upload failed"
        exit 1
    }
    Write-Status "Frontend uploaded"
}

# ============================================
# Rebuild & Restart
# ============================================
Write-Host ""
Write-Host "Rebuilding containers..." -ForegroundColor Yellow

$services = switch ($Component) {
    "Backend" { "backend celery celery-beat" }
    "Frontend" { "frontend" }
    "All" { "" }  # Empty means all services
}

Write-Info "Building $Component (this may take a few minutes)..."
ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml build --no-cache $services"
Write-Status "Build completed"

Write-Info "Restarting services..."
ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml up -d --force-recreate $services"
Write-Status "Services restarted"

# Run migrations if backend changed
if ($Component -eq "All" -or $Component -eq "Backend") {
    Write-Info "Running database migrations..."
    Start-Sleep -Seconds 5  # Wait for backend to be ready
    ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --noinput"
    Write-Status "Migrations completed"
    
    Write-Info "Collecting static files..."
    ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --noinput"
    Write-Status "Static files collected"
}

# ============================================
# Status Check
# ============================================
Write-Host ""
Write-Host "Checking container status..." -ForegroundColor Yellow
$status = ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir && sudo docker compose -f docker-compose.prod.yml ps"
Write-Host $status

# ============================================
# Summary
# ============================================
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Redeployment Completed Successfully!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Your application is live at:" -ForegroundColor Cyan
Write-Host "  [HTTPS] https://kribaat.com" -ForegroundColor White
Write-Host "  [HTTPS] https://www.kribaat.com" -ForegroundColor White
Write-Host "  OR http://$ServerIP (if DNS not configured)" -ForegroundColor Gray
Write-Host ""
Write-Host "View logs:" -ForegroundColor Cyan
Write-Host "  ssh -i `"$PemFile`" $ServerUser@$ServerIP `"cd $RemoteAppDir ; sudo docker compose -f docker-compose.prod.yml logs -f $services`"" -ForegroundColor Gray
Write-Host ""
