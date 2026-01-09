# Quick fix and restart for current deployment issues
param(
    [Parameter(Mandatory=$false)]
    [string]$ServerIP = "43.152.233.234",
    [Parameter(Mandatory=$false)]
    [string]$PemFile = "$PSScriptRoot\Kribaat.pem"
)

$RemoteAppDir = "/home/ubuntu/chatplatform"
$SSHOptions = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"

Write-Host "`n[QUICK FIX] Fixing deployment issues...`n" -ForegroundColor Cyan

# Upload .env with correct password
Write-Host "[INFO] Uploading corrected .env file..." -ForegroundColor Cyan
& scp $SSHOptions.Split(' ') -i $PemFile "$PSScriptRoot\.env.production" "ubuntu@${ServerIP}:$RemoteAppDir/.env"

# Restart containers
Write-Host "[INFO] Restarting containers..." -ForegroundColor Cyan
& ssh $SSHOptions.Split(' ') -i $PemFile "ubuntu@$ServerIP" "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml down; sudo docker compose -f docker-compose.prod.yml up -d"

Write-Host "[INFO] Waiting for containers to be ready..." -ForegroundColor Yellow
Start-Sleep -Seconds 20

# Run migrations
Write-Host "[INFO] Running database migrations..." -ForegroundColor Cyan
& ssh $SSHOptions.Split(' ') -i $PemFile "ubuntu@$ServerIP" "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py migrate --noinput"

# Collect static files
Write-Host "[INFO] Collecting static files..." -ForegroundColor Cyan
& ssh $SSHOptions.Split(' ') -i $PemFile "ubuntu@$ServerIP" "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml exec -T backend python manage.py collectstatic --noinput"

# Check status
Write-Host "`n[INFO] Container Status:" -ForegroundColor Cyan
& ssh $SSHOptions.Split(' ') -i $PemFile "ubuntu@$ServerIP" "cd $RemoteAppDir; sudo docker compose -f docker-compose.prod.yml ps"

Write-Host "`n[SUCCESS] Deployment fixed!`n" -ForegroundColor Green
Write-Host "Your application is now live at:" -ForegroundColor Cyan
Write-Host "  - https://kribaat.com" -ForegroundColor White
Write-Host "  - https://www.kribaat.com`n" -ForegroundColor White
