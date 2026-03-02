#!/bin/bash

# SmartSafe AI - Vercel Quick Deploy Script
# Bu script Linux/Mac için hazırlanmıştır

echo "================================"
echo "SmartSafe AI - Vercel Deploy"
echo "================================"
echo ""

# Check if Vercel CLI is installed
echo "Checking Vercel CLI..."
if ! command -v vercel &> /dev/null; then
    echo "Vercel CLI not found! Installing..."
    npm install -g vercel
    
    if [ $? -ne 0 ]; then
        echo "Error installing Vercel CLI. Please run manually:"
        echo "  npm install -g vercel"
        exit 1
    fi
    echo "Vercel CLI installed successfully!"
else
    echo "Vercel CLI found!"
fi

echo ""
echo "Select deployment type:"
echo "1. Preview Deploy (test)"
echo "2. Production Deploy"
echo ""

read -p "Enter choice (1 or 2): " choice

case $choice in
    1)
        echo ""
        echo "Deploying to Preview..."
        vercel
        ;;
    2)
        echo ""
        echo "Deploying to Production..."
        vercel --prod
        ;;
    *)
        echo "Invalid choice. Exiting..."
        exit 1
        ;;
esac

echo ""
echo "================================"
echo "Deployment Complete!"
echo "================================"
echo ""
echo "Next steps:"
echo "1. Test your deployment URL"
echo "2. Check landing page loads instantly"
echo "3. Test contact form"
echo "4. Test demo request"
echo ""
echo "Need help? Check VERCEL_DEPLOYMENT_GUIDE.md"

