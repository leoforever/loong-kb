#!/bin/bash
# 启动 loong-kb 服务

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

PID=$(ps aux | grep "gunicorn.*wsgi:app" | grep -v grep | awk '{print $2}')
if [ -n "$PID" ]; then
    echo "loong-kb 已在运行 (PID: $PID)"
    exit 0
fi

cd "$APP_DIR"
nohup gunicorn -c gunicorn_config.py wsgi:app > /tmp/loong-kb.log 2>&1 &
NEW_PID=$!
echo "loong-kb 已启动 (PID: $NEW_PID)"
sleep 2

if ps -p $NEW_PID > /dev/null 2>&1; then
    echo "运行中：http://10.40.65.201:5001"
else
    echo "启动失败，请检查 /tmp/loong-kb.log"
fi
