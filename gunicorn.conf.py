#!/usr/bin/env python3
"""
Gunicorn Configuration for SmartSafe AI
Production-ready settings for Render.com deployment
"""

import os
import multiprocessing

# Server socket - Render.com specific
bind = f"0.0.0.0:{os.getenv('PORT', '10000')}"
backlog = 2048

# Worker processes - Memory optimized for Render.com
workers = 1  # Single worker for free tier (512MB limit)
worker_class = "sync"
worker_connections = 500  # Reduced for memory optimization
timeout = 120  # Timeout for requests
keepalive = 5  # Keep connections alive
max_requests = 50  # Restart worker after 50 requests
max_requests_jitter = 5  # Add jitter to prevent thundering herd
preload_app = True  # Preload app for memory efficiency

# Render.com specific settings
daemon = False  # Don't daemonize on Render.com
pidfile = None  # No PID file needed
user = None  # Run as current user
group = None  # Run as current group

# Logging for Render.com - VERBOSE for debugging
loglevel = "debug"
accesslog = "-"  # Log to stdout
errorlog = "-"   # Log to stderr
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
capture_output = True  # Capture stdout/stderr

# Process naming
proc_name = "smartsafe_saas_api"

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Access log format
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Application path
chdir = "/opt/render/project/src"
pythonpath = "/opt/render/project/src"

# SSL (disabled for Render.com)
keyfile = None
certfile = None

# Stats (disabled)
statsd_host = None

# Graceful shutdown
graceful_timeout = 30

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("SmartSafe AI server is ready. Listening on %s", bind)

def on_starting(server):
    """Called just before the master process is initialized."""
    server.log.info("Starting SmartSafe AI server...")

def on_reload(server):
    """Called to recycle workers during a reload via SIGHUP."""
    server.log.info("Reloading SmartSafe AI server...")

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def on_exit(server):
    """Called just before exiting."""
    server.log.info("SmartSafe AI server is shutting down...")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal") 