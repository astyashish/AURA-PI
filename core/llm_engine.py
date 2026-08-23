"""LLM Engine — Ollama interface with dynamic device-aware system prompt."""

import json
import requests
from typing import Generator, Optional


BASE_PROMPT = """You are AURA, a witty but precise local AI assistant running on a Raspberry Pi.
You can control smart-home devices, analyze camera images, and answer questions.

RESPONSE FORMAT (read carefully):
- If the user asks to control a device (turn on/off, dim, set brightness, room commands), you MUST reply in EXACTLY this format:

SPOKEN: <one short, natural confirmation sentence (≤ 15 words)>
ACTION: {"action": "<verb>", ...fields}

Valid actions:
  • Toggle / set:        {"action":"gpio_control","device":"<name>","state":true|false}
  • Dim / set %:         {"action":"set_intensity","device":"<name>","intensity":0-100}
  • Whole room:          {"action":"room_off","room":"<room name>"}   or  "room_on"
  • All devices:         {"action":"all_off"}   or   {"action":"all_on"}

You MAY emit multiple ACTION lines for multi-device commands.

- For ANY other request (questions, chitchat, vision, info) reply normally in plain prose — NO ACTION block. Keep it under 3 sentences unless asked for detail.
- Never mention pin numbers or technical internals to the user.
- Use the exact device names listed below when emitting ACTION blocks.
"""

VISION_SYSTEM_PROMPT = """You are AURA vision module. Describe the image clearly and concisely.
Mention: objects, people (count + actions), readable text, environment, notable details.
Stay under 5 short sentences. Do not invent things that aren't there."""


class LLMEngine:
    def __init__(self, host=None):
        import os
        
        config = {}
        try:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "aura_config.json")
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
            
        models_cfg = config.get("models", {})
        
        self.host = host or config.get("ollama", {}).get("host", "http://localhost:11434")
        self.default_model = models_cfg.get("default", "qwen2.5:3b")
        self.vision_model = models_cfg.get("vision", "llava:7b")
        self.fast_model = models_cfg.get("fast", "qwen2.5:0.5b")
        self.conversation_history = []
        self.max_history = 20
        self._device_context = ""

    # ── connectivity ───────────────────────────────────────────
    def is_available(self) -> bool:
        try:
            return requests.get(f"{self.host}/api/tags", timeout=3).status_code == 200
        except Exception:
            return False

    def list_models(self) -> list:
        try:
            r = requests.get(f"{self.host}/api/tags", timeout=5)
            if r.status_code == 200:
                return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            pass
        return []

    def set_model(self, name):
        self.default_model = name

    def update_device_context(self, devices_by_room):
        """Inject current device list into system prompt."""
        lines = ["", "CURRENT DEVICES:"]
        for room_id, room in devices_by_room.items():
            if not room["devices"]:
                continue
            lines.append(f"  {room['info']['name']}:")
            for d in room["devices"]:
                state = "ON" if d["state"] else "OFF"
                dim = f" ({d['intensity']}%)" if d.get("dimmable") else ""
                lines.append(f"    - {d['name']} [{d['type']}] — {state}{dim}")
        self._device_context = "\n".join(lines)

    def _system_prompt(self):
        return BASE_PROMPT + ("\n" + self._device_context if self._device_context else "")

    # ── chat ──────────────────────────────────────────────────
    def chat(self, user_message: str, model: str = None, stream: bool = False):
        model = model or self.default_model
        self.conversation_history.append({"role": "user", "content": user_message})
        if len(self.conversation_history) > self.max_history:
            self.conversation_history = self.conversation_history[-self.max_history:]

        payload = {
            "model": model,
            "messages": [{"role": "system", "content": self._system_prompt()}] + self.conversation_history,
            "stream": stream,
            "options": {"temperature": 0.2, "num_predict": 300},
        }
        try:
            if stream:
                return self._stream_chat(payload)
            r = requests.post(f"{self.host}/api/chat", json=payload, timeout=120)
            r.raise_for_status()
            content = r.json()["message"]["content"]
            self.conversation_history.append({"role": "assistant", "content": content})
            return content
        except requests.exceptions.ConnectionError:
            return "ERROR: Cannot connect to Ollama. Start it with `ollama serve`."
        except Exception as e:
            return f"ERROR: {e}"

    def _stream_chat(self, payload) -> Generator:
        full = ""
        try:
            with requests.post(f"{self.host}/api/chat", json=payload, stream=True, timeout=120) as r:
                for line in r.iter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    if "message" in data:
                        tok = data["message"].get("content", "")
                        full += tok
                        yield tok
                    if data.get("done"):
                        break
        except Exception as e:
            yield f"\nERROR: {e}"
        finally:
            if full:
                self.conversation_history.append({"role": "assistant", "content": full})

    # ── vision ────────────────────────────────────────────────
    def analyze_image(self, image_base64: str, prompt: str = "Describe what you see.") -> str:
        payload = {
            "model": self.vision_model,
            "messages": [{"role": "user", "content": prompt, "images": [image_base64]}],
            "system": VISION_SYSTEM_PROMPT,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 220},
        }
        try:
            r = requests.post(f"{self.host}/api/chat", json=payload, timeout=180)
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            return f"Vision analysis failed: {e}. (Pull the model: `ollama pull llava:7b`)"

    def quick_query(self, prompt: str) -> str:
        payload = {
            "model": self.fast_model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 100},
        }
        try:
            r = requests.post(f"{self.host}/api/generate", json=payload, timeout=30)
            r.raise_for_status()
            return r.json()["response"]
        except Exception:
            return ""

    def clear_history(self):
        self.conversation_history = []
