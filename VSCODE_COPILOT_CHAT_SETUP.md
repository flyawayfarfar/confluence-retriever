# GitHub Copilot Chat for VS Code — Setup Guide

This guide walks you through installing and using the **search-wiki** skill with
GitHub Copilot Chat in VS Code agent mode, so you can search your Confluence
wiki directly from the chat panel.

## Prerequisites

- **VS Code** with the **GitHub Copilot Chat** extension (v0.26 or later)
- **GitHub Copilot** subscription (Individual, Business, or Enterprise)
- **Python 3.9+**
  - Verify: `python3 --version`
- **Network access** to your Confluence instance
- A **Confluence Personal Access Token (PAT)**
  - In Confluence: profile menu → **Personal Access Tokens** → create token
  - Or via: `https://your-instance/plugins/servlet/de.resolution.apitokenauth/admin`

---

## Installation

### Step 1: Get the Code

**ZIP download works just as well as `git clone`:**

1. Download the ZIP from the project source
2. Unzip it and open a terminal in the folder

### Step 2: Install the Package

> **Optional:** create a virtual environment first to keep dependencies isolated:
> ```bash
> python3 -m venv .venv
> source .venv/bin/activate          # macOS/Linux
> # or
> .venv\Scripts\activate             # Windows PowerShell
> ```

**Required** — install the package to register `confluence-search` on your `PATH`:

```bash
pip install .
```

### Step 3: Configure Credentials

Fastest path — interactive wizard:

```bash
confluence-search setup
```

This prompts for `CONFLUENCE_URL` and `CONFLUENCE_PAT` (input hidden) and
writes `~/.config/confluence-retriever/.env` with `0600` permissions for you.

If you prefer to write the dotfile by hand:

```bash
mkdir -p ~/.config/confluence-retriever
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
```

```
CONFLUENCE_URL=https://your-confluence-root.example.com
CONFLUENCE_PAT=your_personal_access_token_here
```

**Important:**
- `CONFLUENCE_URL` must be the **base instance URL only** — do not include `/rest/` or any path
- Never commit `.env` to git; it's in `.gitignore`

**Verify the configuration:**

```bash
confluence-search doctor
```

All checks green = success (exit code 0). If you see auth errors (exit code 3),
regenerate your PAT.

### Step 4: Install the Skill for VS Code Copilot Chat

Run the installer with the `copilot` target:

```bash
python3 install.py --target copilot
```

**What this does:**
- Reads the skill template from `skills/search-wiki.md`
- Stamps `confluence-search` into the skill
- Writes the configured skill to `~/.copilot/skills/search-wiki/SKILL.md`

For the shared agent-standard location (used by multiple AI tools), also run:

```bash
python3 install.py --target agents
```

**Verify installation:**

```bash
# Dry-run: see what would be written without writing
python3 install.py --target copilot --check

# Verify the file exists
ls ~/.copilot/skills/search-wiki/SKILL.md
```

### Step 5: Configure VS Code Settings

Open VS Code settings JSON (`Ctrl+Shift+P` → `Open User Settings (JSON)`)
and add or verify:

```json
{
  "chat.useAgentSkills": true,
  "chat.agentSkillsLocations": {
    ".github/skills": true,
    ".claude/skills": true,
    ".agents/skills": true,
    "~/.copilot/skills": true,
    "~/.agents/skills": true
  }
}
```

Optional — enables the dedicated skill tool (useful if `/skills` doesn't show
the skill, or if the skill later adds `context: fork`):

```json
{
  "github.copilot.chat.skillTool.enabled": true
}
```

### Step 6: Restart VS Code and Verify

1. Restart VS Code after installing the skill and updating settings.
2. Open the **GitHub Copilot Chat** panel.
3. Switch to **agent mode** (click the mode selector in the chat input).
4. Type `/skills` and confirm `search-wiki` appears in the list.

---

## Windows and WSL — Which Path to Use?

Copilot Chat in VS Code reads skills from the home directory of the environment
where VS Code is running. Pick the scenario that matches your setup:

### Option A: VS Code on Windows, Python on Windows (native)

Use this when `py` or `python` works in PowerShell.

```powershell
cd C:\dev\github\confluence-retriever
py -m pip install .
py install.py --target copilot
```

The skill is written to:

```
C:\Users\<you>\.copilot\skills\search-wiki\SKILL.md
```

### Option B: VS Code on Windows, Python in WSL

Use this when the working Python and `confluence-search` live in WSL.

First verify the CLI is callable from Windows:

```powershell
wsl.exe --exec /home/<you>/.local/bin/confluence-search --help
wsl.exe --exec /home/<you>/.local/bin/confluence-search doctor
```

Then generate the Windows skill from WSL, stamping a `wsl.exe` command:

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 install.py \
  --dest /mnt/c/Users/<you>/.copilot/skills/search-wiki/SKILL.md \
  --command "wsl.exe --exec /home/<you>/.local/bin/confluence-search"
```

### Option C: VS Code Remote WSL

If VS Code is connected to WSL via the Remote - WSL extension, install
everything inside WSL:

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 -m pip install .
python3 install.py --target copilot
```

Expected skill path:

```
/home/<you>/.copilot/skills/search-wiki/SKILL.md
```

**Summary:**

| VS Code environment | Python location | Install target |
|---------------------|-----------------|---------------|
| Windows (local) | Windows | Run `py install.py --target copilot` from PowerShell |
| Windows (local) | WSL | Use `--dest` + `--command "wsl.exe --exec ..."` |
| Remote WSL | WSL | Run `python3 install.py --target copilot` inside WSL |

---

## Usage

### Asking Copilot Chat a Wiki Question

Switch to agent mode in Copilot Chat, then ask naturally:

```
Search Confluence for authentication docs and summarize the top result.
```

```
Use the search-wiki skill to find the deployment process.
```

```
How do I configure the customer API? Check the wiki.
```

**What happens:**
- Copilot loads the `search-wiki` skill.
- Copilot proposes or runs a terminal command such as:
  `confluence-search search --query "authentication" --depth skim --limit 5`
- You approve the terminal command in the VS Code approval flow.
- The command returns ranked Markdown results.
- Copilot synthesizes an answer with visible Confluence URLs.

### Depth Modes

| Mode | Best for | Copilot trigger phrases |
|------|----------|------------------------|
| `links` (default) | "where is", "find the page", "link to" | Quick lookups |
| `skim` | "how do I", "explain the steps", "what are the details" | Steps and procedures |
| `deep` | "compare pages", "verify", "exhaustive research" | Cross-page analysis |

### Running the CLI Directly

You can also use the CLI in the VS Code integrated terminal without involving
the skill:

```bash
confluence-search search --query "deployment process" --limit 5
confluence-search search --query "auth" --space MT --depth skim
confluence-search read 12345 --format markdown
confluence-search doctor
```

---

## Troubleshooting

### `/skills` Does Not Show `search-wiki`

1. Confirm the file exists:
   ```bash
   ls ~/.copilot/skills/search-wiki/SKILL.md
   ```
   If missing, re-run:
   ```bash
   python3 install.py --target copilot
   ```
2. Confirm VS Code is looking at the same home directory (Windows vs WSL).
3. Confirm `chat.useAgentSkills` is `true` in VS Code settings.
4. Restart VS Code.
5. If using a custom path, add it to `chat.agentSkillsLocations`.

### Copilot Loads the Skill but Cannot Run the Command

1. Open the VS Code integrated terminal and run:
   ```bash
   confluence-search --help
   ```
   If it fails, the CLI is not on `PATH` in this terminal environment.
2. Reinstall in the same Python environment VS Code uses, or use `--dest` and
   `--command` to stamp the exact absolute path:
   ```bash
   python3 install.py --target copilot --command /home/<you>/.local/bin/confluence-search
   ```
3. Dry-run to inspect the stamped command:
   ```bash
   python3 install.py --target copilot --check
   ```

### Exit Code 2: Config Error

**Problem:** `confluence-search` exits with "Config file not found".

**Solution:** Run the interactive wizard:
```bash
confluence-search setup
```

Or create the file manually:
```bash
mkdir -p ~/.config/confluence-retriever
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
# Edit it and fill in CONFLUENCE_URL and CONFLUENCE_PAT
```

Verify: `confluence-search doctor`

### Exit Code 3: Auth Failed

**Problem:** `confluence-search` exits with "Auth failed (401/403)".

**Solution:** Regenerate your PAT at your Confluence instance and re-run:
```bash
confluence-search setup
```

### Exit Code 4: Network Error

**Problem:** `confluence-search` exits with "Network error".

**Solution:**
1. Check `CONFLUENCE_URL` is the base URL only (no REST path).
2. If behind a VPN, ensure it is connected.
3. Verify Confluence is reachable in a browser.

### Skill Returns No Results

1. Try a simpler query: `--query "process"` instead of `--query "deploy kubernetes staging"`
2. Verify the term exists in Confluence by searching manually.
3. Use `--limit 10` to widen the result window.
4. Add `--space KEY` if you know which space to search.

---

## Project-Local Alternative

To make the skill travel with the repository for all VS Code users on the team:

```bash
mkdir -p .github/skills/search-wiki
python3 install.py --dest .github/skills/search-wiki/SKILL.md --command confluence-search
```

Only commit this if the team accepts that each developer must install and
configure the CLI locally. Each developer's terminal must have `confluence-search`
on `PATH` for the stamped command to work.

---

## Security & Best Practices

1. **Never commit `.env`** — it contains your PAT. It's in `.gitignore` by default.
2. **Use the user config location** — `confluence-search setup` writes to
   `~/.config/confluence-retriever/.env` automatically, outside any repo.
3. **Regenerate PATs periodically** — re-run `confluence-search setup` after
   rotating your PAT.
4. **Restrict `.env` permissions** — `confluence-search setup` writes it
   `chmod 600` by default; keep it that way if you edit it by hand.
5. **Review terminal commands** — VS Code will prompt you to approve each
   `confluence-search` invocation. That approval step is intentional.

---

## Additional Resources

- **README:** [README.md](README.md) — Feature overview and quick-start examples
