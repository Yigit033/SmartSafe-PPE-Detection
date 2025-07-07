# 🚀 SmartSafe AI - Render.com Deployment Guide

## 📋 Deployment Steps

### 1. Repository Setup
```bash
# Clone or push your code to GitHub
git add .
git commit -m "Render.com deployment ready"
git push origin main
```

### 2. Create Render.com Account
- Go to [render.com](https://render.com)
- Sign up with GitHub account
- Connect your repository

### 3. Create New Web Service
1. Click "New +" → "Web Service"
2. Connect your GitHub repository
3. Select branch: `main`
4. Configure settings:

```yaml
Name: smartsafe-ppe-detection
Environment: Python 3
Region: Oregon (US West)
Branch: main
Build Command: pip install -r requirements.txt && python download_models.py
Start Command: python smartsafe_saas_api.py
```

### 4. Environment Variables
Add these in Render dashboard:

```bash
FLASK_ENV=production
FLASK_APP=smartsafe_saas_api.py
PORT=10000
PYTHONPATH=/opt/render/project/src
CUDA_VISIBLE_DEVICES=""
```

### 5. Health Check
- Health Check Path: `/health`
- This will monitor your app automatically

## 🔧 Configuration Files

### render.yaml (Auto-deployment)
```yaml
services:
  - type: web
    name: smartsafe-ppe-detection
    env: python
    region: oregon
    plan: free
    buildCommand: |
      pip install --upgrade pip
      pip install -r requirements.txt
      python download_models.py
    startCommand: python smartsafe_saas_api.py
    healthCheckPath: /health
    envVars:
      - key: FLASK_ENV
        value: production
      - key: FLASK_APP
        value: smartsafe_saas_api.py
      - key: PORT
        value: 10000
```

## 📊 Free Tier Limits
- ✅ 512MB RAM
- ✅ 0.1 CPU units
- ✅ 400 build hours/month
- ✅ Custom domains
- ✅ SSL certificates
- ❌ Sleeps after 15 minutes of inactivity

## 🎯 App URLs
After deployment:
- **Main App**: `https://smartsafe-ppe-detection.onrender.com`
- **Health Check**: `https://smartsafe-ppe-detection.onrender.com/health`
- **Company Registration**: `https://smartsafe-ppe-detection.onrender.com/`

## 🔄 Deployment Process
1. **Build Phase**: 10-15 minutes (first time)
2. **Model Download**: 2-5 minutes
3. **App Start**: 1-2 minutes
4. **Total**: ~20 minutes first deployment

## 🛠 Troubleshooting

### Common Issues:
1. **Build Timeout**: Optimize requirements.txt
2. **Memory Issues**: Use CPU-only torch version
3. **Model Download**: Ensure download_models.py works
4. **Port Issues**: Use `PORT` environment variable

### Logs Access:
```bash
# View logs in Render dashboard
# Or use Render CLI
render logs -s smartsafe-ppe-detection
```

## 📈 Monitoring
- **Health Check**: Automatic monitoring
- **Metrics**: Available in dashboard
- **Alerts**: Email notifications for downtime

## 🚀 Going Live
1. **Custom Domain**: Add your domain in settings
2. **SSL**: Automatic with custom domains
3. **Scaling**: Upgrade to paid plan for better performance

## 💡 Optimization Tips
- Use `opencv-python-headless` for smaller builds
- Optimize model loading for faster startup
- Use Redis for caching (add Redis service)
- Monitor memory usage

## 📞 Support
- **Render Docs**: [render.com/docs](https://render.com/docs)
- **Community**: [community.render.com](https://community.render.com)
- **Status**: [status.render.com](https://status.render.com)

---
🎉 **Your SmartSafe AI PPE Detection system is now live on Render.com!** 