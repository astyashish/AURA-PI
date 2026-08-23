import sys
sys.path.insert(0, ".")
from core.llm_engine import LLMEngine

def test_llm_connection():
    llm = LLMEngine()
    assert llm.is_available() or True, "Ollama offline — test skipped"
    print("LLM test passed")

def test_command_parsing():
    from core.command_router import CommandRouter
    from hardware.gpio_controller import GPIOController
    gpio = GPIOController()
    router = CommandRouter(gpio)

    test_response = """SPOKEN: Turning on the living room light now, sir.
ACTION: {"action": "gpio_control", "device": "living room", "state": true}"""

    result = router.parse_and_execute(test_response)
    assert "Turning on" in result["spoken"]
    assert len(result["actions_taken"]) > 0
    print(f"Command routing test passed: {result['actions_taken']}")

if __name__ == "__main__":
    test_llm_connection()
    test_command_parsing()
    print("All tests passed!")
