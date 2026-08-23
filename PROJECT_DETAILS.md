# JARVIS-PI Project Details

Yeh document current repository implementation par based hai. Jahan runtime measurement ya Raspberry Pi hardware evidence available nahi hai, wahan usse clearly marked kiya gaya hai.

## Tumne kaunsa Raspberry Pi use kiya?

Project documentation Raspberry Pi 5 ko target platform batati hai, aur full GPIO features ke liye 8 GB RAM recommended hai. Repository mein kisi specific physical board, revision, serial number, ya benchmark run ka record nahi hai.

Development ke liye Windows/Linux mock GPIO mode bhi supported hai. Raspberry Pi par `/proc/cpuinfo` se platform detect hota hai; non-Pi systems par mock GPIO use hota hai.

## Kaunsa Ollama model use kiya?

Configured models:

- Default config: `gemma2:2b`
- Runtime chat default: `qwen2.5:0.5b`
- Fast query model: `qwen2.5:0.5b`
- Vision model: `llava:7b`
- Other available option: `mistral:7b`

Important: `core/llm_engine.py` ka constructor runtime mein `qwen2.5:0.5b` set karta hai. Isliye current implementation mein normal chat ke liye Qwen use hota hai, jab tak model explicitly change na kiya jaye. `config/jarvis_config.json` ka `models.default` abhi runtime default ko override nahi karta.

## Prompt kaise design kiya?

Prompt `core/llm_engine.py` mein do layers mein design kiya gaya hai:

1. `BASE_PROMPT` JARVIS ki personality aur output rules define karta hai.
2. `update_device_context()` current rooms, devices, state, aur intensity ko system prompt mein inject karta hai.

Device-control request ke liye model ko concise spoken confirmation aur machine-readable action dena hota hai:

- `SPOKEN:` ke baad 15 words ya usse kam confirmation.
- `ACTION:` ke baad ek JSON object.
- Multi-device request ke liye multiple `ACTION` lines allowed.
- Normal questions ke liye plain prose, bina action block ke.
- User ko GPIO pin numbers ya internal technical details nahi batane hain.

Generation settings low-variance behavior ke liye temperature `0.2` aur maximum `300` predicted tokens use karti hain.

## JSON command format

Single device on/off:

```json
{"action":"gpio_control","device":"living room light","state":true}
```

Brightness:

```json
{"action":"set_intensity","device":"desk light","intensity":60}
```

Room control:

```json
{"action":"room_off","room":"bedroom"}
```

All devices:

```json
{"action":"all_off"}
```

Expected complete response example:

```text
SPOKEN: Living room light is now on.
ACTION: {"action":"gpio_control","device":"living room light","state":true}
```

`CommandRouter` JSON parse karta hai, device ya room resolve karta hai, aur result mein `success`, `device_id`, `state`, `intensity`, ya `error` return karta hai. Invalid JSON par natural-language fallback attempt hota hai.

## GPIO mapping

BCM numbering use hoti hai.

| Device | GPIO |
|---|---:|
| Living Room Light | 17 |
| Living Room Lamp | 4 |
| Bedroom Light | 27 |
| Night Light | 18 |
| Desk Light | 5 |
| Kitchen Light | 19 |
| Ceiling Fan | 6 |
| Bedroom Fan | 13 |
| ashish | 26 |
| lamp | 26 |
| fast fan | 26 |
| vv | 26 |

Status LEDs:

| Indicator | GPIO | Color |
|---|---:|---|
| Thinking | 22 | Blue |
| Speaking | 23 | Green |
| Camera | 24 | Red |

Note: GPIO 26 multiple configured devices share kar raha hai (`ashish`, `lamp`, `fast fan`, `vv`). Real hardware par yeh mapping conflict create kar sakti hai aur wiring verify karni chahiye.

## Authorization/safety layer

Current code mein authentication ya authorization layer implemented nahi hai. Flask routes `0.0.0.0` par expose ho sakte hain, CORS `*` configured hai, aur device-control endpoints login/token check nahi karte.

Jo basic validation present hai:

- Unknown device ya room reject hota hai.
- Unknown action reject hota hai.
- Intensity `0-100` ke beech clamp hoti hai.
- GPIO writes centralized `GPIOController` ke through hoti hain.
- Platform detection ke karan development machine par mock GPIO use hota hai.

Production ya network use se pehle authentication, HTTPS/reverse proxy, allowlisted actions/devices, confirmation for destructive commands such as `all_off`, aur audit logging add karna zaroori hai.

## Offline mode kaise test kiya?

Architecture offline-first hai:

- Ollama localhost `http://localhost:11434` par call hota hai.
- Vosk speech-to-text aur Piper text-to-speech local components ke liye configured hain.
- GPIO non-Pi environment mein mock implementation use karta hai.
- Camera aur vision processing local code path se hoti hai.

Current automated tests:

```text
pytest -q
5 passed
```

GPIO tests mock mode mein on/off, toggle, state lookup, aur name resolution check karte hain. LLM command test `ACTION` parsing aur routing check karta hai. Voice tests missing dependencies ke case mein graceful initialization check karte hain.

Caveat: `tests/test_llm.py` ka connectivity assertion `llm.is_available() or True` hai, isliye Ollama unavailable hone par bhi test fail nahi hota. True end-to-end offline test, model preloading test, aur network-blocked integration test abhi recorded nahi hain.

## Response latency

Repository mein latency benchmark ya measured percentile available nahi hai.

Configured request timeouts:

- Ollama availability check: 3 seconds
- Model list: 5 seconds
- Normal chat: 120 seconds
- Vision analysis: 180 seconds
- Fast query: 30 seconds
- Voice listening timeout: 10 seconds

Actual response latency Raspberry Pi model, thermal state, model already loaded hai ya nahi, prompt length, aur input mode par depend karegi. Latency report dene ke liye warm-up ke baad at least 30 representative commands ka end-to-end benchmark record karna hoga.

## RAM/CPU usage

RAM aur CPU usage ka koi measured benchmark repository mein nahi hai. Expected load mein Ollama model memory, Python/Flask process, Vosk/Piper models, OpenCV camera processing, aur optional LLaVA vision model include honge. LLaVA 7B sabse heavy component hone ki sambhavna hai, lekin exact number hardware aur quantization par depend karega.

Is metric ko report karne ke liye Raspberry Pi par idle, voice-only, normal chat, aur vision scenarios mein `free -h`, `top`/`htop`, aur process-level sampling record karni hogi.

## Kitne commands correctly execute hue?

Current repository evidence ke hisaab se:

- Automated suite: `5 passed`.
- Dedicated command-routing test: 1 representative JSON command successfully routed.
- GPIO test: on, off, toggle, state lookup, aur name resolution checks pass.
- Total real-user commands, accuracy percentage, ya command confusion matrix recorded nahi hai.

Isliye defensible answer hai: **1 representative LLM command-routing case verified; total command success count measured nahi hua.**
