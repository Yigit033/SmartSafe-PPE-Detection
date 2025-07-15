# 🐍 PythonAnywhere Deployment Guide

## SmartSafe AI - Temporary PythonAnywhere Deployment

### 📝 **IMPORTANT NOTE:**
**Bu geçici bir çözümdür. Maddi durum düzeldiğinde Render.com'a geri döneceğiz.**

### 🎯 **Why PythonAnywhere (Temporary):**
- ✅ **100% Free** - No credit card required
- ✅ **Flask Native** - Perfect for our app
- ✅ **Stable URL** - Good for demos
- ✅ **Supabase Compatible** - Database works
- ✅ **24/7 Uptime** - Reliable hosting

### 🚀 **Deployment Steps:**

#### **1. Create Account:**
- Go to https://pythonanywhere.com/
- Click **"Create a Beginner account"**
- **100% Free** - no payment required

#### **2. Upload Code:**
```bash
# Option 1: Git Clone (Recommended)
git clone https://github.com/Yigit033/SmartSafe-PPE-Detection.git

# Option 2: Upload ZIP
# Download repo as ZIP and upload via Files tab
```

#### **3. Install Dependencies:**
```bash
# In PythonAnywhere Bash console
cd SmartSafe-PPE-Detection
pip3.10 install --user -r requirements.txt
python3.10 download_models.py
```

#### **4. Create Web App:**
- Go to **"Web"** tab
- Click **"Add a new web app"**
- Choose **"Manual configuration"**
- Select **"Python 3.10"**

#### **5. Configure WSGI:**
Edit `/var/www/yourusername_pythonanywhere_com_wsgi.py`:
```python
import sys
import os

# Add your project directory to the sys.path
sys.path.append('/home/yourusername/SmartSafe-PPE-Detection')

# Set environment variables
os.environ['PYTHONANYWHERE_ENVIRONMENT'] = 'production'
os.environ['FLASK_ENV'] = 'production'
os.environ['DATABASE_URL'] = 'postgresql://postgres.nbxntohihcwruwlnthfb:6818.yigit.98@aws-0-us-west-1.pooler.supabase.com:6543/postgres?sslmode=require'

# Import Flask app
from smartsafe_saas_api import app as application

if __name__ == "__main__":
    application.run()
```

#### **6. Set Static Files:**
- **URL:** `/static/`
- **Directory:** `/home/yourusername/SmartSafe-PPE-Detection/static/`

#### **7. Reload Web App:**
- Click **"Reload"** button
- Wait for restart

### 🔗 **Your URL:**
`https://yourusername.pythonanywhere.com`

### 🧪 **Testing:**
```bash
# Test locally first
python3.10 pythonanywhere_setup.py
```

### 📊 **Expected Output:**
```
🐍 PythonAnywhere Setup - Temporary Solution
✅ Environment variables set for PythonAnywhere
✅ Database URL configured (Supabase)
✅ Production mode enabled
🌐 Platform: PythonAnywhere (Temporary)
```

### 🔧 **Troubleshooting:**

**Import Errors:**
```bash
pip3.10 install --user package_name
```

**Database Connection:**
- Check environment variables in WSGI file
- Verify Supabase URL

**Static Files:**
- Ensure static directory path is correct
- Check file permissions

### 💰 **Cost:**
**$0.00/month** - Completely free!

### 🔄 **Future Migration to Render.com:**

When budget allows, we'll migrate to Render.com:
1. **Keep render.yaml** (already configured)
2. **Update environment variables**
3. **Deploy to Render.com**
4. **Update DNS/URLs**

### 📝 **Migration Checklist (Future):**
- [ ] Budget available for Render.com
- [ ] Update render.yaml if needed
- [ ] Deploy to Render.com
- [ ] Test Supabase connection
- [ ] Update public URLs
- [ ] Sunset PythonAnywhere

### 🎯 **Current Status:**
- **Platform:** PythonAnywhere (Temporary)
- **Cost:** $0.00/month
- **Target:** Render.com (When budget allows)
- **Database:** Supabase (Working)

### 🔒 **Security:**
- HTTPS enabled by default
- Environment variables secure
- Database connection encrypted

**Remember: This is temporary until we can afford Render.com!** 🎯 