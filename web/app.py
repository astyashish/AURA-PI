"""Flask + SocketIO web server — Jarvis dashboard and realtime hub."""

import os
import sys
import base64
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from flask_socketio import SocketIO, emit

# allow imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_engine import LLMEngine
from core.command_router import CommandRouter
from core.vision_engine import VisionEngine
from hardware.gpio_controller import GPIOController
from hardware.camera_handler import CameraHandler


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "jarvis-dev-secret")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# core instances
llm = LLMEngine(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
gpio = GPIOController()
router = CommandRouter(gpio)
camera = CameraHandler()
vision = VisionEngine(camera, llm)

camera.start()


# helper to keep LLM aware of current state
def _refresh_llm_context():
    llm.update_device_context(gpio.get_devices_by_room())


_refresh_llm_context()


# ═══ HTTP routes ════════════════════════════════════════════════════════════
@app.route("/favicon.ico")
def favicon():
    # Inline SVG favicon — no external file needed
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<circle cx="50" cy="50" r="45" fill="#000d18" stroke="#00d4ff" stroke-width="4"/>'
        '<text y=".85em" x="22" font-size="60" fill="#00d4ff" font-family="monospace">J</text>'
        '</svg>'
    )
    return Response(svg, mimetype="image/svg+xml")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify({
        "ollama": llm.is_available(),
        "models": llm.list_models(),
        "current_model": llm.default_model,
        "camera": camera.enabled,
        "tts": True,        # browser-side
        "voice": True,      # browser-side
        "real_gpio": False if "mock" in str(type(gpio).__module__).lower() else True,
    })


# ── devices ────────────────────────────────────────────────────────────────
@app.route("/api/devices")
def api_devices():
    return jsonify({
        "by_room": gpio.get_devices_by_room(),
        "flat": gpio.get_all_states(),
        "rooms": gpio.rooms,
    })


@app.route("/api/devices/add", methods=["POST"])
def api_device_add():
    result = gpio.add_device(request.json or {})
    if result["success"]:
        _refresh_llm_context()
        socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


@app.route("/api/devices/<device_id>", methods=["DELETE"])
def api_device_delete(device_id):
    result = gpio.remove_device(device_id)
    if result["success"]:
        _refresh_llm_context()
        socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


@app.route("/api/devices/<device_id>", methods=["PATCH"])
def api_device_update(device_id):
    result = gpio.update_device(device_id, request.json or {})
    if result["success"]:
        _refresh_llm_context()
        socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


@app.route("/api/devices/<device_id>/toggle", methods=["POST"])
def api_device_toggle(device_id):
    result = gpio.toggle_device(device_id)
    socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


@app.route("/api/devices/<device_id>/set", methods=["POST"])
def api_device_set(device_id):
    data = request.json or {}
    if "intensity" in data:
        result = gpio.set_intensity(device_id, data["intensity"])
    else:
        result = gpio.set_device(device_id, bool(data.get("state", False)))
    socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


# ── rooms ──────────────────────────────────────────────────────────────────
@app.route("/api/rooms", methods=["GET", "POST"])
def api_rooms():
    if request.method == "POST":
        result = gpio.add_room(request.json or {})
        if result["success"]:
            _refresh_llm_context()
            socketio.emit("devices_update", gpio.get_devices_by_room())
        return jsonify(result)
    return jsonify({"rooms": gpio.rooms})


@app.route("/api/rooms/<room_id>", methods=["DELETE"])
def api_room_delete(room_id):
    result = gpio.remove_room(room_id)
    if result["success"]:
        socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify(result)


# ── camera ─────────────────────────────────────────────────────────────────
@app.route("/api/camera/capture", methods=["POST"])
def api_camera_capture():
    result = camera.capture_frame()
    return jsonify(result)


@app.route("/api/camera/preview")
def api_camera_preview():
    frame = camera.get_preview_frame()
    if frame:
        return jsonify({"success": True, "frame": frame})
    return jsonify({"success": False})


@app.route("/api/camera/analyze", methods=["POST"])
def api_camera_analyze():
    prompt = (request.json or {}).get("prompt", "Describe what you see.")
    result = vision.describe_scene(prompt)
    return jsonify(result)


# ── models ─────────────────────────────────────────────────────────────────
@app.route("/api/models")
def api_models():
    return jsonify({"models": llm.list_models(), "current": llm.default_model})


@app.route("/api/model/set", methods=["POST"])
def api_model_set():
    model = (request.json or {}).get("model")
    if model:
        llm.set_model(model)
        return jsonify({"success": True, "model": model})
    return jsonify({"success": False})


@app.route("/api/clear_history", methods=["POST"])
def api_clear():
    llm.clear_history()
    return jsonify({"success": True})


# ── chat (HTTP) — used by Voice mode for low-latency replies ──────────────
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.json or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"success": False, "error": "empty"})
    _refresh_llm_context()
    response = llm.chat(msg, stream=False)
    parsed = router.parse_and_execute(response)
    if parsed["actions_taken"]:
        _refresh_llm_context()
        socketio.emit("devices_update", gpio.get_devices_by_room())
    return jsonify({
        "success": True,
        "spoken": parsed["spoken"],
        "raw": response,
        "actions": parsed["actions_taken"],
    })


# ═══ Socket.IO ══════════════════════════════════════════════════════════════
@socketio.on("connect")
def on_connect():
    _refresh_llm_context()
    emit("connected", {"status": "Jarvis online"})
    emit("devices_update", gpio.get_devices_by_room())
    emit("status_update", {
        "ollama": llm.is_available(),
        "model": llm.default_model,
        "models": llm.list_models(),
    })


@socketio.on("chat_message")
def on_chat(data):
    msg = (data.get("message") or "").strip()
    if not msg:
        return
    emit("thinking", {"state": True})

    # vision intent
    if any(k in msg.lower() for k in ["what do you see", "look at", "describe what", "analyze image", "what's in front", "camera view"]):
        if camera.enabled:
            emit("log", {"text": "📷 Capturing for analysis..."})
            result = vision.describe_scene(msg)
            text = result.get("description", "Camera unavailable.")
            frame = camera.get_preview_frame()
            if frame:
                emit("camera_frame", {"frame": frame, "caption": text[:100]})
            emit("response_complete", {"text": text, "spoken": text, "actions": []})
            emit("thinking", {"state": False})
            return

    # standard LLM chat — stream tokens
    full = ""
    for tok in llm.chat(msg, stream=True):
        full += tok
        emit("token", {"token": tok})

    parsed = router.parse_and_execute(full)
    if parsed["actions_taken"]:
        _refresh_llm_context()
        socketio.emit("devices_update", gpio.get_devices_by_room())
        for a in parsed["actions_taken"]:
            emit("action_executed", a)

    emit("response_complete", {
        "text": full,
        "spoken": parsed["spoken"],
        "actions": parsed["actions_taken"],
    })
    emit("thinking", {"state": False})


@socketio.on("voice_transcript")
def on_voice_transcript(data):
    """Receive transcript from browser SpeechRecognition and run as chat."""
    on_chat(data)


@socketio.on("device_toggle")
def on_device_toggle(data):
    result = gpio.toggle_device(data.get("device_id"))
    emit("devices_update", gpio.get_devices_by_room(), broadcast=True)
    emit("action_executed", result)


def run_server(host="0.0.0.0", port=5000):
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    run_server()
