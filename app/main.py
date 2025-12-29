from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.api import websocket
import os
import logging
import sys

# Configure Logging to display in Terminal
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger("app.main")
logger.info("Starting Application...")

app = FastAPI(title="Gemini Voice ChatBot", version="1.0.0")

# Include Websocket Router
app.include_router(websocket.router)

# Serve static files (if we want a basic UI)
# We will create a 'static' directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def get():
    return FileResponse(os.path.join(static_dir, 'index.html'))

if __name__ == "__main__":
    import uvicorn
    # Production grade config: multiple workers usually, but for websockets and stateful connections, 
    # we need to be careful with workers if not using a shared layer (Redis) for state. 
    # Here, state is per-websocket, so multiple workers are fine.
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
