"""
Conversation Agent — full two-way voice chat loop.
100% offline using Vosk (wake) + Whisper (chat) + Ollama LLM + Piper TTS.

Flow:
  wait_for_wake_word → speak "I'm listening" → listen_once →
  LLM chat → parse_and_execute → speak response → repeat
"""

import time
import threading


class ConversationAgent:
    def __init__(self, stt, tts, llm, router, sleep_words=None):
        self.stt   = stt
        self.tts   = tts
        self.llm   = llm
        self.router = router
        self.sleep_words = sleep_words or [
            "goodbye", "stop listening", "bye", "sleep",
            "au revoir", "adiós", "bandh karo",
        ]
        self.active = False
        self._thread = None

    # ── Public API ───────────────────────────────────────────────────────────

    def start_conversation(self):
        """Run a full conversation turn (blocking). Called after wake word."""
        if self.active:
            return
        self.active = True

        try:
            self._run_conversation()
        except Exception as e:
            print(f"[Agent] Unexpected error: {e}")
        finally:
            self.active = False

    def start_in_background(self):
        t = threading.Thread(
            target=self.start_conversation, daemon=True, name="conv-agent"
        )
        t.start()
        self._thread = t
        return t

    # ── Core conversation loop ───────────────────────────────────────────────

    def _run_conversation(self):
        print("\n[Agent] ── Conversation started ──")

        # Signal the user that AURA is ready
        self.tts.speak("Yes, I'm listening.", blocking=False, lang="en")
        time.sleep(0.3)

        consecutive_silences = 0
        max_silences = 2   # exit after 2 silent turns

        while self.active:
            # ── Listen ──────────────────────────────────────────────────────
            # Use Whisper for multi-turn chat (multilingual + better accuracy)
            # Fall back to Vosk result if Whisper unavailable
            text = self.stt.listen_once(timeout=8, use_whisper=self.stt.whisper_enabled)

            if not text:
                consecutive_silences += 1
                print(f"[Agent] Silence ({consecutive_silences}/{max_silences})")
                if consecutive_silences >= max_silences:
                    print("[Agent] Timeout — returning to wake-word mode")
                    self.tts.speak("Going back to sleep. Say 'Aura' to wake me.",
                                   blocking=False)
                    break
                continue
            consecutive_silences = 0

            print(f"[Agent] 👤 User: {text}")

            # ── Sleep / stop words ──────────────────────────────────────────
            if any(w in text.lower() for w in self.sleep_words):
                lang = getattr(self.stt, "last_language", "en")
                print("[Agent] Sleep word detected — ending conversation")
                self.tts.speak("Goodbye!", blocking=True, lang=lang)
                break

            # ── Status LED: thinking ────────────────────────────────────────
            self._set_status_led("thinking", True)

            # ── LLM response ────────────────────────────────────────────────
            lang = getattr(self.stt, "last_language", "en")
            print("[Agent] 🤔 Thinking...")

            try:
                response = self.llm.chat(text)
            except Exception as e:
                print(f"[Agent] LLM error: {e}")
                response = "Sorry, I had trouble thinking. Please try again."

            self._set_status_led("thinking", False)
            print(f"[Agent] 🤖 AURA: {response[:120]}{'...' if len(response)>120 else ''}")

            # ── Execute any GPIO / device actions ───────────────────────────
            try:
                result = self.router.parse_and_execute(response)
                spoken = result.get("spoken", response)
                if result.get("actions_taken"):
                    for a in result["actions_taken"]:
                        if a.get("success"):
                            print(f"[Agent]    ✓ {a.get('message','')}")
            except Exception as e:
                print(f"[Agent] Router error: {e}")
                spoken = response

            # ── Speak ────────────────────────────────────────────────────────
            self._set_status_led("speaking", True)
            self.tts.speak(spoken, blocking=True, lang=lang)
            self._set_status_led("speaking", False)

            print("[Agent] Resuming listen...")

        self.active = False
        print("[Agent] ── Conversation ended ──\n")

    # ── Status LED helper ────────────────────────────────────────────────────

    def _set_status_led(self, name: str, state: bool):
        """Set a status LED via GPIO controller if available on the router."""
        try:
            gpio = getattr(self.router, "gpio", None)
            if gpio and hasattr(gpio, "set_status_led"):
                gpio.set_status_led(name, state)
        except Exception:
            pass
