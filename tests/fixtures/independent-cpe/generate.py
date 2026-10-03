#!/usr/bin/env python3
"""Regenerate the original independent-speaker fixture and FFmpeg PCM oracles."""

import array
import hashlib
import math
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave

ROOT = Path(__file__).resolve().parent
RATE, CHANNELS, SOURCE_SAMPLES = 48_000, 6, 178_224
BURSTS = [(0.12, 0.43), (0.63, 0.91), (1.11, 1.37),
          (1.62, 2.02), (2.31, 2.77), (3.06, 3.39)]


def ffmpeg(*args):
    subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y",
                    *map(str, args)], check=True)


with tempfile.TemporaryDirectory() as directory:
    directory = Path(directory)
    source = directory / "bursts.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(CHANNELS)
        output.setsampwidth(2)
        output.setframerate(RATE)
        pcm = bytearray()
        for i in range(SOURCE_SAMPLES):
            time = i / RATE
            values = [0.0] * CHANNELS
            for channel, (start, end) in enumerate(BURSTS):
                if start <= time < end:
                    gate = min((time - start) * 150, (end - time) * 150, 1)
                    values[channel] = gate * 0.4 * (
                        math.sin(2 * math.pi * (190 + 35 * channel) * time)
                        + 0.35 * math.sin(2 * math.pi * (310 + 83 * channel) * time)
                    )
            pcm.extend(struct.pack("<6h", *[round(x * 32767) for x in values]))
        output.writeframes(pcm)
    encoded = ROOT / "bursts-5.1.aac"
    ffmpeg("-i", source, "-map_metadata", "-1", "-fflags", "+bitexact",
           "-flags:a", "+bitexact", "-c:a", "aac", "-b:a", "256k",
           "-f", "adts", encoded)
    reference = directory / "reference.s16le"
    ffmpeg("-i", encoded, "-c:a", "pcm_s16le", "-f", "s16le", reference)
    samples = array.array("h")
    samples.frombytes(reference.read_bytes())
    # array('h') is native-endian; the stored oracle is little-endian.
    if sys.byteorder != "little":
        samples.byteswap()
    assert len(samples) % CHANNELS == 0
    count = len(samples) // CHANNELS
    rms, probes = bytearray(), bytearray()
    for i in range(0, count, 512):
        for channel in range(CHANNELS):
            window = samples[i * CHANNELS + channel:
                             min((i + 512) * CHANNELS, len(samples)):CHANNELS]
            rms.extend(struct.pack("<f", math.sqrt(sum(s * s for s in window) / len(window))))
    for i in range(0, count, 256):
        probes.extend(struct.pack("<6h", *samples[i * CHANNELS:(i + 1) * CHANNELS]))
    (ROOT / "expected-rms.f32le").write_bytes(rms)
    (ROOT / "expected-probes.s16le").write_bytes(probes)
    print(f"{count} decoded samples/channel including AAC priming and padding")
    for name in ["bursts-5.1.aac", "expected-rms.f32le", "expected-probes.s16le"]:
        print(name, hashlib.sha256((ROOT / name).read_bytes()).hexdigest())
