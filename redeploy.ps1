<#
.SYNOPSIS
    Quick Redeploy Script for Code Updates
    Use this when you've made code changes and want to redeploy

.DESCRIPTION
    This script updates your deployed application with code changes:
    1. Uploads updated backend/frontend code (using smart tarball method)
    2. Rebuilds only changed containers
    3. Restarts services
    4. NO server setup (faster)
    
    OPTIMIZATIONS:
    - Backend: Tarball upload (~15 seconds vs 2-3 minutes)
      • Excludes: __pycache__, .pyc, .pyo, celerybeat-schedule, staticfiles
      • Only uploads source code and essential files
    
    - Frontend: Dist tarball upload (~10 seconds vs 30+ minutes)
      • Pre-built dist folder compressed and uploaded
      • Skips uploading node_modules entirely

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
    Write-Info "Smart backend deployment (tarball approach - much faster!)..."
    
    # Create tarball of backend files (exclude unnecessary files)
    Write-Info "Creating backend tarball (excluding cache/temp files)..."
    $backendTarFile = "backend-deploy-$(Get-Date -Format 'yyyyMMddHHmmss').tar.gz"
    $backendTarPath = Join-Path $PSScriptRoot $backendTarFile
    
    # Exclude patterns: __pycache__, .pyc, .pyo, celerybeat-schedule, .env, db.sqlite3, staticfiles cache
    & tar -C "$PSScriptRoot" -czf $backendTarPath `
        --exclude='__pycache__' `
        --exclude='*.pyc' `
        --exclude='*.pyo' `
        --exclude='celerybeat-schedule' `
        --exclude='db.sqlite3' `
        --exclude='.env' `
        --exclude='*.log' `
        --exclude='staticfiles' `
        backend 2>&1 | Out-Null
    
    if (-not (Test-Path $backendTarPath)) {
        Write-ErrorMsg "Failed to create backend tarball"
        exit 1
    }
    
    $backendTarSize = (Get-Item $backendTarPath).Length / 1MB
    $roundedBackendTarSize = [math]::Round($backendTarSize, 2)
    Write-Status "Backend tarball created: $roundedBackendTarSize MB"
    
    # Upload tarball
    Write-Info "Uploading backend tarball (fast!)..."
    $uploadStart = Get-Date
    scp @SSHOptions -i "$PemFile" $backendTarPath "${ServerUser}@${ServerIP}:/home/$ServerUser/"
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $backendTarPath -ErrorAction SilentlyContinue
        Write-ErrorMsg "Backend upload failed"
        exit 1
    }
    $uploadDuration = [math]::Round(((Get-Date) - $uploadStart).TotalSeconds, 1)
    Write-Status "Backend uploaded in $uploadDuration seconds (tarball method)"
    
    # Extract on server
    Write-Info "Extracting backend files on server..."
    ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir; rm -rf backend; tar -xzf /home/$ServerUser/$backendTarFile; rm /home/$ServerUser/$backendTarFile"
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $backendTarPath -ErrorAction SilentlyContinue
        Write-ErrorMsg "Failed to extract backend on server"
        exit 1
    }
    Write-Status "Backend files extracted"
    
    # Clean up local tarball
    Remove-Item $backendTarPath -ErrorAction SilentlyContinue
    Write-Status "Backend deployed (tarball method - 10-15 seconds vs several minutes!)"
}

if ($Component -eq "All" -or $Component -eq "Frontend") {
    Write-Info "Smart frontend deployment (pre-built dist folder)..."
    
    # Check if dist folder exists - if not, build it
    if (-not (Test-Path "$PSScriptRoot\frontend\dist")) {
        Write-Info "Building frontend (dist folder not found)..."
        $buildLocation = Get-Location
        Set-Location "$PSScriptRoot\frontend"
        
        # Install dependencies if node_modules is missing
        if (-not (Test-Path "node_modules")) {
            Write-Info "Installing frontend dependencies..."
            npm install
        }
        
        # Build for production
        npm run build
        Set-Location $buildLocation
        
        if (-not (Test-Path "$PSScriptRoot\frontend\dist")) {
            Write-ErrorMsg "Frontend build failed - dist folder not created"
            exit 1
        }
        Write-Status "Frontend built successfully"
    } else {
        $distFolder = Get-Item "$PSScriptRoot\frontend\dist"
        $lastBuildTime = $distFolder.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
        Write-Info "Using existing dist folder (built $lastBuildTime)"
        Write-Host "   💡 To rebuild: " -NoNewline -ForegroundColor Yellow
        Write-Host "cd frontend && npm run build" -ForegroundColor Gray
    }
    
    $distSize = (Get-ChildItem -Recurse "$PSScriptRoot\frontend\dist" | Measure-Object -Property Length -Sum).Sum / 1MB
    $roundedSize = [math]::Round($distSize, 2)
    Write-Info "Dist folder size: $roundedSize MB"
    
    # Ensure .dockerignore allows dist folder for production
    Write-Info "Updating .dockerignore to include dist folder..."
    $dockerignoreContent = @"
# Build artifacts excluded during development
# For production deployment, dist/ is needed and included
node_modules
.env.local
.env.development
*.log
.vscode
.git
"@
    $dockerignoreContent | Out-File -FilePath "$PSScriptRoot\frontend\.dockerignore" -Encoding UTF8 -NoNewline
    Write-Status ".dockerignore updated for production"
    
    # Create tarball of deployment files
    Write-Info "Creating deployment tarball..."
    $tarFile = "frontend-deploy-$(Get-Date -Format 'yyyyMMddHHmmss').tar.gz"
    $tarPath = Join-Path $PSScriptRoot $tarFile
    & tar -C "$PSScriptRoot\frontend" -czf $tarPath dist Dockerfile.prod nginx.conf .dockerignore 2>&1 | Out-Null
    
    if (-not (Test-Path $tarPath)) {
        Write-ErrorMsg "Failed to create frontend tarball"
        exit 1
    }
    
    $tarSize = (Get-Item $tarPath).Length / 1MB
    $roundedTarSize = [math]::Round($tarSize, 2)
    Write-Status "Tarball created: $roundedTarSize MB (includes dist folder)"
    
    # Upload tarball
    Write-Info "Uploading tarball (fast!)..."
    $uploadStart = Get-Date
    scp @SSHOptions -i "$PemFile" $tarPath "${ServerUser}@${ServerIP}:/home/$ServerUser/"
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $tarPath -ErrorAction SilentlyContinue
        Write-ErrorMsg "Frontend upload failed"
        exit 1
    }
    $uploadDuration = [math]::Round(((Get-Date) - $uploadStart).TotalSeconds, 1)
    Write-Status "Upload completed in $uploadDuration seconds"
    
    # Extract on server
    Write-Info "Extracting files on server..."
    ssh @SSHOptions -i "$PemFile" "${ServerUser}@${ServerIP}" "cd $RemoteAppDir/frontend; tar -xzf /home/$ServerUser/$tarFile; rm /home/$ServerUser/$tarFile"
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $tarPath -ErrorAction SilentlyContinue
        Write-ErrorMsg "Failed to extract frontend on server"
        exit 1
    }
    Write-Status "Files extracted"
    
    # Clean up local tarball
    Remove-Item $tarPath -ErrorAction SilentlyContinue
    Write-Status "Frontend deployed (includes pre-built dist folder)"
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
