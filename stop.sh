#!/bin/bash
# 停止 loong-kb 服务

PID=$(ps aux | grep "gunicorn.*wsgi:app" | grep -v grep | awk '{print $2}')
if [ -z "$PID" ]; then
    echo "loong-kb 未运行"
else
    kill $PID
    echo "已停止 loong-kb (PID: $PID)"
fi
