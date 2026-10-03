# Independent AAC channel windows

This is an original synthetic signal: six speakers have separate gated tone
bursts at different times. There is no third-party audio. The fixture and
its generator are distributed under this repository's MIT license.

`generate.py` writes 178,224 signed 16-bit samples/channel at 48 kHz in
canonical 5.1 order (L, R, C, LFE, Ls, Rs), encodes AAC LC with FFmpeg's
native AAC encoder at 256 kb/s, then independently decodes the resulting
ADTS stream with FFmpeg. The generator requires Python 3 and FFmpeg;
the Rust regression test requires neither and never skips absent assets.

The original reproducer was encoded in an M4A container and remuxed to ADTS
without reencoding. Direct ADTS generation produces exactly the same bytes
with FFmpeg 9.0.2. The checked-in stream is 176 frames, 180,224 decoded
samples/channel including encoder priming and ADTS end padding.

The first failing frame before the fix is zero-based frame 5: its first CPE
has `common_window=0`, a left LONG_START/sine window and a right ONLY_LONG/KBD
window. Later frames exercise long/short differences, independent short
window groups and unequal `max_sfb`. Those are legal because each channel
transmits its own `ics_info`. A decoder must retain each channel's own
filterbank overlap, rather than requiring the two channels to change windows
together.

The compact PCM oracles come **only from FFmpeg**, not oxideav-aac:

- `expected-probes.s16le`: six little-endian i16 words, canonical channel
  order, at every 256th decoded sample. This checks waveform, polarity,
  activity timing, and channel order. The test permits 8 PCM LSB of error
  for transform/rounding and the fixture's tiny PNS contribution.
- `expected-rms.f32le`: six little-endian f32 RMS values, canonical channel
  order, for every contiguous 512-sample window. The test permits 2 PCM
  LSB of RMS difference. Every window and every channel is checked,
  including silence and overlap tails, rather than only total energy.

A complete sample-for-sample comparison during the repair had these
error-RMS / signal-RMS ratios in channel order:
`0.0000769, 0.0000853, 0.0000792, 0.0003315, 0.0000732, 0.0000744`.
Maximum absolute sample differences were `1, 7, 1, 1, 1, 1` PCM LSB.
The regression stores compact oracles to avoid a 2 MiB raw PCM fixture.

Generated with `ffmpeg version 9.0.2`. SHA-256:

```text
fdefffc1d57edaed0c2da45c95b2eb972f806f3836cf0c39cf1ea20015567c15  bursts-5.1.aac
4f983987bde7087a19d4c81903c6191bb4f93ae109bc13a4b05a9501e10a4be7  expected-rms.f32le
d867d551629f0e5aba6f02083c4c2883b76721fd8c5fa56a11bd618aea5a1d56  expected-probes.s16le
```

The protocol distinction follows Table 4.4 / §4.4.2.3 and §4.6.8 of
ISO/IEC 14496-3. As independent implementation references,
[FFmpeg's `decode_cpe`](https://github.com/FFmpeg/FFmpeg/blob/n9.0/libavcodec/aac/aacdec.c)
parses separate ICS information for `common_window=0`, and
[Fraunhofer FDK's stereo implementation](https://android.googlesource.com/platform/external/aac/+/refs/heads/main/libAACdec/src/stereo.cpp)
quotes the requirement that M/S and intensity stereo use `common_window=1`.
An all-zero M/S mask alone does not identify an independent pair: a shared
pair may still use intensity stereo.
