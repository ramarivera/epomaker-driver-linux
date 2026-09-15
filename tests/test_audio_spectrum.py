import math

import pytest

from epomaker_driver.audio_spectrum import (
    DEFAULT_SETTINGS,
    FFT_SIZE,
    SAMPLE_RATE,
    SETTINGS_LIMITS,
    SpectrumAnalyzer,
)


def sine(frequency: float, amplitude: float = 1.0) -> list[float]:
    return [
        amplitude * math.sin(2 * math.pi * frequency * index / SAMPLE_RATE)
        for index in range(FFT_SIZE)
    ]


def test_settings_are_exposed_as_single_source_of_truth():
    assert DEFAULT_SETTINGS == {
        "gain": 10,
        "tilt": 0.5,
        "contrast": 2,
        "release": 0.85,
        "min_db": -60,
        "max_db": 0,
        "attack_frames": 5,
    }
    assert SETTINGS_LIMITS["release"] == (0.5, 0.99, 0.01)


def test_neutral_bin_centered_sine_peaks_in_one_band():
    bin_index = 11
    analyzer = SpectrumAnalyzer(
        gain=1, tilt=0, contrast=1, min_db=-80, max_db=20, attack_frames=1, release=0.5
    )
    output = analyzer.process(sine(bin_index * SAMPLE_RATE / FFT_SIZE))
    matching = [band for band, bins in enumerate(analyzer.band_bins) if bin_index in bins]
    assert len(matching) == 1
    assert output[matching[0]] == max(output)
    assert output[matching[0]] == pytest.approx(0.8, abs=0.03)


def test_last_band_excludes_bins_above_20_khz():
    assert all(SAMPLE_RATE * index / FFT_SIZE < 20_000 for index in SpectrumAnalyzer.band_bins[-1])
    assert 214 not in SpectrumAnalyzer.band_bins[-1]


def test_silence_is_zero_and_input_is_not_mutated():
    samples = [0.0] * FFT_SIZE
    assert SpectrumAnalyzer(attack_frames=1).process(samples) == [0.0] * 32
    assert samples == [0.0] * FFT_SIZE


@pytest.mark.parametrize("samples", ["x" * FFT_SIZE, 123])
def test_pcm_must_be_a_sized_sequence(samples):
    with pytest.raises(ValueError, match="exactly 512"):
        SpectrumAnalyzer().process(samples)


def test_reset_clears_release_history():
    analyzer = SpectrumAnalyzer(attack_frames=1, release=0.5)
    analyzer.process(sine(1000))
    analyzer.process([0.0] * FFT_SIZE)
    analyzer.reset()
    assert analyzer.process([0.0] * FFT_SIZE) == [0.0] * 32


@pytest.mark.parametrize(
    "setting, values",
    [
        ("gain", [True, 0, 21]),
        ("tilt", [-0.01, 2.01]),
        ("contrast", [0.49, 4.01]),
        ("release", [0.49, 1.0]),
        ("min_db", [-80.1, -19.9]),
        ("max_db", [-20.1, 20.1]),
        ("attack_frames", [True, 1.5, 0, 21]),
    ],
)
def test_invalid_settings_are_rejected(setting, values):
    for value in values:
        with pytest.raises(ValueError):
            SpectrumAnalyzer(**{setting: value})
    with pytest.raises(ValueError):
        SpectrumAnalyzer(min_db=-20, max_db=-20)


@pytest.mark.parametrize("control", ["gain", "tilt", "contrast", "release", "attack_frames"])
def test_controls_change_analysis(control):
    base = {
        "gain": 1,
        "tilt": 0,
        "contrast": 1,
        "release": 0.5,
        "min_db": -80,
        "max_db": 20,
        "attack_frames": 1,
    }
    changed = dict(base)
    changed[control] = {"gain": 2, "tilt": 1, "contrast": 2, "release": 0.99, "attack_frames": 2}[
        control
    ]
    first = SpectrumAnalyzer(**base).process(sine(1000))
    changed_analyzer = SpectrumAnalyzer(**changed)
    if control == "release":
        changed_analyzer.process(sine(1000))
        second = changed_analyzer.process([0.0] * FFT_SIZE)
        assert second != [0.0] * 32
        return
    second = changed_analyzer.process(sine(1000))
    assert first != second


@pytest.mark.parametrize(
    "samples",
    [[0.0] * 511, [0.0] * 513, [0.0] * 511 + [math.nan], [0.0] * 511 + [True], [1e308] * FFT_SIZE],
)
def test_invalid_pcm_is_rejected(samples):
    with pytest.raises(ValueError):
        SpectrumAnalyzer().process(samples)


def test_oversized_integer_pcm_is_rejected_cleanly():
    with pytest.raises(ValueError, match="finite"):
        SpectrumAnalyzer().process([10**1000] * FFT_SIZE)
