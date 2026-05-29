"""Tests for kb.data_dir() — KB_DATA_DIR resolution."""

import kb


def test_data_dir_defaults_to_repo_root_data(monkeypatch):
    monkeypatch.delenv("KB_DATA_DIR", raising=False)
    assert kb.data_dir() == (kb.REPO_ROOT / "data").resolve()


def test_data_dir_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("KB_DATA_DIR", str(tmp_path))
    assert kb.data_dir() == tmp_path.resolve()
