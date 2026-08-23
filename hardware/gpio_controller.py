"""GPIO Controller with CRUD, intensity (PWM), rooms, and persistence."""

import json
import os
from pathlib import Path
from threading import Lock


def _is_raspberry_pi():
    try:
        with open("/proc/cpuinfo", "r") as f:
            return "Raspberry Pi" in f.read()
    except Exception:
        return False


if _is_raspberry_pi() and os.getenv("ENABLE_GPIO", "true").lower() == "true":
    try:
        import RPi.GPIO as GPIO  # type: ignore
        # Test if this RPi.GPIO version actually supports this board (e.g. Pi 5 RP1 chip)
        GPIO.setmode(GPIO.BCM)
        REAL_GPIO = True
        print("[GPIO] Running on Raspberry Pi — real GPIO enabled")
    except (ImportError, RuntimeError) as e:
        from hardware import mock_gpio as GPIO
        REAL_GPIO = False
        print(f"[GPIO] RPi.GPIO not available or incompatible ({e}) — using mock")
else:
    from hardware import mock_gpio as GPIO
    REAL_GPIO = False
    print("[GPIO] Dev mode — using mock GPIO")


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
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        for d in self.devices.values():
            self._setup_pin(d)
        for led in self.status_leds.values():
            GPIO.setup(led["pin"], GPIO.OUT, initial=GPIO.LOW)

    def _setup_pin(self, device):
        pin = device["gpio_pin"]
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        if REAL_GPIO and device.get("dimmable"):
            try:
                p = GPIO.PWM(pin, 1000)
                p.start(0)
                self._pwm[pin] = p
            except Exception as e:
                print(f"[GPIO] PWM init failed for pin {pin}: {e}")

    # ── apply state to hardware ────────────────────────────────
    def _apply(self, device):
        pin = device["gpio_pin"]
        state = device["state"]
        intensity = max(0, min(100, int(device.get("intensity", 100))))
        if REAL_GPIO and pin in self._pwm:
            self._pwm[pin].ChangeDutyCycle(intensity if state else 0)
        else:
            GPIO.output(pin, GPIO.HIGH if state else GPIO.LOW)

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
        # exact id
        if name_lower in self.devices:
            return name_lower
        # exact name / alias
        for did, d in self.devices.items():
            if d["name"].lower() == name_lower:
                return did
            for alias in d.get("aliases", []):
                if alias.lower() == name_lower:
                    return did
        # partial
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
            try:
                GPIO.output(self.status_leds[led_name]["pin"], GPIO.HIGH if state else GPIO.LOW)
            except Exception:
                pass

    def cleanup(self):
        for p in self._pwm.values():
            try:
                p.stop()
            except Exception:
                pass
        GPIO.cleanup()
