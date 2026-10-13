"""
lgpio wrapper — provides an RPi.GPIO-compatible interface using the lgpio library.
Used on Raspberry Pi 5 where RPi.GPIO is not compatible with the RP1 GPIO chip.

This wrapper maps RPi.GPIO BCM-mode pin numbers → the same interface,
so the rest of the codebase doesn't need to know which backend is being used.
"""

import lgpio as _lgpio

BCM = "BCM"
BOARD = "BOARD"
OUT = 1
IN = 0
HIGH = 1
LOW = 0
PUD_UP = "PUD_UP"
PUD_DOWN = "PUD_DOWN"

_chip = None
_pin_directions = {}   # pin -> OUT/IN
_pwm_handles = {}      # pin -> (thread, duty_cycle)
_mode = None

# ── chip handle ──────────────────────────────────────────────

def _get_chip():
    global _chip
    if _chip is None:
        _chip = _lgpio.gpiochip_open(0)
    return _chip


# ── mode / warnings ─────────────────────────────────────────

def setmode(mode):
    global _mode
    _mode = mode
    # lgpio always uses BCM (GPIO numbers directly)
    print(f"[lgpio] Mode set to {mode}")


def setwarnings(flag):
    pass


# ── setup ────────────────────────────────────────────────────

def setup(pin, direction, initial=LOW, pull_up_down=None):
    chip = _get_chip()
    _pin_directions[pin] = direction
    if direction == OUT:
        _lgpio.gpio_claim_output(chip, pin, initial)
        print(f"[lgpio] Pin {pin} → OUTPUT, initial={bool(initial)}")
    else:
        if pull_up_down == PUD_UP:
            _lgpio.gpio_claim_input(chip, pin, _lgpio.SET_PULL_UP)
        elif pull_up_down == PUD_DOWN:
            _lgpio.gpio_claim_input(chip, pin, _lgpio.SET_PULL_DOWN)
        else:
            _lgpio.gpio_claim_input(chip, pin)
        print(f"[lgpio] Pin {pin} → INPUT")


# ── output / input ───────────────────────────────────────────

def output(pin, state):
    chip = _get_chip()
    val = 1 if state else 0
    _lgpio.gpio_write(chip, pin, val)
    print(f"[lgpio] Pin {pin} → {'HIGH ✓' if val else 'LOW ✗'}")


def input(pin):
    chip = _get_chip()
    return _lgpio.gpio_read(chip, pin)


# ── PWM ──────────────────────────────────────────────────────

class PWM:
    """Software PWM using lgpio tx_pwm."""

    def __init__(self, pin, frequency):
        self._pin = pin
        self._freq = frequency
        self._duty = 0
        self._running = False

    def start(self, duty_cycle):
        self._duty = max(0.0, min(100.0, float(duty_cycle)))
        chip = _get_chip()
        if self._duty == 0:
            _lgpio.gpio_write(chip, self._pin, 0)
        else:
            _lgpio.tx_pwm(chip, self._pin, self._freq, self._duty)
        self._running = True
        print(f"[lgpio] PWM pin {self._pin} started @ {self._freq}Hz, duty={self._duty}%")

    def ChangeDutyCycle(self, duty_cycle):
        self._duty = max(0.0, min(100.0, float(duty_cycle)))
        chip = _get_chip()
        if self._duty == 0:
            _lgpio.tx_pwm(chip, self._pin, self._freq, 0)
            _lgpio.gpio_write(chip, self._pin, 0)
        else:
            _lgpio.tx_pwm(chip, self._pin, self._freq, self._duty)

    def ChangeFrequency(self, frequency):
        self._freq = frequency
        chip = _get_chip()
        _lgpio.tx_pwm(chip, self._pin, self._freq, self._duty)

    def stop(self):
        chip = _get_chip()
        try:
            _lgpio.tx_pwm(chip, self._pin, 0, 0)
            _lgpio.gpio_write(chip, self._pin, 0)
        except Exception:
            pass
        self._running = False


# ── cleanup ──────────────────────────────────────────────────

def cleanup(pins=None):
    global _chip
    chip = _chip
    if chip is None:
        return
    try:
        if pins is not None:
            pin_list = pins if isinstance(pins, (list, tuple)) else [pins]
            for p in pin_list:
                try:
                    _lgpio.gpio_free(chip, p)
                except Exception:
                    pass
        else:
            for p in list(_pin_directions.keys()):
                try:
                    _lgpio.gpio_free(chip, p)
                except Exception:
                    pass
            _pin_directions.clear()
            _lgpio.gpiochip_close(chip)
            _chip = None
            print("[lgpio] Cleanup done — chip closed")
    except Exception as e:
        print(f"[lgpio] Cleanup error: {e}")


def get_all_states():
    chip = _get_chip()
    result = {}
    for pin in _pin_directions:
        try:
            result[pin] = bool(_lgpio.gpio_read(chip, pin))
        except Exception:
            result[pin] = False
    return result
