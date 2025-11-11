# 🧪 TESTING GUIDE - Production Verification

## 📋 Test Categories

1. **Build Tests** - Verify Docker build succeeds
2. **Startup Tests** - Verify application starts correctly
3. **Health Tests** - Verify health check endpoint
4. **Database Tests** - Verify database connectivity
5. **Model Tests** - Verify model loading
6. **API Tests** - Verify API endpoints
7. **Error Tests** - Verify error handling
8. **Performance Tests** - Verify performance

---

## 🔨 BUILD TESTS

### Test 1.1: Docker Build Succeeds
```bash
# Build locally
docker build -t smartsafe-test .

# Expected output:
# ✅ Build completed successfully
# ✅ Models downloaded successfully (or lazy loading message)
```

### Test 1.2: Model Download Works
```bash
# Check build logs for:
# 📥 Downloading models...
# ✅ Models downloaded successfully
# ls -lah /app/data/models/
```

### Test 1.3: Dependencies Installed
```bash
# Check build logs for:
# Successfully installed [package count] packages
# No errors or warnings
```

---

## 🚀 STARTUP TESTS

### Test 2.1: Application Starts
```bash
# Run container
docker run -e RENDER=1 -p 5000:10000 smartsafe-test

# Expected output:
# ✅ SH17 Model Manager API'ye entegre edildi
# ✅ SmartSafe AI SaaS API Server initialized
# Your service is live 🎉
```

### Test 2.2: No Startup Errors
```bash
# Check logs for:
# ❌ No error messages
# ⚠️ No critical warnings
# ✅ All modules initialized
```

### Test 2.3: Database Connection
```bash
# Check logs for:
# ✅ PostgreSQL configuration found
# OR
# ✅ SQLite database initialized
```

---

## 🏥 HEALTH CHECK TESTS

### Test 3.1: Health Endpoint Returns 200
```bash
curl -i http://localhost:5000/health

# Expected:
# HTTP/1.1 200 OK
# {
#   "status": "ok",
#   "database": "ok",
#   "models": "ok"
# }
```

### Test 3.2: Health Endpoint Returns Correct Status
```bash
curl http://localhost:5000/health | jq .

# Expected fields:
# - status: "ok" or "degraded"
# - timestamp: ISO format
# - database: "ok" or "degraded"
# - models: "ok" or "degraded"
# - version: "1.0"
# - environment: "production" or "development"
```

### Test 3.3: Health Check Timing
```bash
time curl http://localhost:5000/health

# Expected: < 1 second
```

---

## 🗄️ DATABASE TESTS

### Test 4.1: PostgreSQL Connection
```bash
# Check logs for:
# ✅ PostgreSQL connection pool initialized
# ✅ Successfully connected to database
```

### Test 4.2: Connection Pool Works
```bash
# Make multiple requests
for i in {1..10}; do
  curl http://localhost:5000/health
done

# Expected: All succeed without connection errors
```

### Test 4.3: SQLite Fallback Works
```bash
# Simulate PostgreSQL failure by removing DATABASE_URL
unset DATABASE_URL

# Restart application
# Check logs for:
# ✅ SQLite database initialized
# ✅ Fallback to SQLite successful
```

### Test 4.4: Connection Timeout Handling
```bash
# Check logs for:
# ✅ Connection timeout: 45 seconds
# ✅ Max retries: 5
# ✅ Retry delay: exponential backoff
```

---

## 🤖 MODEL TESTS

### Test 5.1: Models Load Successfully
```bash
# Check logs for:
# ✅ Fallback model yüklendi
# ✅ YOLOv8n fallback model başarıyla indirildi
```

### Test 5.2: Model Paths Resolved
```bash
# Check logs for:
# ✅ Found model at: /app/data/models/yolov8n.pt
# OR
# ✅ Found model at: data/models/yolov8n.pt
```

### Test 5.3: Lazy Loading Works
```bash
# In production mode, check logs for:
# 🔄 Lazy loading: [sector] modeli yükleniyor...
# ✅ [sector] modeli lazy loading ile yüklendi
```

### Test 5.4: Model Fallback Chain
```bash
# Simulate missing models
# Check logs for:
# 1. Try pre-downloaded models
# 2. Try alternative paths
# 3. Auto-download models
# 4. Use fallback model
```

---

## 🔌 API TESTS

### Test 6.1: Demo Request Endpoint
```bash
curl -X POST http://localhost:5000/api/request-demo \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "Test Company",
    "sector": "construction",
    "contact_email": "test@example.com",
    "contact_name": "Test User"
  }'

# Expected: 200 OK (not 502)
# Response: {"success": true, ...}
```

### Test 6.2: Company Creation
```bash
curl -X POST http://localhost:5000/api/companies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Company",
    "sector": "construction"
  }'

# Expected: 200 OK
# Response: {"id": "...", "name": "Test Company"}
```

### Test 6.3: API Response Time
```bash
time curl http://localhost:5000/api/companies

# Expected: < 500ms
```

### Test 6.4: API Error Handling
```bash
# Test 404
curl http://localhost:5000/api/nonexistent
# Expected: 404 with error message

# Test 400
curl -X POST http://localhost:5000/api/request-demo \
  -H "Content-Type: application/json" \
  -d '{}'
# Expected: 400 with validation error
```

---

## ⚠️ ERROR HANDLING TESTS

### Test 7.1: 404 Error Handler
```bash
curl -i http://localhost:5000/api/nonexistent

# Expected:
# HTTP/1.1 404 Not Found
# {
#   "error": "Resource not found",
#   "code": "NOT_FOUND"
# }
```

### Test 7.2: 500 Error Handler
```bash
# Trigger internal error
curl -X POST http://localhost:5000/api/invalid \
  -H "Content-Type: application/json" \
  -d 'invalid json'

# Expected:
# HTTP/1.1 500 Internal Server Error
# {
#   "error": "Internal server error",
#   "code": "INTERNAL_ERROR"
# }
```

### Test 7.3: Error Logging
```bash
# Check logs for:
# ❌ [Error level] - Error message with context
# ✅ Stack trace included
# ✅ Timestamp recorded
```

### Test 7.4: Production Error Messages
```bash
# In production mode, check:
# ✅ Error messages don't expose sensitive data
# ✅ Stack traces not shown to users
# ✅ Generic error messages in responses
```

---

## ⚡ PERFORMANCE TESTS

### Test 8.1: Cold Start Time
```bash
# Restart container
docker restart smartsafe-test

# Measure time until:
# Your service is live 🎉

# Expected: 15-30 seconds
```

### Test 8.2: Warm Start Time
```bash
# After first request, restart container
# Measure time until ready

# Expected: 2-5 seconds
```

### Test 8.3: Request Latency
```bash
# Make 100 requests and measure
for i in {1..100}; do
  time curl http://localhost:5000/health
done

# Expected: 100-500ms average
```

### Test 8.4: Model Inference Time
```bash
# Send detection request
time curl -X POST http://localhost:5000/api/detect \
  -H "Content-Type: application/json" \
  -d '{"image": "..."}'

# Expected: 1-3 seconds
```

### Test 8.5: Concurrent Requests
```bash
# Send 10 concurrent requests
ab -n 100 -c 10 http://localhost:5000/health

# Expected:
# Requests per second: > 10
# Failed requests: 0
# Connection errors: 0
```

---

## 📊 LOAD TESTS

### Test 9.1: Connection Pool Under Load
```bash
# Send 50 concurrent requests
ab -n 500 -c 50 http://localhost:5000/health

# Expected:
# ✅ All requests succeed
# ✅ No connection pool exhaustion
# ✅ Response time < 1s
```

### Test 9.2: Database Under Load
```bash
# Send 100 database queries
for i in {1..100}; do
  curl http://localhost:5000/api/companies &
done
wait

# Expected:
# ✅ All succeed
# ✅ No connection errors
# ✅ No timeouts
```

### Test 9.3: Model Inference Under Load
```bash
# Send 20 concurrent detection requests
for i in {1..20}; do
  curl -X POST http://localhost:5000/api/detect \
    -H "Content-Type: application/json" \
    -d '{"image": "..."}' &
done
wait

# Expected:
# ✅ All succeed
# ✅ No out-of-memory errors
# ✅ Response time < 5s
```

---

## 🔐 SECURITY TESTS

### Test 10.1: SSL/TLS Enabled
```bash
curl -i https://app.getsmartsafeai.com/health

# Expected:
# HTTP/1.1 200 OK
# Secure connection
```

### Test 10.2: Error Messages Safe
```bash
# Trigger error and check response
curl http://localhost:5000/api/invalid

# Expected:
# ✅ No stack traces in response
# ✅ No file paths exposed
# ✅ No database details exposed
```

### Test 10.3: Environment Variables Protected
```bash
# Check logs for:
# ✅ No DATABASE_URL logged
# ✅ No API keys logged
# ✅ No passwords logged
```

---

## 📋 TEST CHECKLIST

### Pre-Deployment
- [ ] Build test passes
- [ ] Startup test passes
- [ ] Health check test passes
- [ ] Database test passes
- [ ] Model test passes
- [ ] API test passes
- [ ] Error handling test passes
- [ ] Performance test passes

### Post-Deployment
- [ ] Production health check works
- [ ] Production API endpoints work
- [ ] Production database connected
- [ ] Production models loaded
- [ ] Production error handling works
- [ ] Production performance acceptable

### Ongoing
- [ ] Daily health check
- [ ] Weekly load test
- [ ] Monthly security audit
- [ ] Quarterly performance review

---

## 🎯 SUCCESS CRITERIA

### All Tests Pass When:
- ✅ Build completes without errors
- ✅ Application starts successfully
- ✅ Health check returns 200 OK
- ✅ Database connection established
- ✅ Models load successfully
- ✅ API endpoints respond correctly
- ✅ Error handlers work properly
- ✅ Performance meets expectations

### Deployment Ready When:
- ✅ All tests pass locally
- ✅ All tests pass in production
- ✅ No errors in logs
- ✅ No performance issues
- ✅ No security issues
- ✅ Documentation complete

---

## 📞 DEBUGGING

### If Test Fails
1. Check error message
2. Review relevant logs
3. Check configuration
4. Verify environment variables
5. Review code changes
6. Test in isolation

### Common Issues
- **Build fails:** Check Dockerfile, dependencies
- **Startup fails:** Check imports, configuration
- **Health check fails:** Check database, models
- **API fails:** Check routes, error handlers
- **Performance slow:** Check cold start, connection pool

---

**Test Suite Version:** 1.0
**Last Updated:** November 11, 2025
**Status:** ✅ Ready for Testing
