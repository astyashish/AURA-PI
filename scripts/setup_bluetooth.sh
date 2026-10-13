#!/bin/bash
# =============================================================================
#  AURA-PI — Bluetooth Headset/Earbuds Full Setup Script
#  Works with PipeWire + bluez (Raspberry Pi OS Bookworm)
#  Supports: TWS earbuds, over-ear headsets, any A2DP/HFP device
# =============================================================================

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AURA-PI — Bluetooth Audio Setup                   ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Pre-checks ────────────────────────────────────────────────────────────────
if ! systemctl is-active --quiet bluetooth; then
  echo "Starting Bluetooth service..."
  sudo systemctl start bluetooth
fi

if ! command -v bluetoothctl &>/dev/null; then
  echo "Error: bluetoothctl not found. Install with: sudo apt install bluez"
  exit 1
fi

# ── Check PipeWire/PulseAudio for BT audio ────────────────────────────────────
BT_AUDIO_OK=false
if systemctl --user is-active --quiet pipewire-pulse 2>/dev/null; then
  echo "[OK] PipeWire-Pulse running — Bluetooth audio will work"
  BT_AUDIO_OK=true
elif systemctl --user is-active --quiet pulseaudio 2>/dev/null; then
  echo "[OK] PulseAudio running — checking Bluetooth module..."
  pactl list modules short 2>/dev/null | grep -q "module-bluetooth" && BT_AUDIO_OK=true
fi

if [ "$BT_AUDIO_OK" = false ]; then
  echo "[Warning] PipeWire/PulseAudio Bluetooth not confirmed running."
  echo "  Run setup.sh first to configure audio properly."
  echo ""
fi

# ── Power on Bluetooth adapter ────────────────────────────────────────────────
echo "Powering on Bluetooth adapter..."
bluetoothctl power on
bluetoothctl agent on
bluetoothctl default-agent

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Put your earbuds/headset into PAIRING MODE now."
echo "  (Usually hold power button 5+ seconds until LED blinks)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "Press ENTER when earbuds are in pairing mode..."

# ── Scan for devices ──────────────────────────────────────────────────────────
echo ""
echo "Scanning for Bluetooth devices (20 seconds)..."
echo "Look for your device name in the list below:"
echo ""

# Run scan in background and collect results
SCAN_RESULTS=$(timeout 20 bluetoothctl scan on 2>&1 &
  SCAN_PID=$!
  sleep 20
  kill $SCAN_PID 2>/dev/null
  bluetoothctl devices)

# Show discovered devices
bluetoothctl devices | while read -r line; do
  echo "  → $line"
done

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Enter MAC address of your earbuds (e.g. AA:BB:CC:DD:EE:FF): " MAC

if [ -z "$MAC" ]; then
  echo "No MAC address entered. Exiting."
  exit 1
fi

# Validate MAC format
if ! echo "$MAC" | grep -qE "^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$"; then
  echo "Invalid MAC address format. Example: AA:BB:CC:DD:EE:FF"
  exit 1
fi

echo ""
echo "Pairing with $MAC..."
bluetoothctl pair "$MAC" && echo "  ✓ Paired" || echo "  ⚠ Pairing failed — device may already be paired"

echo "Trusting $MAC..."
bluetoothctl trust "$MAC" && echo "  ✓ Trusted"

echo "Connecting to $MAC..."
bluetoothctl connect "$MAC" && echo "  ✓ Connected!" || {
  echo "  ⚠ Connection failed. Retrying in 3s..."
  sleep 3
  bluetoothctl connect "$MAC" && echo "  ✓ Connected on retry!" || echo "  ✗ Connection failed"
}

sleep 2

# ── Set as default audio sink ─────────────────────────────────────────────────
echo ""
echo "Setting Bluetooth device as default audio output..."

# Give PipeWire/PulseAudio time to register the new device
sleep 3

# Find the BT sink
BT_SINK=""
for i in 1 2 3 4 5; do
  BT_SINK=$(pactl list sinks short 2>/dev/null | \
    grep -i "bluez\|bluetooth\|a2dp\|hsp" | \
    head -1 | awk '{print $2}')
  if [ -n "$BT_SINK" ]; then
    break
  fi
  echo "  Waiting for BT audio sink (attempt $i/5)..."
  sleep 2
done

if [ -n "$BT_SINK" ]; then
  pactl set-default-sink "$BT_SINK"
  echo "  ✓ Default audio output → $BT_SINK"

  # Also set as default source (microphone) if it has one
  BT_SOURCE=$(pactl list sources short 2>/dev/null | \
    grep -i "bluez\|bluetooth\|hsp\|hfp" | \
    head -1 | awk '{print $2}')
  if [ -n "$BT_SOURCE" ]; then
    pactl set-default-source "$BT_SOURCE"
    echo "  ✓ Default microphone → $BT_SOURCE"
  fi
else
  echo "  ⚠ No Bluetooth audio sink found yet."
  echo "  The device may still appear — check: pactl list sinks short"
fi

# ── Save MAC for auto-reconnect ───────────────────────────────────────────────
AURA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "$MAC" > "$AURA_DIR/.bt_device_mac"
echo ""
echo "  BT MAC saved to .bt_device_mac for auto-reconnect"

# ── Auto-reconnect service ────────────────────────────────────────────────────
echo ""
echo "Creating Bluetooth auto-reconnect service..."

sudo tee /etc/systemd/system/bt-autoconnect.service > /dev/null << SERVICE_EOF
[Unit]
Description=Bluetooth Auto-Connect for AURA-PI
After=bluetooth.target
Requires=bluetooth.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/bin/bash -c 'sleep 5 && bluetoothctl connect $MAC'
User=$USER

[Install]
WantedBy=multi-user.target
SERVICE_EOF

sudo systemctl daemon-reload
sudo systemctl enable bt-autoconnect.service
echo "  ✓ Auto-reconnect service enabled (connects on boot)"

# ── Test audio ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
read -p "Test audio? Play a test beep to your earbuds? (y/N): " TEST_AUDIO

if [[ "$TEST_AUDIO" =~ ^[Yy]$ ]]; then
  echo "Playing test tone..."
  if [ -n "$BT_SINK" ]; then
    # Generate and play a 440Hz beep
    python3 -c "
import subprocess, struct, math
rate=44100; dur=1; freq=440
samples=[int(32767*math.sin(2*math.pi*freq*i/rate)) for i in range(rate*dur)]
import wave, tempfile, os
f=tempfile.NamedTemporaryFile(suffix='.wav',delete=False)
with wave.open(f.name,'w') as w:
    w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
    w.writeframes(struct.pack('<'+'h'*len(samples),*samples))
subprocess.run(['paplay','--device','$BT_SINK',f.name])
os.unlink(f.name)
" 2>/dev/null && echo "  ✓ Test tone played!" || \
    speaker-test -t sine -f 440 -l 1 -s 1 2>/dev/null || \
    echo "  ⚠ Could not play test tone (earbuds should still work with AURA)"
  fi
fi

# ── Test microphone ───────────────────────────────────────────────────────────
if [ -n "$BT_SOURCE" ]; then
  echo ""
  read -p "Test microphone recording (3 seconds)? (y/N): " TEST_MIC
  if [[ "$TEST_MIC" =~ ^[Yy]$ ]]; then
    echo "Recording 3 seconds from BT microphone..."
    arecord -D "pulse" -f S16_LE -r 16000 -c 1 -d 3 /tmp/aura_mic_test.wav 2>/dev/null && \
      echo "  ✓ Microphone recording OK (saved to /tmp/aura_mic_test.wav)" || \
      echo "  ⚠ Mic recording failed — check: pactl list sources short"
  fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✓  Bluetooth Setup Complete!                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "  Your earbuds ($MAC) are paired and set as default."
echo "  AURA-PI voice input/output will use them automatically."
echo ""
echo "  Useful commands:"
echo "    pactl list sinks short          # list audio outputs"
echo "    pactl list sources short        # list audio inputs"
echo "    bluetoothctl devices            # list paired devices"
echo "    bluetoothctl connect $MAC   # manually reconnect"
echo ""
echo "  Start AURA-PI:"
echo "    source venv/bin/activate && python main.py"
echo ""
