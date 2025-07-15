# 🚀 Fly.io Deployment Guide - 100% FREE

## SmartSafe AI - Fly.io Free Deployment

### 🆓 Why Fly.io?
- ✅ **Generous free tier** (3 shared-cpu apps)
- ✅ **160GB bandwidth/month**
- ✅ **Professional platform**
- ✅ **No credit card required**
- ✅ **Automatic scaling**

### 📋 Prerequisites
- GitHub account
- Fly.io account (free signup)
- Supabase database (already configured)

### 🔧 Installation

1. **Install Fly CLI:**
   ```bash
   # Windows (PowerShell)
   iwr https://fly.io/install.ps1 -useb | iex
   
   # macOS/Linux
   curl -L https://fly.io/install.sh | sh
   ```

2. **Login to Fly.io:**
   ```bash
   fly auth login
   ```

### 🚀 Deployment Steps

1. **Initialize Fly App:**
   ```bash
   fly launch --no-deploy
   ```

2. **Set Environment Variables:**
   ```bash
   fly secrets set DATABASE_URL="postgresql://postgres.nbxntohihcwruwlnthfb:6818.yigit.98@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require"
   fly secrets set FLY_ENVIRONMENT="production"
   fly secrets set FLASK_ENV="production"
   ```

3. **Deploy:**
   ```bash
   fly deploy
   ```

### 📊 Expected Output
```
==> Building image
==> Installing Python dependencies
==> Downloading YOLOv8 models
==> Starting Flask server
🚀 FLY.IO - Starting optimized Flask server...
🌐 Platform: Fly.io
🌐 Starting server on 0.0.0.0:8080
🔧 Environment: production
🔧 Debug mode: False
* Running on all addresses (0.0.0.0)
* Running on http://0.0.0.0:8080
```

### 🔍 Health Check
- Fly.io automatically monitors `/health` endpoint
- Expected response: `{"status": "healthy"}`

### 📈 Monitoring
```bash
fly logs          # View logs
fly status        # Check app status
fly open          # Open app in browser
```

### 🛠️ Troubleshooting

**Build Issues:**
```bash
fly logs --app smartsafe-ppe-detection
```

**Memory Issues:**
```bash
fly scale memory 1024  # Increase to 1GB (still free)
```

**Database Issues:**
```bash
fly secrets list  # Check environment variables
```

### 💰 Cost (FREE!)
- **Shared CPU**: FREE
- **256MB-1GB RAM**: FREE
- **160GB bandwidth**: FREE
- **3 apps**: FREE

### 🔄 Updates
```bash
# After code changes
git push origin main
fly deploy
```

### 📝 Commands Cheat Sheet
```bash
fly launch           # Initialize app
fly deploy           # Deploy app
fly open             # Open in browser
fly logs             # View logs
fly status           # Check status
fly scale memory 512 # Scale memory
fly secrets set KEY=value  # Set environment variable
```

### 🎯 Next Steps
1. Sign up at https://fly.io/
2. Install Fly CLI
3. Run `fly launch --no-deploy`
4. Set environment variables
5. Run `fly deploy`

### 🔒 Security
- Automatic HTTPS
- Environment variables encrypted
- Network isolation
- DDoS protection

**Total Cost: $0.00/month** 🎉 