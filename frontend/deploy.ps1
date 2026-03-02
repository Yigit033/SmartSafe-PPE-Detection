# SmartSafe AI - Vercel Quick Deploy Script
# Bu script Windows PowerShell için hazırlanmıştır

Write-Host "================================" -ForegroundColor Cyan
Write-Host "SmartSafe AI - Vercel Deploy" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# Check if Vercel CLI is installed
Write-Host "Checking Vercel CLI..." -ForegroundColor Yellow
$vercelInstalled = Get-Command vercel -ErrorAction SilentlyContinue

if (-not $vercelInstalled) {
    Write-Host "Vercel CLI not found! Installing..." -ForegroundColor Red
    npm install -g vercel
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error installing Vercel CLI. Please run manually:" -ForegroundColor Red
        Write-Host "  npm install -g vercel" -ForegroundColor White
        exit 1
    }
    Write-Host "Vercel CLI installed successfully!" -ForegroundColor Green
} else {
    Write-Host "Vercel CLI found!" -ForegroundColor Green
}

Write-Host ""
Write-Host "Select deployment type:" -ForegroundColor Yellow
Write-Host "1. Preview Deploy (test)" -ForegroundColor White
Write-Host "2. Production Deploy" -ForegroundColor White
Write-Host ""

$choice = Read-Host "Enter choice (1 or 2)"

switch ($choice) {
    "1" {
        Write-Host ""
        Write-Host "Deploying to Preview..." -ForegroundColor Cyan
        vercel
    }
    "2" {
        Write-Host ""
        Write-Host "Deploying to Production..." -ForegroundColor Cyan
        vercel --prod
    }
    default {
        Write-Host "Invalid choice. Exiting..." -ForegroundColor Red
        exit 1
    }
}

Write-Host ""
Write-Host "================================" -ForegroundColor Green
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "================================" -ForegroundColor Green
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Test your deployment URL" -ForegroundColor White
Write-Host "2. Check landing page loads instantly" -ForegroundColor White
Write-Host "3. Test contact form" -ForegroundColor White
Write-Host "4. Test demo request" -ForegroundColor White
Write-Host ""
Write-Host "Need help? Check VERCEL_DEPLOYMENT_GUIDE.md" -ForegroundColor Cyan

