"""
Mock GPIO module for development on Windows/Linux (non-Pi systems).
Simulates RPi.GPIO behavior so all code runs without hardware.
"""

BCM = "BCM"
BOARD = "BOARD"
OUT = "OUT"
IN = "IN"
HIGH = True
LOW = False
PUD_UP = "PUD_UP"
PUD_DOWN = "PUD_DOWN"

_pin_states = {}
_mode = None

def setmode(mode):
    global _mode
    _mode = mode
    print(f"[MockGPIO] Mode set to {mode}")

def setwarnings(flag):
    pass

def setup(pin, direction, initial=LOW, pull_up_down=None):
    _pin_states[pin] = initial
    print(f"[MockGPIO] Pin {pin} set up as {'OUTPUT' if direction == OUT else 'INPUT'}, initial={initial}")

def output(pin, state):
    _pin_states[pin] = state
    state_str = "HIGH ✓" if state else "LOW ✗"
    print(f"[MockGPIO] Pin {pin} → {state_str}")

def input(pin):
    return _pin_states.get(pin, LOW)

def cleanup(pins=None):
    if pins:
        for pin in (pins if isinstance(pins, list) else [pins]):
            _pin_states.pop(pin, None)
    else:
        _pin_states.clear()
    print("[MockGPIO] Cleanup done")

def get_all_states():
    return dict(_pin_states)
