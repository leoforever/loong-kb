"""Gunicorn config for loong-kb streaming"""
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
