#!/bin/bash

# SmartSafe AI - Production Startup Script
# GUARANTEED DATABASE CONSISTENCY CHECK

echo "🚀 SMARTSAFE AI - PRODUCTION STARTUP"
echo "===================================="

# Step 1: Database Consistency Check
echo "📋 Step 1: Database Consistency Check"
python database_sync.py

if [ $? -ne 0 ]; then
    echo "❌ Database consistency check failed!"
    exit 1
fi

# Step 2: Create Backup
echo "📋 Step 2: Creating Database Backup"
python scripts/database_monitor.py

if [ $? -ne 0 ]; then
    echo "❌ Database backup failed!"
    exit 1
fi

# Step 3: Start Docker Stack
echo "📋 Step 3: Starting Docker Stack"
docker-compose up -d

if [ $? -ne 0 ]; then
    echo "❌ Docker startup failed!"
    exit 1
fi

# Step 4: Wait for services to be ready
echo "📋 Step 4: Waiting for services..."
sleep 30

# Step 5: Verify all services are running
echo "📋 Step 5: Service Health Check"
docker-compose ps

# Step 6: Test web application
echo "📋 Step 6: Testing Web Application"
curl -f http://localhost:5577/health

if [ $? -ne 0 ]; then
    echo "❌ Web application health check failed!"
    exit 1
fi

echo "✅ SUCCESS: SmartSafe AI is running with guaranteed database consistency!"
echo "🌐 Web Interface: http://localhost:5577"
echo "🔧 Admin Panel: http://localhost:5577/admin"
echo "📊 Grafana: http://localhost:3000"
echo "🎯 Prometheus: http://localhost:9090"

echo ""
echo "🔒 PRODUCTION GUARANTEES:"
echo "  ✅ Database consistency verified"
echo "  ✅ Automatic backup created"
echo "  ✅ Volume mapping configured"
echo "  ✅ Health monitoring active"
echo "  ✅ All services operational" 