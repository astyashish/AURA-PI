"""Command Router — parses LLM ACTION blocks (or natural language)
and dispatches device + room operations."""

import json
import re
from hardware.gpio_controller import GPIOController


# words that signal off
OFF_WORDS = {"off", "stop", "disable", "shut", "kill", "deactivate", "switch off", "turn off"}
ON_WORDS = {"on", "start", "enable", "activate", "switch on", "turn on", "light up", "power on"}


class CommandRouter:
    def __init__(self, gpio: GPIOController):
        self.gpio = gpio

    # ── public entry point ─────────────────────────────────────
    def parse_and_execute(self, llm_response: str) -> dict:
        spoken = llm_response
        actions_taken = []

        # spoken block
        m = re.search(r"SPOKEN:\s*(.+?)(?=ACTION:|$)", llm_response, re.DOTALL | re.IGNORECASE)
        if m:
            spoken = m.group(1).strip()

        # extract every ACTION json
        for match in re.finditer(r"ACTION:\s*(\{.*?\})", llm_response, re.DOTALL | re.IGNORECASE):
            try:
                action = json.loads(match.group(1))
                actions_taken.append(self._execute(action))
            except json.JSONDecodeError:
                pass

        # fallback rule-based
        if not actions_taken:
            inferred = self._infer_from_text(llm_response)
            for a in inferred:
                actions_taken.append(self._execute(a))

        # tidy spoken text
        spoken = re.sub(r"ACTION:\s*\{.*?\}", "", spoken, flags=re.DOTALL).strip()
        if not spoken:
            spoken = "Done." if actions_taken else llm_response.strip()

        return {"spoken": spoken, "actions_taken": actions_taken, "raw": llm_response}

    # ── direct API used by web UI quick commands ───────────────
    def execute_user_text(self, text: str) -> list:
        out = []
        for a in self._infer_from_text(text):
            out.append(self._execute(a))
        return out

    # ── action dispatch ────────────────────────────────────────
    def _execute(self, action: dict) -> dict:
        a = (action.get("action") or "").lower()

        if a in ("gpio_control", "set_device", "device_set"):
            did = self._resolve(action)
            if not did:
                return {"success": False, "error": f"Unknown device: {action.get('device')}"}
            state = bool(action.get("state", True))
            if "intensity" in action:
                self.gpio.set_intensity(did, action["intensity"])
            return self.gpio.set_device(did, state)

        if a in ("gpio_toggle", "toggle"):
            did = self._resolve(action)
            if not did:
                return {"success": False, "error": f"Unknown device: {action.get('device')}"}
            return self.gpio.toggle_device(did)

        if a in ("set_intensity", "dim", "brightness"):
            did = self._resolve(action)
            if not did:
                return {"success": False, "error": f"Unknown device: {action.get('device')}"}
            return self.gpio.set_intensity(did, action.get("intensity", action.get("value", 50)))

        if a in ("all_off", "everything_off"):
            results = [self.gpio.set_device(did, False) for did in list(self.gpio.devices)]
            return {"success": True, "message": "All devices off", "devices": results}

        if a in ("all_on", "everything_on"):
            results = [self.gpio.set_device(did, True) for did in list(self.gpio.devices)]
            return {"success": True, "message": "All devices on", "devices": results}

        if a in ("room_off", "room_on"):
            room = self.gpio.resolve_room(action.get("room", ""))
            if not room:
                return {"success": False, "error": "Unknown room"}
            state = a == "room_on"
            results = [self.gpio.set_device(d, state) for d in self.gpio.devices_in_room(room)]
            return {"success": True, "message": f"{room} {'on' if state else 'off'}", "devices": results}

        return {"success": False, "error": f"Unknown action: {a}"}

    def _resolve(self, action: dict):
        name = action.get("device") or action.get("device_id") or action.get("name")
        return self.gpio.resolve_device_by_name(name) if name else None

    # ── natural-language fallback ──────────────────────────────
    def _infer_from_text(self, text: str) -> list:
        t = text.lower()
        actions = []

        if any(p in t for p in ["all lights off", "everything off", "turn off all", "all off", "lights off everywhere"]):
            return [{"action": "all_off"}]
        if any(p in t for p in ["all lights on", "everything on", "turn on all", "all on"]):
            return [{"action": "all_on"}]

        # room-level
        for r in self.gpio.rooms:
            rname = r["name"].lower()
            if rname in t or r["id"].replace("_", " ") in t:
                if any(w in t for w in ["off", "shut", "kill"]):
                    actions.append({"action": "room_off", "room": r["id"]})
                    return actions
                if any(w in t for w in ["on", "light up", "activate"]) and "turn" in t:
                    actions.append({"action": "room_on", "room": r["id"]})
                    return actions

        # intensity / dim / set to NN%
        m = re.search(r"(\d{1,3})\s*%", t)
        intensity = int(m.group(1)) if m else None

        # match devices
        for did, d in self.gpio.devices.items():
            names = [d["name"].lower()] + [a.lower() for a in d.get("aliases", [])]
            if any(n in t for n in names):
                turn_off = any(w in t for w in ["turn off", "switch off", "shut", "disable", " off"])
                turn_on = any(w in t for w in ["turn on", "switch on", "enable", "activate", " on "])
                if intensity is not None:
                    actions.append({"action": "set_intensity", "device": did, "intensity": intensity})
                elif turn_off:
                    actions.append({"action": "gpio_control", "device": did, "state": False})
                elif turn_on:
                    actions.append({"action": "gpio_control", "device": did, "state": True})
        return actions
