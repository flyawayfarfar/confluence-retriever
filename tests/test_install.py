"""Unit tests for the assistant skill installer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import install


class TestSkillDest:
    def test_claude_uses_claude_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("claude") == tmp_path / ".claude" / "skills" / "search-wiki" / "SKILL.md"

    def test_copilot_uses_copilot_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("copilot") == tmp_path / ".copilot" / "skills" / "search-wiki" / "SKILL.md"

    def test_gemini_uses_gemini_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("gemini") == tmp_path / ".gemini" / "skills" / "search-wiki" / "SKILL.md"

    def test_antigravity_uses_gemini_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("antigravity") == tmp_path / ".gemini" / "skills" / "search-wiki" / "SKILL.md"

    def test_agents_uses_shared_agent_skill_path(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("agents") == tmp_path / ".agents" / "skills" / "search-wiki" / "SKILL.md"

    def test_default_falls_back_to_claude(self, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        assert install.skill_dest("other") == tmp_path / ".claude" / "skills" / "search-wiki" / "SKILL.md"


class TestResolveCommand:
    def test_explicit_command_wins(self):
        assert install.resolve_command("my-custom") == "my-custom"

    def test_defaults_to_confluence_search(self):
        assert install.resolve_command(None) == "confluence-search"


class TestSkillTemplateStamping:
    def test_template_contains_command_placeholder(self):
        content = install.SKILL_TEMPLATE.read_text(encoding="utf-8")
        assert install.COMMAND_PLACEHOLDER in content


class TestSupportFiles:
    def test_support_file_sources_include_evals(self):
        names = [path.name for path in install.support_file_sources()]

        assert names == ["evals.md"]

    def test_install_copies_support_files(self, monkeypatch, tmp_path):
        destination = tmp_path / "search-wiki" / "SKILL.md"
        monkeypatch.setattr(
            sys,
            "argv",
            ["install.py", "--dest", str(destination), "--command", "confluence-search"],
        )

        install.main()

        assert destination.exists()
        assert (destination.parent / "evals.md").exists()
