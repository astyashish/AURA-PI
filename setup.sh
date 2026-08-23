#!/bin/bash

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   JARVIS-PI Setup — Raspberry Pi          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

set -e

# Update system
echo "[1/8] Updating system packages..."
sudo apt-get update -qq

# Install system dependencies
echo "[2/8] Installing system dependencies..."
sudo apt-get install -y -qq \
  python3-pip python3-venv git \
  portaudio19-dev libasound2-dev \
  ffmpeg libopenblas-dev \
  build-essential cmake \
  espeak espeak-data \
  libatlas-base-dev

# Create virtual environment
echo "[3/8] Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install Python packages
echo "[4/8] Installing Python packages..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
# Install RPi.GPIO / rpi-lgpio on Pi 5 (RP1 chip) & older Pis
pip install rpi-lgpio -q 2>/dev/null || pip install RPi.GPIO -q 2>/dev/null || echo "  (RPi GPIO not available — mock GPIO will be used)"

# Install Ollama
echo "[5/8] Installing Ollama..."
if ! command -v ollama &> /dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
  echo "  Ollama installed"
else
  echo "  Ollama already installed"
fi

# Download LLM models
echo "[6/8] Downloading LLM models (this takes a while)..."
ollama serve &
OLLAMA_PID=$!
sleep 5

echo "  Downloading qwen2.5:3b (default model, recommended)..."
ollama pull qwen2.5:3b || echo "  Warning: qwen2.5:3b pull failed"

echo "  Downloading qwen2.5:0.5b (fastest, minimal RAM)..."
ollama pull qwen2.5:0.5b || echo "  Warning: qwen2.5:0.5b pull failed"

echo "  Downloading gemma2:2b (balanced alternative)..."
ollama pull gemma2:2b || echo "  Warning: gemma2:2b pull failed"

echo "  Downloading llava:7b (vision/image analysis, ~4GB)..."
echo "  Automatically pulling vision model for fully automated setup."
ollama pull llava:7b || echo "  Warning: llava:7b pull failed"

kill $OLLAMA_PID 2>/dev/null || true

# Download Vosk speech model
echo "[7/8] Downloading Vosk speech recognition model..."
mkdir -p models
cd models
if [ ! -d "vosk-model-small-en-us-0.15" ]; then
  wget -q "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
  unzip -q vosk-model-small-en-us-0.15.zip
  rm vosk-model-small-en-us-0.15.zip
  echo "  Vosk model downloaded"
else
  echo "  Vosk model already present"
fi

# Install Piper TTS (aarch64 for Pi 5)
echo "  Installing Piper TTS..."
PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_aarch64.tar.gz"
if [ ! -f "/usr/local/bin/piper" ]; then
  wget -q "$PIPER_URL" -O piper_linux_aarch64.tar.gz || echo "  Piper download failed, checking fallback"
  if [ -f "piper_linux_aarch64.tar.gz" ]; then
    tar -xzf piper_linux_aarch64.tar.gz
    sudo cp piper/piper /usr/local/bin/ 2>/dev/null || sudo mv piper /usr/local/bin/ 2>/dev/null || echo "  Could not install Piper globally"
    rm -rf piper_linux_aarch64.tar.gz piper
  fi
fi

mkdir -p voices
if [ ! -f "voices/en_US-lessac-medium.onnx" ]; then
  echo "  Downloading Piper voice model..."
  wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx" -O voices/en_US-lessac-medium.onnx
  wget -q "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json" -O voices/en_US-lessac-medium.onnx.json
fi

cd ..

# Copy env file
echo "[8/8] Setting up configuration..."
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  Created .env from template"
fi

mkdir -p captured_images

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║   Setup Complete!                         ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "  To start Jarvis:"
echo "    source venv/bin/activate"
echo "    ollama serve &"
echo "    python main.py"
echo ""
echo "  Then open: http://localhost:5000"
echo "  Or on network: http://$(hostname -I | awk '{print $1}'):5000"
echo ""
