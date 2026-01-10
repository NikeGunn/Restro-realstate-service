# Direct vite build bypassing npm
$ErrorActionPreference = "Stop"

Write-Host "Building frontend directly with vite..." -ForegroundColor Cyan

$frontendPath = "C:\Users\Nautilus\Desktop\RESTRO\Restro & real estate\frontend"
Set-Location $frontendPath

# Clean dist
if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
    Write-Host "Cleaned old dist folder" -ForegroundColor Yellow
}

# Run vite directly
Write-Host "Running vite build..." -ForegroundColor Yellow
& node .\node_modules\vite\bin\vite.js build

if (Test-Path "dist") {
    $distSize = (Get-ChildItem -Recurse "dist" | Measure-Object -Property Length -Sum).Sum / 1MB
    Write-Host "✅ Build successful! Size: $([math]::Round($distSize, 2)) MB" -ForegroundColor Green
    
    Write-Host ""
    Write-Host "Now deploy with:" -ForegroundColor Yellow
    Write-Host "  cd .." -ForegroundColor Gray
    Write-Host "  .\redeploy.ps1 -Component Frontend" -ForegroundColor Gray
} else {
    Write-Host "❌ Build failed - dist folder not created" -ForegroundColor Red
    exit 1
}
