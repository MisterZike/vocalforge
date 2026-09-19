"""WAV reading/writing plus optional ffmpeg export to other formats."""
from __future__ import annotations

import shutil
import struct
import subprocess
import wave
from pathlib import Path

import numpy as np


def write_wav(path: str | Path, x: np.ndarray, sr: int, bits: int = 24) -> Path:
    """Write mono or stereo float audio.  ``bits`` may be 16, 24 or 32 (float)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    ch = x.shape[1]
    x = np.clip(x, -1.0, 1.0)

    if bits == 32:                      # IEEE float -- written by hand
        data = x.astype("<f4").tobytes()
        _write_float_wav(path, data, sr, ch)
        return path

    if bits == 24:
        q = np.round(x * 8388607.0).astype(np.int32)
        b = q.astype("<i4").tobytes()
        data = bytearray()
        for i in range(0, len(b), 4):
            data += b[i:i + 3]
        data = bytes(data)
        sampwidth = 3
    else:
        q = np.round(x * 32767.0).astype("<i2")
        data = q.tobytes()
        sampwidth = 2

    with wave.open(str(path), "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(sampwidth)
        w.setframerate(sr)
        w.writeframes(data)
    return path


def _write_float_wav(path: Path, data: bytes, sr: int, ch: int) -> None:
    block = ch * 4
    hdr = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 3, ch, sr, sr * block, block, 32)
    hdr += b"data" + struct.pack("<I", len(data))
    path.write_bytes(hdr + data)


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        sw = w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
    elif sw == 3:
        a = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        v = a[:, 0] | (a[:, 1] << 8) | (a[:, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float64) / 8388608.0
    elif sw == 4:
        x = np.frombuffer(raw, dtype="<i4").astype(np.float64) / 2147483648.0
    else:
        x = np.frombuffer(raw, dtype=np.uint8).astype(np.float64) / 128.0 - 1.0
    return (x.reshape(-1, ch) if ch > 1 else x), sr


def export(path: str | Path, x: np.ndarray, sr: int, bits: int = 24) -> Path:
    """Write any format ffmpeg understands; falls back to WAV without ffmpeg."""
    path = Path(path)
    if path.suffix.lower() in (".wav", ""):
        return write_wav(path.with_suffix(".wav"), x, sr, bits)
    if not shutil.which("ffmpeg"):
        return write_wav(path.with_suffix(".wav"), x, sr, bits)
    tmp = path.with_suffix(".tmp.wav")
    write_wav(tmp, x, sr, 32)
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(tmp),
                    str(path)], check=True)
    tmp.unlink(missing_ok=True)
    return path
