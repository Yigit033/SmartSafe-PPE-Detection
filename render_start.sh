#!/bin/bash

# Render.com Deployment Script for SmartSafe AI
# Memory Optimized Production Startup

echo "🚀 Starting SmartSafe AI on Render.com..."

# Set environment variables for production
export RENDER=true
export FLASK_ENV=production
export PYTHONPATH="${PYTHONPATH}:."

# Memory optimization
export OMP_NUM_THREADS=2
export MKL_NUM_THREADS=2
export OPENBLAS_NUM_THREADS=2
export VECLIB_MAXIMUM_THREADS=2
export NUMEXPR_NUM_THREADS=2

# YOLOv8 optimization
export YOLO_CONFIG_DIR=/tmp
export ULTRALYTICS_CONFIG_DIR=/tmp

# GPU/CPU Auto-detection (will use GPU if available)
# Uncomment the line below to force CPU-only mode:
# export CUDA_VISIBLE_DEVICES=""

# GPU optimization if available
export TORCH_USE_CUDA_DSA=1
export CUDA_LAUNCH_BLOCKING=0

echo "📦 Environment configured for production"
echo "🔧 Memory optimization enabled"
echo "🌐 Starting Flask application..."

# Start the application
python smartsafe_saas_api.py
