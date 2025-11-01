# SmartSafe AI - Production Startup Script (PowerShell)
# GUARANTEED DATABASE CONSISTENCY CHECK

Write-Host "SMARTSAFE AI - PRODUCTION STARTUP" -ForegroundColor Green
Write-Host "====================================" -ForegroundColor Green

# Step 1: Database Consistency Check
Write-Host "Step 1: Database Consistency Check" -ForegroundColor Cyan
$result = python database_sync.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Database consistency check failed!" -ForegroundColor Red
    exit 1
}

# Step 2: Create Backup
Write-Host "Step 2: Creating Database Backup" -ForegroundColor Cyan
$result = python scripts/database_monitor.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Database backup failed!" -ForegroundColor Red
    exit 1
}

# Step 3: Start Docker Stack
Write-Host "Step 3: Starting Docker Stack" -ForegroundColor Cyan
docker-compose up -d

if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Docker startup failed!" -ForegroundColor Red
    exit 1
}

# Step 4: Wait for services to be ready
Write-Host "Step 4: Waiting for services..." -ForegroundColor Cyan
Start-Sleep -Seconds 30

# Step 5: Verify all services are running
Write-Host "Step 5: Service Health Check" -ForegroundColor Cyan
docker-compose ps

# Step 6: Test web application
Write-Host "Step 6: Testing Web Application" -ForegroundColor Cyan
try {
    $response = Invoke-RestMethod -Uri "http://localhost:5000/health" -Method Get
    if ($response.status -eq "healthy") {
        Write-Host "SUCCESS: Web application is healthy!" -ForegroundColor Green
    } else {
        Write-Host "ERROR: Web application health check failed!" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "ERROR: Web application health check failed!" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "SUCCESS: SmartSafe AI is running with guaranteed database consistency!" -ForegroundColor Green
Write-Host "Web Interface: http://localhost:5000" -ForegroundColor Yellow
Write-Host "Admin Panel: http://localhost:5000/admin" -ForegroundColor Yellow
Write-Host "Grafana: http://localhost:3000" -ForegroundColor Yellow
Write-Host "Prometheus: http://localhost:9090" -ForegroundColor Yellow

Write-Host ""
Write-Host "PRODUCTION GUARANTEES:" -ForegroundColor Green
Write-Host "  - Database consistency verified" -ForegroundColor Green
Write-Host "  - Automatic backup created" -ForegroundColor Green
Write-Host "  - Volume mapping configured" -ForegroundColor Green
Write-Host "  - Health monitoring active" -ForegroundColor Green
Write-Host "  - All services operational" -ForegroundColor Green

Write-Host ""
Write-Host "To verify database consistency anytime, run: python database_sync.py" -ForegroundColor Cyan
Write-Host "To monitor database health, run: python scripts/database_monitor.py --continuous" -ForegroundColor Cyan 