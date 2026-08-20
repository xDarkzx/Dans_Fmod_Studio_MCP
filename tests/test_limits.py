import pytest

from fmod_mcp.tools import (
    automation_tools,
    bank_tools,
    event_tools,
    folder_tools,
    marker_tools,
    mixer_tools,
    parameter_tools,
    snapshot_tools,
    sound_tools,
)
from fmod_mcp_shared.constants import MAX_AUTOMATION_POINTS, MAX_NAME_LENGTH
from fmod_mcp_shared.error_codes import ErrorCode, FmodMCPError


@pytest.mark.parametrize(
    "module", [event_tools, parameter_tools, bank_tools, mixer_tools]
)
def test_empty_names_rejected(module):
    with pytest.raises(FmodMCPError) as ei:
        module._check_name("")
    assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE
    with pytest.raises(FmodMCPError) as ei2:
        module._check_name("   ")
    assert ei2.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_oversized_name_rejected():
    with pytest.raises(FmodMCPError) as ei:
        event_tools._check_name("x" * (MAX_NAME_LENGTH + 1))
    assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_volume_range():
    mixer_tools._check_volume(0.0)
    mixer_tools._check_volume(-80.0)
    mixer_tools._check_volume(10.0)
    for bad in (-80.1, 10.1, 5000):
        with pytest.raises(FmodMCPError) as ei:
            mixer_tools._check_volume(bad)
        assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_sound_type_whitelist():
    assert "SingleSound" in sound_tools.ALLOWED_SOUND_TYPES
    assert "MultiSound" in sound_tools.ALLOWED_SOUND_TYPES
    assert "EventSound" in sound_tools.ALLOWED_SOUND_TYPES


def test_import_path_validation(tmp_path):
    # Not absolute
    with pytest.raises(FmodMCPError) as ei:
        sound_tools._check_import("relative.wav")
    assert ei.value.code == ErrorCode.INVALID_PATH
    # Missing file
    missing = tmp_path / "nope.wav"
    with pytest.raises(FmodMCPError) as ei2:
        sound_tools._check_import(str(missing))
    assert ei2.value.code == ErrorCode.INVALID_PATH
    # Bad extension on an existing file
    bad = tmp_path / "x.txt"
    bad.write_text("not audio")
    with pytest.raises(FmodMCPError) as ei3:
        sound_tools._check_import(str(bad))
    assert ei3.value.code == ErrorCode.INVALID_FORMAT
    # Happy path
    good = tmp_path / "x.wav"
    good.write_bytes(b"RIFF")
    sound_tools._check_import(str(good))


def _write_wav(path, samples, framerate=44100, sampwidth=2, nchannels=1):
    import struct
    import wave

    with wave.open(str(path), "wb") as w:
        w.setnchannels(nchannels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        fmt = {1: "B", 2: "h"}[sampwidth]
        w.writeframes(struct.pack(f"<{len(samples)}{fmt}", *samples))


def test_silent_wav_rejected(tmp_path):
    silent = tmp_path / "silent.wav"
    _write_wav(silent, [0] * 4410)  # 0.1s of digital silence
    with pytest.raises(FmodMCPError) as ei:
        sound_tools._check_wav_not_silent(str(silent))
    assert ei.value.code == ErrorCode.INVALID_FORMAT
    assert "silent" in str(ei.value)


def test_real_audio_wav_passes(tmp_path):
    import math

    loud = tmp_path / "loud.wav"
    _write_wav(loud, [int(10000 * math.sin(i * 0.05)) for i in range(4410)])
    sound_tools._check_wav_not_silent(str(loud))  # must not raise


def test_malformed_wav_skips_check_rather_than_false_positive(tmp_path):
    # A file that merely has a .wav extension but isn't valid WAV data
    # (e.g. compressed/exotic formats) must not be misread as silent.
    fake = tmp_path / "fake.wav"
    fake.write_bytes(b"not actually a wav file")
    sound_tools._check_wav_not_silent(str(fake))  # must not raise


def test_effect_whitelist():
    assert "CompressorEffect" in mixer_tools.ALLOWED_EFFECTS
    assert "LoudnessMeter" in mixer_tools.ALLOWED_EFFECTS


def test_parameter_type_whitelist():
    assert "UserEnumeration" in parameter_tools.ALLOWED_PARAM_TYPES
    assert "Distance" in parameter_tools.ALLOWED_PARAM_TYPES


def test_folder_kind_whitelist():
    assert folder_tools.ALLOWED_FOLDER_KINDS == {"EventFolder", "AssetFolder"}


def test_automator_property_whitelist():
    assert "volume" in automation_tools.ALLOWED_AUTOMATOR_PROPERTIES
    assert "pitch" in automation_tools.ALLOWED_AUTOMATOR_PROPERTIES
    with pytest.raises(FmodMCPError) as ei:
        automation_tools._check_property("pan")
    assert ei.value.code == ErrorCode.INVALID_TYPE


def test_automation_driver_type_whitelist():
    assert "parameter" in automation_tools.ALLOWED_DRIVER_TYPES
    assert "timeline" in automation_tools.ALLOWED_DRIVER_TYPES


def test_automation_points_validation():
    # Non-list
    with pytest.raises(FmodMCPError) as ei:
        automation_tools._check_points("nope")
    assert ei.value.code == ErrorCode.INVALID_PARAMETER
    # Empty
    with pytest.raises(FmodMCPError) as ei2:
        automation_tools._check_points([])
    assert ei2.value.code == ErrorCode.INVALID_PARAMETER
    # Malformed pair
    with pytest.raises(FmodMCPError) as ei3:
        automation_tools._check_points([[0, 1], [2]])
    assert ei3.value.code == ErrorCode.INVALID_PARAMETER
    # Non-numeric
    with pytest.raises(FmodMCPError) as ei4:
        automation_tools._check_points([["a", 1]])
    assert ei4.value.code == ErrorCode.INVALID_PARAMETER
    # Too many
    too_many = [[i, i] for i in range(MAX_AUTOMATION_POINTS + 1)]
    with pytest.raises(FmodMCPError) as ei5:
        automation_tools._check_points(too_many)
    assert ei5.value.code == ErrorCode.VALUE_OUT_OF_RANGE
    # Happy path — floats coerced
    assert automation_tools._check_points([[0, -80], [0.5, -6.5]]) == [
        [0.0, -80.0],
        [0.5, -6.5],
    ]


def test_snapshot_name_validation():
    snapshot_tools._check_name("Cave")
    with pytest.raises(FmodMCPError) as ei:
        snapshot_tools._check_name("")
    assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_marker_loop_mode_whitelist():
    assert marker_tools.ALLOWED_LOOP_MODES == {"None", "Looping", "Magnet"}


def test_marker_position_validation():
    marker_tools._check_position(0.0)
    marker_tools._check_position(12.5)
    with pytest.raises(FmodMCPError) as ei:
        marker_tools._check_position(-0.1)
    assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_marker_length_validation():
    marker_tools._check_length(0.5)
    with pytest.raises(FmodMCPError) as ei:
        marker_tools._check_length(0)
    assert ei.value.code == ErrorCode.VALUE_OUT_OF_RANGE
    with pytest.raises(FmodMCPError) as ei2:
        marker_tools._check_length(-1)
    assert ei2.value.code == ErrorCode.VALUE_OUT_OF_RANGE


def test_marker_entity_types_cover_all_track_add_methods():
    # Every MarkerTrack.addX() creation method has a matching entry so
    # marker_list can actually find what got created.
    assert marker_tools.MARKER_ENTITY_TYPES == (
        "NamedMarker",
        "LoopRegion",
        "SustainPoint",
        "TransitionMarker",
        "TransitionRegion",
    )
