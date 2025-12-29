from __future__ import annotations

import base64
import json
import logging
from typing import AsyncIterator, Optional

import websockets

from app.core.config import settings

logger = logging.getLogger(__name__)


class GeminiLiveService:
    def __init__(self, *, session_id: str):
        self.session_id = session_id
        self.api_key = settings.GEMINI_API_KEY
        self.model = getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")
        self.voice_name = getattr(settings, "GEMINI_VOICE", "Aoede")

        self.uri = "wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1alpha.GenerativeService.BidiGenerateContent"
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ai_speaking = False

        self._sent_audio_chunks = 0
        self._sent_audio_bytes = 0
        self._recv_audio_chunks = 0
        self._recv_audio_bytes = 0

    async def connect(self) -> None:
        try:
            logger.info("[%s] Connecting to Gemini Live API: %s", self.session_id, self.uri)
            # websockets renamed `extra_headers` -> `additional_headers` (v14+).
            connect_kwargs = dict(
                ping_interval=20,
                ping_timeout=20,
                max_size=4 * 1024 * 1024,
            )
            try:
                self.ws = await websockets.connect(
                    self.uri,
                    additional_headers={"x-goog-api-key": self.api_key},
                    **connect_kwargs,
                )
            except TypeError:
                self.ws = await websockets.connect(
                    self.uri,
                    extra_headers={"x-goog-api-key": self.api_key},
                    **connect_kwargs,
                )
            await self._send_setup()

            logger.info("[%s] Waiting for Gemini handshake (setupComplete)...", self.session_id)
            raw_msg = await self.ws.recv()
            msg = json.loads(raw_msg)
            if "setupComplete" not in msg:
                logger.error("[%s] Handshake failed: %s", self.session_id, raw_msg)
                raise RuntimeError("Did not receive setupComplete from Gemini")

            logger.info("[%s] Gemini handshake complete", self.session_id)
        except Exception:
            logger.exception("[%s] Failed to connect to Gemini", self.session_id)
            raise

    async def _send_setup(self) -> None:
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        setup_msg = {
            "setup": {
                "model": f"models/{self.model}",
                "generation_config": {
                    "response_modalities": ["AUDIO"],
                    "speech_config": {
                        "voice_config": {
                            "prebuilt_voice_config": {
                                "voice_name": self.voice_name,
                            }
                        }
                    },
                },
                "system_instruction": {"parts": [{"text": settings.SYSTEM_PROMPT}]},
            }
        }
        logger.info("[%s] Sending setup: model=%s voice=%s", self.session_id, self.model, self.voice_name)
        await self.ws.send(json.dumps(setup_msg))

    async def send_audio(self, audio_chunk: bytes) -> None:
        if not self.ws or not audio_chunk:
            return

        b64_audio = base64.b64encode(audio_chunk).decode("utf-8")
        msg = {
            "realtime_input": {
                "audio": {
                    "mime_type": f"audio/pcm;rate={settings.GEMINI_SAMPLE_RATE}",
                    "data": b64_audio,
                }
            }
        }

        self._sent_audio_chunks += 1
        self._sent_audio_bytes += len(audio_chunk)
        await self.ws.send(json.dumps(msg))

    async def send_text(self, text: str) -> None:
        if not self.ws:
            return

        logger.info("[%s] Sending text trigger (%d chars)", self.session_id, len(text))
        msg = {
            "client_content": {
                "turns": [{"role": "user", "parts": [{"text": text}]}],
                "turn_complete": True,
            }
        }
        await self.ws.send(json.dumps(msg))

    async def receive(self) -> AsyncIterator[bytes]:
        if not self.ws:
            return

        async for message in self.ws:
            try:
                data = json.loads(message)

                if "error" in data:
                    logger.error("[%s] Gemini error: %s", self.session_id, data["error"])
                    continue

                server_content = data.get("serverContent")
                if not server_content:
                    continue

                if server_content.get("turnComplete"):
                    logger.info("[%s] Gemini turn complete (AI finished speaking)", self.session_id)
                    self.ai_speaking = False

                model_turn = server_content.get("modelTurn")
                if not model_turn:
                    continue

                for part in model_turn.get("parts", []):
                    inline_data = part.get("inlineData")
                    if not inline_data:
                        continue

                    b64_audio = inline_data.get("data")
                    if not b64_audio:
                        continue

                    self.ai_speaking = True
                    audio_bytes = base64.b64decode(b64_audio)
                    self._recv_audio_chunks += 1
                    self._recv_audio_bytes += len(audio_bytes)
                    yield audio_bytes
            except Exception:
                logger.exception("[%s] Error parsing Gemini message", self.session_id)
                continue

    async def close(self) -> None:
        if not self.ws:
            return

        try:
            await self.ws.send(json.dumps({"realtime_input": {"audio_stream_end": True}}))
        except Exception:
            pass

        try:
            await self.ws.close()
        finally:
            logger.info(
                "[%s] Gemini ws closed (sent: %d chunks / %d bytes, recv: %d chunks / %d bytes)",
                self.session_id,
                self._sent_audio_chunks,
                self._sent_audio_bytes,
                self._recv_audio_chunks,
                self._recv_audio_bytes,
            )
