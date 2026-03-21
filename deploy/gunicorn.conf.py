# Gunicorn config for testbank
# Optimized for 2-core / 2GB server

bind = "127.0.0.1:8001"  # Only listen locally; nginx proxies to here
workers = 3
max_requests = 1000       # Recycle workers to prevent memory leaks
max_requests_jitter = 50
timeout = 30
accesslog = "-"
errorlog = "-"
