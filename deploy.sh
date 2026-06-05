#!/bin/bash
# 部署并启动 loong-kb 服务
# 代码即部署，配置文件: config.yaml（已包含密钥）

set -e

APP_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=== loong-kb 部署 ==="
echo "代码目录: $APP_DIR"
echo ""

# 检查配置
if [ ! -f "$APP_DIR/config.yaml" ]; then
    echo "错误：config.yaml 不存在"
    exit 1
fi

# 停止旧服务
echo "[1/2] 停止旧服务..."
bash "$APP_DIR/stop.sh" 2>/dev/null || true

# 启动服务
echo "[2/2] 启动服务..."
cd "$APP_DIR"
nohup gunicorn -c gunicorn_config.py wsgi:app > /tmp/loong-kb.log 2>&1 &
echo "PID: $!"
sleep 2
echo ""
echo "=== 部署完成 ==="
echo "访问地址: http://10.40.65.201:5001"
echo "日志: /tmp/loong-kb.log"
