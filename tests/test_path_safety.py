"""Tests for fmod_mcp_shared/path_safety.py — traversal and system-dir guard."""

import os
import sys

import pytest

from fmod_mcp_shared.error_codes import ErrorCode, FmodMCPError
from fmod_mcp_shared.path_safety import safe_path


def test_empty_path_rejected():
    with pytest.raises(FmodMCPError) as ei:
        safe_path("")
    assert ei.value.code == ErrorCode.INVALID_PATH


def test_relative_path_rejected():
    with pytest.raises(FmodMCPError) as ei:
        safe_path("relative.wav")
    assert ei.value.code == ErrorCode.INVALID_PATH


def test_traversal_rejected(tmp_path):
    with pytest.raises(FmodMCPError) as ei:
        safe_path(str(tmp_path / ".." / ".." / "x.wav"))
    assert ei.value.code == ErrorCode.INVALID_PATH


def test_valid_path_returns_resolved(tmp_path):
    f = tmp_path / "audio.wav"
    f.write_bytes(b"RIFF")
    resolved = safe_path(str(f))
    assert os.path.isabs(resolved)
    assert resolved == os.path.realpath(str(f))


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific blocked dirs")
def test_windows_system_dir_rejected():
    with pytest.raises(FmodMCPError) as ei:
        safe_path(r"C:\Windows\System32\evil.wav")
    assert ei.value.code == ErrorCode.INVALID_PATH


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX-specific blocked dirs")
def test_posix_system_dir_rejected():
    with pytest.raises(FmodMCPError) as ei:
        safe_path("/etc/evil.wav")
    assert ei.value.code == ErrorCode.INVALID_PATH
