import sys
sys.path.insert(0, ".")
from hardware.gpio_controller import GPIOController

def test_gpio():
    gpio = GPIOController()

    # Test turning devices on/off
    result = gpio.set_device("living_room_light", True)
    assert result["success"], f"Failed: {result}"
    print(f"✓ Turn on: {result['message']}")

    result = gpio.set_device("living_room_light", False)
    assert result["success"]
    print(f"✓ Turn off: {result['message']}")

    result = gpio.toggle_device("bedroom_light")
    assert result["success"]
    print(f"✓ Toggle: {result['message']}")

    states = gpio.get_all_states()
    assert "living_room_light" in states
    print(f"✓ All states: {list(states.keys())}")

    device_id = gpio.resolve_device_by_name("living room")
    assert device_id == "living_room_light"
    print(f"✓ Name resolve: '{device_id}'")

    print("\n✓ All GPIO tests passed!")

if __name__ == "__main__":
    test_gpio()
