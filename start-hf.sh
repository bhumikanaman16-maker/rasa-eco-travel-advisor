#!/usr/bin/env bash
set -e

echo "=================================================="
echo "  EcoTravel Advisor – Hugging Face Container Startup"
echo "=================================================="

# 1. Start Rasa Action Server on port 5055
echo "[1/3] Starting Rasa Action Server on port 5055..."
python -m rasa_sdk --actions actions --port 5055 &
ACTION_PID=$!

# Wait briefly for action server initialization
sleep 3

# 2. Start Rasa Core/NLU Server on port 5005
echo "[2/3] Starting Rasa Server on port 5005..."
rasa run --enable-api --cors "*" --model /app/models --endpoints /app/endpoints.hf.yml --port 5005 &
RASA_PID=$!

# Monitor background process health during startup
echo "Waiting for Rasa server to initialize models..."
sleep 15

# 3. Start Nginx reverse proxy on port 7860 in foreground
echo "[3/3] Starting Nginx reverse proxy on port 7860..."
exec nginx -c /app/nginx.hf.conf
