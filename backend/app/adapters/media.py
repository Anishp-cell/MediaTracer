"""Video and audio adapters built on PyAV (bundled FFmpeg).

Video: coarse frame sampling every `video_sample_seconds` (auto-widened so a
long video never exceeds `video_max_frames`). Each sampled frame becomes an
image unit whose locator is the real presentation timestamp. If the video has
an audio track, that track is also indexed as timestamped audio windows.

Audio: decoded and resampled to 16 kHz mono (the model's expected input) in a
streaming fashion and cut into overlapping windows with exact start/end times.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import numpy as np
from PIL import Image, ImageDraw

from ..config import Settings
from .base import Adapter, AdapterError, Unit, thumbnail

AUDIO_RATE = 16000
SILENCE_RMS = 1e-4


def _av():
    import av  # imported lazily so the app still starts without PyAV

    return av


def _av_msg(e: Exception) -> str:
    """FFmpeg error text without the internal file path (e.g. 'Invalid data found when processing input')."""
    return getattr(e, "strerror", None) or type(e).__name__


def probe_duration(container) -> float | None:
    if container.duration:
        return container.duration / 1_000_000  # AV_TIME_BASE
    for s in container.streams:
        if s.duration and s.time_base:
            return float(s.duration * s.time_base)
    return None


def waveform_image(samples: np.ndarray, width: int = 480, height: int = 120) -> Image.Image:
    """Render a min/max waveform of real samples as a preview."""
    img = Image.new("RGB", (width, height), (24, 28, 38))
    draw = ImageDraw.Draw(img)
    if samples.size:
        cols = np.array_split(samples, width)
        mid = height / 2
        peak = max(float(np.abs(samples).max()), 1e-6)
        for x, c in enumerate(cols):
            if c.size == 0:
                continue
            lo, hi = float(c.min()) / peak, float(c.max()) / peak
            draw.line([(x, mid - hi * mid * 0.9), (x, mid - lo * mid * 0.9)], fill=(94, 234, 212))
    return img


def iter_audio_windows(path: Path, window_s: float, hop_s: float) -> Iterator[tuple[float, float, np.ndarray]]:
    """Yield (start_s, end_s, mono float32 samples @16 kHz) windows, streaming."""
    av = _av()
    try:
        container = av.open(str(path))
    except (av.error.FFmpegError, OSError) as e:  # type: ignore[attr-defined]
        raise AdapterError(f"Could not open media: {_av_msg(e)}") from e
    try:
        if not container.streams.audio:
            return
        stream = container.streams.audio[0]
        resampler = av.AudioResampler(format="flt", layout="mono", rate=AUDIO_RATE)
        win, hop = int(window_s * AUDIO_RATE), int(hop_s * AUDIO_RATE)
        buf = np.zeros(0, dtype=np.float32)
        offset = 0  # sample index of buf[0]
        last_end = 0  # sample index where the previous emitted window ended

        def drain(final: bool):
            nonlocal buf, offset, last_end
            while len(buf) >= win or (final and offset + len(buf) - last_end > AUDIO_RATE // 2):
                chunk = buf[:win]
                last_end = offset + len(chunk)
                yield offset / AUDIO_RATE, (offset + len(chunk)) / AUDIO_RATE, chunk.copy()
                if len(buf) <= win:
                    buf = np.zeros(0, dtype=np.float32)
                    offset += len(chunk)
                    break
                buf = buf[hop:]
                offset += hop

        try:
            for frame in container.decode(stream):
                for out in resampler.resample(frame):
                    buf = np.concatenate([buf, out.to_ndarray().reshape(-1).astype(np.float32)])
                yield from drain(False)
            for out in resampler.resample(None):
                buf = np.concatenate([buf, out.to_ndarray().reshape(-1).astype(np.float32)])
        except av.error.FFmpegError as e:  # type: ignore[attr-defined]
            raise AdapterError(f"Audio decoding failed: {_av_msg(e)}") from e
        yield from drain(True)
    finally:
        container.close()


def _audio_units(path: Path, settings: Settings, kind: str, loc_type: str, duration: float | None) -> Iterator[Unit]:
    for start, end, samples in iter_audio_windows(path, settings.audio_window_seconds, settings.audio_hop_seconds):
        rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
        if rms < SILENCE_RMS:
            continue  # digital silence carries no searchable content
        loc = {"type": loc_type, "start": round(start, 3), "end": round(end, 3)}
        if duration:
            loc["duration"] = round(duration, 3)
        yield Unit(kind=kind, modality="audio", locator=loc, audio=samples, audio_rate=AUDIO_RATE,
                   preview=waveform_image(samples), extra={"rms": rms})


class AudioAdapter(Adapter):
    family = "audio"
    formats = {".wav": "WAV", ".mp3": "MP3", ".m4a": "M4A", ".flac": "FLAC", ".ogg": "Ogg"}
    needs = ("audio",)

    def availability(self) -> str | None:
        try:
            _av()
        except ImportError:
            return "PyAV (av) is not installed"
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        av = _av()
        try:
            with av.open(str(path)) as c:
                if not c.streams.audio:
                    raise AdapterError("File has no audio stream")
                duration = probe_duration(c)
        except av.error.FFmpegError as e:  # type: ignore[attr-defined]
            raise AdapterError(f"Could not open audio: {_av_msg(e)}") from e
        produced = 0
        for u in _audio_units(path, settings, "audio", "audio", duration):
            produced += 1
            yield u
        if produced == 0:
            raise AdapterError("Audio is silent or too short to index")


class VideoAdapter(Adapter):
    family = "video"
    formats = {".mp4": "MP4", ".mov": "QuickTime", ".webm": "WebM", ".mkv": "Matroska"}
    needs = ("image",)

    def availability(self) -> str | None:
        try:
            _av()
        except ImportError:
            return "PyAV (av) is not installed"
        return None

    def iter_units(self, path: Path, settings: Settings) -> Iterator[Unit]:
        av = _av()
        try:
            container = av.open(str(path))
        except av.error.FFmpegError as e:  # type: ignore[attr-defined]
            raise AdapterError(f"Could not open video: {_av_msg(e)}") from e
        produced = 0
        try:
            if not container.streams.video:
                raise AdapterError("File has no video stream")
            duration = probe_duration(container)
            has_audio = bool(container.streams.audio)
            interval = settings.video_sample_seconds
            if duration and duration / interval > settings.video_max_frames:
                interval = duration / settings.video_max_frames
            stream = container.streams.video[0]
            stream.thread_type = "AUTO"
            next_t = 0.0
            try:
                for frame in container.decode(stream):
                    if frame.time is None:
                        continue
                    t = float(frame.time)
                    if t + 1e-6 < next_t:
                        continue
                    img = frame.to_image().convert("RGB")
                    seg_end = t + interval if duration is None else min(t + interval, duration)
                    loc = {"type": "video", "time": round(t, 3), "start": round(t, 3), "end": round(seg_end, 3),
                           "sample_interval": round(interval, 3)}
                    if duration:
                        loc["duration"] = round(duration, 3)
                    produced += 1
                    yield Unit(kind="frame", modality="image", locator=loc, image=img, preview=thumbnail(img, 480))
                    next_t = t + interval
            except av.error.FFmpegError as e:  # type: ignore[attr-defined]
                if produced == 0:
                    raise AdapterError(f"Video decoding failed: {_av_msg(e)}") from e
                # Keep frames decoded before a corrupt tail.
        finally:
            container.close()
        if produced == 0:
            raise AdapterError("No decodable video frames")
        if has_audio:
            # Locator type "video" so results open the video player at the right time.
            yield from _audio_units(path, settings, "video_audio", "video", duration)


def sample_frames(path: Path, start: float, end: float, step: float) -> list[tuple[float, Image.Image]]:
    """Decode frames in [start, end] every `step` seconds (used for fine-grained refinement)."""
    av = _av()
    out: list[tuple[float, Image.Image]] = []
    with av.open(str(path)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        if start > 0 and stream.time_base:
            container.seek(int(max(start - 1, 0) / stream.time_base), stream=stream, backward=True)
        next_t = start
        for frame in container.decode(stream):
            if frame.time is None:
                continue
            t = float(frame.time)
            if t > end:
                break
            if t + 1e-6 < next_t:
                continue
            out.append((t, frame.to_image().convert("RGB")))
            next_t = t + step
    return out
