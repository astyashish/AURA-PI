#!/bin/bash

echo "╔══════════════════════════════════════════════════════╗"
echo "║   AURA-PI — Bluetooth Headset Setup Helper           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "This script helps you pair your Bluetooth headset."
echo "Make sure your headset is in PAIRING MODE before continuing."
echo ""
read -p "Press Enter to start scanning for devices..."

echo ""
echo "Starting scan for 15 seconds..."
echo "Please note the MAC address (e.g., AA:BB:CC:DD:EE:FF) of your headset."
echo ""

# Scan for devices
bluetoothctl --timeout 15 scan on

echo ""
read -p "Enter the MAC address of your headset: " mac_address

if [ -z "$mac_address" ]; then
    echo "No MAC address entered. Exiting."
    exit 1
fi

echo ""
echo "Pairing with $mac_address..."
bluetoothctl pair "$mac_address"

echo ""
echo "Trusting $mac_address..."
bluetoothctl trust "$mac_address"

echo ""
echo "Connecting to $mac_address..."
bluetoothctl connect "$mac_address"

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Bluetooth Setup Complete!                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo "Your headset should now be connected."
echo "PulseAudio/PipeWire will automatically use it as the default input/output."
echo "If you have issues, run 'alsamixer' to check volumes or use the Pi OS desktop."
echo ""
