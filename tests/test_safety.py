"""Tests for fmod_mcp/safety.py — the auto-backup safety net.

Uses a fake client (no real FMOD/Script Server dependency) since the logic
here is pure decision-making: given the project's filePath, should a backup
happen, and does a failure in either the filePath check or the save call
ever propagate instead of being swallowed. Mirrors Reaper-MCP's
tests/test_safety.py.
"""

import asyncio
import os

import pytest

import fmod_mcp.safety as safety


class FakeClient:
    """Records calls and returns canned responses keyed off the JS body."""

    def __init__(self, file_path=None, get_info_raises=False, save_raises=False):
        self.calls = []
        self.file_path = file_path
        self.get_info_raises = get_info_raises
        self.save_raises = save_raises

    async def execute(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if "filePath" in command:
            if self.get_info_raises:
                raise RuntimeError("simulated failure")
            return {"success": True, "result": {"filePath": self.file_path}}
        if "studio.project.save" in command:
            if self.save_raises:
                raise RuntimeError("simulated failure")
            return {"success": True, "result": True}
        raise AssertionError(f"unexpected command: {command}")


@pytest.fixture(autouse=True)
def reset_backup_state():
    """The 'already backed up this session' set is module-level — isolate tests."""
    safety._backed_up_this_session.clear()
    yield
    safety._backed_up_this_session.clear()


def _make_project(tmp_path):
    """A minimal FMOD-shaped project dir: .fspro + Metadata/Assets/Build."""
    project_dir = tmp_path / "MyGame"
    project_dir.mkdir()
    (project_dir / "MyGame.fspro").write_text("pointer")
    metadata = project_dir / "Metadata"
    metadata.mkdir()
    (metadata / "Event.yaml").write_text("events: []")
    assets = project_dir / "Assets"
    assets.mkdir()
    (assets / "big.wav").write_bytes(b"\0" * 1024)
    build = project_dir / "Build"
    build.mkdir()
    (build / "Master.bank").write_bytes(b"\0" * 1024)
    return str(project_dir / "MyGame.fspro")


def test_never_saved_project_skips_backup():
    client = FakeClient(file_path="")
    result = asyncio.run(safety.ensure_backup(client))
    assert result is None
    assert not any("save" in cmd for cmd, _ in client.calls)


def test_saved_project_triggers_backup_excluding_assets_and_build(tmp_path):
    fspro = _make_project(tmp_path)
    client = FakeClient(file_path=fspro)
    result = asyncio.run(safety.ensure_backup(client))
    assert result is not None
    backup_dir = result["backup_path"]
    assert os.path.isdir(backup_dir)
    assert os.path.exists(os.path.join(backup_dir, "MyGame.fspro"))
    assert os.path.exists(os.path.join(backup_dir, "Metadata", "Event.yaml"))
    assert not os.path.exists(os.path.join(backup_dir, "Assets"))
    assert not os.path.exists(os.path.join(backup_dir, "Build"))
    assert any("studio.project.save" in cmd for cmd, _ in client.calls)


def test_second_call_same_project_is_noop(tmp_path):
    fspro = _make_project(tmp_path)
    client = FakeClient(file_path=fspro)
    first = asyncio.run(safety.ensure_backup(client))
    second = asyncio.run(safety.ensure_backup(client))
    assert first is not None
    assert second is None
    save_calls = [c for c in client.calls if "studio.project.save" in c[0]]
    assert len(save_calls) == 1


def test_get_info_failure_does_not_raise():
    client = FakeClient(get_info_raises=True)
    result = asyncio.run(safety.ensure_backup(client))
    assert result is None


def test_save_failure_does_not_raise(tmp_path):
    fspro = _make_project(tmp_path)
    client = FakeClient(file_path=fspro, save_raises=True)
    result = asyncio.run(safety.ensure_backup(client))
    assert result is None
