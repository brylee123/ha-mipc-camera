"""Decode bounded in-memory audio; never let FFmpeg fetch input URLs."""

from io import BytesIO
from threading import Event

import av

MAX_MEDIA_BYTES = 5 * 1024 * 1024


def iter_audio(data: bytes, stop: Event):
    """Convert WAV, MP3, FLAC, Ogg or M4A audio to PCM16 mono 16 kHz."""
    if not data or len(data) > MAX_MEDIA_BYTES:
        raise ValueError("Audio download is empty or too large")
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        kind = "wav"
    elif (
        data[:3] == b"ID3"
        or data[0] == 0xFF
        and len(data) > 1
        and data[1] & 0xE0 == 0xE0
    ):
        kind = "mp3"
    elif data[:4] == b"fLaC":
        kind = "flac"
    elif data[:4] == b"OggS":
        kind = "ogg"
    elif data[4:8] == b"ftyp":
        kind = "mov"
    else:
        raise ValueError("Unsupported audio file")
    samples = 0
    with (
        av.logging.Capture(local=True),
        av.open(
            BytesIO(data), format=kind, options={"protocol_whitelist": "pipe"}
        ) as container,
    ):
        if not container.streams.audio:
            raise ValueError("Media has no audio track")
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)

        for frame in container.decode(container.streams.audio[0]):
            if stop.is_set():
                return
            for converted in resampler.resample(frame):
                chunk = bytes(converted.planes[0])[: converted.samples * 2]
                samples += converted.samples
                yield chunk
        for converted in resampler.resample(None):
            chunk = bytes(converted.planes[0])[: converted.samples * 2]
            samples += converted.samples
            yield chunk
    if not samples and not stop.is_set():
        raise ValueError("Media has no audio samples")


def decode_audio(data: bytes, stop: Event) -> bytes:
    """Convenience decoder for callers that need a complete PCM byte string."""
    return b"".join(iter_audio(data, stop))
