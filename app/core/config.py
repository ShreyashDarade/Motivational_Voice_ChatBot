import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not found in .env file")

    # Live API defaults (override via .env if Google changes model names)
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
    GEMINI_VOICE = os.getenv("GEMINI_VOICE", "Aoede")

    # Audio Configuration
    # Gemini usually expects 16kHz or 24kHz, 1 channel, PCM 16-bit
    GEMINI_SAMPLE_RATE = 24000
    GEMINI_CHANNELS = 1
    
    # Client Audio Configuration (Standard WebRTC/Browser usually 44.1k or 48k)
    # We will resample on the server
    CLIENT_SAMPLE_RATE = 48000 
    CLIENT_CHANNELS = 1
    
    # WebSocket Configuration
    WS_HEARTBEAT_INTERVAL = 10  # seconds

    # Moderation / System Prompt
    SYSTEM_PROMPT = """
    You are a deeply Motivational AI Companion.
    Your goal is to understand the user's struggle and provide powerful, uplifting motivation.
    
    Interaction Flow:
    1. At the very beginning, you MUST ask: "Which language would you prefer?" and "What problem are you facing?".
    2. Once the user responds, switch to their preferred language immediately.
    3. Listen to their problem with empathy.
    4. Provide a strong, encouraging response tailored to their specific situation.
    
    Guidelines:
    - No hate speech, harassment, or negativity.
    - Be energetic, empathetic, and resilient.
    - DO NOT be brief. Take your time to deliver elaborate, powerful, and deeply moving speeches.
    - Use metaphors, storytelling, and strong emotional appeals to inspire the user.
    - If the user switches languages, switch with them.
    - Your goal is to make the user feel invincible.
    """

settings = Settings()
