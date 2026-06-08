"""Gunicorn config for loong-kb — reads server from config.yaml"""

import os
import sys
from pathlib import Path

# Ensure config_loader can be imported
sys.path.insert(0, str(Path(__file__).parent))

try:
    from app.config import get_server_config
    srv = get_server_config()
    bind = f"{srv['host']}:{srv['port']}"
except Exception:
    # Fallback to defaults if config.yaml not found
    bind = "0.0.0.0:5001"

workers = 1
worker_class = "gevent"
worker_connections = 1000
max_requests = 0
timeout = 300
keepalive = 65
accesslog = "-"
errorlog = "-"
loglevel = "info"