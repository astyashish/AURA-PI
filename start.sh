#!/bin/bash
# JARVIS-PI Quick Start for Raspberry Pi

echo "╔══════════════════════════════════════════════════╗"
echo "║          Starting JARVIS-PI on Raspberry Pi       ║"
echo "╚══════════════════════════════════════════════════╝"

# Navigate to project directory
cd "$(dirname "$0")"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Virtual environment not found. Running setup.sh first..."
    chmod +x setup.sh
    ./setup.sh
    source venv/bin/activate
fi

# Ensure Ollama service is running
if ! pgrep -x "ollama" > /dev/null; then
    echo "Starting Ollama service..."
    ollama serve > /dev/null 2>&1 &
    sleep 3
fi

# Start JARVIS
python3 main.py
