from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import logging
import traceback
import time
import uuid
from app.services.gemini_service import GeminiLiveService
from app.services.audio_utils import AudioProcessor
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = uuid.uuid4().hex[:8]
    client_host = getattr(websocket.client, "host", "unknown")
    logger.info("[%s] Client connected (%s)", session_id, client_host)
    
    # Initialize services for this session
    gemini_service = GeminiLiveService(session_id=session_id)
    audio_processor = AudioProcessor(
        input_rate=settings.CLIENT_SAMPLE_RATE,
        output_rate=settings.GEMINI_SAMPLE_RATE
    )

    # Lightweight per-session counters (avoid per-chunk logs unless debugging).
    last_stats_log = time.monotonic()
    in_audio_bytes = 0
    in_audio_chunks = 0
    out_audio_bytes = 0
    out_audio_chunks = 0
    out_audio_bytes_window = 0
    out_audio_chunks_window = 0
    last_out_stats_log = time.monotonic()
    seen_gemini_audio = False
    
    try:
        await gemini_service.connect()
        
        # Initialize Greeting immediately after handshake
        # The response will be buffered by the websocket until we start reading
        logger.info("[%s] Sending initial greeting trigger...", session_id)
        await gemini_service.send_text("Hello! Please warmly welcome the user and immediately ask them specifically: 'Which language would you prefer to speak in?' and 'What challenge or problem are you facing today?' so you can motivate them.")
        
    except Exception as e:
        logger.error("[%s] Failed to connect to Gemini: %s", session_id, e)
        await websocket.close(code=1011) # Internal Error
        return

    # Task to handle incoming audio from client -> Gemini
    async def receive_from_client():
        nonlocal last_stats_log, in_audio_bytes, in_audio_chunks
        try:
            while True:
                # receive() returns an ASGI message dict which can contain 'text' or 'bytes'
                message = await websocket.receive()
                
                if "bytes" in message and message["bytes"]:
                    data = message["bytes"]
                    in_audio_chunks += 1
                    in_audio_bytes += len(data)

                    # Process audio (Resample 48k -> 24k)
                    processed_audio = audio_processor.resample_audio(data, input_format='int16')
                    if processed_audio:
                        await gemini_service.send_audio(processed_audio)

                    # Periodic stats to terminal to help debug "mic not reaching Gemini"
                    now = time.monotonic()
                    if now - last_stats_log >= 1.0:
                        logger.info(
                            "[%s] RX mic: %d chunks / %d bytes (input_rate=%d -> %d)",
                            session_id,
                            in_audio_chunks,
                            in_audio_bytes,
                            audio_processor.input_rate,
                            audio_processor.output_rate,
                        )
                        last_stats_log = now
                        in_audio_chunks = 0
                        in_audio_bytes = 0
                        
                elif "text" in message and message["text"]:
                    # Handle JSON messages (e.g., Ping for latency, Config)
                    try:
                        import json
                        payload = json.loads(message["text"])
                        msg_type = payload.get("type")

                        if msg_type == "ping":
                            # Send pong back immediately
                            await websocket.send_json({
                                "type": "pong", 
                                "timestamp": payload.get("timestamp")
                            })
                        
                        elif msg_type == "config":
                            # Update AudioProcessor with client's actual Sample Rate
                            client_rate = payload.get("sampleRate")
                            if client_rate:
                                audio_processor.input_rate = int(client_rate)
                                logger.info(
                                    "[%s] Client config: sendRate=%sHz (context=%sHz, chunkMs=%s)",
                                    session_id,
                                    client_rate,
                                    payload.get("sourceSampleRate"),
                                    payload.get("chunkMs"),
                                )
                                
                    except Exception as e:
                        logger.warning("[%s] Failed to parse text message: %s", session_id, e)

        except WebSocketDisconnect:
            logger.info("[%s] Client disconnected", session_id)
        except Exception as e:
            logger.error("[%s] Error in receive_from_client: %s", session_id, e)
            traceback.print_exc()

    # Task to handle incoming audio from Gemini -> Client
    async def send_to_client():
        nonlocal out_audio_bytes, out_audio_chunks, out_audio_bytes_window, out_audio_chunks_window, last_out_stats_log, seen_gemini_audio
        try:
            async for audio_chunk in gemini_service.receive():
                if audio_chunk:
                    out_audio_chunks += 1
                    out_audio_bytes += len(audio_chunk)
                    out_audio_chunks_window += 1
                    out_audio_bytes_window += len(audio_chunk)

                    if not seen_gemini_audio:
                        logger.info("[%s] First audio received from Gemini (%d bytes)", session_id, len(audio_chunk))
                        seen_gemini_audio = True

                    now = time.monotonic()
                    if now - last_out_stats_log >= 1.0:
                        logger.info(
                            "[%s] TX audio to browser: %d chunks / %d bytes",
                            session_id,
                            out_audio_chunks_window,
                            out_audio_bytes_window,
                        )
                        last_out_stats_log = now
                        out_audio_chunks_window = 0
                        out_audio_bytes_window = 0

                    # Send back directly (Client will play 24k PCM)
                    await websocket.send_bytes(audio_chunk)
        except Exception as e:
            logger.error("[%s] Error in send_to_client: %s", session_id, e)

    try:
        # Run both tasks
        client_task = asyncio.create_task(receive_from_client())
        gemini_task = asyncio.create_task(send_to_client())
        
        done, pending = await asyncio.wait(
            [client_task, gemini_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        for task in pending:
            task.cancel()
            
    except Exception as e:
        logger.error("[%s] Error in websocket session: %s", session_id, e)
    finally:
        await gemini_service.close()
        logger.info(
            "[%s] Session closed (TX to client: %d chunks / %d bytes)",
            session_id,
            out_audio_chunks,
            out_audio_bytes,
        )
