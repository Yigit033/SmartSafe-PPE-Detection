#!/usr/bin/env python3
"""
Gunicorn Configuration for SmartSafe AI
Production-ready settings for Render.com deployment
"""

import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
backlog = 2048

# Worker processes
workers = 1  # Single worker for free tier
worker_class = "sync"
worker_connections = 1000
timeout = 120  # Reduced timeout for better responsiveness
keepalive = 5  # Increased keepalive
max_requests = 100
max_requests_jitter = 10

# Restart workers after this many requests to prevent memory leaks
max_requests = 100
max_requests_jitter = 10

# Logging
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "smartsafe_ai"

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (if needed)
keyfile = None
certfile = None

# Application
wsgi_app = "smartsafe_saas_api:app"
chdir = "/opt/render/project/src"
pythonpath = "/opt/render/project/src"

# Preload application
preload_app = True

# Enable stats
statsd_host = None

# Worker timeout
timeout = 300
graceful_timeout = 30

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("SmartSafe AI server is ready. Listening on %s", bind)

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal") 