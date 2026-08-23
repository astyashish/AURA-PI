"""
Wake word manager — wraps VoiceInput wake word detection and triggers listening loop.
"""

import threading
from core.voice_input import VoiceInput
from core.voice_output import VoiceOutput


class WakeWordManager:
    def __init__(self, voice_input: VoiceInput, voice_output: VoiceOutput,
                 wake_word: str = "aura", on_command_callback=None):
        self.voice_input = voice_input
        self.voice_output = voice_output
        self.wake_word = wake_word
        self.on_command_callback = on_command_callback
        self.active = False

    def start(self):
        self.active = True
        self.voice_input.detect_wake_word(
            wake_word=self.wake_word,
            callback=self._on_wake
        )

    def _on_wake(self):
        self.voice_output.speak("Yes? How can I help?", blocking=False)
        command = self.voice_input.listen_once(timeout=10)
        if command and self.on_command_callback:
            self.on_command_callback(command)

    def stop(self):
        self.active = False
