#!/usr/bin/env python3
"""Install the search-wiki skill for Claude Code, Codex, Gemini, Antigravity, or GitHub Copilot.

Works on Windows, macOS, and Linux — no shell required.

Usage:
    python install.py                                # install for Claude Code (default)
    python install.py --target codex                 # install for Codex
    python install.py --target gemini                # install for Gemini
    python install.py --target antigravity           # install for Antigravity CLI (agy)
    python install.py --target copilot               # install for GitHub Copilot
    python install.py --target agents                # install to shared ~/.agents skills
    python install.py --dest /path/to/SKILL.md       # custom destination
    python install.py --command "confluence-search"  # override invocation stamped into skill
    python install.py --check                        # dry-run: print what would be written
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

SKILL_TEMPLATE = Path(__file__).parent / "skills" / "search-wiki.md"
SKILL_SUPPORT_FILES = ("evals.md",)

COMMAND_PLACEHOLDER = "{COMMAND}"


def skill_dest(target: str) -> Path:
    if target == "codex":
        codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
        return codex_home / "skills" / "search-wiki" / "SKILL.md"
    if target == "gemini":
        return Path.home() / ".gemini" / "skills" / "search-wiki" / "SKILL.md"
    if target == "antigravity":
        return Path.home() / ".gemini" / "skills" / "search-wiki" / "SKILL.md"
    if target == "copilot":
        return Path.home() / ".copilot" / "skills" / "search-wiki" / "SKILL.md"
    if target == "agents":
        return Path.home() / ".agents" / "skills" / "search-wiki" / "SKILL.md"
    return Path.home() / ".claude" / "skills" / "search-wiki" / "SKILL.md"


def resolve_command(explicit: str | None) -> str:
    """Return the command string to stamp into the skill.

    Preference order:
    1. ``--command`` passed on the install.py CLI
    2. ``confluence-search`` on PATH (recommended console script)
    3. ``confluence-search`` as the default fallback
    """
    if explicit:
        return explicit
    if shutil.which("confluence-search"):
        return "confluence-search"
    return "confluence-search"


def support_file_sources() -> list[Path]:
    """Return support files installed beside SKILL.md."""
    return [SKILL_TEMPLATE.parent / name for name in SKILL_SUPPORT_FILES]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("claude", "codex", "gemini", "antigravity", "copilot", "agents"),
        default="claude",
        help="Assistant skill directory to install into (default: claude)",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=None,
        help="Exact SKILL.md path to write; overrides --target",
    )
    parser.add_argument(
        "--command",
        type=str,
        default=None,
        help="CLI invocation stamped into the skill (default: auto-detect "
             "`confluence-search` on PATH).",
    )
    parser.add_argument("--check", action="store_true", help="Dry run — print result without writing")
    args = parser.parse_args()

    if not SKILL_TEMPLATE.exists():
        print(f"ERROR: skill template not found at {SKILL_TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    support_files = support_file_sources()
    missing_support_files = [path for path in support_files if not path.exists()]
    if missing_support_files:
        for path in missing_support_files:
            print(f"ERROR: skill support file not found at {path}", file=sys.stderr)
        sys.exit(1)

    command = resolve_command(args.command)

    content = (
        SKILL_TEMPLATE.read_text(encoding="utf-8")
        .replace(COMMAND_PLACEHOLDER, command)
    )

    dest = args.dest if args.dest is not None else skill_dest(args.target)

    if args.check:
        print(f"Would write to: {dest}\n")
        print(f"Stamped command: {command}\n")
        print(content)
        for source in support_files:
            print(f"\nWould copy support file: {source.name} -> {dest.parent / source.name}")
        return

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    for source in support_files:
        target = dest.parent / source.name
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Installed: {dest}")
    for source in support_files:
        print(f"Installed support file: {dest.parent / source.name}")
    print(f"Stamped command: {command}")


if __name__ == "__main__":
    main()
