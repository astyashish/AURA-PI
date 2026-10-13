"""
GPIO Controller — fully supports Raspberry Pi 5 (RP1 chip via lgpio/rpi-lgpio)
                  and older Pis (RPi.GPIO) with automatic detection.
                  Falls back to MockGPIO on non-Pi systems (dev/Windows).
"""

import json
import os
from pathlib import Path
from threading import Lock


# ──────────────────────────────────────────────────────────────────────────────
# GPIO backend detection — priority: rpi-lgpio > RPi.GPIO > lgpio > mock
# ──────────────────────────────────────────────────────────────────────────────

def _is_raspberry_pi():
    try:
        with open("/proc/cpuinfo", "r") as f:
            content = f.read()
            return "Raspberry Pi" in content or "BCM" in content or "Hardware" in content
    except Exception:
        return False


def _detect_pi_version():
    """Returns 5 for Pi 5, 4 for Pi 4/older, 0 if not Pi."""
    try:
        with open("/proc/cpuinfo", "r") as f:
            content = f.read()
        for line in content.splitlines():
            if line.startswith("Model"):
                if "Pi 5" in line:
                    return 5
                return 4
    except Exception:
        pass
    return 0


REAL_GPIO = False
GPIO_BACKEND = "mock"

if _is_raspberry_pi() and os.getenv("ENABLE_GPIO", "true").lower() == "true":
    pi_ver = _detect_pi_version()

    # --- Try rpi-lgpio first (best for Pi 5 and works on Pi 4 too) ---
    if not REAL_GPIO:
        try:
            import RPi.GPIO as _GPIO  # rpi-lgpio installs as RPi.GPIO
            _GPIO.setmode(_GPIO.BCM)
            _GPIO.setwarnings(False)
            # Quick test — if this is the real lgpio-backed version it won't raise
            _GPIO.setup(26, _GPIO.OUT)
            _GPIO.output(26, _GPIO.LOW)
            _GPIO.cleanup(26)
            import RPi.GPIO as GPIO
            GPIO.setwarnings(False)
            REAL_GPIO = True
            GPIO_BACKEND = "rpi-lgpio" if pi_ver == 5 else "RPi.GPIO"
            print(f"[GPIO] ✓ Running on Raspberry Pi {pi_ver} — {GPIO_BACKEND} enabled")
        except RuntimeError as e:
            if "SOC peripheral base address" in str(e) or "RP1" in str(e):
                print(f"[GPIO] RPi.GPIO incompatible with Pi 5 RP1 chip: {e}")
            else:
                print(f"[GPIO] RPi.GPIO RuntimeError: {e}")
        except ImportError:
            pass
        except Exception as e:
            print(f"[GPIO] RPi.GPIO init error: {e}")

    # --- Try lgpio directly (Pi 5 native) ---
    if not REAL_GPIO:
        try:
            import lgpio as _lgpio
            # lgpio works differently — wrap it into RPi.GPIO-compatible interface
            from hardware import lgpio_wrapper as GPIO
            REAL_GPIO = True
            GPIO_BACKEND = "lgpio"
            print("[GPIO] ✓ Using lgpio backend (Pi 5 native)")
        except ImportError:
            pass
        except Exception as e:
            print(f"[GPIO] lgpio init error: {e}")

    if not REAL_GPIO:
        from hardware import mock_gpio as GPIO
        print("[GPIO] ⚠ No compatible GPIO library found — using mock")
else:
    from hardware import mock_gpio as GPIO
    if not _is_raspberry_pi():
        print("[GPIO] Dev mode (non-Pi system) — using mock GPIO")
    else:
        print("[GPIO] GPIO disabled via ENABLE_GPIO=false — using mock")


# ──────────────────────────────────────────────────────────────────────────────
# Controller
# ──────────────────────────────────────────────────────────────────────────────

class GPIOController:
    def __init__(self, config_path="config/gpio_devices.json"):
        self.config_path = Path(config_path)
        self.devices = {}
        self.rooms = []
        self.status_leds = {}
        self._pwm = {}
        self._lock = Lock()
        self._load_config()
        self._setup_gpio()

    # ── persistence ────────────────────────────────────────────
    def _load_config(self):
        with open(self.config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        self.rooms = cfg.get("rooms", [])
        for d in cfg.get("devices", []):
            self.devices[d["id"]] = d.copy()
        self.status_leds = cfg.get("status_leds", {})

    def _save_config(self):
        with self._lock:
            data = {
                "rooms": self.rooms,
                "devices": list(self.devices.values()),
                "status_leds": self.status_leds,
            }
            tmp = self.config_path.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            tmp.replace(self.config_path)

    # ── GPIO setup ─────────────────────────────────────────────
    def _setup_gpio(self):
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
        except Exception as e:
            print(f"[GPIO] setmode error: {e}")

        # Track which pins we've already set up to avoid duplicate setup
        _setup_pins = set()
        for d in self.devices.values():
            pin = d["gpio_pin"]
            if pin not in _setup_pins:
                self._setup_pin(d)
                _setup_pins.add(pin)

        for led_name, led in self.status_leds.items():
            pin = led["pin"]
            if pin not in _setup_pins:
                try:
                    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
                    print(f"[GPIO] Status LED '{led_name}' → pin {pin}")
                    _setup_pins.add(pin)
                except Exception as e:
                    print(f"[GPIO] Status LED setup failed pin {pin}: {e}")

    def _setup_pin(self, device):
        pin = device["gpio_pin"]
        try:
            GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
            print(f"[GPIO] Pin {pin} → '{device['name']}' (OUTPUT)")
        except Exception as e:
            print(f"[GPIO] Pin {pin} setup error: {e}")
            return

        if REAL_GPIO and device.get("dimmable"):
            try:
                p = GPIO.PWM(pin, 1000)
                p.start(0)
                self._pwm[pin] = p
                print(f"[GPIO] Pin {pin} PWM initialized")
            except Exception as e:
                print(f"[GPIO] PWM init failed for pin {pin}: {e}")

    # ── apply state to hardware ────────────────────────────────
    def _apply(self, device):
        pin = device["gpio_pin"]
        state = device["state"]
        intensity = max(0, min(100, int(device.get("intensity", 100))))
        try:
            if REAL_GPIO and pin in self._pwm:
                self._pwm[pin].ChangeDutyCycle(intensity if state else 0)
                print(f"[GPIO] Pin {pin} PWM → {intensity if state else 0}%")
            else:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
                print(f"[GPIO] Pin {pin} → {'HIGH ✓' if state else 'LOW ✗'}")
        except Exception as e:
            print(f"[GPIO] Output error pin {pin}: {e}")

    # ── CRUD / control ─────────────────────────────────────────
    def set_device(self, device_id, state):
        if device_id not in self.devices:
            return {"success": False, "error": f"Device '{device_id}' not found"}
        d = self.devices[device_id]
        d["state"] = bool(state)
        self._apply(d)
        self._save_config()
        return {
            "success": True,
            "device_id": device_id,
            "name": d["name"],
            "state": d["state"],
            "intensity": d.get("intensity", 100),
            "gpio_pin": d["gpio_pin"],
            "gpio_backend": GPIO_BACKEND,
            "message": f"{d['name']} turned {'ON' if state else 'OFF'}",
        }

    def toggle_device(self, device_id):
        if device_id not in self.devices:
            return {"success": False, "error": f"Device '{device_id}' not found"}
        return self.set_device(device_id, not self.devices[device_id]["state"])

    def set_intensity(self, device_id, intensity):
        if device_id not in self.devices:
            return {"success": False, "error": f"Device '{device_id}' not found"}
        d = self.devices[device_id]
        intensity = max(0, min(100, int(intensity)))
        d["intensity"] = intensity
        if intensity > 0:
            d["state"] = True
        self._apply(d)
        self._save_config()
        return {
            "success": True,
            "device_id": device_id,
            "name": d["name"],
            "state": d["state"],
            "intensity": intensity,
            "message": f"{d['name']} intensity set to {intensity}%",
        }

    def add_device(self, payload):
        did = payload.get("id") or payload.get("name", "").lower().replace(" ", "_")
        if not did:
            return {"success": False, "error": "Device id/name required"}
        if did in self.devices:
            return {"success": False, "error": f"Device '{did}' already exists"}
        d = {
            "id": did,
            "name": payload.get("name", did.replace("_", " ").title()),
            "type": payload.get("type", "light"),
            "room": payload.get("room", "living_room"),
            "gpio_pin": int(payload.get("gpio_pin", 26)),
            "state": False,
            "intensity": int(payload.get("intensity", 100)),
            "dimmable": bool(payload.get("dimmable", True)),
            "icon": payload.get("icon", "💡"),
            "aliases": payload.get("aliases", [payload.get("name", did).lower()]),
        }
        self.devices[did] = d
        try:
            self._setup_pin(d)
        except Exception as e:
            print(f"[GPIO] Setup pin failed: {e}")
        self._save_config()
        return {"success": True, "device_id": did, "device": d, "message": f"Added {d['name']}"}

    def remove_device(self, device_id):
        if device_id not in self.devices:
            return {"success": False, "error": "Device not found"}
        d = self.devices.pop(device_id)
        pin = d["gpio_pin"]
        if pin in self._pwm:
            try:
                self._pwm[pin].stop()
            except Exception:
                pass
            self._pwm.pop(pin, None)
        self._save_config()
        return {"success": True, "message": f"Removed {d['name']}"}

    def update_device(self, device_id, updates):
        if device_id not in self.devices:
            return {"success": False, "error": "Device not found"}
        d = self.devices[device_id]
        for k, v in updates.items():
            if k in ("name", "type", "room", "icon", "aliases", "dimmable"):
                d[k] = v
            elif k == "gpio_pin":
                d[k] = int(v)
            elif k == "intensity":
                d[k] = max(0, min(100, int(v)))
        self._save_config()
        return {"success": True, "device": d}

    # ── rooms ──────────────────────────────────────────────────
    def add_room(self, payload):
        rid = payload.get("id") or payload.get("name", "").lower().replace(" ", "_")
        if not rid:
            return {"success": False, "error": "Room id/name required"}
        if any(r["id"] == rid for r in self.rooms):
            return {"success": False, "error": "Room already exists"}
        room = {
            "id": rid,
            "name": payload.get("name", rid.replace("_", " ").title()),
            "icon": payload.get("icon", "🏠"),
        }
        self.rooms.append(room)
        self._save_config()
        return {"success": True, "room": room}

    def remove_room(self, room_id):
        self.rooms = [r for r in self.rooms if r["id"] != room_id]
        self._save_config()
        return {"success": True}

    # ── lookup ─────────────────────────────────────────────────
    def get_all_states(self):
        return {
            did: {
                "name": d["name"],
                "state": d["state"],
                "type": d["type"],
                "room": d.get("room", ""),
                "intensity": d.get("intensity", 100),
                "dimmable": d.get("dimmable", False),
                "icon": d.get("icon", ""),
                "gpio_pin": d["gpio_pin"],
                "aliases": d.get("aliases", []),
            }
            for did, d in self.devices.items()
        }

    def get_devices_by_room(self):
        out = {r["id"]: {"info": r, "devices": []} for r in self.rooms}
        out.setdefault("_unassigned", {"info": {"id": "_unassigned", "name": "Other", "icon": "📦"}, "devices": []})
        states = self.get_all_states()
        for did, d in states.items():
            room = d.get("room") or "_unassigned"
            if room not in out:
                room = "_unassigned"
            out[room]["devices"].append({"id": did, **d})
        return out

    def resolve_device_by_name(self, name):
        if not name:
            return None
        name_lower = name.lower().strip()
        if name_lower in self.devices:
            return name_lower
        for did, d in self.devices.items():
            if d["name"].lower() == name_lower:
                return did
            for alias in d.get("aliases", []):
                if alias.lower() == name_lower:
                    return did
        best = None
        best_score = 0
        for did, d in self.devices.items():
            score = 0
            if name_lower in d["name"].lower():
                score = len(name_lower)
            for alias in d.get("aliases", []):
                if name_lower in alias.lower() or alias.lower() in name_lower:
                    score = max(score, min(len(name_lower), len(alias)))
            if score > best_score:
                best_score = score
                best = did
        return best

    def resolve_room(self, name):
        if not name:
            return None
        name_lower = name.lower().strip()
        for r in self.rooms:
            if r["id"] == name_lower or r["name"].lower() == name_lower:
                return r["id"]
            if name_lower in r["name"].lower():
                return r["id"]
        return None

    def devices_in_room(self, room_id, device_type=None):
        return [did for did, d in self.devices.items()
                if d.get("room") == room_id and (device_type is None or d["type"] == device_type)]

    # ── status LEDs ────────────────────────────────────────────
    def set_status_led(self, led_name, state):
        if led_name in self.status_leds:
            pin = self.status_leds[led_name]["pin"]
            try:
                GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)
            except Exception as e:
                pass  # silent fail for status LEDs

    def pulse_status_led(self, led_name, times=3, delay=0.1):
        """Blink a status LED N times."""
        import time
        if led_name not in self.status_leds:
            return
        pin = self.status_leds[led_name]["pin"]
        for _ in range(times):
            try:
                GPIO.output(pin, GPIO.HIGH)
                time.sleep(delay)
                GPIO.output(pin, GPIO.LOW)
                time.sleep(delay)
            except Exception:
                break

    # ── info ───────────────────────────────────────────────────
    @staticmethod
    def gpio_info():
        return {
            "backend": GPIO_BACKEND,
            "real_gpio": REAL_GPIO,
        }

    def cleanup(self):
        for p in self._pwm.values():
            try:
                p.stop()
            except Exception:
                pass
        try:
            GPIO.cleanup()
        except Exception:
            pass
        print("[GPIO] Cleanup done")
