"""Unit tests for the assistant skill installer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import install


class TestSkillDest:
    def test_codex_uses_codex_home_when_set(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CODEX_HOME", str(tmp_path / "codex-home"))

        assert install.skill_dest("codex") == tmp_path / "codex-home" / "skills" / "search-wiki" / "SKILL.md"

    def test_codex_defaults_to_home_codex(self, monkeypatch, tmp_path):
        monkeypatch.delenv("CODEX_HOME", raising=False)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("codex") == tmp_path / ".codex" / "skills" / "search-wiki" / "SKILL.md"

    def test_gemini_uses_home_gemini(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("gemini") == tmp_path / ".gemini" / "skills" / "search-wiki" / "SKILL.md"

    def test_copilot_uses_documented_personal_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("copilot") == tmp_path / ".copilot" / "skills" / "search-wiki" / "SKILL.md"

    def test_agents_uses_shared_agent_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("agents") == tmp_path / ".agents" / "skills" / "search-wiki" / "SKILL.md"

    def test_claude_is_default_fallback(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("claude") == tmp_path / ".claude" / "skills" / "search-wiki" / "SKILL.md"
