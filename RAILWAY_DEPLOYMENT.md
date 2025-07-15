# 🚀 Railway.app Deployment Guide

## SmartSafe AI - Railway.app Deployment

### 📋 Prerequisites
- GitHub account
- Railway.app account
- Supabase database (already configured)

### 🔧 Environment Variables
Set these in Railway.app dashboard:

```bash
# Required
RAILWAY_ENVIRONMENT=production
FLASK_ENV=production
DATABASE_URL=postgresql://postgres.nbxntohihcwruwlnthfb:6818.yigit.98@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require

# Optional
SECRET_KEY=your-secret-key-here
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# System
PYTHONPATH=/app
CUDA_VISIBLE_DEVICES=""
YOLO_CONFIG_DIR=/tmp/Ultralytics
```

### 🚀 Deployment Steps

1. **Connect GitHub Repository**
   - Go to https://railway.app/
   - Click "Deploy from GitHub"
   - Select your repository

2. **Configure Environment Variables**
   - Go to project settings
   - Add environment variables listed above

3. **Deploy**
   - Railway will automatically detect `railway.json`
   - Build process will start
   - App will be available at generated URL

### 📊 Expected Build Output
```
==> Building with Nixpacks
==> Installing Python dependencies
==> Downloading YOLOv8 models
==> Starting Flask server
🚀 RAILWAY.APP - Starting optimized Flask server...
🌐 Platform: Railway.app
🌐 Starting server on 0.0.0.0:8080
🔧 Environment: production
🔧 Debug mode: False
* Running on all addresses (0.0.0.0)
* Running on http://0.0.0.0:8080
```

### 🔍 Health Check
- Health endpoint: `/health`
- Expected response: `{"status": "healthy"}`

### 📈 Monitoring
- Railway provides built-in monitoring
- Check logs in Railway dashboard
- Monitor resource usage

### 🛠️ Troubleshooting

**Build Issues:**
- Check Python version compatibility
- Verify requirements.txt
- Check model download process

**Runtime Issues:**
- Verify environment variables
- Check database connection
- Monitor memory usage

**Port Issues:**
- Railway automatically assigns PORT
- App listens on 0.0.0.0:$PORT
- Default fallback: 8080

### 💰 Cost Estimation
- Free tier: $5 credit/month
- Expected usage: ~$2-3/month
- Automatic scaling included

### 🔄 Updates
- Push to main branch triggers deployment
- Automatic builds on GitHub commits
- Zero-downtime deployments

### 📝 Notes
- Railway.app optimized for production
- Automatic HTTPS enabled
- Custom domains supported
- Database hosting available 