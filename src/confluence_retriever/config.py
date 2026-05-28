"""Configuration loading and exit-code constants."""

import sys
from pathlib import Path


PROJECT_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
USER_ENV_FILE = Path.home() / ".config" / "confluence-retriever" / ".env"
TIMEOUT_SECONDS = 10

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_NETWORK = 4


def load_config() -> tuple[str, str]:
    """Load CONFLUENCE_PAT and CONFLUENCE_URL. Returns (pat, base_url)."""
    env_file = USER_ENV_FILE if USER_ENV_FILE.exists() else PROJECT_ENV_FILE
    if not env_file.exists():
        print("ERROR: Config file not found.", file=sys.stderr)
        print(f"Checked: {USER_ENV_FILE}", file=sys.stderr)
        print(f"Checked: {PROJECT_ENV_FILE}", file=sys.stderr)
        print(
            "Copy .env.example to one of those paths and fill in CONFLUENCE_PAT, "
            "or run `confluence-search setup` for an interactive prompt.",
            file=sys.stderr,
        )
        sys.exit(EXIT_CONFIG)

    from dotenv import dotenv_values

    config = dotenv_values(env_file)
    pat = config.get("CONFLUENCE_PAT", "").strip()
    if not pat:
        print(f"ERROR: CONFLUENCE_PAT is not set in {env_file}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)

    base_url = config.get("CONFLUENCE_URL", "").rstrip("/")
    if not base_url:
        print(f"ERROR: CONFLUENCE_URL is not set in {env_file}", file=sys.stderr)
        sys.exit(EXIT_CONFIG)
    return pat, base_url
