# Gemini CLI Setup for Confluence Retriever

This guide explains how to set up the `confluence-retriever` tool and its corresponding skill for use with Gemini CLI.

## Prerequisites

- Gemini CLI installed and configured.
- Python 3.9+ installed.
- A Confluence Personal Access Token (PAT).

## Step 1: Install Dependencies

In the project root, run:

```bash
pip install -r requirements.txt
```

## Step 2: Configure Credentials

1. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
2. Edit `.env` and provide your Confluence URL and PAT:
   ```text
   CONFLUENCE_URL=https://your-instance.atlassian.net
   CONFLUENCE_PAT=your_personal_access_token
   ```

*Note: You can also place this file at `~/.config/confluence-retriever/.env` for global use.*

## Step 3: Install the Gemini Skill

Run the installer with the `--target gemini` flag:

```bash
python3 install.py --target gemini
```

This will create a new skill directory at `~/.gemini/skills/search-wiki/` and stamp the absolute path to this project into the `SKILL.md` file.

## Step 4: Verify Installation

Start a new Gemini CLI session and ask a question that would require a wiki search, for example:

> "Search the wiki for 'onboarding process'"

Gemini should identify that it needs the `search-wiki` skill, activate it, run the `wiki_answer.py` script, and present you with the results.

## Troubleshooting

- **Skill not found:** Ensure the skill was installed to `~/.gemini/skills/search-wiki/SKILL.md`. You can check this by running `ls ~/.gemini/skills/search-wiki/`.
- **Authentication errors:** Verify your `CONFLUENCE_PAT` and `CONFLUENCE_URL` in the `.env` file.
- **Python errors:** Ensure you are using Python 3.9+ and all requirements from `requirements.txt` are installed.
