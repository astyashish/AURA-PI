"""
Conversational Agent Loop
Handles continuous two-way voice conversation with multilingual support.
"""
import time
import threading

class ConversationAgent:
    def __init__(self, stt, tts, llm, router, sleep_words=None):
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.router = router
        self.sleep_words = sleep_words or ["goodbye", "stop listening", "bye", "au revoir", "adiós"]
        self.active = False
        
    def start_conversation(self):
        """Starts a blocking loop for continuous conversation."""
        if self.active:
            return
            
        self.active = True
        print("\n[Conversation] Agent activated. Listening...")
        self.tts.speak("I am listening.", blocking=True, lang="en")
        
        while self.active:
            # We use Whisper for conversational turns if available
            text = self.stt.listen_once(timeout=10, use_whisper=True)
            
            if not text:
                print("[Conversation] Silence timeout. Exiting conversation mode.")
                self.active = False
                break
                
            print(f"[Conversation User] {text}")
            
            if any(word in text.lower() for word in self.sleep_words):
                print("[Conversation] Sleep word detected.")
                lang = getattr(self.stt, "last_language", "en")
                self.tts.speak("Goodbye.", blocking=True, lang=lang)
                self.active = False
                break
                
            # Get the language that was detected by whisper
            lang = getattr(self.stt, "last_language", "en")
            
            print(f"[Conversation AURA] (Thinking...)")
            response = self.llm.chat(text)
            print(f"[Conversation AURA] {response}")
            
            # Execute potential hardware commands 
            result = self.router.parse_and_execute(response)
            
            # Speak out the response in the correct language
            self.tts.speak(result["spoken"], blocking=True, lang=lang)
            
            print("[Conversation] Resuming listening...")

    def start_in_background(self):
        """Starts the conversation loop in a background thread."""
        t = threading.Thread(target=self.start_conversation, daemon=True)
        t.start()
        return t
