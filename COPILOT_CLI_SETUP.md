# GitHub Copilot CLI Setup Guide

This guide walks you through installing and using the **search-wiki** skill with GitHub Copilot CLI, enabling you to search your Confluence wiki directly from the command line.

## Prerequisites

- **GitHub Copilot CLI** installed and configured (version 0.1.0 or later)
  - [Download and install](https://github.com/github/gh-copilot)
  - Verify: `copilot --version`
- **Python 3.9+** installed
  - Verify: `python3 --version`
- **Network access** to your Confluence instance
- A **Confluence Personal Access Token (PAT)**
  - [See setup instructions](confluence-pat-setup.md)

## Installation

### Step 1: Clone or Download the Repository

```bash
git clone https://github.com/flyawayfarfar/confluence-retriever.git
cd confluence-retriever
```

Or if you prefer a specific directory:

```bash
cd /path/to/your/projects
git clone https://github.com/flyawayfarfar/confluence-retriever.git
```

### Step 2: Install Python Dependencies

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# or
.venv\Scripts\activate             # Windows PowerShell

pip install -r requirements.txt
```

### Step 3: Configure Your Confluence Credentials

Copy the environment template:

```bash
cp .env.example .env
```

Edit `.env` and fill in your Confluence URL and Personal Access Token:

```
CONFLUENCE_URL=https://your-instance.atlassian.net
CONFLUENCE_PAT=your_personal_access_token_here
```

**Important:**
- `CONFLUENCE_URL` must be the **base instance URL only** — do not include `/rest/` or any path
- Get your PAT from your Confluence instance: `https://your-instance.atlassian.net/plugins/servlet/de.resolution.apitokenauth/admin`
- For security: `chmod 600 .env` (Linux/macOS) to restrict file permissions
- Never commit `.env` to git; it's in `.gitignore`

**Verify the configuration:**

```bash
python3 scripts/wiki_answer.py --query "test" --limit 1
```

If successful, you'll see results (exit code 0). If you see auth errors (exit code 3), regenerate your PAT.

### Step 4: Install the Skill for GitHub Copilot CLI

Run the installer with the `copilot` target:

```bash
python3 install.py --target copilot
```

**What this does:**
- Reads the skill template from `skills/search-wiki.md`
- Substitutes the absolute path to `scripts/wiki_answer.py` into the skill
- Writes the configured skill to `~/.copilot/skills/search-wiki/SKILL.md`

For the shared agent-standard location, also run:

```bash
python3 install.py --target agents
```

This writes to `~/.agents/skills/search-wiki/SKILL.md`.

**Verify installation:**

```bash
# Dry-run: see what would be written
python3 install.py --target copilot --check

# Actual install
python3 install.py --target copilot

# Verify the file exists
ls ~/.copilot/skills/search-wiki/SKILL.md
ls ~/.agents/skills/search-wiki/SKILL.md
```

### Step 5: Test the Skill Integration

Start a new GitHub Copilot CLI session, or reload skills inside an existing session:

```text
/skills reload
/skills info search-wiki
```

Then use it:

```bash
search "authentication" --limit 5
search "deployment process" --depth skim
```

Or invoke the skill directly:

```bash
copilot skill search-wiki --query "API" --space MT
```

---

## Usage

### Basic Syntax

```bash
copilot search-wiki --query "TERM" [--space KEY] [--depth MODE] [--limit N]
```

### Examples

#### Simple Search

Find documentation about authentication:

```bash
copilot search-wiki --query "authentication"
```

Returns the top 5 matching pages with title, URL, and excerpt.

#### Multiple Search Terms

Search for either term (OR logic):

```bash
copilot search-wiki --query "API" --query "REST"
```

#### Filter to a Specific Space

Search only in the Mobile Team (MT) space:

```bash
copilot search-wiki --query "deployment" --space MT
```

#### Get More Details

Fetch body snippets from the top result:

```bash
copilot search-wiki --query "release process" --depth skim
```

This adds the first paragraph from the top-ranked page, useful for procedural questions like "how do I...?"

#### Deep Search

Verify information across multiple pages:

```bash
copilot search-wiki --query "authentication" --depth deep
```

This fetches larger snippets from the top 3 results, useful for comparison and verification.

### Depth Modes

| Mode | API calls | Body fetched | Best for |
|------|-----------|-------------|----------|
| `links` (default) | 1 search | None | Quick finding: "where is the page?" |
| `skim` | 1 search + 1 body | 1 page, 1200 chars | Details: "how do I...?" or "explain the steps" |
| `deep` | 1 search + 3 bodies | 3 pages, 2000 chars each | Verification: "compare pages" or "source of truth" |

### All Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `--query TEXT` | required | Search term (repeat for OR) |
| `--space KEY` | none | Filter to a Confluence space (e.g., `MT`, `IIT`) |
| `--limit N` | 5 | Max results |
| `--depth links` | `links` | Title, URL, excerpt only |
| `--depth skim` | `links` | Fetch one capped body from top page |
| `--depth deep` | `links` | Fetch larger bodies from top 3 pages |
| `--body-top N` | by depth | Override # of pages to fetch bodies for |
| `--body-chars N` | by depth | Override max body chars per page |

---

## Troubleshooting

### "Skill not found" Error

**Problem:** Running `copilot search-wiki` returns "skill not found" or similar.

**Solution:**
1. Verify the skill was installed:
   ```bash
   ls ~/.copilot/skills/search-wiki/SKILL.md
   ls ~/.agents/skills/search-wiki/SKILL.md
   ```
2. If missing, re-run: `python3 install.py --target copilot`
3. Restart GitHub Copilot CLI or run `/skills reload` in the active session.

### Exit Code 2: Config Error

**Problem:** `wiki_answer.py` exits with code 2 and message "Config file not found".

**Solution:**
1. Verify `.env` exists in the repository root:
   ```bash
   ls -la /path/to/confluence-retriever/.env
   ```
2. If missing, create it:
   ```bash
   cd /path/to/confluence-retriever
   cp .env.example .env
   # Edit .env and fill in CONFLUENCE_URL and CONFLUENCE_PAT
   ```
3. Test directly: `python3 scripts/wiki_answer.py --query "test" --limit 1`

### Exit Code 3: Auth Failed

**Problem:** `wiki_answer.py` exits with code 3 and message "Auth failed (401/403)".

**Solution:**
1. Check the PAT in `.env` is correct and hasn't expired.
2. Regenerate the PAT at your Confluence instance:
   - Go to `https://your-instance.atlassian.net/plugins/servlet/de.resolution.apitokenauth/admin`
   - Create a new PAT and update `.env`
3. Test: `python3 scripts/wiki_answer.py --query "test" --limit 1`

### Exit Code 4: Network Error

**Problem:** `wiki_answer.py` exits with code 4 and message "Network error".

**Solution:**
1. Check internet connectivity: `ping your-instance.atlassian.net`
2. Verify `CONFLUENCE_URL` in `.env`:
   - Should be `https://your-instance.atlassian.net` (no path)
   - Not `https://your-instance.atlassian.net/rest/api/...`
3. If behind a VPN, ensure VPN is connected.
4. Check if your Confluence instance is accessible from a browser first.

### Skill Returns No Results

**Problem:** Query runs successfully but returns no matching pages.

**Solution:**
1. Try a simpler, broader query: `--query "process"` instead of `--query "deploy kubernetes"`
2. Verify the term actually exists in Confluence — search there manually first
3. Use `--limit 10` to see if any results are returned at all
4. Try `--space KEY` if you know which space to search

### "Permission Denied" on `.env` File (Linux/macOS)

**Problem:** Error about permissions when the script tries to read `.env`.

**Solution:**
1. Ensure the file is readable: `chmod 644 .env`
2. Ensure the script has permission to read it: `ls -la .env`

### Installer Writes to Wrong Directory

**Problem:** `install.py --target copilot` writes to an unexpected location.

**Solution:**
1. Run with `--check` to see where it would write:
   ```bash
   python3 install.py --target copilot --check
   ```
2. If the path is incorrect, use `--dest` to specify manually:
   ```bash
   python3 install.py --dest ~/.copilot/skills/search-wiki/SKILL.md
   ```

---

## Integrating with Your Workflow

### Create an Alias

For quick access, create a shell alias:

```bash
# Add to ~/.bashrc or ~/.zshrc
alias wiki='copilot search-wiki'

# Then use: wiki "authentication"
```

Or configure GitHub Copilot CLI alias:

```bash
copilot alias set wiki search-wiki
```

### Use in Scripts

You can call the CLI directly from other scripts:

```bash
#!/bin/bash
python3 /path/to/confluence-retriever/scripts/wiki_answer.py \
  --query "deployment" \
  --depth skim \
  --limit 3
```

### Uninstall

To remove the skill:

```bash
rm -rf ~/.copilot/skills/search-wiki
rm -rf ~/.agents/skills/search-wiki
```

---

## Security & Best Practices

1. **Never commit `.env`** — it contains your PAT. It's in `.gitignore` by default.
2. **Use user config location** — consider storing `.env` in `~/.config/confluence-retriever/.env` instead of the repo:
   ```bash
   mkdir -p ~/.config/confluence-retriever
   cp .env.example ~/.config/confluence-retriever/.env
   chmod 600 ~/.config/confluence-retriever/.env
   # Then edit and add credentials
   ```
3. **Regenerate PATs periodically** — GitHub Copilot CLI can be configured to remind you.
4. **Restrict `.env` permissions** — use `chmod 600 .env` on Unix-like systems.
5. **Keep Python updated** — `pip install --upgrade pip` periodically.

---

## Additional Resources

- **README:** [README.md](README.md) — Feature overview and quick-start examples
- **PAT Setup:** [confluence-pat-setup.md](confluence-pat-setup.md) — How to generate your Confluence PAT
- **Implementation Notes:** [confluence-retriever-implementation.md](confluence-retriever-implementation.md) — Design and architecture
- **Copilot Instructions:** [.github/copilot-instructions.md](.github/copilot-instructions.md) — For Copilot CLI developers and maintainers

---

## Support

If you encounter issues:

1. **Check the troubleshooting section above.**
2. **Run tests locally:**
   ```bash
   pytest tests/test_wiki_answer.py -v
   ```
3. **Enable verbose output** by running the CLI directly:
   ```bash
   python3 scripts/wiki_answer.py --query "test" --limit 1
   ```
4. **Check logs** — GitHub Copilot CLI logs are typically at `~/.config/github-copilot/logs/`.

---

## What's Next?

- **Explore your wiki** — Try different queries and depths to get familiar with the tool
- **Create aliases** — Set up shortcuts for common searches (see "Integrating with Your Workflow" above)
- **Feedback** — Let the team know which queries work best and which don't

Happy searching! 🔍
