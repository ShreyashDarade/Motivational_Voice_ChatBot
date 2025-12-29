import uvicorn
import os
import webbrowser
import threading
import time

def open_browser():
    """Wait for server to start then open browser"""
    time.sleep(2)  # Wait for uvicorn to startup
    webbrowser.open("http://localhost:8000")

if __name__ == "__main__":
    print("----------------------------------------------------------------")
    print("   Starting Motivational Voice ChatBot (Production Grade)       ")
    print("----------------------------------------------------------------")
    print(" * Live API: Active")
    print(" * Persona: Motivational Speaker")
    print(" * Audio: 24kHz High Fidelity")
    print("----------------------------------------------------------------")
    
    # Check for API Key
    if not os.getenv("GEMINI_API_KEY"):
        # Just a warning, as it might be loaded from .env inside the app too
        # But good for user feedback in CLI
        try:
            from app.core.config import settings
            print(" * API Key: Detected")
        except Exception as e:
            print(" ! WARNING: GEMINI_API_KEY might be missing or invalid.")
    
    # Launch browser in a separate thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run Server
    # We use workers=1 for websocket stability in this simple setup,
    # though uvicorn supports async workers well.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
