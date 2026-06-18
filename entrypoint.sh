#!/bin/bash
set -e

Xvfb :99 -screen 0 1280x720x24 -nolisten tcp &
XVFB_PID=$!

sleep 2

if ! ps -p $XVFB_PID > /dev/null 2>&1; then
    echo "[ERROR] Xvfb failed to start"
    exit 1
fi

echo "[INFO] Xvfb started on DISPLAY=:99 (PID=$XVFB_PID)"

export DISPLAY=:99
export PATH="/app/build:${PATH}"

echo "[INFO] Starting Streamlit on port 7860..."
exec python3 -m streamlit run /app/app.py \
    --server.port=7860 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --browser.gatherUsageStats=false
