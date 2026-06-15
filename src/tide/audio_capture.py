"""PipeWire/PulseAudio monitor capture for the visualizer.

PortAudio (which sounddevice wraps) doesn't expose sink monitors on
PipeWire+PA reliably — it just sees the default *input* (typically the
mic). Instead we shell out to ``parec``, which is the canonical PA way
to capture from a sink's ``.monitor`` source. Works on PipeWire and
classic PulseAudio identically.

The capture loop runs in a Python thread; FFT and band-binning run there
too so the GUI thread only sees ready-to-render arrays. Results are
delivered on the GUI thread via Qt signals.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time

import numpy as np
from PySide6.QtCore import QObject, Signal


SAMPLE_RATE = 44_100
CHUNK = 1024              # samples per FFT chunk; ~23ms at 44.1kHz
BANDS = 32
SMOOTH_ALPHA = 0.45
EPS = 1e-9


def _build_band_edges(n_bands: int = BANDS, sample_rate: int = SAMPLE_RATE,
                       chunk: int = CHUNK, low_hz: float = 30.0,
                       high_hz: float = 16_000.0) -> np.ndarray:
    n_bins = chunk // 2 + 1
    hz_per_bin = (sample_rate / 2.0) / (n_bins - 1)
    log_lo = np.log10(low_hz)
    log_hi = np.log10(high_hz)
    cut_hz = np.logspace(log_lo, log_hi, n_bands + 1)
    edges = np.clip(np.round(cut_hz / hz_per_bin).astype(int), 1, n_bins - 1)
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = min(n_bins - 1, edges[i - 1] + 1)
    return edges


_HANN_WINDOW = np.hanning(CHUNK).astype(np.float32)
_BAND_EDGES = _build_band_edges()


def _compute_bands(samples: np.ndarray, prev: np.ndarray | None = None) -> np.ndarray:
    windowed = samples * _HANN_WINDOW
    spec = np.fft.rfft(windowed)
    mag = np.abs(spec)
    bands = np.empty(BANDS, dtype=np.float32)
    for i in range(BANDS):
        lo, hi = _BAND_EDGES[i], _BAND_EDGES[i + 1]
        if hi > lo:
            bands[i] = mag[lo:hi].mean()
        else:
            bands[i] = mag[lo]
    bands = np.log1p(bands * 8.0)
    ref = max(bands.max(), 1.5)
    bands = np.clip(bands / ref, 0.0, 1.0)
    if prev is not None and prev.shape == bands.shape:
        attack = bands > prev
        result = prev.copy()
        result[attack] = SMOOTH_ALPHA * bands[attack] + (1 - SMOOTH_ALPHA) * prev[attack]
        rel_a = SMOOTH_ALPHA * 0.45
        result[~attack] = rel_a * bands[~attack] + (1 - rel_a) * prev[~attack]
        return result
    return bands


def list_monitor_sources() -> list[tuple[str, str]]:
    """Return [(name, human_label), ...] for all available .monitor sources.

    Used by the settings dialog + viz cog so users can pick a non-default sink.
    """
    if shutil.which("pactl") is None:
        return []
    try:
        out = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return []
    result: list[tuple[str, str]] = []
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if not name.endswith(".monitor"):
            continue
        # Tidy up the label: drop the alsa_output prefix + .monitor suffix
        label = name
        if label.startswith("alsa_output."):
            label = label[len("alsa_output."):]
        if label.endswith(".monitor"):
            label = label[:-len(".monitor")]
        result.append((name, label))
    return result


def _default_sink_monitor() -> str | None:
    """Return ``<default_sink>.monitor`` or None if pactl is missing."""
    if shutil.which("pactl") is None:
        return None
    try:
        out = subprocess.run(
            ["pactl", "info"], capture_output=True, text=True, timeout=2,
        )
    except Exception:
        return None
    sink = None
    for line in out.stdout.splitlines():
        if line.startswith("Default Sink:"):
            sink = line.split(":", 1)[1].strip()
            break
    if not sink:
        return None
    return sink + ".monitor"


class AudioVisualizerFeed(QObject):
    bands_updated = Signal(object)         # numpy.ndarray (BANDS,)
    waveform_updated = Signal(object)      # numpy.ndarray (CHUNK,)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: subprocess.Popen | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._running = False
        self._monitor = "(not started)"
        self._prev_bands: np.ndarray | None = None

    @property
    def running(self) -> bool:
        return self._running

    @property
    def device(self) -> str:
        return self._monitor

    def start(self, source: str | None = None) -> bool:
        if self._running:
            return True
        if shutil.which("parec") is None:
            self.error.emit("parec not found — install libpulse")
            return False
        monitor = source or _default_sink_monitor()
        if not monitor:
            self.error.emit("couldn't resolve a sink monitor — check pactl info")
            return False

        try:
            self._proc = subprocess.Popen(
                [
                    "parec",
                    "-d", monitor,
                    "--rate", str(SAMPLE_RATE),
                    "--channels", "1",
                    "--format", "float32le",
                    "--raw",
                    "--latency-msec", "10",
                    "--client-name", "tide-visualizer",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        except Exception as exc:
            self.error.emit(f"parec failed to start: {exc}")
            return False

        self._monitor = monitor
        self._stop.clear()
        self._thread = threading.Thread(target=self._process_loop, name="tide-fft", daemon=True)
        self._thread.start()
        self._running = True
        return True

    def stop(self) -> None:
        if not self._running:
            return
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            try:
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._thread = None
        self._running = False
        self._prev_bands = None

    # ---------- worker ----------

    def _process_loop(self) -> None:
        chunk_bytes = CHUNK * 4   # float32
        assert self._proc is not None and self._proc.stdout is not None
        stdout = self._proc.stdout
        while not self._stop.is_set():
            try:
                data = stdout.read(chunk_bytes)
            except Exception:
                break
            if not data or len(data) < chunk_bytes:
                # parec died or stream paused — small backoff so we don't spin.
                if self._stop.wait(0.05):
                    break
                continue
            samples = np.frombuffer(data, dtype=np.float32)
            try:
                self._prev_bands = _compute_bands(samples, self._prev_bands)
            except Exception:
                continue
            self.bands_updated.emit(self._prev_bands.copy())
            self.waveform_updated.emit(samples.copy())


# Singleton.
_instance: AudioVisualizerFeed | None = None


def feed() -> AudioVisualizerFeed:
    global _instance
    if _instance is None:
        _instance = AudioVisualizerFeed()
    return _instance
