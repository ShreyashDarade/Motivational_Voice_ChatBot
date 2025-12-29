class PCMProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();

    const processorOptions = options?.processorOptions ?? {};

    this.inputSampleRate = sampleRate;
    this.targetSampleRate = processorOptions.targetSampleRate ?? 24000;
    this.chunkMs = processorOptions.chunkMs ?? 20;
    this.gain = processorOptions.gain ?? 1.0;

    this.inputFramesPerChunk = Math.max(
      1,
      Math.round((this.inputSampleRate * this.chunkMs) / 1000)
    );
    this.outputFramesPerChunk = Math.max(
      1,
      Math.round((this.targetSampleRate * this.chunkMs) / 1000)
    );

    this._buffer = new Float32Array(this.inputFramesPerChunk * 2);
    this._bufferFill = 0;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0) return true;
    const inputChannel = input[0];
    if (!inputChannel) return true;

    // Grow buffer if needed (rare).
    if (this._bufferFill + inputChannel.length > this._buffer.length) {
      const newBuffer = new Float32Array((this._bufferFill + inputChannel.length) * 2);
      newBuffer.set(this._buffer.subarray(0, this._bufferFill));
      this._buffer = newBuffer;
    }

    this._buffer.set(inputChannel, this._bufferFill);
    this._bufferFill += inputChannel.length;

    while (this._bufferFill >= this.inputFramesPerChunk) {
      const inChunk = this._buffer.subarray(0, this.inputFramesPerChunk);
      const outChunk =
        this.inputSampleRate === this.targetSampleRate
          ? inChunk
          : this._resample(inChunk, this.outputFramesPerChunk);

      const int16Data = new Int16Array(outChunk.length);
      for (let i = 0; i < outChunk.length; i++) {
        let s = outChunk[i] * this.gain;
        s = Math.max(-1, Math.min(1, s));
        int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }

      this.port.postMessage(int16Data.buffer, [int16Data.buffer]);

      const remaining = this._bufferFill - this.inputFramesPerChunk;
      if (remaining > 0) {
        this._buffer.copyWithin(0, this.inputFramesPerChunk, this._bufferFill);
      }
      this._bufferFill = remaining;
    }

    return true;
  }

  _resample(inChunk, outLength) {
    const inLength = inChunk.length;
    if (outLength <= 0) return new Float32Array(0);
    if (inLength === outLength) return inChunk;

    // Fast path for common integer downsample (e.g., 48k -> 24k).
    const factor = inLength / outLength;
    if (Number.isInteger(factor) && factor >= 2) {
      const out = new Float32Array(outLength);
      const intFactor = factor | 0;
      for (let i = 0; i < outLength; i++) {
        let sum = 0;
        const base = i * intFactor;
        for (let j = 0; j < intFactor; j++) sum += inChunk[base + j];
        out[i] = sum / intFactor;
      }
      return out;
    }

    // Linear interpolation for arbitrary ratios.
    const out = new Float32Array(outLength);
    const ratio = (inLength - 1) / (outLength - 1);
    for (let i = 0; i < outLength; i++) {
      const pos = i * ratio;
      const i0 = Math.floor(pos);
      const i1 = Math.min(i0 + 1, inLength - 1);
      const frac = pos - i0;
      out[i] = inChunk[i0] * (1 - frac) + inChunk[i1] * frac;
    }
    return out;
  }
}

registerProcessor("pcm-processor", PCMProcessor);
