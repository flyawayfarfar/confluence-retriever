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


class TestResolveCommand:
    def test_explicit_command_wins(self, monkeypatch):
        monkeypatch.setattr(install.shutil, "which", lambda _: "/usr/local/bin/confluence-search")
        assert install.resolve_command("my-custom", "/proj") == "my-custom"

    def test_console_script_preferred_when_on_path(self, monkeypatch):
        monkeypatch.setattr(install.shutil, "which", lambda name: "/x/" + name if name == "confluence-search" else None)
        assert install.resolve_command(None, "/proj") == "confluence-search"

    def test_falls_back_to_legacy_script_when_no_console_script(self, monkeypatch):
        monkeypatch.setattr(install.shutil, "which", lambda _: None)
        assert install.resolve_command(None, "/proj") == "python3 /proj/scripts/wiki_answer.py"


class TestSkillTemplateStamping:
    def test_template_contains_both_placeholders(self):
        content = install.SKILL_TEMPLATE.read_text(encoding="utf-8")
        assert install.PROJECT_ROOT_PLACEHOLDER in content
        assert install.COMMAND_PLACEHOLDER in content


class TestSupportFiles:
    def test_support_file_sources_include_evals_and_memory(self):
        names = [path.name for path in install.support_file_sources()]

        assert names == ["evals.md", "memory.md"]

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
        assert (destination.parent / "memory.md").exists()
