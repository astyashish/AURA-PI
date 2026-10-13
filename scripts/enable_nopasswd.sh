#!/bin/bash
# One-time: enable passwordless sudo for this user so AURA scripts never ask again.
# You type your password ONCE here, never again.
U="$(whoami)"
echo "$U ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/aura-pi >/dev/null \
  && sudo chmod 440 /etc/sudoers.d/aura-pi \
  && echo "✓ Passwordless sudo enabled for $U"
