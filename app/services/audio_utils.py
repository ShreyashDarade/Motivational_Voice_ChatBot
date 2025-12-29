import numpy as np
from scipy import signal

class AudioProcessor:
    def __init__(self, input_rate: int, output_rate: int):
        self.input_rate = input_rate
        self.output_rate = output_rate

    def resample_audio(self, audio_data: bytes, input_format='int16') -> bytes:
        """
        Resamples raw PCM audio data.
        
        Args:
            audio_data: Raw bytes of audio data.
            input_format: Format of input data ('int16', 'float32').
            
        Returns:
            Resampled audio data as bytes (int16).
        """
        if not audio_data:
            return b""

        # Fast path: already int16 PCM at the desired rate.
        if input_format == "int16" and self.input_rate == self.output_rate:
            return audio_data

        # Convert bytes to numpy array
        if input_format == 'int16':
            audio_np = np.frombuffer(audio_data, dtype=np.int16)
        elif input_format == 'float32':
            audio_np = np.frombuffer(audio_data, dtype=np.float32)
            # Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
            audio_np = (audio_np * 32767).astype(np.int16)
        else:
            raise ValueError(f"Unsupported input format: {input_format}")

        if self.input_rate == self.output_rate:
            return audio_np.astype(np.int16).tobytes()

        # Resample (polyphase is lower-latency than FFT for streaming chunks)
        try:
            gcd = int(np.gcd(self.input_rate, self.output_rate))
            up = int(self.output_rate // gcd)
            down = int(self.input_rate // gcd)
            resampled = signal.resample_poly(audio_np.astype(np.float32), up, down)
        except Exception:
            return b""  # Handle empty/too-small chunks gracefully

        # Clip + cast back to int16 PCM
        resampled = np.clip(resampled, -32768, 32767)
        return resampled.astype(np.int16).tobytes()

    @staticmethod
    def create_wav_header(sample_rate: int, channels: int, bits_per_sample: int, data_size: int) -> bytes:
        """Helper to verify audio dumps if needed"""
        import struct
        byte_rate = sample_rate * channels * bits_per_sample // 8
        block_align = channels * bits_per_sample // 8
        return struct.pack(
            '<4sI4s4sIHHIIHH4sI',
            b'RIFF',
            36 + data_size,
            b'WAVE',
            b'fmt ',
            16,
            1,  # PCM
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b'data',
            data_size
        )
