# SPDX-License-Identifier: MIT OR Apache-2.0
"""WAV files in memory: read one into samples and its format, write samples back in that same format.

A stem has to fit its source exactly (a pattern or a loop set on the sample must fit the stems too), so it is written
with the source's rate, channels and sample format, and the same number of frames.

Read: PCM at 16, 24 or 32 bits, 32-bit float, plain or WAVE_FORMAT_EXTENSIBLE. Written: the same, as plain PCM or float.
"""
import struct
from dataclasses import dataclass

import numpy as np

PCM, FLOAT, EXTENSIBLE = 1, 3, 0xFFFE


class WavError(ValueError):
    """The bytes are not a WAV this can read."""


@dataclass(frozen=True)
class Format:
    rate: int
    channels: int
    bits: int
    float: bool = False

    @property
    def frame_bytes(self):
        return self.channels * self.bits // 8


def read(data):
    """(samples, format) of a WAV file's bytes. The samples are float32, shaped (frames, channels), in -1 to 1."""
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise WavError("not a RIFF WAVE file")
    fmt, audio, at = None, None, 12
    while at + 8 <= len(data):
        kind, size = data[at:at + 4], struct.unpack("<I", data[at + 4:at + 8])[0]
        body = data[at + 8:at + 8 + size]
        if kind == b"fmt ":
            fmt = parse_format(body)
        elif kind == b"data":
            audio = body                     # a data chunk cut short (a file still being written) keeps what is there
        at += 8 + size + (size & 1)          # chunks are padded to an even length
    if fmt is None:
        raise WavError("no fmt chunk")
    if audio is None:
        raise WavError("no data chunk")
    frames = len(audio) // fmt.frame_bytes
    raw = audio[:frames * fmt.frame_bytes]
    if fmt.float:
        samples = np.frombuffer(raw, dtype="<f4").astype(np.float32)
    elif fmt.bits == 16:
        samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif fmt.bits == 24:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        value = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        value = np.where(value >= 1 << 23, value - (1 << 24), value)
        samples = value.astype(np.float32) / float(1 << 23)
    else:
        samples = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    return samples.reshape(frames, fmt.channels), fmt


def parse_format(body):
    if len(body) < 16:
        raise WavError("fmt chunk too short")
    tag, channels, rate, _, _, bits = struct.unpack("<HHIIHH", body[:16])
    if tag == EXTENSIBLE:
        if len(body) < 26:
            raise WavError("extensible fmt chunk too short")
        tag = struct.unpack("<H", body[24:26])[0]       # the sub-format GUID starts with the plain tag
    if not 1 <= channels <= 8 or not 8000 <= rate <= 192000:
        raise WavError("%d channels at %d Hz" % (channels, rate))
    if tag == PCM and bits in (16, 24, 32):
        return Format(rate, channels, bits)
    if tag == FLOAT and bits == 32:
        return Format(rate, channels, 32, float=True)
    raise WavError("sample format %d at %d bits is not read" % (tag, bits))


def write(samples, fmt):
    """The bytes of a WAV file holding `samples` (frames, channels) in format `fmt`."""
    samples = np.asarray(samples, dtype=np.float32)
    if samples.ndim != 2 or samples.shape[1] != fmt.channels:
        raise ValueError("samples are %s, the format has %d channels" % (samples.shape, fmt.channels))
    if fmt.float:
        raw = samples.astype("<f4").tobytes()
    else:
        full = float(1 << (fmt.bits - 1))
        ints = np.clip(np.round(samples * full), -full, full - 1).astype(np.int64)
        if fmt.bits == 16:
            raw = ints.astype("<i2").tobytes()
        elif fmt.bits == 24:
            u = (ints & 0xFFFFFF).astype(np.uint32).reshape(-1)
            raw = np.stack([u & 0xFF, (u >> 8) & 0xFF, (u >> 16) & 0xFF], axis=1).astype(np.uint8).tobytes()
        else:
            raw = ints.astype("<i4").tobytes()
    tag = FLOAT if fmt.float else PCM
    head = struct.pack("<HHIIHH", tag, fmt.channels, fmt.rate, fmt.rate * fmt.frame_bytes, fmt.frame_bytes, fmt.bits)
    body = b"WAVE" + b"fmt " + struct.pack("<I", len(head)) + head + b"data" + struct.pack("<I", len(raw)) + raw
    if len(raw) & 1:
        body += b"\0"
    return b"RIFF" + struct.pack("<I", len(body)) + body


def fit(samples, frames):
    """`samples` cut or padded with silence to exactly `frames` frames."""
    if len(samples) >= frames:
        return samples[:frames]
    pad = np.zeros((frames - len(samples), samples.shape[1]), dtype=samples.dtype)
    return np.concatenate([samples, pad])
