/** A mono 16-bit PCM WAV file of a 440 Hz tone, built in memory for upload tests. */
export function makeWav(seconds: number, sampleRate = 16_000): Buffer {
  const samples = Math.round(seconds * sampleRate);
  const dataBytes = samples * 2;
  const wav = Buffer.alloc(44 + dataBytes);
  wav.write("RIFF", 0);
  wav.writeUInt32LE(36 + dataBytes, 4);
  wav.write("WAVE", 8);
  wav.write("fmt ", 12);
  wav.writeUInt32LE(16, 16); // fmt chunk size
  wav.writeUInt16LE(1, 20); // PCM
  wav.writeUInt16LE(1, 22); // mono
  wav.writeUInt32LE(sampleRate, 24);
  wav.writeUInt32LE(sampleRate * 2, 28); // bytes per second
  wav.writeUInt16LE(2, 32); // bytes per sample frame
  wav.writeUInt16LE(16, 34); // bits per sample
  wav.write("data", 36);
  wav.writeUInt32LE(dataBytes, 40);
  for (let i = 0; i < samples; i++) {
    const value = Math.sin((2 * Math.PI * 440 * i) / sampleRate) * 0.3 * 32767;
    wav.writeInt16LE(Math.round(value), 44 + i * 2);
  }
  return wav;
}
