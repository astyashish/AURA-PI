import sys
sys.path.insert(0, ".")

def test_voice_input_safe_init():
    """VoiceInput must initialize gracefully even without Vosk/PyAudio."""
    from core.voice_input import VoiceInput
    vi = VoiceInput()
    # If vosk/pyaudio not installed, enabled should be False (no crash)
    assert isinstance(vi.enabled, bool)
    print(f"✓ VoiceInput init OK (enabled={vi.enabled})")

def test_voice_output_safe_init():
    """VoiceOutput must initialize gracefully and pick an engine or be silent."""
    from core.voice_output import VoiceOutput
    vo = VoiceOutput()
    assert isinstance(vo.enabled, bool)
    print(f"✓ VoiceOutput init OK (engine={vo.engine}, enabled={vo.enabled})")

if __name__ == "__main__":
    test_voice_input_safe_init()
    test_voice_output_safe_init()
    print("\n✓ All voice tests passed!")
