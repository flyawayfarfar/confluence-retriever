import pytest
import confluence_retriever.config as _config


@pytest.fixture(autouse=True)
def _isolate_env_files(tmp_path, monkeypatch):
    """Prevent tests from reading the real ~/.config/confluence-retriever/.env."""
    monkeypatch.setattr(_config, "USER_ENV_FILE", tmp_path / "nonexistent.env")
