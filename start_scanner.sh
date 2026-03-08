#!/bin/bash

# Crypto Scanner Startup Script for Oracle Cloud

cd /home/ubuntu/Gemini_Crypto
source venv/bin/activate

# Get the public IP address
PUBLIC_IP=$(curl -s ifconfig.me)

echo "=========================================="
echo "Starting Crypto Scanner..."
echo "=========================================="
echo "Access the dashboard at:"
echo "http://${PUBLIC_IP}:8001"
echo "=========================================="

# Start the FastAPI server
python3 backend/main.py
