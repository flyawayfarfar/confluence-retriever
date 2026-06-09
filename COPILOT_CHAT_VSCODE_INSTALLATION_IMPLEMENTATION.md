# GitHub Copilot Chat for VS Code Skill Installation Implementation

This document describes how the `search-wiki` Agent Skill from this repository
should be installed and used with GitHub Copilot Chat in VS Code.

## Research Summary

Current GitHub and VS Code documentation treats Agent Skills as portable
directories containing a `SKILL.md` file. They work with GitHub Copilot cloud
agent, GitHub Copilot CLI, and GitHub Copilot Chat in VS Code agent mode.

Relevant documented behavior:

- Personal skills are installed under `~/.copilot/skills/<skill-name>/SKILL.md`
  or `~/.agents/skills/<skill-name>/SKILL.md`.
- Project skills are installed under `.github/skills/<skill-name>/SKILL.md`,
  `.claude/skills/<skill-name>/SKILL.md`, or `.agents/skills/<skill-name>/SKILL.md`.
- VS Code discovers skills from `chat.agentSkillsLocations`.
- VS Code's `chat.useAgentSkills` setting enables Agent Skills and is documented
  as enabled by default.
- `github.copilot.chat.skillTool.enabled` enables the dedicated skill tool and is
  required for forked-context skills. The current `search-wiki` skill does not use
  `context: fork`, so this setting is useful for diagnostics and newer behavior
  but is not the basic install requirement.
- VS Code extensions can contribute skills with the `contributes.chatSkills`
  contribution point, but this repository is a Python CLI and skill package, not
  a VS Code extension.

Sources checked on 2026-06-01:

- GitHub Docs: https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills
- VS Code Agent Skills docs: https://code.visualstudio.com/docs/copilot/customization/agent-skills
- VS Code Copilot settings reference: https://code.visualstudio.com/docs/copilot/reference/copilot-settings

## What This Means for `confluence-retriever`

The `search-wiki` skill is already structured in the format Copilot expects:

```text
skills/search-wiki.md
```

The repository installer turns that template into an installed `SKILL.md`:

```text
~/.copilot/skills/search-wiki/SKILL.md
```

The installer also stamps the command Copilot should run into the skill body.
The preferred command is:

```bash
confluence-search
```

If `confluence-search` is not on `PATH`, the installer falls back to:

```bash
python3 <repo-root>/scripts/wiki_answer.py
```

For VS Code Copilot Chat, the skill is not a chat extension by itself. It is a
set of instructions that Copilot can load in agent mode. When the skill is used,
Copilot follows the instructions and runs the configured CLI command through the
terminal tool, subject to the user's normal VS Code approval flow.

## Recommended Implementation

Use the existing personal-skill installer as the primary implementation:

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 -m pip install .
python3 install.py --target copilot
```

This installs the CLI and writes:

```text
~/.copilot/skills/search-wiki/SKILL.md
```

Also install to the shared Agent Skills location if you use multiple agents:

```bash
python3 install.py --target agents
```

This writes:

```text
~/.agents/skills/search-wiki/SKILL.md
```

## Windows and WSL Path Decision

Install the skill in the same environment where VS Code's Copilot Chat is
running.

If VS Code is running locally on Windows, Copilot Chat reads skills from the
Windows user profile:

```text
C:\Users\<you>\.copilot\skills\search-wiki\SKILL.md
```

The command stamped inside that Windows skill can use either native Windows
Python or WSL Python. Pick the runtime that can already run the CLI and reach
the configured credentials.

### Option A: Native Windows Python

Use this when `py` or `python` works in `cmd.exe` or PowerShell.

```powershell
cd C:\dev\github\confluence-retriever
py -m pip install .
py install.py --target copilot
```

If the `py` launcher is unavailable but `python` works, use:

```powershell
cd C:\dev\github\confluence-retriever
python -m pip install .
python install.py --target copilot
```

The installer writes:

```text
C:\Users\<you>\.copilot\skills\search-wiki\SKILL.md
```

and should stamp:

```text
confluence-search
```

assuming the Windows console script is on `PATH`.

### Option B: Windows VS Code Calling WSL

Use this when VS Code runs locally on Windows, but the working Python and
`confluence-search` installation live in WSL.

First verify the WSL CLI:

```powershell
wsl.exe --exec /home/<you>/.local/bin/confluence-search --help
wsl.exe --exec /home/<you>/.local/bin/confluence-search doctor
```

Then generate the Windows Copilot skill from WSL, targeting the Windows profile
path and stamping a Windows-callable WSL command:

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 install.py \
  --dest /mnt/c/Users/<you>/.copilot/skills/search-wiki/SKILL.md \
  --command "wsl.exe --exec /home/<you>/.local/bin/confluence-search"
```

For this verified machine on 2026-06-01, the working install is:

```text
C:\Users\WM76YE\.copilot\skills\search-wiki\SKILL.md
```

with the stamped command:

```text
wsl.exe --exec /home/ming/.local/bin/confluence-search
```

Verified from Windows with:

```powershell
wsl.exe --exec /home/ming/.local/bin/confluence-search doctor
```

Result:

```text
[ok] config file: /mnt/c/dev/github/confluence-retriever/.env
[ok] CONFLUENCE_URL = https://orangesharing.com
[ok] search round-trip (1 result)
All checks passed.
```

### Option C: VS Code Remote WSL

If VS Code is connected to WSL with the Remote - WSL extension, install inside
WSL:

```bash
cd /mnt/c/dev/github/confluence-retriever
python3 -m pip install .
python3 install.py --target copilot
```

Expected skill path:

```text
/home/<you>/.copilot/skills/search-wiki/SKILL.md
```

Do not assume one install covers both. Windows VS Code and VS Code Remote WSL
have different home directories and may have different Python environments.

In short:

- Windows VS Code + Windows Python: install Windows CLI and Windows skill.
- Windows VS Code + WSL Python: install Windows skill, but stamp `wsl.exe ...`.
- Remote WSL VS Code + WSL Python: install WSL CLI and WSL skill.

## Configuration

Configure the Confluence credentials in the environment where the CLI runs.
The CLI checks `~/.config/confluence-retriever/.env` first, then repo-local
`.env`.

Recommended personal config location:

```bash
mkdir -p ~/.config/confluence-retriever
cp .env.example ~/.config/confluence-retriever/.env
chmod 600 ~/.config/confluence-retriever/.env
```

Edit the file:

```text
CONFLUENCE_URL=https://your-confluence-root.example.com
CONFLUENCE_PAT=your_personal_access_token
```

`CONFLUENCE_URL` must be the root instance URL only. Do not include REST paths.

Verify the CLI before testing Copilot:

```bash
confluence-search search --query "test" --limit 1
```

If the console script is not on `PATH`, verify the fallback:

```bash
python3 scripts/wiki_answer.py search --query "test" --limit 1
```

## VS Code Settings

Open VS Code settings JSON and verify Agent Skills are enabled:

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

Optional setting for the dedicated skill tool:

```json
{
  "github.copilot.chat.skillTool.enabled": true
}
```

Use this optional setting if `/skills` does not show the skill, if you are
testing newer Agent Skills behavior, or if the skill later adds `context: fork`.

## Verification in VS Code Copilot Chat

1. Restart VS Code after installing the skill.
2. Open GitHub Copilot Chat.
3. Switch to agent mode.
4. Type `/skills` and confirm `search-wiki` appears.
5. Ask a wiki-oriented question:

```text
Use the search-wiki skill to find the deployment process.
```

or:

```text
Search Confluence for authentication docs and summarize the top result.
```

Expected behavior:

- Copilot loads the `search-wiki` skill.
- Copilot proposes or runs a terminal command such as
  `confluence-search search --query "authentication" --depth skim --limit 5`.
- The command returns ranked Markdown results.
- Copilot synthesizes an answer and includes visible Confluence URLs.

## Project-Local Alternative

If the team wants this skill to travel with the repository for VS Code users,
add a project skill copy:

```bash
mkdir -p .github/skills/search-wiki
python3 install.py --dest .github/skills/search-wiki/SKILL.md
```

Tradeoff: the generated file contains machine-specific command paths if
`confluence-search` is not installed on `PATH`. For a committed project skill,
prefer installing the package first so the stamped command is the portable
console script:

```bash
python3 -m pip install .
python3 install.py --dest .github/skills/search-wiki/SKILL.md --command confluence-search
```

Only commit the project skill if the team accepts that each developer must
install and configure the CLI locally.

## VS Code Extension Alternative

Do not build a VS Code extension just to enable this skill. The personal or
project Agent Skill locations are enough.

Use a VS Code extension only if the project later needs Marketplace
distribution, extension-managed setup UI, or bundled commands. In that case,
the extension would need this shape:

```text
extension-root/
└── skills/
    └── search-wiki/
        └── SKILL.md
```

and `package.json` would include:

```json
{
  "contributes": {
    "chatSkills": [
      {
        "path": "./skills/search-wiki/SKILL.md"
      }
    ]
  }
}
```

The `name` field in `SKILL.md` must match the parent directory:

```yaml
name: search-wiki
```

## Troubleshooting

If `/skills` does not show `search-wiki`:

- Confirm the file exists at `~/.copilot/skills/search-wiki/SKILL.md`.
- Confirm VS Code is looking at the same home directory where you installed it.
- Confirm `chat.useAgentSkills` is `true`.
- Restart VS Code.
- If using a nonstandard location, add it to `chat.agentSkillsLocations`.

If Copilot loads the skill but cannot run the command:

- Run `confluence-search --help` in the VS Code integrated terminal.
- Reinstall the CLI in the same Python environment VS Code uses.
- Re-run `python3 install.py --target copilot --check` and inspect the stamped
  command.
- Re-run `python3 install.py --target copilot --command confluence-search` after
  ensuring `confluence-search` is on `PATH`.

If the CLI returns config or auth errors:

- Verify `~/.config/confluence-retriever/.env` or repo-local `.env` exists.
- Verify `CONFLUENCE_URL` is the root URL only.
- Verify `CONFLUENCE_PAT` is valid and not expired.
- Run `confluence-search search --query "test" --limit 1` outside Copilot first.

## Implementation Status

Current repository support is sufficient for VS Code Copilot Chat personal skill
installation:

- `install.py --target copilot` writes the correct personal skill location.
- `skills/search-wiki.md` has valid Agent Skill frontmatter.
- `pyproject.toml` exposes the `confluence-search` console script.

Recommended follow-up improvement:

- Add a short VS Code Copilot Chat section to `README.md` that links to this
  document and clarifies the Windows versus WSL install target.
