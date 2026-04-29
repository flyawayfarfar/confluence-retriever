#!/usr/bin/env python3
"""Install the search-wiki skill into ~/.claude/skills/search-wiki/SKILL.md.

Works on Windows, macOS, and Linux — no shell required.

Usage:
    python install.py          # installs from the directory this script lives in
    python install.py --check  # dry-run: print what would be written
"""

import argparse
import shutil
import sys
from pathlib import Path

SKILL_TEMPLATE = Path(__file__).parent / "skills" / "search-wiki.md"
SKILL_DEST = Path.home() / ".claude" / "skills" / "search-wiki" / "SKILL.md"
PLACEHOLDER = "<PROJECT_ROOT>"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Dry run — print result without writing")
    args = parser.parse_args()

    if not SKILL_TEMPLATE.exists():
        print(f"ERROR: skill template not found at {SKILL_TEMPLATE}", file=sys.stderr)
        sys.exit(1)

    project_root = str(Path(__file__).parent.resolve())
    content = SKILL_TEMPLATE.read_text(encoding="utf-8").replace(PLACEHOLDER, project_root)

    if args.check:
        print(f"Would write to: {SKILL_DEST}\n")
        print(content)
        return

    SKILL_DEST.parent.mkdir(parents=True, exist_ok=True)
    SKILL_DEST.write_text(content, encoding="utf-8")
    print(f"Installed: {SKILL_DEST}")
    print(f"Project root stamped in: {project_root}")


if __name__ == "__main__":
    main()
