# SmartSafe AI - Production Docker Image
FROM python:3.11-slim

# Metadata
LABEL maintainer="SmartSafe AI Team"
LABEL version="1.0"
LABEL description="SmartSafe AI PPE Detection SaaS Platform"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=smartsafe_saas_api.py
ENV FLASK_ENV=production

# Create app directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libc-dev \
    libffi-dev \
    libssl-dev \
    libopencv-dev \
    python3-opencv \
    wget \
    curl \
    # Dependencies for pygame
    libsdl2-dev \
    libsdl2-mixer-dev \
    libsdl2-image-dev \
    libsdl2-ttf-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY requirements.txt .

# Install Python dependencies with retry and timeout
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --timeout 300 --retries 3 -r requirements.txt

# Copy application code
COPY . .

# Create necessary directories with proper permissions
RUN mkdir -p /app/logs /app/data/models /app/static/uploads && \
    chmod -R 755 /app/logs /app/data /app/static

# Download PPE detection models - CRITICAL for production
RUN python download_models.py && \
    echo "✅ Models downloaded successfully" || \
    echo "⚠️ Model download failed, will attempt lazy loading at runtime"

# Verify models were downloaded
RUN ls -lah /app/data/models/ || echo "Models directory will be populated at runtime"

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash smartsafe
RUN chown -R smartsafe:smartsafe /app
USER smartsafe

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Run the application
CMD ["python", "-m", "src.smartsafe.api.smartsafe_saas_api"]
