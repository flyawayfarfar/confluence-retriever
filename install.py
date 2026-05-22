#!/usr/bin/env python3
"""Install the search-wiki skill for Claude Code, Codex, Gemini, or GitHub Copilot CLI.

Works on Windows, macOS, and Linux — no shell required.

Usage:
    python install.py                      # install for Claude Code
    python install.py --target codex       # install for Codex
    python install.py --target gemini      # install for Gemini
    python install.py --target copilot     # install for GitHub Copilot CLI
    python install.py --target agents      # install to shared ~/.agents skills
    python install.py --dest /path/to/search-wiki/SKILL.md
    python install.py --check              # dry-run: print what would be written
"""

import argparse
import os
import sys
from pathlib import Path

SKILL_TEMPLATE = Path(__file__).parent / "skills" / "search-wiki.md"
PLACEHOLDER = "<PROJECT_ROOT>"


def skill_dest(target: str) -> Path:
    if target == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        return codex_home / "skills" / "search-wiki" / "SKILL.md"
    if target == "gemini":
        return Path.home() / ".gemini" / "skills" / "search-wiki" / "SKILL.md"
    if target == "copilot":
        return Path.home() / ".copilot" / "skills" / "search-wiki" / "SKILL.md"
    if target == "agents":
        return Path.home() / ".agents" / "skills" / "search-wiki" / "SKILL.md"
    return Path.home() / ".claude" / "skills" / "search-wiki" / "SKILL.md"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("claude", "codex", "gemini", "copilot", "agents"),
        default="claude",
        help="Assistant skill directory to install into (default: claude)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Exact SKILL.md path to write; overrides --target",
    )
    parser.add_argument("--check", action="store_true", help="Dry run — print result without writing")
    args = parser.parse_args()

    if not SKILL_TEMPLATE.exists():
        print(f"ERROR: skill template not found at {SKILL_TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    project_root = str(Path(__file__).parent.resolve())
    content = SKILL_TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, project_root)
    dest = args.dest if args.dest is not None else skill_dest(args.target)

    if args.check:
        print(f"Would write to: {dest}\n")
        print(content)
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    print(f"Installed: {dest}")
    print(f"Project root stamped in: {project_root}")


if __name__ == "__main__":
    main()
