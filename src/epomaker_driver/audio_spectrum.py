"""Independent deterministic audio spectrum analysis for the Glyph workflow.

This implementation makes no parity claim about the vendor's undisclosed DSP
and performs no capture, device, or file I/O. ``tilt`` weights each band's
amplitude by ``(band_center_hz / 1,000) ** tilt``; ``contrast`` is the power
exponent applied to the clamped dB level. Rising levels are smoothed over
``attack_frames`` frames, while falling levels use the release recurrence
``previous * release + current * (1 - release)``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

SAMPLE_RATE = 48_000
FFT_SIZE = 512
BAND_COUNT = 32
_MIN_FREQUENCY = 20.0
_MAX_FREQUENCY = 20_000.0

DEFAULT_SETTINGS: dict[str, float | int] = {
    "gain": 10,
    "tilt": 0.5,
    "contrast": 2,
    "release": 0.85,
    "min_db": -60,
    "max_db": 0,
    "attack_frames": 5,
}
SETTINGS_LIMITS: dict[str, tuple[float | int, float | int, float | int]] = {
    "gain": (1, 20, 1),
    "tilt": (0, 2, 0.01),
    "contrast": (0.5, 4, 0.01),
    "release": (0.5, 0.99, 0.01),
    "min_db": (-80, -20, 0.1),
    "max_db": (-20, 20, 0.1),
    "attack_frames": (1, 20, 1),
}


def _validate_scalar(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f"{name} must be a finite number") from error
    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")
    return number


def _validate_setting(value: object, name: str) -> float | int:
    if name == "attack_frames":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("attack_frames must be an integer")
        number: float | int = value
    else:
        number = _validate_scalar(value, name)
    lower, upper, _step = SETTINGS_LIMITS[name]
    if not lower <= number <= upper:
        raise ValueError(f"{name} must be between {lower} and {upper}")
    return number


def _make_bit_reversal() -> tuple[int, ...]:
    bits = FFT_SIZE.bit_length() - 1
    return tuple(int(f"{index:0{bits}b}"[::-1], 2) for index in range(FFT_SIZE))


def _make_twiddles() -> tuple[tuple[complex, ...], ...]:
    stages: list[tuple[complex, ...]] = []
    length = 2
    while length <= FFT_SIZE:
        stages.append(
            tuple(
                complex(
                    math.cos(-2 * math.pi * index / length), math.sin(-2 * math.pi * index / length)
                )
                for index in range(length // 2)
            )
        )
        length *= 2
    return tuple(stages)


def _make_band_bins() -> tuple[tuple[int, ...], ...]:
    edges = tuple(
        _MIN_FREQUENCY * (_MAX_FREQUENCY / _MIN_FREQUENCY) ** (index / BAND_COUNT)
        for index in range(BAND_COUNT + 1)
    )
    # The strict upper edge applies to every band, including the last one.
    return tuple(
        tuple(
            bin_index
            for bin_index in range(1, FFT_SIZE // 2 + 1)
            if edges[band] <= SAMPLE_RATE * bin_index / FFT_SIZE < edges[band + 1]
        )
        for band in range(BAND_COUNT)
    )


_BIT_REVERSAL = _make_bit_reversal()
_TWIDDLES = _make_twiddles()
_WINDOW = tuple(
    0.5 - 0.5 * math.cos(2 * math.pi * index / (FFT_SIZE - 1)) for index in range(FFT_SIZE)
)
_COHERENT_GAIN = sum(_WINDOW) / FFT_SIZE
_BAND_BINS = _make_band_bins()
_BAND_CENTERS = tuple(
    _MIN_FREQUENCY * (_MAX_FREQUENCY / _MIN_FREQUENCY) ** ((index + 0.5) / BAND_COUNT)
    for index in range(BAND_COUNT)
)


def _fft(values: Sequence[float]) -> list[complex]:
    result = [complex(values[index], 0.0) for index in _BIT_REVERSAL]
    length = 2
    for twiddles in _TWIDDLES:
        half = length // 2
        for start in range(0, FFT_SIZE, length):
            for offset, twiddle in enumerate(twiddles):
                left = start + offset
                right = left + half
                even = result[left]
                odd = result[right] * twiddle
                result[left] = even + odd
                result[right] = even - odd
        length *= 2
    return result


class SpectrumAnalyzer:
    """Analyze one 512-sample mono frame into 32 finite values in ``0..1``."""

    sample_rate = SAMPLE_RATE
    fft_size = FFT_SIZE
    band_count = BAND_COUNT
    band_bins = _BAND_BINS

    def __init__(
        self,
        *,
        gain: float = DEFAULT_SETTINGS["gain"],
        tilt: float = DEFAULT_SETTINGS["tilt"],
        contrast: float = DEFAULT_SETTINGS["contrast"],
        release: float = DEFAULT_SETTINGS["release"],
        min_db: float = DEFAULT_SETTINGS["min_db"],
        max_db: float = DEFAULT_SETTINGS["max_db"],
        attack_frames: int = DEFAULT_SETTINGS["attack_frames"],
    ) -> None:
        settings = {
            "gain": gain,
            "tilt": tilt,
            "contrast": contrast,
            "release": release,
            "min_db": min_db,
            "max_db": max_db,
            "attack_frames": attack_frames,
        }
        self.__dict__.update(
            {name: _validate_setting(value, name) for name, value in settings.items()}
        )
        if self.min_db >= self.max_db:
            raise ValueError("min_db must be less than max_db")
        self._previous = [0.0] * BAND_COUNT

    def reset(self) -> None:
        """Clear attack/release state so the next frame has no history."""
        self._previous = [0.0] * BAND_COUNT

    def process(self, samples: Sequence[float | int]) -> list[float]:
        """Process exactly 512 finite PCM samples without mutating the input."""
        if isinstance(samples, (str, bytes, bytearray)):
            raise ValueError("samples must contain exactly 512 values")
        try:
            if len(samples) != FFT_SIZE:
                raise ValueError("samples must contain exactly 512 values")
        except TypeError as error:
            raise ValueError("samples must contain exactly 512 values") from error
        values = [_validate_scalar(sample, "samples") for sample in samples]
        try:
            spectrum = _fft([sample * _WINDOW[index] for index, sample in enumerate(values)])
            scale = 2.0 / (FFT_SIZE * _COHERENT_GAIN)
            amplitudes = [
                max((abs(spectrum[index]) * scale for index in bins), default=0.0)
                for bins in _BAND_BINS
            ]
        except (OverflowError, ValueError) as error:
            raise ValueError("samples produce non-finite FFT output") from error
        if not all(math.isfinite(amplitude) for amplitude in amplitudes):
            raise ValueError("samples produce non-finite FFT output")
        result: list[float] = []
        for band, amplitude in enumerate(amplitudes):
            if amplitude <= 0:
                current = 0.0
            else:
                tilt_weight = (_BAND_CENTERS[band] / 1000.0) ** self.tilt
                db = 20 * math.log10(amplitude * self.gain * tilt_weight)
                level = max(0.0, min(1.0, (db - self.min_db) / (self.max_db - self.min_db)))
                current = level**self.contrast
            previous = self._previous[band]
            if current >= previous:
                current = previous + (current - previous) / self.attack_frames
            else:
                current = previous * self.release + current * (1 - self.release)
            self._previous[band] = current
            result.append(current)
        return result
